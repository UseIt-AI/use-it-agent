/**
 * Workflow 模块导出
 * 
 * 这是一个独立的 Feature 模块，包含：
 * - 数据类型定义
 * - API 封装
 * - 数据管理 Hooks
 * - UI 组件
 */

// ============================================
// API
// ============================================
export { workflowApi, WorkflowApiError } from './api';
export type { WorkflowChangeCallback } from './api';

// ============================================
// Types
// ============================================
export type {
  // 基础类型
  Position,
  Viewport,
  HandlePosition,
  
  // 节点类型
  NodeType,
  NodeData,
  StartNodeData,
  EndNodeData,
  ToolUseNodeData,
  BrowserUseNodeData,
  McpUseNodeData,
  
  // 节点相关
  WorkflowNode,
  Variable,
  TraceInfo,
  DetailedStep,
  StepCaption,
  TimeInfo,
  ModelConfig,
  PromptConfig,
  ContextConfig,
  VisionConfig,
  
  // 连线相关
  WorkflowEdge,
  EdgeData,
  
  // 图
  Graph,
  
  // 数据库模型
  Workflow,
  WorkflowListItem,
  PublicWorkflowListItem,
  WorkflowPublication,
  
  // Bundled assets
  BundledAsset,
  WorkflowStatus,
  
  // API 参数
  CreateWorkflowParams,
  UpdateWorkflowParams,
  UpdatePublicationParams,
  
  // 配置
  NodeConfig,
} from './types';

export {
  NODE_CONFIGS,
  DEFAULT_VIEWPORT,
  DEFAULT_GRAPH,
} from './types';

// ============================================
// Hooks (数据管理)
// ============================================
export {
  useWorkflowList,
  useWorkflow,
  useWorkflowGraph,
  useCreateWorkflow,
  useDeleteWorkflow,
  usePublicWorkflows,
} from './hooks/useWorkflow';

export { useWorkflowDiagram } from './hooks/useWorkflowDiagram';

// ============================================
// Components (UI)
// ============================================
export { default as WorkflowEditor } from './components/WorkflowEditor';
export { default as WorkflowOverview } from './components/WorkflowOverview';
export { WorkflowList } from './components/WorkflowList';
