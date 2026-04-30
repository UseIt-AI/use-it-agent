/**
 * GUI Handler - GUI 操作处理
 * 
 * 处理与 Local Engine 的 GUI 操作通信：
 * - 新格式：tool_call (target=gui)
 * - 旧格式：client_request (screenshot, execute, execute_actions, screen_info)
 * 
 * 调用 Local Engine API:
 * - POST /api/v1/computer/step
 * - POST /api/v1/computer/screenshot
 * - GET /api/v1/computer/screen
 */

import { ExecutionResult } from './types';
import { Message } from '../types';
import { logRouter } from '@/utils/logger';

// 项目文件列表的默认深度
const PROJECT_FILES_MAX_DEPTH = 10;

// ==================== 辅助函数 ====================

/**
 * 将 scroll 数组格式转换为 scroll_x/scroll_y 格式
 * AI 发送格式: { type: "scroll", scroll: [0, -500] }
 * Local Engine 期望格式: { type: "scroll", scroll_x: 0, scroll_y: -500 }
 */
function normalizeScrollAction(action: any): any {
  if (action.type === 'scroll' && Array.isArray(action.scroll) && action.scroll.length >= 2) {
    const normalized = { ...action };
    if (normalized.scroll_x === undefined) {
      normalized.scroll_x = action.scroll[0];
    }
    if (normalized.scroll_y === undefined) {
      normalized.scroll_y = action.scroll[1];
    }
    logRouter('scroll 数组转换: [%d, %d] -> scroll_x=%d, scroll_y=%d', 
      action.scroll[0], action.scroll[1], normalized.scroll_x, normalized.scroll_y);
    return normalized;
  }
  return action;
}

/**
 * 预处理 actions 数组，标准化格式
 */
function preprocessActions(actions: any[]): any[] {
  return actions.map(normalizeScrollAction);
}

// ==================== 截图处理 ====================

/**
 * 处理截图动作
 * 
 * @param currentUrl Local Engine URL
 * @param setMessages 更新消息的函数
 * @param botMessageId 当前 bot 消息 ID
 * @param projectPath 项目路径（可选，用于附带项目文件列表）
 * @returns 截图结果（base64）
 */
export async function handleScreenshot(
  currentUrl: string,
  setMessages: React.Dispatch<React.SetStateAction<Message[]>>,
  botMessageId: string,
  projectPath?: string
): Promise<{ status: string; result: string; project_files?: string }> {
  logRouter('handleScreenshot: 开始截图, projectPath=%s', projectPath ? 'yes' : 'no');
  
  // 构建请求体
  const requestBody: Record<string, any> = {
    resize: true,
  };
  
  // 如果有 projectPath，使用 /screenshot 端点并附带项目文件列表
  if (projectPath) {
    requestBody.include_project_files = true;
    requestBody.project_path = projectPath;
    requestBody.project_max_depth = PROJECT_FILES_MAX_DEPTH;
    
    const response = await fetch(`${currentUrl}/api/v1/computer/screenshot`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(requestBody),
    });
    
    if (!response.ok) throw new Error(`Local engine error: ${response.status}`);
    const data = await response.json();
    
    if (!data.success || !data.data?.image_base64) {
      throw new Error('Screenshot failed or no image returned');
    }
    
    // 将截图存入 message.screenshots
    setMessages((prev) =>
      prev.map((msg) => {
        if (msg.id !== botMessageId) return msg;
        const screenshots = msg.screenshots || [];
        return {
          ...msg,
          screenshots: [...screenshots, data.data.image_base64],
        };
      })
    );
    
    logRouter('handleScreenshot: 截图成功 (with project_files)');
    return { 
      status: 'success', 
      result: data.data.image_base64,
      project_files: data.data.project_files,
    };
  }
  
  // 没有 projectPath，使用原来的 /step 端点
  const response = await fetch(`${currentUrl}/api/v1/computer/step`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ actions: [{ type: 'screenshot' }] }),
  });

  if (!response.ok) throw new Error(`Local engine error: ${response.status}`);
  const data = await response.json();

  // 新 API 返回格式: { success: true, data: { action_results: [...] } }
  const actionResults = data.data?.action_results || [];
  const screenshotResult = actionResults.find(
    (r: any) => r.ok && r.result?.type === 'screenshot'
  );

  if (!screenshotResult) {
    throw new Error('Screenshot failed or no image returned');
  }

  // 将截图存入 message.screenshots
  setMessages((prev) =>
    prev.map((msg) => {
      if (msg.id !== botMessageId) return msg;
      const screenshots = msg.screenshots || [];
      return {
        ...msg,
        screenshots: [...screenshots, screenshotResult.result.image_base64],
      };
    })
  );

  logRouter('handleScreenshot: 截图成功');
  return { status: 'success', result: screenshotResult.result.image_base64 };
}

// ==================== 执行动作处理 ====================

/**
 * 处理单个执行动作
 * 
 * @param currentUrl Local Engine URL
 * @param params 动作参数
 * @returns 执行结果
 */
export async function handleExecute(
  currentUrl: string,
  params: any
): Promise<{ status: string; result: any }> {
  logRouter('handleExecute: type=%s', params?.type);
  
  const response = await fetch(`${currentUrl}/api/v1/computer/step`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ actions: [params] }),
  });

  if (!response.ok) throw new Error(`Local engine error: ${response.status}`);
  const data = await response.json();
  
  logRouter('handleExecute: 执行成功');
  return { status: 'success', result: data };
}

/**
 * 处理屏幕信息请求
 * 
 * @param currentUrl Local Engine URL
 * @returns 屏幕尺寸信息
 */
export async function handleScreenInfo(
  currentUrl: string
): Promise<{ status: string; result: { width: number; height: number } }> {
  logRouter('handleScreenInfo: 获取屏幕信息');
  
  const response = await fetch(`${currentUrl}/api/v1/computer/screen`);
  if (!response.ok) throw new Error(`Local engine error: ${response.status}`);
  const data = await response.json();
  
  // 新 API 返回格式: { success: true, data: { width, height, ... } }
  const screenData = data.data || data;
  
  logRouter('handleScreenInfo: %dx%d', screenData.width, screenData.height);
  return { status: 'success', result: { width: screenData.width, height: screenData.height } };
}

/**
 * 处理多个执行动作（execute_actions）
 * 
 * @param currentUrl Local Engine URL
 * @param params 包含 actions 数组的参数
 * @param setMessages 更新消息的函数
 * @param botMessageId 当前 bot 消息 ID
 * @param projectPath 项目路径（可选，用于附带项目文件列表）
 * @returns 执行结果
 */
export async function handleExecuteActions(
  currentUrl: string,
  params: any,
  setMessages: React.Dispatch<React.SetStateAction<Message[]>>,
  botMessageId: string,
  projectPath?: string
): Promise<{ status: string; result: any }> {
  const rawActions = params?.actions || [];
  
  // 预处理 actions，标准化格式
  const actions = preprocessActions(rawActions);
  
  logRouter('handleExecuteActions: 执行 %d 个 actions, projectPath=%s', actions.length, projectPath ? 'yes' : 'no');
  
  // 构建请求体
  const requestBody: Record<string, any> = { actions };
  
  // 如果有 projectPath 且 actions 中包含截图，附带项目文件列表
  const hasScreenshot = actions.some((a: any) => a.type === 'screenshot');
  if (projectPath && hasScreenshot) {
    requestBody.return_screenshot = true;
    // 注意：/step 端点暂不支持 include_project_files，需要单独调用 /screenshot
    // 这里先保持原有逻辑，后续可以优化
  }
  
  const response = await fetch(`${currentUrl}/api/v1/computer/step`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(requestBody),
  });

  if (!response.ok) throw new Error(`Local engine error: ${response.status}`);
  const data = await response.json();

  // 新 API 返回格式: { success: true, data: { action_results: [...] } }
  const actionResults = data.data?.action_results || [];
  
  // 检查是否有截图结果
  const screenshotResult = actionResults.find(
    (r: any) => r.ok && r.result?.type === 'screenshot'
  );
  
  if (screenshotResult) {
    const screenshotBase64 = screenshotResult.result.image_base64;
    
    // 将截图存入 message.screenshots，并更新最后一个 CUA 卡片的 screenshotIndex
    setMessages((prev) =>
      prev.map((msg) => {
        if (msg.id !== botMessageId) return msg;
        const screenshots = msg.screenshots || [];
        const newScreenshotIndex = screenshots.length;
        
        logRouter('添加截图到 message.screenshots, 索引: %d', newScreenshotIndex);
        
        // 找到最后一个 CUA 卡片（非搜索类），更新为最新截图
        let targetCuaBlockIndex = -1;
        for (let i = msg.blocks.length - 1; i >= 0; i--) {
          const block = msg.blocks[i];
          if (block.type === 'card' && block.card.type === 'cua' && !block.card.searchResult) {
            targetCuaBlockIndex = i;
            break;
          }
        }
        
        const updatedBlocks = msg.blocks.map((block, idx) => {
          if (idx === targetCuaBlockIndex && block.type === 'card' && block.card.type === 'cua') {
            return {
              ...block,
              card: { ...block.card, screenshotIndex: newScreenshotIndex }
            };
          }
          return block;
        });
        
        return {
          ...msg,
          screenshots: [...screenshots, screenshotBase64],
          blocks: updatedBlocks,
        };
      })
    );
    
    // 优化：只在顶层返回 screenshot，不在 action_results 中重复
    // Backend 的 extract_from_callback 会优先从顶层 screenshot 提取
    // 这样可以减少约 50% 的传输数据量
    return { 
      status: 'success', 
      result: {
        // 过滤掉 action_results 中的截图，避免重复传输
        action_results: actionResults.map((r: any) => {
          if (r.result?.type === 'screenshot') {
            // 只保留元信息，不重复传输 image_base64
            return {
              ...r,
              result: {
                type: 'screenshot',
                resized: r.result.resized,
                compressed: r.result.compressed,
                // image_base64 已在顶层 screenshot 中
              }
            };
          }
          return r;
        }),
        screenshot: screenshotBase64
      }
    };
  }
  
  return { status: 'success', result: { action_results: actionResults } };
}

// ==================== Tool Call 处理（新标准格式） ====================

/**
 * 处理 GUI tool_call（新标准格式）
 * 
 * @param currentUrl Local Engine URL
 * @param name 动作名称（click, type, scroll, etc.）
 * @param args 动作参数
 * @param setMessages 更新消息的函数
 * @param botMessageId 当前 bot 消息 ID
 * @param projectPath 项目路径（可选，用于附带项目文件列表）
 * @returns 执行结果
 */
export async function handleToolCall(
  currentUrl: string,
  name: string,
  args: Record<string, any>,
  setMessages: React.Dispatch<React.SetStateAction<Message[]>>,
  botMessageId: string,
  projectPath?: string
): Promise<ExecutionResult> {
  logRouter('handleToolCall: name=%s, projectPath=%s', name, projectPath ? 'yes' : 'no');

  try {
    // 构建 action 对象
    const action: Record<string, any> = { type: name, ...args };
    
    // 标准化 scroll 动作
    const normalizedAction = normalizeScrollAction(action);
    
    // 执行动作 + 截图
    const actions = [
      normalizedAction,
      { type: 'wait', seconds: 0.8 },
      { type: 'screenshot' },
    ];

    // 如果是 stop 动作，只截图
    if (name === 'stop') {
      actions.length = 0;
      actions.push({ type: 'screenshot' });
    }

    // 构建请求体，如果有 projectPath 则附带项目文件列表
    const requestBody: Record<string, any> = { actions };
    if (projectPath) {
      requestBody.return_screenshot = true;
    }

    const response = await fetch(`${currentUrl}/api/v1/computer/step`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(requestBody),
    });

    if (!response.ok) {
      throw new Error(`Local engine error: ${response.status}`);
    }

    const data = await response.json();
    const actionResults = data.data?.action_results || [];

    // 检查是否有截图结果
    const screenshotResult = actionResults.find(
      (r: any) => r.ok && r.result?.type === 'screenshot'
    );

    if (screenshotResult) {
      const screenshotBase64 = screenshotResult.result.image_base64;

      // 将截图存入 message.screenshots
      setMessages((prev) =>
        prev.map((msg) => {
          if (msg.id !== botMessageId) return msg;
          const screenshots = msg.screenshots || [];
          const newScreenshotIndex = screenshots.length;

          logRouter('handleToolCall: 添加截图, 索引=%d', newScreenshotIndex);

          // 找到最后一个 CUA 卡片（非搜索类），更新为最新截图
          let targetCuaBlockIndex = -1;
          for (let i = msg.blocks.length - 1; i >= 0; i--) {
            const block = msg.blocks[i];
            if (block.type === 'card' && block.card.type === 'cua' && !block.card.searchResult) {
              targetCuaBlockIndex = i;
              break;
            }
          }

          const updatedBlocks = msg.blocks.map((block, idx) => {
            if (idx === targetCuaBlockIndex && block.type === 'card' && block.card.type === 'cua') {
              return {
                ...block,
                card: { ...block.card, screenshotIndex: newScreenshotIndex },
              };
            }
            return block;
          });

          return {
            ...msg,
            screenshots: [...screenshots, screenshotBase64],
            blocks: updatedBlocks,
          };
        })
      );

      // 优化：过滤掉 action_results 中的截图数据，避免重复传输
      return {
        success: true,
        data: {
          action_results: actionResults.map((r: any) => {
            if (r.result?.type === 'screenshot') {
              return {
                ...r,
                result: {
                  type: 'screenshot',
                  resized: r.result.resized,
                  compressed: r.result.compressed,
                }
              };
            }
            return r;
          }),
          screenshot: screenshotBase64,
        },
      };
    }

    return {
      success: true,
      data: { action_results: actionResults },
    };
  } catch (error: any) {
    console.error('[GuiHandler] handleToolCall failed:', error);
    return {
      success: false,
      data: null,
      error: error.message,
    };
  }
}
