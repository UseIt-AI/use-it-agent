/**
 * Event Handler - 统一处理所有流式事件
 */

import { API_URL } from '@/config/runtimeEnv';
import { logHandler } from '@/utils/logger';
import {
  Message,
  ContentBlock,
  TextBlock,
  CardBlock,
  CompletionBlock,
  Card,
  CUAAction,
  StreamEvent,
  CommandHandlerContext,
  TextEvent,
  ErrorEvent,
  ClientRequestEvent,
  ToolStartEvent,
  ToolDeltaEvent,
  ToolEndEvent,
  CuaStartEvent,
  CuaDeltaEvent,
  CuaUpdateEvent,
  CuaRequestEvent,
  CuaEndEvent,
  NodeStartEvent,
  NodeUpdateEvent,
  NodeEndEvent,
  NodeCompleteEvent,
  WorkflowProgressEvent,
  ActionCompletedEvent,
  ToolResultEvent,
  PlannerCompleteEvent,
  SearchResultPayload,
  SearchResultItem,
  RAGChunk,
} from './types';

// ==================== 辅助函数 ====================

/**
 * 追加文本到 TextBlock
 * 如果最后一个 block 是 TextBlock，追加到它；否则创建新的 TextBlock
 */
function appendToTextBlock(message: Message, content: string): Message {
  const blocks = [...message.blocks];
  const lastBlock = blocks[blocks.length - 1];
  
  if (lastBlock?.type === 'text') {
    // 追加到现有 TextBlock
    blocks[blocks.length - 1] = {
      ...lastBlock,
      content: lastBlock.content + content
    };
  } else {
    // 创建新的 TextBlock
    blocks.push({ type: 'text', content });
  }
  
  return { ...message, blocks };
}

/**
 * 通过 ID 查找卡片
 */
function findCardById(message: Message, id: string): Card | null {
  for (const block of message.blocks) {
    if (block.type === 'card' && block.card.id === id) {
      return block.card;
    }
  }
  return null;
}

/**
 * 通过 ID 更新卡片
 */
function updateCardById(message: Message, id: string, updates: Partial<Card>): Message {
  const blocks = message.blocks.map(block => {
    if (block.type === 'card' && block.card.id === id) {
      return {
        ...block,
        card: { ...block.card, ...updates }
      };
    }
    return block;
  });
  
  return { ...message, blocks };
}

/**
 * 添加卡片到 blocks（如果已存在相同 ID 的卡片则跳过）
 */
function addCard(message: Message, card: Card): Message {
  // 检查是否已存在相同 ID 的卡片
  const existingCard = message.blocks.find(
    block => block.type === 'card' && block.card.id === card.id
  );
  if (existingCard) {
    logHandler('卡片已存在，跳过添加: %s', card.id);
    return message;
  }
  
  const blocks = [...message.blocks];
  blocks.push({ type: 'card', card });
  return { ...message, blocks };
}

// ==================== 事件处理函数 ====================

/**
 * 处理文本事件
 */
function handleTextEvent(event: TextEvent, message: Message): Message {
  return appendToTextBlock(message, event.delta);
}

/** 避免同一错误在 StrictMode / 高频 SSE 下重复刷满控制台 */
let lastErrorLog: { msg: string; at: number } | null = null;
const ERROR_LOG_THROTTLE_MS = 4000;

/**
 * 处理错误事件
 * 只在 console 中打印，不在 UI 中显示
 */
function handleErrorEvent(event: ErrorEvent, message: Message): Message {
  const now = Date.now();
  if (
    !lastErrorLog ||
    lastErrorLog.msg !== event.message ||
    now - lastErrorLog.at > ERROR_LOG_THROTTLE_MS
  ) {
    console.error('[EventHandler] Error event:', event.message);
    lastErrorLog = { msg: event.message, at: now };
  }
  return message;
}

/**
 * 处理 Tool 开始事件
 */
function handleToolStart(event: ToolStartEvent, message: Message): Message {
  const card: Card = {
    id: event.toolId,
    type: 'tool',
    status: 'running',
    title: event.title,
    toolName: event.toolName,
    input: event.input,
    nodeId: event.nodeId,
    startedAt: Date.now()
  };
  return addCard(message, card);
}

/**
 * 处理 Tool 增量事件
 */
function handleToolDelta(event: ToolDeltaEvent, message: Message): Message {
  const card = findCardById(message, event.toolId);
  if (card) {
    return updateCardById(message, event.toolId, {
      reasoning: (card.reasoning || '') + event.reasoning
    });
  }
  return message;
}

/**
 * 处理 Tool 结束事件
 */
function handleToolEnd(event: ToolEndEvent, message: Message): Message {
  return updateCardById(message, event.toolId, {
    status: event.status,
    output: event.output,
    duration: event.duration,
    completedAt: Date.now()
  });
}

/**
 * 查找最后一个 Node 卡片的 ID
 */
function findLastNodeId(message: Message): string | undefined {
  for (let i = message.blocks.length - 1; i >= 0; i--) {
    const block = message.blocks[i];
    if (block.type === 'card' && block.card.type === 'node') {
      return block.card.id;
    }
  }
  return undefined;
}

/**
 * 判断是否应该跳过某些 CUA 事件（不创建卡片）
 * 
 * 跳过的情况：
 * 1. cuaId 包含 "_result" - 这是代码执行结果通知，不是真正的 CUA 步骤
 * 2. title 是纯状态通知（如 "执行结果"）
 */
function shouldSkipCuaEvent(event: CuaStartEvent): boolean {
  // 跳过执行结果通知（cuaId 包含 _result）
  if (event.cuaId.includes('_result')) {
    logHandler('CUA 跳过执行结果通知: %s', event.cuaId);
    return true;
  }
  return false;
}

/**
 * 处理 CUA 开始事件
 * 
 * 截图分配逻辑：
 * 1. 计算已分配截图的 CUA 卡片数量
 * 2. 如果 screenshots.length > 已分配数量，说明有"未分配"的截图
 * 3. 将第一个未分配的截图分配给新创建的 CUA 卡片
 * 
 * Node 关联逻辑：
 * - 如果后端发送了 nodeId，使用后端的值
 * - 如果没有 nodeId，自动关联到最后一个 Node 卡片（用于折叠功能）
 */
function handleCuaStart(event: CuaStartEvent, message: Message): Message {
  // 跳过不需要显示的 CUA 事件
  if (shouldSkipCuaEvent(event)) {
    return message;
  }
  const currentScreenshotCount = message.screenshots?.length || 0;
  
  // 新卡片始终关联最新的截图（即 AI 当前看到的画面）
  const screenshotIndexToAssign = currentScreenshotCount > 0
    ? currentScreenshotCount - 1
    : undefined;
  
  // 如果后端没有发送 nodeId，自动关联到最后一个 Node
  const nodeId = event.nodeId || findLastNodeId(message);
  
  logHandler('CUA handleCuaStart: cuaId=%s step=%s nodeId=%s', event.cuaId, event.step, nodeId);
  
  const card: Card = {
    id: event.cuaId,
    type: 'cua',
    status: 'running',
    step: event.step,
    title: event.title,
    screenshotIndex: screenshotIndexToAssign,
    nodeId: nodeId, // 使用解析后的 nodeId
    startedAt: Date.now()
  };
  return addCard(message, card);
}

// Reasoning 解析逻辑已移至 utils/reasoningParser.ts
import { parseReasoning } from '../utils/reasoningParser';

/**
 * 处理 CUA 思考过程增量事件 (追加到 reasoning)
 */
function handleCuaDelta(event: CuaDeltaEvent, message: Message): Message {
  const card = findCardById(message, event.cuaId);
  if (card) {
    if (event.kind === 'search_progress') {
      const payload = (event.payload || {}) as any;
      const prev = card.searchProgress || {};
      // 合并 queries：只有新 payload 有非空数组时才覆盖，否则保留之前的
      const mergedQueries = (payload.queries && payload.queries.length > 0)
        ? payload.queries
        : prev.queries;
      const next = {
        ...prev,
        ...payload,
        queries: mergedQueries,
      };
      if (!Object.keys(payload).length && event.reasoning) {
        next.message = event.reasoning;
      }
      return updateCardById(message, event.cuaId, {
        searchProgress: next
      });
    }
    if (event.kind === 'search_result') {
      const payload = event.payload as any;
      return updateCardById(message, event.cuaId, {
        searchResult: payload || { answer: event.reasoning }
      });
    }
    if (event.kind === 'extract_progress') {
      const payload = (event.payload || {}) as any;
      return updateCardById(message, event.cuaId, {
        extractProgress: payload
      });
    }
    // 1. 追加原始数据到 rawReasoning
    const newRawReasoning = (card.rawReasoning || '') + event.reasoning;
    
    // 2. 尝试从累积的原始数据中提取干净的文本
    const formattedReasoning = parseReasoning(newRawReasoning);
    
    return updateCardById(message, event.cuaId, {
      rawReasoning: newRawReasoning,
      reasoning: formattedReasoning || card.reasoning // 如果提取结果为空（例如只收到 Key），保持上一帧的显示，避免闪烁
    });
  }
  return message;
}

/**
 * 处理 CUA 动作内容更新事件 (更新 content 和 action)
 */
function handleCuaUpdate(event: CuaUpdateEvent, message: Message): Message {
  const card = findCardById(message, event.cuaId);
  if (card) {
    const actionContent = event.content;
    
    // 生成 action title（如 "click (405, 984)"）
    let actionTitle = card.title;
    if (actionContent?.type && actionContent.type !== 'stop') {
      actionTitle = actionContent.type;
      // 添加坐标信息
      if (actionContent.coordinate) {
        actionTitle += ` (${actionContent.coordinate[0]}, ${actionContent.coordinate[1]})`;
      } else if (actionContent.x !== undefined && actionContent.y !== undefined) {
        actionTitle += ` (${actionContent.x}, ${actionContent.y})`;
      }
      // 添加文本信息
      if (actionContent.text) {
        const truncated = actionContent.text.length > 20 
          ? actionContent.text.substring(0, 20) + '...' 
          : actionContent.text;
        actionTitle += `: "${truncated}"`;
      }
      // 添加按键信息
      if (actionContent.key) {
        actionTitle += `: ${actionContent.key}`;
      }
    }
    
    logHandler('CUA handleCuaUpdate: cuaId=%s actionType=%s', event.cuaId, actionContent?.type);
    return updateCardById(message, event.cuaId, {
      content: JSON.stringify(actionContent),
      action: actionContent as CUAAction,
      title: actionTitle
    });
  }
  return message;
}

/**
 * 处理 CUA 结束事件
 */
function handleCuaEnd(event: CuaEndEvent, message: Message): Message {
  const updates: Partial<Card> = {
    status: event.status,
    completedAt: Date.now()
  };
  if (event.title) updates.title = event.title;
  if (event.action) updates.action = event.action;
  
  return updateCardById(message, event.cuaId, updates);
}

/**
 * 处理 Node 开始事件 - 创建 Node 卡片
 */
function handleNodeStart(event: NodeStartEvent, message: Message): Message {
  logHandler('Node handleNodeStart: nodeId=%s title=%s', event.nodeId, event.title);
  
  const card: Card = {
    id: event.nodeId,
    type: 'node',
    status: 'running',
    title: event.title || 'Node',
    nodeType: event.nodeType,
    instruction: event.instruction,
    progress: event.progress,
    startedAt: event.startedAt || Date.now()
  };
  return addCard(message, card);
}

/**
 * 处理 Node 更新事件 - 忽略（不需要卡片更新）
 */
function handleNodeUpdate(_event: NodeUpdateEvent, message: Message): Message {
  // Node 更新事件不需要显示，直接返回原消息
  return message;
}

/**
 * 处理 Node 结束事件 - 更新 Node 卡片状态
 */
function handleNodeEnd(event: NodeEndEvent, message: Message): Message {
  logHandler('Node handleNodeEnd: nodeId=%s status=%s', event.nodeId, event.status);
  
  const updates: Partial<Card> = {
    status: event.status,
    completedAt: event.completedAt || Date.now()
  };
  if (event.progress) updates.progress = event.progress;
  
  return updateCardById(message, event.nodeId, updates);
}

/**
 * 处理工作流完成事件 - 添加完成块
 */
function handleWorkflowComplete(message: Message): Message {
  logHandler('handleWorkflowComplete: 当前 blocks=%d', message.blocks.length);
  
  const completionBlock: CompletionBlock = {
    type: 'completion',
    id: `completion_${Date.now()}`,
    timestamp: Date.now()
  };
  
  return {
    ...message,
    blocks: [...message.blocks, completionBlock]
  };
}

/**
 * 从文件路径中提取文件名
 */
function extractFileName(path: string): string {
  if (!path) return 'Unknown Document';
  // 处理 S3 路径或本地路径
  const parts = path.split('/');
  const fileName = parts[parts.length - 1];
  // 移除查询参数
  return fileName.split('?')[0] || 'Unknown Document';
}

/**
 * 将 RAG 结果转换为 SearchResultPayload 格式
 */
function convertRAGToSearchResult(event: ToolResultEvent): SearchResultPayload {
  const structuredData = event.structured_data;
  
  logHandler('convertRAGToSearchResult: structured_data=%s chunks=%d', 
    !!structuredData, 
    structuredData?.chunks?.length || 0
  );
  
  // 如果没有结构化数据，返回空结果
  if (!structuredData || !structuredData.chunks) {
    logHandler('convertRAGToSearchResult: 无结构化数据');
    return {
      source: 'rag_search',
      timestamp: new Date().toISOString(),
    };
  }
  
  // 转换 chunks 为 SearchResultItem
  const results: SearchResultItem[] = structuredData.chunks.map((chunk: RAGChunk) => ({
    title: extractFileName(chunk.path),
    url: chunk.path,
    snippet: chunk.content.length > 300 
      ? chunk.content.substring(0, 300) + '...' 
      : chunk.content,
    score: chunk.score,
    contentType: chunk.content_type,
    page: chunk.metadata?.meta_page,
    totalPages: chunk.metadata?.meta_total_pages,
    chunkId: chunk.chunk_id,
  }));
  
  logHandler('convertRAGToSearchResult: 转换完成，results.length=%d', results.length);
  
  return {
    results,
    source: 'rag_search',
    query: structuredData.query,
    subQueries: structuredData.sub_queries,
    metadata: structuredData.metadata ? {
      totalResults: structuredData.metadata.total_results,
      returnedResults: structuredData.metadata.returned_results,
      searchTime: structuredData.metadata.search_time || structuredData.metadata.total_time,
    } : undefined,
    timestamp: new Date().toISOString(),
  };
}

/**
 * 处理 Tool Result 事件
 * 
 * 主要用于处理 planner 返回的工具调用结果，如 rag_search, web_search 等
 */
function handleToolResult(event: ToolResultEvent, message: Message): Message {
  logHandler('handleToolResult: name=%s success=%s id=%s', event.name, event.success, event.id);
  
  // 只处理搜索类工具
  if (event.name !== 'rag_search' && event.name !== 'web_search') {
    // 非搜索工具，将结果作为文本追加
    if (event.result) {
      return appendToTextBlock(message, `\n${event.result}\n`);
    }
    return message;
  }
  
  // 构建搜索结果
  const searchResult = event.name === 'rag_search' 
    ? convertRAGToSearchResult(event)
    : {
        answer: event.result,
        source: 'web_search' as const,
        timestamp: new Date().toISOString(),
      };
  
  logHandler('handleToolResult: searchResult.source=%s results.length=%d', 
    searchResult.source, 
    searchResult.results?.length || 0
  );
  
  // 查找最后一个 CUA 卡片（优先关联到已有卡片）
  let targetCuaId: string | null = null;
  for (let i = message.blocks.length - 1; i >= 0; i--) {
    const block = message.blocks[i];
    if (block.type === 'card' && block.card.type === 'cua' && !block.card.searchResult) {
      // 只关联到还没有搜索结果的 CUA 卡片
      targetCuaId = block.card.id;
      break;
    }
  }
  
  // 如果找到了没有搜索结果的 CUA 卡片，更新它
  if (targetCuaId) {
    logHandler('handleToolResult: 更新现有 CUA 卡片 %s', targetCuaId);
    return updateCardById(message, targetCuaId, {
      searchResult,
    });
  }
  
  // 否则创建一个新的 CUA 卡片来显示搜索结果
  const cardId = `search-${event.id || Date.now()}`;
  logHandler('handleToolResult: 创建新 CUA 卡片 %s', cardId);
  
  const card: Card = {
    id: cardId,
    type: 'cua',
    status: 'completed',
    title: event.name === 'rag_search' ? 'RAG Search' : 'Web Search',
    searchResult,
    startedAt: Date.now(),
    completedAt: Date.now(),
  };
  
  return addCard(message, card);
}

/**
 * 处理 Planner Complete 事件
 * 
 * 当 planner 完成一轮思考时触发，可能包含工具调用计划
 */
function handlePlannerComplete(event: PlannerCompleteEvent, message: Message): Message {
  const toolPlan = event.content?.tool_plan;
  if (!toolPlan) return message;
  
  logHandler('handlePlannerComplete: Action=%s ToolCalls=%d', 
    toolPlan.Action, 
    toolPlan.ToolCalls?.length || 0
  );
  
  // 如果有 Thinking 内容，可以追加到文本
  // 注意：这里我们选择不显示 Thinking，因为它可能会造成信息过载
  // 如果需要显示，可以取消下面的注释
  // if (toolPlan.Thinking) {
  //   message = appendToTextBlock(message, toolPlan.Thinking);
  // }
  
  return message;
}

/**
 * 处理动作完成事件（远程模式）
 * 
 * 主要用于：
 * 1. 接收 Desktop 执行操作后返回的截图
 * 2. 将截图添加到 message.screenshots 数组
 * 3. 更新对应 CUA 卡片的 screenshotIndex
 */
function handleActionCompleted(event: { type: 'action_completed'; screenshot?: string; content?: any }, message: Message): Message {
  const screenshot = event.screenshot;
  
  // 如果没有截图，直接返回
  if (!screenshot) {
    logHandler('action_completed: 无截图');
    return message;
  }
  
  const screenshots = message.screenshots || [];
  const newScreenshotIndex = screenshots.length;
  
  logHandler('action_completed: 添加截图, 索引=%d', newScreenshotIndex);
  
  // 找到最后一个 CUA 卡片（非搜索类），更新为最新截图
  let targetCuaBlockIndex = -1;
  for (let i = message.blocks.length - 1; i >= 0; i--) {
    const block = message.blocks[i];
    if (block.type === 'card' && block.card.type === 'cua' && !block.card.searchResult) {
      targetCuaBlockIndex = i;
      break;
    }
  }
  
  // 更新 blocks：为目标 CUA 卡片设置 screenshotIndex
  const updatedBlocks = message.blocks.map((block, idx) => {
    if (idx === targetCuaBlockIndex && block.type === 'card' && block.card.type === 'cua') {
      return {
        ...block,
        card: { ...block.card, screenshotIndex: newScreenshotIndex }
      };
    }
    return block;
  });
  
  return {
    ...message,
    screenshots: [...screenshots, screenshot],
    blocks: updatedBlocks,
  };
}

// ==================== 主处理函数 ====================

/**
 * 处理流式事件（纯函数版本）
 * 返回更新后的 Message
 */
export function processEvent(event: StreamEvent | ActionCompletedEvent, message: Message): Message {
  let result: Message;
  switch (event.type) {
    case 'text':
      result = handleTextEvent(event, message);
      break;
    case 'error':
      result = handleErrorEvent(event, message);
      break;
    case 'tool_start':
      result = handleToolStart(event, message);
      break;
    case 'tool_delta':
      result = handleToolDelta(event, message);
      break;
    case 'tool_end':
      result = handleToolEnd(event, message);
      break;
    case 'cua_start':
      result = handleCuaStart(event, message);
      break;
    case 'cua_delta':
      result = handleCuaDelta(event, message);
      break;
    case 'cua_update':
      result = handleCuaUpdate(event, message);
      break;
    case 'cua_end':
      result = handleCuaEnd(event, message);
      break;
    case 'node_start':
      result = handleNodeStart(event, message);
      break;
    case 'node_update':
      result = handleNodeUpdate(event, message);
      break;
    case 'node_end':
      result = handleNodeEnd(event, message);
      break;
    case 'node_complete': {
      // 后端 AI Run 可能直接下发 node_complete，与 node_end 等价，统一按 node_end 处理
      const e = event as NodeCompleteEvent;
      result = handleNodeEnd(
        {
          type: 'node_end',
          nodeId: e.nodeId ?? e.node_id ?? '',
          status: e.status ?? 'completed',
          progress: e.progress,
          completedAt: e.completedAt ?? e.completed_at,
        },
        message
      );
      break;
    }
    case 'workflow_complete':
      result = handleWorkflowComplete(message);
      break;
    case 'workflow_progress':
      // 工作流进度事件（节点切换通知）
      // 目前仅记录日志，前端不需要特殊 UI 处理
      logHandler('workflow_progress: %O', (event as WorkflowProgressEvent).content);
      result = message;
      break;
    case 'action_completed':
      // 动作完成事件（远程模式）- 可能包含截图
      result = handleActionCompleted(event as any, message);
      break;
    case 'tool_result':
      // 工具调用结果事件（planner 模式）
      result = handleToolResult(event as ToolResultEvent, message);
      break;
    case 'planner_complete':
      // Planner 完成事件
      result = handlePlannerComplete(event as PlannerCompleteEvent, message);
      break;
    default:
      result = message;
  }
  return result;
}

/**
 * 创建空的 assistant 消息
 */
export function createEmptyAssistantMessage(id: string): Message {
  return {
    id,
    role: 'assistant',
    timestamp: Date.now(),
    blocks: []
  };
}

/**
 * 检查消息是否有正在运行的卡片
 */
export function hasRunningCard(message: Message): boolean {
  return message.blocks.some(
    block => block.type === 'card' && block.card.status === 'running'
  );
}

/**
 * 获取最后一个 CUA 卡片（用于判断是否隐藏 loading）
 */
export function getLastCuaCard(message: Message): Card | null {
  for (let i = message.blocks.length - 1; i >= 0; i--) {
    const block = message.blocks[i];
    if (block.type === 'card' && block.card.type === 'cua') {
      return block.card;
    }
  }
  return null;
}







