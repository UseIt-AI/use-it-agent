/**
 * Tool Handler - 处理工具调用相关的事件
 */

import { CommandHandlerContext, Message } from './types';

export interface ToolEvent {
  type: 'tool_call_start' | 'tool_call_complete';
  tool_name: string;
  tool_display_name?: string;
  tool_id?: string;
  input?: Record<string, any>;
  output?: string;
  status?: 'pending' | 'running' | 'completed' | 'error';
  duration?: number;
}

/**
 * 处理工具调用开始事件
 * 不清空 content，让渲染层动态处理 streaming 中的内容显示
 * content 会在 tool_call_complete 时被保存到 reasoning
 */
export function handleToolCallStart(
  event: ToolEvent,
  ctx: CommandHandlerContext
): void {
  const { botMessageId, setMessages } = ctx;
  
  // 忽略没有有效 tool_name 的事件
  if (!event.tool_name || event.tool_name === 'unknown') {
    return;
  }
  
  setMessages((prev: Message[]) =>
    prev.map((msg) => {
      if (msg.id !== botMessageId) return msg;
      
      const currentTools = msg.details?.tool_calls || [];
      
      // 去重：如果已经有相同 tool_id 或相同 tool_name 且 running 的卡片，跳过
      const toolId = event.tool_id || `tool_${Date.now()}`;
      const isDuplicate = currentTools.some((t: any) => 
        (event.tool_id && t.id === event.tool_id) ||
        (t.toolName === event.tool_name && t.status === 'running')
      );
      
      if (isDuplicate) {
        return msg;
      }
      
      // 添加新的工具调用记录
      const newToolCall = {
        id: toolId,
        toolName: event.tool_name,
        toolDisplayName: event.tool_display_name || event.tool_name,
        status: 'running' as const,
        input: event.input,
        timestamp: Date.now()
      };
      
      return {
        ...msg,
        details: {
          ...msg.details,
          tool_calls: [...currentTools, newToolCall]
        }
      };
    })
  );
}

/**
 * 处理工具调用完成事件
 * 将当前 content 作为 reasoning 保存到工具卡片，然后清空 content
 */
export function handleToolCallComplete(
  event: ToolEvent,
  ctx: CommandHandlerContext
): void {
  const { botMessageId, setMessages } = ctx;
  
  setMessages((prev: Message[]) =>
    prev.map((msg) => {
      if (msg.id !== botMessageId) return msg;
      
      const currentTools = msg.details?.tool_calls || [];
      
      // 获取当前 content 作为 reasoning（streaming 结束时固定下来）
      const reasoning = msg.content.trim();
      
      // 找到对应的工具调用并更新
      const updatedTools = currentTools.map((tool: any) => {
        // 通过 tool_id 或者最后一个 running 状态的工具来匹配
        if (
          (event.tool_id && tool.id === event.tool_id) ||
          (!event.tool_id && tool.toolName === event.tool_name && tool.status === 'running')
        ) {
          return {
            ...tool,
            status: event.status || 'completed',
            output: event.output,
            duration: event.duration,
            reasoning: reasoning || tool.reasoning, // 保存 reasoning
            completedAt: Date.now()
          };
        }
        return tool;
      });
      
      return {
        ...msg,
        content: '', // 清空 content，后续 token 会归属到下一个工具或最终回复
        details: {
          ...msg.details,
          tool_calls: updatedTools
        }
      };
    })
  );
}

/**
 * 统一处理工具事件
 */
export function handleToolEvent(
  event: ToolEvent,
  ctx: CommandHandlerContext
): void {
  switch (event.type) {
    case 'tool_call_start':
      handleToolCallStart(event, ctx);
      break;
    case 'tool_call_complete':
      handleToolCallComplete(event, ctx);
      break;
    default:
      console.log('[Tool] Unknown event type:', event.type);
  }
}

