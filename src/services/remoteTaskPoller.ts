/**
 * 远程任务轮询器
 * 
 * Desktop 专用服务：
 * - 定期从 Backend 获取待执行事件（tool_call/client_request）
 * - 复用现有的 handler 执行 Local Engine 操作
 * - 将执行结果回传给 Backend
 * 
 * 架构说明（方案 A：SSE 流分叉）：
 * - Web 端调用 /api/v1/remote/task (stream=true) → 收到 SSE 流（UI 事件）
 * - Backend 将 tool_call/client_request 存入 pending_events 队列
 * - Desktop 端轮询 /api/v1/remote/pending-events/{taskId} → 获取事件
 * - Desktop 执行后回调 /api/v1/workflow/callback/{requestId}
 * 
 * 职责分离：
 * - Web 端：显示 UI + 持久化（谁显示谁持久化）
 * - Desktop 端：只执行 Local Engine 操作
 */

import { getApiUrl, LOCAL_ENGINE_URL } from '../config/runtimeEnv';
import { handleToolCall, handleClientRequest } from '../features/chat/handlers/localEngine/router';
import type { CommandHandlerContext, Message } from '../features/chat/handlers/types';
import type { ToolCallEvent, ClientRequestEvent } from '../features/chat/handlers/localEngine/types';

class RemoteTaskPoller {
  private polling = false;
  private pollInterval = 1000; // 1秒轮询一次（事件需要快速响应）
  private taskPollInterval = 3000; // 3秒轮询一次任务
  private userId: string | null = null;
  private pollTimeoutId: NodeJS.Timeout | null = null;
  
  // 当前正在处理的任务 ID
  private currentTaskId: string | null = null;

  /**
   * 开始轮询远程任务
   */
  async start(userId: string) {
    if (this.polling) {
      console.log('[RemotePoller] 已在运行中');
      return;
    }

    this.userId = userId;
    this.polling = true;
    console.log('[RemotePoller] 开始轮询远程任务...', { userId });
    this.poll();
  }

  /**
   * 停止轮询
   */
  stop() {
    this.polling = false;
    if (this.pollTimeoutId) {
      clearTimeout(this.pollTimeoutId);
      this.pollTimeoutId = null;
    }
    console.log('[RemotePoller] 停止轮询');
  }

  /**
   * 轮询循环
   */
  private async poll() {
    while (this.polling && this.userId) {
      try {
        // 1. 检查当前任务是否有待执行事件
        if (this.currentTaskId) {
          const hasEvents = await this.pollPendingEvents(this.currentTaskId);
          if (hasEvents) {
            // 有事件处理，快速轮询
            await this.sleep(this.pollInterval);
            continue;
          }
        }

        // 2. 检查是否有新任务（同时更新心跳）
        const taskInfo = await this.fetchPendingTasks();
        
        if (taskInfo.currentTaskId && taskInfo.hasPendingEvents) {
          // 有正在执行的任务且有待处理事件
          this.currentTaskId = taskInfo.currentTaskId;
          await this.sleep(this.pollInterval);
          continue;
        }

        if (taskInfo.tasks.length > 0) {
          // 有新任务（非 streaming 模式）
          const task = taskInfo.tasks[0];
          console.log(`[RemotePoller] 📥 收到远程任务: ${task.task_id}`);
          console.log(`[RemotePoller] 任务内容: ${task.message}`);
          
          this.currentTaskId = task.task_id;
          
          try {
            await this.executeTask(task);
            console.log(`[RemotePoller] ✅ 任务完成: ${task.task_id}`);
          } catch (error) {
            console.error(`[RemotePoller] ❌ 任务失败: ${task.task_id}`, error);
          } finally {
            this.currentTaskId = null;
          }
        }
      } catch (error) {
        console.error('[RemotePoller] 轮询错误:', error);
      }

      // 等待下次轮询
      await this.sleep(this.taskPollInterval);
    }
  }

  /**
   * 轮询待执行事件
   * 
   * @returns 是否有事件被处理
   */
  private async pollPendingEvents(taskId: string): Promise<boolean> {
    try {
      const response = await fetch(
        `${getApiUrl()}/api/v1/remote/pending-events/${taskId}`
      );

      if (!response.ok) {
        return false;
      }

      const data = await response.json();
      const event = data.event;

      if (!event) {
        return false;
      }

      const eventType = event.type;
      console.log(`[RemotePoller] 📨 收到待执行事件: type=${eventType}`);

      // 创建上下文
      const ctx = this.createRemoteContext(taskId);

      // 处理事件
      if (eventType === 'tool_call') {
        console.log(`[RemotePoller] 🔧 开始处理 tool_call: ${event.target}.${event.name}`);
        await handleToolCall(event as ToolCallEvent, ctx);
        console.log(`[RemotePoller] ✅ tool_call 处理完成`);
        return true;
      }

      if (eventType === 'client_request') {
        console.log(`[RemotePoller] 🔧 开始处理 client_request: action=${event.action} requestId=${event.requestId}`);
        await handleClientRequest(event as ClientRequestEvent, ctx);
        console.log(`[RemotePoller] ✅ client_request 处理完成`);
        return true;
      }

      console.warn(`[RemotePoller] ⚠️ 未知事件类型: ${eventType}`);
      return false;

    } catch (error) {
      // 网络错误静默处理
      return false;
    }
  }

  /**
   * 从 Backend 获取待执行的任务
   */
  private async fetchPendingTasks(): Promise<{
    tasks: any[];
    currentTaskId: string | null;
    hasPendingEvents: boolean;
  }> {
    try {
      const response = await fetch(
        `${getApiUrl()}/api/v1/remote/pending-tasks/${this.userId}`
      );

      if (!response.ok) {
        // 404 可能是 API 还没部署，静默处理
        if (response.status === 404) {
          return { tasks: [], currentTaskId: null, hasPendingEvents: false };
        }
        throw new Error(`HTTP ${response.status}`);
      }

      const data = await response.json();
      return {
        tasks: data.tasks || [],
        currentTaskId: data.current_task_id || null,
        hasPendingEvents: data.has_pending_events || false,
      };
    } catch (error) {
      // 网络错误静默处理，避免刷屏
      return { tasks: [], currentTaskId: null, hasPendingEvents: false };
    }
  }

  /**
   * 创建远程任务专用的 CommandHandlerContext
   * 
   * 特点：
   * - setMessages 是空操作（远程模式不需要更新本地 UI）
   * - localEngineUrl 使用本地配置
   */
  private createRemoteContext(taskId: string): CommandHandlerContext {
    // 远程模式下，UI 更新是空操作
    // 实际的 UI 显示由 Web 端处理
    const noopSetMessages = (() => {}) as React.Dispatch<React.SetStateAction<Message[]>>;
    
    return {
      botMessageId: `remote_${taskId}`,
      setMessages: noopSetMessages,
      localEngineUrl: LOCAL_ENGINE_URL,
      userId: this.userId || undefined,
    };
  }

  /**
   * 执行任务（非 streaming 模式，兼容旧逻辑）
   * 
   * 注意：streaming 模式的任务由 pending-events 处理，不会进入这里
   */
  private async executeTask(task: any) {
    try {
      // 调用 Backend 的 workflow API 执行任务
      // 使用 workflow_id 作为 workflow_run_id（确保是有效的 UUID）
      const response = await fetch(`${getApiUrl()}/api/v1/workflow`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message: task.message,
          user_id: task.user_id,
          workflow_run_id: task.task_id,
          workflow_id: task.workflow_id,
          project_id: task.project_id,
          chat_id: task.chat_id,
          source: 'remote',
        }),
      });

      if (!response.ok) {
        throw new Error(`Workflow API 返回 ${response.status}`);
      }

      // 处理 SSE 流式响应
      const reader = response.body?.getReader();
      if (!reader) {
        throw new Error('无法读取响应流');
      }

      const decoder = new TextDecoder();
      let resultText = '';
      let lastScreenshot: string | null = null;

      // 创建上下文
      const ctx = this.createRemoteContext(task.task_id);

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        const chunk = decoder.decode(value, { stream: true });
        const lines = chunk.split('\n').filter(line => line.trim());

        console.log(`[RemotePoller] 📦 收到 SSE chunk, ${lines.length} 行`);

        for (const line of lines) {
          try {
            let event: any;
            if (line.startsWith('data:')) {
              const jsonStr = line.replace(/^data:\s*/, '');
              event = JSON.parse(jsonStr);
            } else {
              event = JSON.parse(line);
            }
            
            const eventType = event.type;

            // 处理 tool_call 事件
            if (eventType === 'tool_call') {
              console.log(`[RemotePoller] 🔧 处理 tool_call: ${event.target}.${event.name}`);
              await handleToolCall(event as ToolCallEvent, ctx);
              continue;
            }

            // 处理 client_request 事件
            if (eventType === 'client_request') {
              console.log(`[RemotePoller] 🔧 处理 client_request: action=${event.action}`);
              await handleClientRequest(event as ClientRequestEvent, ctx);
              continue;
            }

            // 处理文本输出
            if (eventType === 'text' && typeof event.delta === 'string') {
              resultText += event.delta;
            }
            
            // 处理截图
            if (eventType === 'screenshot' || event.screenshot) {
              lastScreenshot = event.screenshot || event.image_base64;
            }
            
            // 任务完成
            if (eventType === 'workflow_complete' || eventType === 'workflow_completed') {
              break;
            }
            
            // 错误处理
            if (eventType === 'error') {
              throw new Error(event.content || event.message || '未知错误');
            }

          } catch (parseError) {
            // 跳过无法解析的行（可能是 SSE 格式问题）
            if (line.startsWith('data:')) {
              try {
                const jsonStr = line.replace(/^data:\s*/, '');
                const event = JSON.parse(jsonStr);
                // 重新处理
                if (event.type === 'client_request') {
                  await this.handleClientRequest(event);
                } else if (event.type === 'tool_call') {
                  await this.handleToolCall(event);
                }
              } catch {
                // 忽略
              }
            }
          }
        }
      }

      // 提交结果
      await this.submitResult(task.task_id, {
        success: true,
        result: resultText,
        screenshot: lastScreenshot,
      });

    } catch (error) {
      // 提交错误结果
      await this.submitResult(task.task_id, {
        success: false,
        error: String(error),
      });
      throw error;
    }
  }

  /**
   * 提交任务执行结果
   */
  private async submitResult(taskId: string, result: any) {
    try {
      await fetch(`${getApiUrl()}/api/v1/remote/result/${taskId}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(result),
      });
    } catch (error) {
      console.error('[RemotePoller] 提交结果失败:', error);
    }
  }

  /**
   * 延时工具
   */
  private sleep(ms: number): Promise<void> {
    return new Promise(resolve => {
      this.pollTimeoutId = setTimeout(resolve, ms);
    });
  }
}

// 导出单例
export const remoteTaskPoller = new RemoteTaskPoller();
