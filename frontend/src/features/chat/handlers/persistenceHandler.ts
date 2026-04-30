/**
 * Persistence Handler - 处理 Workflow 执行数据的持久化
 * 将事件处理与数据库存储解耦
 */

import {
  createRunNode,
  updateRunNodeStatus,
  updateRunNodeProgress,
  createCuaStepAction,
  updateCuaStepAction,
  createToolCallAction,
  updateToolCallAction,
  type RunNode,
  type NodeAction,
} from '@/utils/workflowPersistence';
import { logHandler } from '@/utils/logger';
import type { CommandHandlerContext } from './types';

// ============================================================
// 持久化上下文
// ============================================================

export interface PersistenceContext {
  userId: string;
  chatId: string;
  workflowRunId: string;
  
  // 当前 Node 的 run_nodes.id
  currentRunNodeId?: string;
  
  // 当前 CUA Step 的 node_actions.id
  currentCuaActionId?: string;
  
  // 当前 Tool Call 的 node_actions.id
  currentToolActionId?: string;
  
  // Node 步骤计数器
  nodeStepIndex: number;
  
  // Action 步骤计数器（每个 Node 内部重置）
  actionStepIndex: number;
}

/**
 * 创建持久化上下文
 */
export function createPersistenceContext(
  userId: string,
  chatId: string,
  workflowRunId: string
): PersistenceContext {
  return {
    userId,
    chatId,
    workflowRunId,
    nodeStepIndex: 0,
    actionStepIndex: 0,
  };
}

// ============================================================
// Node 持久化
// ============================================================

/**
 * 持久化 Node 开始事件
 */
export async function persistNodeStart(
  ctx: PersistenceContext,
  event: {
    nodeId: string;
    nodeType: string;
    title?: string;
    instruction?: string;
  }
): Promise<string> {
  try {
    ctx.nodeStepIndex += 1;
    ctx.actionStepIndex = 0; // 重置 action 计数器
    
    const runNode = await createRunNode(
      ctx.workflowRunId,
      event.nodeId,
      event.nodeType as any,
      ctx.nodeStepIndex,
      {
        title: event.title,
        instruction: event.instruction,
      }
    );
    
    ctx.currentRunNodeId = runNode.id;
    logHandler('Node started: %s', runNode.id);
    return runNode.id;
  } catch (error) {
    console.error('[PersistenceHandler] ❌ Failed to persist node_start:', error);
    throw error;
  }
}

/**
 * 持久化 Node 更新事件
 */
export async function persistNodeUpdate(
  ctx: PersistenceContext,
  event: {
    progress?: { current: number; total?: number; message?: string };
  }
): Promise<void> {
  if (!ctx.currentRunNodeId) {
    console.warn('[PersistenceHandler] ⚠️ No currentRunNodeId for node_update');
    return;
  }
  
  try {
    if (event.progress) {
      await updateRunNodeProgress(
        ctx.currentRunNodeId,
        event.progress.current,
        event.progress.total,
        event.progress.message
      );
    }
  } catch (error) {
    console.error('[PersistenceHandler] ❌ Failed to persist node_update:', error);
    // 不抛出错误，进度更新失败不阻塞主流程
  }
}

/**
 * 持久化 Node 结束事件
 */
export async function persistNodeEnd(
  ctx: PersistenceContext,
  event: {
    status: 'completed' | 'failed';
    reasoning?: string;
    output?: string;
    error_message?: string;
    tokens_used?: number;
  }
): Promise<void> {
  if (!ctx.currentRunNodeId) {
    console.warn('[PersistenceHandler] ⚠️ No currentRunNodeId for node_end');
    return;
  }
  
  try {
    await updateRunNodeStatus(ctx.currentRunNodeId, event.status, {
      reasoning: event.reasoning,
      output: event.output,
      error_message: event.error_message,
      tokens_used: event.tokens_used,
    });
    
    logHandler('Node ended: %s', ctx.currentRunNodeId);
    ctx.currentRunNodeId = undefined;
  } catch (error) {
    console.error('[PersistenceHandler] ❌ Failed to persist node_end:', error);
    throw error;
  }
}

// ============================================================
// CUA Step 持久化
// ============================================================

/**
 * 持久化 CUA Step 开始事件（含截图上传）
 */
export async function persistCuaStepStart(
  ctx: PersistenceContext,
  event: {
    step: number;
    screenshot?: string;
    title?: string;
    reasoning?: string;
  }
): Promise<string | undefined> {
  if (!ctx.currentRunNodeId) {
    console.warn('[PersistenceHandler] ⚠️ No currentRunNodeId for cua_step_start');
    return undefined;
  }
  
  try {
    ctx.actionStepIndex = event.step; // 使用事件中的 step 作为索引
    
    const action = await createCuaStepAction(
      ctx.currentRunNodeId,
      event.step,
      ctx.userId,
      {
        title: event.title || `Step ${event.step}`,
        screenshotBase64: event.screenshot,
        reasoning: event.reasoning,
      }
    );
    
    ctx.currentCuaActionId = action.id;
    logHandler('CUA step started: %s', action.id);
    return action.id;
  } catch (error) {
    console.error('[PersistenceHandler] ❌ Failed to persist cua_step_start:', error);
    // 不抛出错误，截图上传失败不阻塞主流程
    return undefined;
  }
}

/**
 * 持久化 CUA Step 动作事件
 */
export async function persistCuaStepAction(
  ctx: PersistenceContext,
  event: {
    step: number;
    action?: {
      type: string;
      x?: number;
      y?: number;
      text?: string;
      key?: string;
    };
    reasoning?: string;
    content?: string;
  }
): Promise<void> {
  if (!ctx.currentCuaActionId) {
    console.warn('[PersistenceHandler] ⚠️ No currentCuaActionId for cua_step_action');
    return;
  }
  
  try {
    await updateCuaStepAction(ctx.currentCuaActionId, {
      actionDetail: event.action as any,
      reasoning: event.reasoning,
      content: event.content,
    });
  } catch (error) {
    console.error('[PersistenceHandler] ❌ Failed to persist cua_step_action:', error);
    // 不抛出错误
  }
}

/**
 * 持久化 CUA Step 结束事件
 */
export async function persistCuaStepEnd(
  ctx: PersistenceContext,
  event: {
    status: 'completed' | 'failed';
    duration_ms?: number;
    error_message?: string;
  }
): Promise<void> {
  if (!ctx.currentCuaActionId) {
    console.warn('[PersistenceHandler] ⚠️ No currentCuaActionId for cua_step_end');
    return;
  }
  
  try {
    await updateCuaStepAction(ctx.currentCuaActionId, {
      status: event.status,
      duration_ms: event.duration_ms,
      error_message: event.error_message,
    });
    
    logHandler('CUA step ended: %s', ctx.currentCuaActionId);
    ctx.currentCuaActionId = undefined;
  } catch (error) {
    console.error('[PersistenceHandler] ❌ Failed to persist cua_step_end:', error);
    // 不抛出错误
  }
}

// ============================================================
// Tool Call 持久化
// ============================================================

/**
 * 持久化 Tool Call 开始事件
 */
export async function persistToolStart(
  ctx: PersistenceContext,
  event: {
    toolId: string;
    toolName: string;
    title?: string;
    input?: Record<string, any>;
    reasoning?: string;
  }
): Promise<string | undefined> {
  if (!ctx.currentRunNodeId) {
    console.warn('[PersistenceHandler] ⚠️ No currentRunNodeId for tool_start');
    return undefined;
  }
  
  try {
    ctx.actionStepIndex += 1;
    
    const action = await createToolCallAction(
      ctx.currentRunNodeId,
      ctx.actionStepIndex,
      event.toolName,
      {
        title: event.title || event.toolName,
        input: event.input,
        reasoning: event.reasoning,
      }
    );
    
    ctx.currentToolActionId = action.id;
    logHandler('Tool call started: %s', action.id);
    return action.id;
  } catch (error) {
    console.error('[PersistenceHandler] ❌ Failed to persist tool_start:', error);
    return undefined;
  }
}

/**
 * 持久化 Tool Call 结束事件
 */
export async function persistToolEnd(
  ctx: PersistenceContext,
  event: {
    status: 'completed' | 'failed';
    output?: Record<string, any>;
    reasoning?: string;
    duration_ms?: number;
    error_message?: string;
  }
): Promise<void> {
  if (!ctx.currentToolActionId) {
    console.warn('[PersistenceHandler] ⚠️ No currentToolActionId for tool_end');
    return;
  }
  
  try {
    await updateToolCallAction(ctx.currentToolActionId, {
      status: event.status,
      output: event.output,
      reasoning: event.reasoning,
      duration_ms: event.duration_ms,
      error_message: event.error_message,
    });
    
    logHandler('Tool call ended: %s', ctx.currentToolActionId);
    ctx.currentToolActionId = undefined;
  } catch (error) {
    console.error('[PersistenceHandler] ❌ Failed to persist tool_end:', error);
    // 不抛出错误
  }
}

// ============================================================
// 批量持久化（用于流式事件）
// ============================================================

/**
 * 处理流式事件并持久化
 * 返回是否成功处理
 */
export async function handleEventPersistence(
  ctx: PersistenceContext | undefined,
  event: { type: string; [key: string]: any }
): Promise<boolean> {
  // 如果没有持久化上下文，跳过
  if (!ctx) {
    return false;
  }
  
  try {
    switch (event.type) {
      case 'node_start':
        await persistNodeStart(ctx, {
          nodeId: event.nodeId,
          nodeType: event.nodeType,
          title: event.title,
          instruction: event.instruction,
        });
        return true;
        
      case 'node_update':
        await persistNodeUpdate(ctx, {
          progress: event.progress,
        });
        return true;
        
      case 'node_end':
        await persistNodeEnd(ctx, {
          status: event.status,
          reasoning: (event as any).reasoning,
          output: (event as any).output,
          error_message: (event as any).error_message,
          tokens_used: (event as any).tokens_used,
        });
        return true;

      case 'node_complete':
        await persistNodeEnd(ctx, {
          status: (event as any).status ?? 'completed',
          reasoning: (event as any).reasoning,
          output: (event as any).output,
          error_message: (event as any).error_message,
          tokens_used: (event as any).tokens_used,
        });
        return true;

      case 'cua_step_start':
        await persistCuaStepStart(ctx, {
          step: event.content?.step || event.step,
          screenshot: event.content?.screenshot || event.screenshot,
          title: event.content?.title || event.title,
          reasoning: event.content?.reasoning || event.reasoning,
        });
        return true;
        
      case 'cua_step_action':
        await persistCuaStepAction(ctx, {
          step: event.content?.step || event.step,
          action: event.content?.action || event.action,
          reasoning: event.content?.reasoning || event.reasoning,
          content: event.content?.content || event.actionContent,
        });
        return true;
        
      case 'cua_end':
        await persistCuaStepEnd(ctx, {
          status: event.status || 'completed',
          duration_ms: event.duration_ms,
          error_message: event.error_message,
        });
        return true;
        
      case 'tool_start':
        await persistToolStart(ctx, {
          toolId: event.toolId,
          toolName: event.toolName,
          title: event.title,
          input: event.input,
          reasoning: event.reasoning,
        });
        return true;
        
      case 'tool_end':
        await persistToolEnd(ctx, {
          status: event.status,
          output: typeof event.output === 'string' 
            ? { result: event.output } 
            : event.output,
          reasoning: event.reasoning,
          duration_ms: event.duration ? event.duration * 1000 : undefined,
          error_message: event.error_message,
        });
        return true;
        
      default:
        // 其他事件不需要持久化
        return false;
    }
  } catch (error) {
    console.error(`[PersistenceHandler] ❌ Failed to handle ${event.type}:`, error);
    return false;
  }
}

