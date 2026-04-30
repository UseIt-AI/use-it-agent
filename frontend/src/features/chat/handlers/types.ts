/**
 * 消息类型定义
 */

// ==================== 核心类型 ====================

/**
 * 消息 - 对话中的一条消息
 */
/**
 * 附加文件信息
 */
export interface AttachedFile {
  id: string;
  path: string;
  name: string;
  type: 'file' | 'folder';
}

/**
 * 附加图片信息（来自粘贴或上传）
 *
 * 图片会被上传到 Supabase Storage（bucket: chat-attachments），DB 只
 * 存 `storagePath` 和（可刷新的）签名 `url`。`base64` 仅在发送当下
 * 作为本次 HTTP 请求 body 附带给后端使用，不再持久化；从历史加载
 * 恢复的 AttachedImage 通常只有 `url` / `storagePath`。
 */
export interface AttachedImage {
  id: string;
  name: string;
  mimeType: string;
  size: number;
  /** data URI / 纯 base64；仅 "本次发送" 时携带，不会写回 DB。 */
  base64?: string;
  /** Signed URL（24h），用于 UI 展示与后端回灌下载。 */
  url?: string;
  /** Storage object path，用于重新签名 / service-role 下载。 */
  storagePath?: string;
  /** Signed URL 过期的 epoch ms（用于判断是否需要 re-sign）。 */
  urlExpiresAt?: number;
}

export interface Message {
  id: string;                    // 消息唯一 ID
  role: 'user' | 'assistant';    // 消息角色
  timestamp: number;             // 时间戳
  
  // ===== 核心：内容块数组（保持顺序）=====
  blocks: ContentBlock[];        // 文本和卡片交替出现，保持顺序
  
  // ===== 辅助数据 =====
  screenshots?: string[];        // CUA 截图（base64 数组）
  attachedFiles?: AttachedFile[]; // 用户消息附加的文件/文件夹
  attachedImages?: AttachedImage[]; // 用户消息附加的图片（粘贴或上传）
  
  // ===== 兼容旧版本 =====
  content?: string;              // 兼容旧版本的纯文本内容
  details?: any;                 // 兼容旧版本的详情数据
}

/**
 * 内容块：文本、卡片、完成块或"问用户"块
 */
export type ContentBlock = TextBlock | CardBlock | CompletionBlock | AskUserBlock;

/**
 * Inline "ask_user" 块 - 在对话流里渲染的问答卡片
 *
 * 契约来自 Orchestrator 的 `ask_user` tool_call (target === 'user')。
 * 用户回答后，本块的 status/answer 会被原地更新，从而成为聊天历史的一部分，
 * 跟代码助手的 "agent 提问 + 用户回答" 一样沉淀在时间线上。
 */
export interface AskUserBlock {
  type: 'ask_user';
  /** tool_call.id — 作为回调关联 key 和 resolver key。 */
  toolCallId: string;
  /** 对话框参数（prompt / kind / options / timeout 等）。 */
  args: import('./localEngine/types').AskUserArgs;
  /** 当前状态：等待中 / 已回答 / 已取消（Esc/超时）。 */
  status: 'pending' | 'answered' | 'dismissed';
  /** 用户最终提交的答复；status !== 'pending' 时填充。 */
  answer?: import('./localEngine/types').AskUserResponse;
  /** 块被创建的时间戳，用于倒计时基准。 */
  startedAt: number;
}

/**
 * 完成块 - 工作流完成后显示
 */
export interface CompletionBlock {
  type: 'completion';
  id: string;                    // 唯一 ID
  timestamp: number;             // 完成时间戳
  feedback?: 'like' | 'dislike'; // 用户反馈
}

/**
 * 文本块
 */
export interface TextBlock {
  type: 'text';
  content: string;               // Markdown 文本
}

/**
 * 卡片块
 */
export interface CardBlock {
  type: 'card';
  card: Card;                    // 卡片数据
}

/**
 * 统一卡片类型
 */
export interface Card {
  id: string;                    // 卡片唯一 ID
  type: 'tool' | 'cua' | 'node'; // 卡片类型
  status: 'pending' | 'running' | 'completed' | 'failed' | 'cancelled';
  title: string;                 // 显示标题
  
  // ===== 通用字段 =====
  content?: string;              // 描述或结果摘要
  startedAt?: number;            // 开始时间戳
  completedAt?: number;          // 完成时间戳
  
  // ===== Tool 特有字段 =====
  toolName?: string;             // 工具名称（如 'modify_design'）
  input?: Record<string, any>;   // 输入参数
  output?: string;               // 执行结果
  reasoning?: string;            // LLM 思考过程（Markdown） - 可能会被格式化
  rawReasoning?: string;         // 原始 LLM 思考过程（用于流式追加）
  duration?: number;             // 执行耗时（秒）
  
  // ===== CUA 特有字段 =====
  step?: number;                 // CUA 步骤序号
  action?: CUAAction;            // 执行的动作
  screenshotIndex?: number;      // 对应 screenshots 数组的索引
  searchProgress?: SearchProgressPayload; // 搜索进度（结构化）
  searchResult?: SearchResultPayload;     // 搜索结果（结构化）
  extractProgress?: ExtractProgressPayload; // 文档提取进度（结构化）
  
  // ===== Node 特有字段（Workflow 模式）=====
  nodeType?: string;             // 节点类型（如 'computer-use', 'computer-use-word' 等）
  instruction?: string;          // Node 的任务说明
  progress?: NodeProgress;       // 进度信息
  
  // ===== 关联字段 =====
  nodeId?: string;               // 所属 Node ID（Tool/CUA 卡片用）
  
  // ===== 错误信息 =====
  error?: string;                // 执行失败时的错误信息
}

/**
 * CUA 动作
 */
export interface CUAAction {
  type: 'click' | 'type' | 'key' | 'scroll' | 'screenshot' | 'wait';
  x?: number;
  y?: number;
  text?: string;
  key?: string;
}

/**
 * Node 进度
 */
export interface NodeProgress {
  current: number;               // 当前步骤（从 1 开始）
  total?: number;                // 总步骤数（可选）
  message?: string;              // 进度描述
}

// ==================== 事件类型 ====================

/**
 * 文本增量事件
 */
export interface TextEvent {
  type: 'text';
  delta: string;
}

/**
 * 错误事件
 */
export interface ErrorEvent {
  type: 'error';
  message: string;
  code?: string;
}

/**
 * 客户端请求事件
 */
export interface ClientRequestEvent {
  type: 'client_request';
  requestId: string;
  action: 'screenshot' | 'execute' | 'screen_info';
  params?: any;
}

/**
 * Tool 开始事件
 */
export interface ToolStartEvent {
  type: 'tool_start';
  toolId: string;
  title: string;
  toolName: string;
  input?: Record<string, any>;
  nodeId?: string;
}

/**
 * Tool 增量事件
 */
export interface ToolDeltaEvent {
  type: 'tool_delta';
  toolId: string;
  reasoning: string;
}

/**
 * Tool 结束事件
 */
export interface ToolEndEvent {
  type: 'tool_end';
  toolId: string;
  status: 'completed' | 'failed';
  output?: string;
  duration?: number;
}

/**
 * CUA 开始事件
 */
export interface CuaStartEvent {
  type: 'cua_start';
  cuaId: string;
  step: number;
  title: string;
  screenshotIndex?: number;
  nodeId?: string;
}

/**
 * CUA 思考过程增量事件 (Planner/Actor reasoning)
 */
export interface CuaDeltaEvent {
  type: 'cua_delta';
  cuaId: string;
  reasoning: string;      // 思考过程，追加到 card.reasoning
  kind: 'planner' | 'actor' | 'search_progress' | 'search_result' | 'extract_progress';
  payload?: SearchProgressPayload | SearchResultPayload | ExtractProgressPayload;
}

/**
 * CUA 动作内容更新事件 (Actor action)
 */
export interface CuaUpdateEvent {
  type: 'cua_update';
  cuaId: string;
  content: any;           // 动作内容，更新 card.content
  kind: 'actor';
}

/**
 * CUA 结束事件
 */
export interface CuaEndEvent {
  type: 'cua_end';
  cuaId: string;
  status: 'completed' | 'failed';
  title?: string;
  action?: CUAAction;
}

/**
 * CUA 请求事件（纯透传给 Local Engine）
 */
export interface CuaRequestEvent {
  type: 'cua_request';
  cuaId: string;
  requestId: string;
  requestType: string;
  params: Record<string, any>;
  timeout?: number;
}

/**
 * Node 开始事件
 */
export interface NodeStartEvent {
  type: 'node_start';
  nodeId: string;
  title: string;
  nodeType: string;      // 节点类型（如 'computer-use', 'computer-use-word', 'tool-use' 等）
  instruction?: string;  // Node 的任务说明
  progress?: NodeProgress;
  startedAt?: number;    // 开始时间戳
}

/**
 * Node 更新事件
 */
export interface NodeUpdateEvent {
  type: 'node_update';
  nodeId: string;
  progress: NodeProgress;
}

/**
 * Node 结束事件
 */
export interface NodeEndEvent {
  type: 'node_end';
  nodeId: string;
  status: 'completed' | 'failed';
  progress?: NodeProgress;
  completedAt?: number;  // 完成时间戳
}

/**
 * Node 完成事件（后端 AI Run 可能直接下发，与 node_end 等价）
 */
export interface NodeCompleteEvent {
  type: 'node_complete';
  nodeId?: string;
  node_id?: string;
  status?: 'completed' | 'failed';
  progress?: NodeProgress;
  completedAt?: number;
  completed_at?: number;
}

/**
 * 工作流完成事件
 */
export interface WorkflowCompleteEvent {
  type: 'workflow_complete';
}

/**
 * 工作流进度事件（节点切换通知）
 */
export interface WorkflowProgressEvent {
  type: 'workflow_progress';
  content: {
    next_node_id: string;
    is_workflow_completed: boolean;
  };
}

/**
 * 动作完成事件（远程模式截图回传）
 */
export interface ActionCompletedEvent {
  type: 'action_completed';
  screenshot?: string;
  content?: any;
}

/**
 * Extract progress payload (doc_extract 文档提取进度)
 */
export interface ExtractProgressPayload {
  stage: string;                 // 阶段：init, open_document, process_page, extract_captions, extract_elements, find_figures, find_tables, render_figures, render_tables, generate_markdown, complete
  message: string;               // 进度描述
  percentage: number;            // 百分比 0-100
  current_page: number;          // 当前页码
  total_pages: number;           // 总页数
  current_figure: number;        // 当前图表序号
  total_figures: number;         // 总图表数
}

/**
 * Search progress payload
 */
export interface SearchQueryProgress {
  query: string;
  status: 'pending' | 'searching' | 'done' | 'error' | string;
  results_count?: number;
}

export interface SearchProgressPayload {
  stage?: string;
  message?: string;
  queries?: SearchQueryProgress[];
  current_query?: string | null;
  total_results?: number;
  elapsed_time?: number;
}

/**
 * Search result payload
 */
export interface SearchResultItem {
  title: string;
  url: string;
  snippet?: string;
  score?: number;
  // RAG 特有字段
  contentType?: string;    // pdf, txt, docx 等文档类型
  page?: number;           // 页码
  totalPages?: number;     // 总页数
  chunkId?: string;        // chunk ID
}

export interface SearchResultPayload {
  answer?: string;
  results?: SearchResultItem[];
  source?: 'web_search' | 'rag_search' | string;  // 搜索来源
  timestamp?: string;
  // RAG 特有字段
  query?: string;          // 搜索查询
  subQueries?: string[];   // 子查询列表
  metadata?: {
    totalResults?: number;
    returnedResults?: number;
    searchTime?: number;
  };
}

/**
 * Tool Result 事件
 */
export interface ToolResultEvent {
  type: 'tool_result';
  id: string;              // tool call ID
  name: string;            // 工具名称 (rag_search, web_search 等)
  result: string;          // 格式化的结果文本
  success: boolean;
  error?: string | null;
  structured_data?: {
    result_type: string;
    query?: string;
    sub_queries?: string[];
    chunks?: RAGChunk[];
    metadata?: {
      total_results?: number;
      returned_results?: number;
      search_time?: number;
      total_time?: number;
    };
  };
}

/**
 * RAG Chunk 结构
 */
export interface RAGChunk {
  chunk_id: string;
  content: string;
  score: number;
  path: string;
  content_type: string;
  metadata?: {
    meta_page?: number;
    meta_total_pages?: number;
    meta_source_type?: string;
    [key: string]: any;
  };
}

/**
 * Planner Complete 事件
 */
export interface PlannerCompleteEvent {
  type: 'planner_complete';
  content: {
    tool_plan: {
      Thinking?: string;
      Action?: string;
      Title?: string;
      ToolCalls?: Array<{
        id: string;
        name: string;
        args: Record<string, any>;
      }>;
      MilestoneCompleted?: boolean;
      Observation?: string;
      Reasoning?: string;
    };
  };
}

/**
 * 所有流式事件的联合类型
 */
export type StreamEvent =
  | TextEvent
  | ErrorEvent
  | ClientRequestEvent
  | ToolStartEvent
  | ToolDeltaEvent
  | ToolEndEvent
  | CuaStartEvent
  | CuaDeltaEvent
  | CuaUpdateEvent
  | CuaRequestEvent
  | CuaEndEvent
  | NodeStartEvent
  | NodeUpdateEvent
  | NodeEndEvent
  | NodeCompleteEvent
  | WorkflowCompleteEvent
  | WorkflowProgressEvent
  | ActionCompletedEvent
  | ToolResultEvent
  | PlannerCompleteEvent;

// ==================== Handler 上下文 ====================

export interface CommandHandlerContext {
  botMessageId: string;
  setMessages: React.Dispatch<React.SetStateAction<Message[]>>;
  localEngineUrl: string;
  
  // ===== 动态 URL 获取（用于 VM IP 可能变化的场景）=====
  // 如果提供了 computerName，执行命令前会刷新获取最新 IP
  computerName?: string;
  getLocalEngineUrlFresh?: () => Promise<string>;
  
  // ===== 项目相关 =====
  projectPath?: string;  // 项目路径，用于 snapshot/screenshot 时附带项目文件列表
  
  // ===== 持久化相关 =====
  userId?: string;
  chatId?: string;
  workflowRunId?: string;
  
  // 当前 Node 的 run_nodes.id（用于关联 node_actions）
  currentRunNodeId?: string;
  setCurrentRunNodeId?: (id: string | undefined) => void;
}

// ==================== 兼容旧版本的类型 ====================

export interface CommandEvent {
  type: string;
  command?: string;
  data?: any;
  content?: string;
}
