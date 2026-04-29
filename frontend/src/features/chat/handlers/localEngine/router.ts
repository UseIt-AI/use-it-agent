/**
 * Local Engine Router - 事件路由
 * 
 * 作为 Local Engine 通信的统一入口，负责：
 * - 接收 tool_call 事件（新标准格式）
 * - 接收 client_request 事件（旧格式，保留兼容）
 * - 根据 target 分发到对应的 handler（guiHandler、officeHandler）
 * - 处理与 Backend 的回调通信
 */

import { API_URL } from '@/config/runtimeEnv';
import { logRouter, logHandler, createRequestTracker } from '@/utils/logger';
import type { CommandHandlerContext } from '../types';
import {
  ClientRequestEvent,
  ToolCallEvent,
  ExecutionResult,
  isToolCallEvent,
  isGUIToolCall,
  isOfficeToolCall,
  isBrowserToolCall,
  isAppToolCall,
  isAskUserToolCall,
} from './types';
import * as guiHandler from './guiHandler';
import * as officeHandler from './officeHandler';
import * as browserHandler from './browserHandler';
import * as autocadHandler from './autocadHandler';
import * as codeHandler from './codeHandler';
import appAction from '../appActions/registry';
import { handleAskUserCall } from '../userInteractionHandler';

// ==================== Tool Call 路由（新标准格式） ====================

/**
 * 处理 tool_call 事件（新标准格式）
 * 
 * 根据 target 路由到对应的 handler
 * 
 * @param event tool_call 事件
 * @param ctx 上下文
 */
export async function handleToolCall(
  event: ToolCallEvent,
  ctx: CommandHandlerContext
): Promise<void> {
  const { localEngineUrl, getLocalEngineUrlFresh, setMessages, botMessageId, projectPath } = ctx;
  const { id, target, name, args } = event;

  // 创建请求追踪器
  const tracker = createRequestTracker('tool_call', id);
  tracker.eventReceived(`${target}.${name}`);

  logRouter('handleToolCall: id=%s target=%s name=%s', id, target, name);
  logHandler('[Router] RAW tool_call received: %O', { id, target, name, args });

  // ==================== target === "user" — ask_user dispatcher ====================
  // This is not a Local Engine call; it's a "please ask the user X and
  // tell me the answer" request from the orchestrator. We render the
  // question INLINE in the current assistant message (as an AskUserBlock)
  // and wait for the user to answer via the card, then POST the
  // spec-defined `execution_result.user_response` payload.
  if (target === 'user') {
    tracker.startProcessing();
    try {
      await handleAskUserCall(event as any, { setMessages, botMessageId });
      tracker.callbackEnd(true);
    } catch (err) {
      console.error('[Router] ask_user dispatch failed:', err);
      tracker.callbackEnd(false);
    }
    return;
  }

  try {
    // 获取最新的 Local Engine URL（VM IP 可能已变化）
    tracker.startProcessing();
    const currentUrl = getLocalEngineUrlFresh
      ? await getLocalEngineUrlFresh()
      : localEngineUrl;

    let result: ExecutionResult;

    // 记录即将调用的 endpoint
    tracker.localEngineRequestStart(`${target}/${name}`);

    // 根据 target 路由
    switch (target) {
      case 'gui':
        result = await guiHandler.handleToolCall(currentUrl, name, args, setMessages, botMessageId, projectPath);
        break;

      case 'word':
        result = await officeHandler.handleWordToolCall(currentUrl, name, args, setMessages, botMessageId, projectPath);
        break;

      case 'excel':
        result = await officeHandler.handleExcelToolCall(currentUrl, name, args, setMessages, botMessageId, projectPath);
        break;

      case 'ppt':
        result = await officeHandler.handlePPTToolCall(currentUrl, name, args, setMessages, botMessageId, projectPath);
        break;

      case 'browser':
        result = await browserHandler.handleToolCall(currentUrl, name, args, setMessages, botMessageId, projectPath);
        break;

      case 'autocad':
        result = await autocadHandler.handleAutoCADToolCall(currentUrl, name, args, setMessages, botMessageId);
        break;

      case 'code':
        result = await codeHandler.handleToolCall(currentUrl, name, args, setMessages, botMessageId, projectPath);
        break;
      case 'app': {
        const actionResult = await appAction.executeAction(name, args);
        result = {
          success: actionResult.success,
          data: actionResult.data || null,
          error: actionResult.error,
        };
        break;
      };

      case 'workflow': {
        // Workflow execution is handled by the backend FlowProcessor.
        // The frontend just acknowledges and the chat loop will start
        // sending screenshots in subsequent /agent calls.
        logRouter('workflow dispatch acknowledged: name=%s args=%O', name, args);
        result = {
          success: true,
          data: { workflow_id: args?.workflow_id, status: 'dispatched' },
          error: undefined,
        };
        break;
      }

      default:
        throw new Error(`Unknown target: ${target}`);
    }

    // 记录 Local Engine 返回
    const dataSize = result.data ? JSON.stringify(result.data).length : 0;
    tracker.localEngineRequestEnd(result.success, `${(dataSize / 1024).toFixed(1)}KB`);

    logRouter('tool_call 完成: id=%s success=%s', id, result.success);
    logHandler('[Router] tool_call result: success=%s, error=%s, dataSize=%sKB',
      result.success, result.error || 'none', (dataSize / 1024).toFixed(1));

    // 回调给 Backend（带重试，防止 Future 未就绪时 404）
    tracker.callbackStart();
    const callbackBody = JSON.stringify({
      status: result.success ? 'success' : 'error',
      result: result.data,
      error: result.error,
    });
    
    const MAX_CALLBACK_RETRIES = 3;
    const CALLBACK_RETRY_DELAY_MS = 2000; // 2 秒
    let callbackOk = false;
    
    for (let attempt = 0; attempt < MAX_CALLBACK_RETRIES; attempt++) {
      try {
        const cbResp = await fetch(`${API_URL}/api/v1/workflow/callback/${id}`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: callbackBody,
        });
        
        if (cbResp.ok) {
          callbackOk = true;
          break;
        }
        
        // 404 = Future 尚未注册（Backend 还在处理 AI Run SSE），等待后重试
        if (cbResp.status === 404 && attempt < MAX_CALLBACK_RETRIES - 1) {
          logRouter(
            'tool_call callback 404, 重试 %d/%d (request_id=%s)',
            attempt + 1,
            MAX_CALLBACK_RETRIES,
            id
          );
          await new Promise((r) => setTimeout(r, CALLBACK_RETRY_DELAY_MS));
          continue;
        }
        
        // 其他非 200 状态码，记录警告但不阻塞
        console.warn(
          `[Router] tool_call callback non-ok: status=${cbResp.status}, id=${id}`
        );
        break;
      } catch (fetchErr) {
        console.error(`[Router] tool_call callback fetch error (attempt ${attempt + 1}):`, fetchErr);
        if (attempt < MAX_CALLBACK_RETRIES - 1) {
          await new Promise((r) => setTimeout(r, CALLBACK_RETRY_DELAY_MS));
        }
      }
    }
    
    tracker.callbackEnd(callbackOk);

    // 更新 UI 显示执行结果（如果失败）
    // 将错误附加到最后一个 CUA 卡片上，而不是作为独立文本块
    if (!result.success && result.error) {
      setMessages((prev) =>
        prev.map((msg) => {
          if (msg.id !== botMessageId) return msg;
          const blocks = [...msg.blocks];
          
          // 找到最后一个 CUA 卡片并更新其 error 字段
          for (let i = blocks.length - 1; i >= 0; i--) {
            const block = blocks[i];
            if (block.type === 'card' && block.card.type === 'cua') {
              blocks[i] = {
                ...block,
                card: {
                  ...block.card,
                  status: 'failed',
                  error: `${target} API error: ${result.error}`,
                },
              };
              return { ...msg, blocks };
            }
          }
          
          // 如果没找到 CUA 卡片，fallback 到文本块（不应该发生）
          blocks.push({
            type: 'text',
            content: `\n⚠️ ${target} 操作失败: ${result.error}\n`,
          });
          return { ...msg, blocks };
        })
      );
    }
  } catch (error: any) {
    console.error('[Router] tool_call failed:', error);

    // 回传错误给 Backend（带重试）
    try {
      const errBody = JSON.stringify({ status: 'error', error: error.message });
      for (let attempt = 0; attempt < 3; attempt++) {
        try {
          const errResp = await fetch(`${API_URL}/api/v1/workflow/callback/${id}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: errBody,
          });
          if (errResp.ok) break;
          if (errResp.status === 404 && attempt < 2) {
            await new Promise((r) => setTimeout(r, 2000));
            continue;
          }
          console.warn(`[Router] Error callback non-ok: status=${errResp.status}`);
          break;
        } catch (fetchErr) {
          if (attempt < 2) {
            await new Promise((r) => setTimeout(r, 2000));
          } else {
            throw fetchErr;
          }
        }
      }
    } catch (e) {
      console.error('[Router] Failed to report error back to server:', e);
    }

    // 更新 UI 显示错误 - 附加到最后一个 CUA 卡片
    setMessages((prev) =>
      prev.map((msg) => {
        if (msg.id !== botMessageId) return msg;
        const blocks = [...msg.blocks];
        
        // 找到最后一个 CUA 卡片并更新其 error 字段
        for (let i = blocks.length - 1; i >= 0; i--) {
          const block = blocks[i];
          if (block.type === 'card' && block.card.type === 'cua') {
            blocks[i] = {
              ...block,
              card: {
                ...block.card,
                status: 'failed',
                error: `${target} error: ${error.message}`,
              },
            };
            return { ...msg, blocks };
          }
        }
        
        // 如果没找到 CUA 卡片，fallback 到文本块
        blocks.push({
          type: 'text',
          content: `\n⚠️ ${target} 操作失败: ${error.message}\n`,
        });
        return { ...msg, blocks };
      })
    );
  }
}

// ==================== Client Request 路由（旧格式，保留兼容） ====================

/**
 * 处理 client_request 事件
 * 
 * 根据 action 类型路由到 guiHandler 中的对应函数
 * 
 * @deprecated 将逐步迁移到 handleToolCall
 * @param event client_request 事件
 * @param ctx 上下文
 */
export async function handleClientRequest(
  event: ClientRequestEvent,
  ctx: CommandHandlerContext
): Promise<void> {
  const { localEngineUrl, getLocalEngineUrlFresh, setMessages, botMessageId, projectPath } = ctx;
  const { requestId, action, params } = event;

  // 创建请求追踪器
  const tracker = createRequestTracker('client_request', requestId);
  tracker.eventReceived(action);

  logRouter('handleClientRequest: action=%s requestId=%s', action, requestId);

  try {
    // 获取最新的 Local Engine URL（VM IP 可能已变化）
    tracker.startProcessing();
    const currentUrl = getLocalEngineUrlFresh
      ? await getLocalEngineUrlFresh()
      : localEngineUrl;

    let result: any = null;

    // 记录即将调用的 endpoint
    tracker.localEngineRequestStart(action);

    // 路由到 guiHandler
    switch (action) {
      case 'screenshot':
        result = await guiHandler.handleScreenshot(currentUrl, setMessages, botMessageId, projectPath);
        break;
      case 'execute':
        result = await guiHandler.handleExecute(currentUrl, params);
        break;
      case 'screen_info':
        result = await guiHandler.handleScreenInfo(currentUrl);
        break;
      case 'execute_actions':
        result = await guiHandler.handleExecuteActions(currentUrl, params, setMessages, botMessageId, projectPath);
        break;
      default:
        throw new Error(`Unknown action type: ${action}`);
    }

    // 记录 Local Engine 返回
    const dataSize = result ? JSON.stringify(result).length : 0;
    tracker.localEngineRequestEnd(true, `${(dataSize / 1024).toFixed(1)}KB`);

    // 回传结果给后端
    tracker.callbackStart();
    await fetch(`${API_URL}/api/v1/workflow/callback/${requestId}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(result),
    });
    tracker.callbackEnd(true);

    logRouter('client_request 完成: action=%s requestId=%s', action, requestId);
  } catch (error: any) {
    console.error('[Router] client_request failed:', error);

    // 回传错误
    try {
      await fetch(`${API_URL}/api/v1/workflow/callback/${requestId}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status: 'error', error: error.message }),
      });
    } catch (e) {
      console.error('[Router] Failed to report error back to server:', e);
    }

    // 更新 UI 显示错误 - 附加到最后一个 CUA 卡片
    setMessages((prev) =>
      prev.map((msg) => {
        if (msg.id !== botMessageId) return msg;
        const blocks = [...msg.blocks];
        
        // 找到最后一个 CUA 卡片并更新其 error 字段
        for (let i = blocks.length - 1; i >= 0; i--) {
          const block = blocks[i];
          if (block.type === 'card' && block.card.type === 'cua') {
            blocks[i] = {
              ...block,
              card: {
                ...block.card,
                status: 'failed',
                error: `客户端操作失败: ${error.message}`,
              },
            };
            return { ...msg, blocks };
          }
        }
        
        // 如果没找到 CUA 卡片，fallback 到文本块
        blocks.push({ type: 'text', content: `\n⚠️ 客户端操作失败: ${error.message}\n` });
        return { ...msg, blocks };
      })
    );
  }
}

// ==================== 导出类型守卫函数 ====================

export {
  isToolCallEvent,
  isGUIToolCall,
  isOfficeToolCall,
  isBrowserToolCall,
  isAppToolCall,
  isAskUserToolCall,
} from './types';
