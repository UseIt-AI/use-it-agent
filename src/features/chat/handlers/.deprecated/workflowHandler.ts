/**
 * Workflow Handler - 处理工作流相关的事件
 */

import { CommandHandlerContext, Message } from './types';
import { API_URL } from '@/config/runtimeEnv';

export interface WorkflowEvent {
  type: string;
  content?: any;
  step_id?: string;
}

/**
 * 处理客户端动作请求 (远程模式)
 */
export async function handleClientActionRequest(
  event: WorkflowEvent,
  ctx: CommandHandlerContext
): Promise<void> {
  const { botMessageId, setMessages, localEngineUrl } = ctx;
  const content = event.content; // { action: string, request_id: string, params?: any }
  
  if (!content || !content.request_id) {
    console.error('[Workflow] Invalid client action request:', event);
    return;
  }

  const requestId = content.request_id;
  const actionType = content.action;
  const params = content.params;

  console.log(`[Workflow] Handling client action: ${actionType}, requestId: ${requestId}`);

  try {
    let result: { status: string; result: any } | null = null;
    
    // 1. 调用 Local Engine
    if (actionType === 'screenshot') {
      const response = await fetch(`${localEngineUrl}/execute_computer_use`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ actions: [{ type: 'screenshot' }] })
      });
      
      if (!response.ok) throw new Error(`Local engine error: ${response.status}`);
      const data = await response.json();
      
      // 提取截图结果
      const results = data.results || [];
      const screenshotResult = results.find((r: any) => r.ok && r.result?.type === 'screenshot');
      
      if (screenshotResult) {
        result = { status: 'success', result: screenshotResult.result.image_base64 };
      } else {
        throw new Error('Screenshot failed or no image returned');
      }
      
    } else if (actionType === 'execute') {
      const response = await fetch(`${localEngineUrl}/execute_computer_use`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ actions: [params] })
      });
      
      if (!response.ok) throw new Error(`Local engine error: ${response.status}`);
      const data = await response.json();
      result = { status: 'success', result: data };
    } else if (actionType === 'screen_info') {
      const response = await fetch(`${localEngineUrl}/screen_info`);
      if (!response.ok) throw new Error(`Local engine error: ${response.status}`);
      const data = await response.json();
      // data format: { width: number, height: number }
      // 后端期望格式: { result: { width, height }, status: 'success' }
      result = { status: 'success', result: { width: data.width, height: data.height } };
    } else {
      throw new Error(`Unknown action type: ${actionType}`);
    }

    // 2. 回传结果给后端
    // 注意：这里需要后端 API 地址，我们可以从 current url 或者配置中获取
    // 假设 API_URL 在 config 或者通过 ctx 传递更好，目前 ctx 没有 API_URL，我们假设它是相对路径或者从环境变量获取
    // 由于 useChat 中定义了 API_URL，最好将其传入 ctx。
    // 与 main.py 中 workflow.router prefix="/api/v1" 一致
    await fetch(`${API_URL}/api/v1/workflow/callback/${requestId}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(result)
    });

  } catch (error: any) {
    console.error('[Workflow] Client action failed:', error);
    
    // 回传错误
    try {
        await fetch(`${API_URL}/api/v1/workflow/callback/${requestId}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ status: 'error', error: error.message })
        });
    } catch (e) {
        console.error('[Workflow] Failed to report error back to server:', e);
    }

    // 更新 UI 显示错误
    setMessages((prev: Message[]) =>
      prev.map((msg) =>
        msg.id === botMessageId
          ? { ...msg, content: msg.content + `\n⚠️ 客户端操作失败: ${error.message}\n` }
          : msg
      )
    );
  }
}

/**
 * 处理工作流事件
 */
export function handleWorkflowEvent(
  event: WorkflowEvent,
  ctx: CommandHandlerContext
): void {
  const { botMessageId, setMessages } = ctx;
  
  switch (event.type) {
    case 'plan_start':
      setMessages((prev: Message[]) =>
        prev.map((msg) =>
          msg.id === botMessageId
            ? { ...msg, content: msg.content + `\n🔧 ${event.content}\n` }
            : msg
        )
      );
      break;
      
    case 'plan_complete':
      const planContent = event.content;
      setMessages((prev: Message[]) =>
        prev.map((msg) =>
          msg.id === botMessageId
            ? {
                ...msg,
                details: {
                  ...msg.details,
                  workflow_steps: [
                    ...(msg.details?.workflow_steps || []),
                    {
                      type: 'plan',
                      title: `工作流规划: ${planContent?.workflow_name}`,
                      content: `步骤: ${planContent?.steps?.join(' → ')}`,
                      status: 'completed',
                      timestamp: Date.now()
                    }
                  ]
                }
              }
            : msg
        )
      );
      break;
      
    case 'plan_error':
      setMessages((prev: Message[]) =>
        prev.map((msg) =>
          msg.id === botMessageId
            ? { ...msg, content: msg.content + `\n⚠️ ${event.content}\n` }
            : msg
        )
      );
      break;
      
    case 'execute_start':
      setMessages((prev: Message[]) =>
        prev.map((msg) =>
          msg.id === botMessageId
            ? { ...msg, content: msg.content + `\n${event.content}\n` }
            : msg
        )
      );
      break;
      
    case 'workflow_start':
      const startContent = event.content;
      setMessages((prev: Message[]) =>
        prev.map((msg) =>
          msg.id === botMessageId
            ? {
                ...msg,
                content: msg.content + `\n**${startContent?.name}:** ${startContent?.description || ''}\n\n`,
              }
            : msg
        )
      );
      break;
      
    case 'step_start':
      const stepStartContent = event.content;
      setMessages((prev: Message[]) =>
        prev.map((msg) =>
          msg.id === botMessageId
            ? {
                ...msg,
                // 在步骤开始前多加两个换行符，增加间距
                // content: msg.content + `\n\n---\n### 任务: ${stepStartContent?.step_index}/${stepStartContent?.total_steps}: ${stepStartContent?.step_name}\n${stepStartContent?.description || ''}\n\n`,
                content: msg.content + `\n\n---\n### 子任务:\n${stepStartContent?.description || ''}\n\n`,
              }
            : msg
        )
      );
      break;
      
    case 'step_complete':
      setMessages((prev: Message[]) =>
        prev.map((msg) => {
          if (msg.id !== botMessageId) return msg;
          
          // Clean up any running steps for this stepId
          const stepId = event.content?.step_id;
          if (!stepId) return msg;
          
          const currentSteps = msg.details?.workflow_steps || [];
          const newSteps = [...currentSteps];
          let changed = false;
          
          newSteps.forEach((step, index) => {
              if (step.stepId === stepId && step.status === 'running') {
                  // If it's still running at step completion, mark it as completed
                  // This handles "Generating report..." which has no explicit "done" event except step completion
                  const isReportCard = step.type === 'report' || step.title?.includes('生成报告');
                  newSteps[index] = { 
                      ...step, 
                      status: 'completed',
                      // 报告卡片保持原标题，其他卡片修改标题
                      title: isReportCard ? '报告生成完成' : (step.title.replace('正在', '').replace('...', '') + ' 完成')
                  };
                  changed = true;
              }
          });
          
          if (!changed) return msg;
          
          return {
              ...msg,
              details: { ...msg.details, workflow_steps: newSteps }
          };
        })
      );
      break;
      
    case 'step_error':
      const stepErrorContent = event.content;
      setMessages((prev: Message[]) =>
        prev.map((msg) =>
          msg.id === botMessageId
            ? {
                ...msg,
                content: msg.content + `\n❌ 步骤失败: ${stepErrorContent?.error}\n`,
              }
            : msg
        )
      );
      break;

    // CUA 特定事件
    case 'cua_step_start':
      const cuaStartContent = event.content; // { step, screenshot, width, height }
      console.log('[Workflow] Received screenshot for step', cuaStartContent?.step);
      
      setMessages((prev: Message[]) =>
        prev.map((msg) => {
          if (msg.id !== botMessageId) return msg;
          
          const currentScreenshots = msg.screenshots || [];
          
          // 使用 step 索引直接赋值，防止顺序错乱
          const newScreenshots = [...currentScreenshots];
          if (cuaStartContent?.step > 0) {
              // 确保存储空间足够
              while (newScreenshots.length < cuaStartContent.step) {
                  newScreenshots.push(""); // 填充空位
              }
              newScreenshots[cuaStartContent.step - 1] = cuaStartContent.screenshot;
          }
          
          return {
            ...msg,
            screenshots: newScreenshots
          };
        })
      );
      break;

    case 'cua_step_action':
      const cuaActionContent = event.content; // { step, action }
      setMessages((prev: Message[]) =>
        prev.map((msg) => {
          if (msg.id !== botMessageId) return msg;
          
          const details = msg.details || {};
          const cuaActions = details.cua_actions || [];
          
          // 使用数组存储动作信息，索引对应步骤 (step - 1)
          const newCuaActions = [...cuaActions];
          // step 从 1 开始
          if (cuaActionContent.step > 0) {
              newCuaActions[cuaActionContent.step - 1] = cuaActionContent.action;
          }
          
          return {
            ...msg,
            details: {
              ...details,
              cua_actions: newCuaActions
            }
          };
        })
      );
      break;
      
    case 'workflow_complete':
      // 由 eventHandler 处理，添加 CompletionBlock
      // 旧格式兼容：也在 content 中添加标记
      setMessages((prev: Message[]) =>
        prev.map((msg) => {
          if (msg.id !== botMessageId) return msg;
          // 如果有 blocks（V2 格式），由 eventHandler 处理
          if (msg.blocks && msg.blocks.length > 0) return msg;
          // 旧格式：添加到 content
          return {
            ...msg,
            content: msg.content + `\n\n---\n\n**[✓] Done.**\n`,
          };
        })
      );
      break;
      
    case 'workflow_error':
      const workflowErrorContent = event.content;
      setMessages((prev: Message[]) =>
        prev.map((msg) =>
          msg.id === botMessageId
            ? {
                ...msg,
                details: {
                  ...msg.details,
                  workflow_steps: [
                    ...(msg.details?.workflow_steps || []),
                    {
                      type: 'error',
                      title: '工作流错误',
                      content: workflowErrorContent?.error,
                      status: 'failed',
                      timestamp: Date.now()
                    }
                  ]
                }
              }
            : msg
        )
      );
      break;
      
    // RAG Node 特定事件 / 通用状态事件
    case 'status':
      // 注意：CUA 模式下，状态信息已由 CUA 卡片展示，不需要额外创建 status 卡片
      // 只在控制台打印，不更新 UI，避免冗余卡片
      console.log('[Workflow] Status:', event.content);
      break;

    case 'queries':
      setMessages((prev: Message[]) =>
        prev.map((msg) => {
          if (msg.id !== botMessageId) return msg;

          const currentSteps = msg.details?.workflow_steps || [];
          const stepId = event.step_id;
          const newSteps = [...currentSteps];
          const content = Array.isArray(event.content) ? event.content.join('\n') : JSON.stringify(event.content);
          
          let updated = false;
          if (stepId) {
              for (let i = newSteps.length - 1; i >= 0; i--) {
                  if (newSteps[i].stepId === stepId && newSteps[i].status === 'running') {
                      newSteps[i] = {
                          ...newSteps[i],
                          type: 'retrieval',  // 统一使用 retrieval 类型
                          title: '生成检索查询',
                          content: content,
                          status: 'completed',
                          timestamp: Date.now()
                      };
                      updated = true;
                      break;
                  }
              }
          }
          
          if (!updated) {
              newSteps.push({
                  id: stepId ? `${stepId}_queries_${Date.now()}` : `queries_${Date.now()}`,
                  stepId: stepId,
                  type: 'retrieval',  // 统一使用 retrieval 类型
                  title: '生成检索查询',
                  content: content,
                  status: 'completed',
                  timestamp: Date.now()
              });
          }

          return {
            ...msg,
            details: {
              ...msg.details,
              workflow_steps: newSteps
            }
          };
        })
      );
      break;
      
    case 'retrieval_info':
      const retrievalContent = event.content;
      setMessages((prev: Message[]) =>
        prev.map((msg) => {
          if (msg.id !== botMessageId) return msg;

          const currentSteps = msg.details?.workflow_steps || [];
          const stepId = event.step_id;
          const newSteps = [...currentSteps];
          
          let updated = false;
          if (stepId) {
              for (let i = newSteps.length - 1; i >= 0; i--) {
                  if (newSteps[i].stepId === stepId && newSteps[i].status === 'running') {
                      newSteps[i] = {
                          ...newSteps[i],
                          type: 'retrieval',
                          title: '知识库检索完成',
                          content: `找到 ${retrievalContent?.chunks_count} 个文档片段, ${retrievalContent?.screenshots_count} 张截图`,
                          status: 'completed',
                          timestamp: Date.now(),
                          details: retrievalContent
                      };
                      updated = true;
                      break;
                  }
              }
          }
          
          if (!updated) {
              newSteps.push({
                  id: stepId ? `${stepId}_retrieval_${Date.now()}` : `retrieval_${Date.now()}`,
                  stepId: stepId,
                  type: 'retrieval',
                  title: '知识库检索完成',
                  content: `找到 ${retrievalContent?.chunks_count} 个文档片段, ${retrievalContent?.screenshots_count} 张截图`,
                  status: 'completed',
                  timestamp: Date.now(),
                  details: retrievalContent
              });
          }

          return {
            ...msg,
            details: {
              ...msg.details,
              workflow_steps: newSteps
            }
          };
        })
      );
      break;
      
    case 'screenshots':
      setMessages((prev: Message[]) =>
        prev.map((msg) =>
          msg.id === botMessageId
            ? {
                ...msg,
                content: msg.content + `\n🖼️ 找到 ${event.content?.length || 0} 张相关截图\n`,
              }
            : msg
        )
      );
      break;
      
    case 'export_result':
      const exportContent = event.content;
      setMessages((prev: Message[]) =>
        prev.map((msg) => {
          if (msg.id !== botMessageId) return msg;

          const currentSteps = msg.details?.workflow_steps || [];
          const stepId = event.step_id;
          const newSteps = [...currentSteps];
          
          let updated = false;
          if (stepId) {
              for (let i = newSteps.length - 1; i >= 0; i--) {
                  if (newSteps[i].stepId === stepId && newSteps[i].status === 'running') {
                      newSteps[i] = {
                          ...newSteps[i],
                          type: 'export',
                          title: '文档已生成',
                          content: `文件名: ${exportContent?.filename}`,
                          status: 'completed',
                          timestamp: Date.now(),
                          details: exportContent
                      };
                      updated = true;
                      break;
                  }
              }
          }
          
          if (!updated) {
              newSteps.push({
                  id: stepId ? `${stepId}_export_${Date.now()}` : `export_${Date.now()}`,
                  stepId: stepId,
                  type: 'export',
                  title: '文档已生成',
                  content: `文件名: ${exportContent?.filename}`,
                  status: 'completed',
                  timestamp: Date.now(),
                  details: exportContent
              });
          }

          return {
            ...msg,
            details: {
              ...msg.details,
              workflow_steps: newSteps
            }
          };
        })
      );
      break;

    default:
      console.log('[Workflow] Unknown event type:', event.type);
  }
}
