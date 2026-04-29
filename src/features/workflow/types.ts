/**
 * Workflow 编排系统类型定义
 * 
 * 兼容 React Flow 数据结构
 */

// ==================== 基础类型 ====================

export interface Position {
  x: number;
  y: number;
}

export interface Viewport {
  x: number;
  y: number;
  zoom: number;
}

export type HandlePosition = 'left' | 'right' | 'top' | 'bottom';

// ==================== 节点类型 ====================

export type NodeType =
  | 'start'
  | 'end'
  | 'tool-use'
  | 'computer-use'
  | 'computer-use-gui'
  | 'computer-use-browser'
  | 'computer-use-excel'
  | 'computer-use-word'
  | 'computer-use-powerpoint'
  | 'computer-use-ppt'
  | 'browser-use'
  | 'human-in-the-loop'
  | 'code-use'
  | 'if-else'
  | 'loop'
  | 'loop-start'
  | 'loop-end'
  | 'mcp-use'
  | 'agent';

// ==================== 追踪信息 ====================

export interface TraceInfo {
  user_id: string | null;
  trace_id: string | null;
  instruction: string;
  video_url: string;
  video_url_externel: string;
  cover_img: string;
}

// ==================== Step / Trace 相关 ====================

export interface StepCaption {
  screen_language: string;
  observation_action_before: string;
  observation_action_after: string;
  think: string;
  action: string;
  expectation: string;
}

export interface TimeInfo {
  start_time: number;
  end_time: number;
  current_action_trigger_timestamp: number;
  next_action_trigger_timestamp: number;
  last_action_trigger_timestamp: number;
}

export interface DetailedStep {
  step_idx: number;
  milestone_step_idx: number;
  caption: StepCaption;
  time_info: TimeInfo;
  icon_info?: any[];
}

export interface ModelConfig {
  provider: string;
  name: string;
  mode: string;
  completion_params: Record<string, any>;
}

export interface PromptConfig {
  jinja2_variables: {
    name: string;
    value: string;
  }[];
}

export interface ContextConfig {
  enabled: boolean;
  variable_selector: any[];
}

export interface VisionConfig {
  enabled: boolean;
}

// ==================== 节点数据类型 ====================

export interface Variable {
  name: string;
  type: 'string' | 'number' | 'boolean' | 'object';
  default?: any;
  required?: boolean;
}

// 基础节点数据
interface NodeDataBase {
  type: NodeType;
  title: string;
  desc?: string;
  selected: boolean;
  trace_info?: TraceInfo;
  skills?: string[];
}

// Start 节点
export interface StartNodeData extends NodeDataBase {
  type: 'start';
  variables?: Variable[];
}

// End 节点
export interface EndNodeData extends NodeDataBase {
  type: 'end';
  outputs?: any[];
}

// MCP Use 节点
export interface McpUseNodeData extends NodeDataBase {
  type: 'mcp-use';
  instruction?: string;
  mcp_server_name?: string;
  mcp_function_info?: string;
}

// Agent 节点（orchestrator / AgentNodeHandler 后端）
export interface AgentNodeData extends NodeDataBase {
  type: 'agent';
  instruction?: string;
  /**
   * Whitelist of tool packs the agent may use.
   * Allowed values: 'gui' | 'browser' | 'excel' | 'word' | 'ppt' | 'autocad' | 'code'.
   * Empty / undefined means no whitelist (all permitted tools are available).
   */
  groups?: string[];
  model?: string;
}

// If-Else 节点（轻量占位，后续可扩展为条件分支结构）
export interface IfElseNodeData extends NodeDataBase {
  type: 'if-else';
  conditions?: Array<{
    label: string;
    expression: string;
  }>;
}

// Loop 节点（轻量占位，后续可扩展为循环配置）
export interface LoopNodeData extends NodeDataBase {
  type: 'loop';
  max_iterations?: number;
}

export interface LoopStartNodeData extends NodeDataBase {
  type: 'loop-start';
}

export interface LoopEndNodeData extends NodeDataBase {
  type: 'loop-end';
}

// Tool Use 节点
export interface ToolUseNodeData extends NodeDataBase {
  type: 'tool-use';
  instruction?: string;
  model?: string;
  tools?: string[];
  /**
   * Per-tool settings for tools enabled on this LLM node.
   * Example:
   * {
   *   web_search: { instructions: "..." },
   *   mcp: { ... }
   * }
   */
  toolSettings?: Record<string, any>;
  outputFormat?: 'text' | 'json' | 'markdown';
}

// Computer Use Action Type
export type ComputerUseActionType = 'gui' | 'autocad' | 'excel' | 'word' | 'ppt';

// Computer Use 节点（轻量占位）
export interface ComputerUseNodeData extends NodeDataBase {
  type: 'computer-use';
  instruction?: string;
  task_tips?: string;
  model?: string;
  /** Action type for specialized AI processors */
  action_type?: ComputerUseActionType;
  /** Optional parsed steps from recording / analyzer */
  steps?: string[];
  /** Optional detailed steps (same shape as GUI milestone) */
  detailed_steps?: DetailedStep[];
  /** Cover image URL for this node */
  cover_img?: string;
}

// Computer Use GUI 节点
export interface ComputerUseGuiNodeData extends NodeDataBase {
  type: 'computer-use-gui';
  instruction?: string;
  task_tips?: string;
  model?: string;
  steps?: string[];
  detailed_steps?: DetailedStep[];
  cover_img?: string;
}

// Computer Use Browser 节点
export interface ComputerUseBrowserNodeData extends NodeDataBase {
  type: 'computer-use-browser';
  instruction?: string;
  task_tips?: string;
  model?: string;
  steps?: string[];
  detailed_steps?: DetailedStep[];
  cover_img?: string;
}

// Computer Use Excel 节点
export interface ComputerUseExcelNodeData extends NodeDataBase {
  type: 'computer-use-excel';
  instruction?: string;
  task_tips?: string;
  model?: string;
  steps?: string[];
  detailed_steps?: DetailedStep[];
  cover_img?: string;
}

// Computer Use Word 节点
export interface ComputerUseWordNodeData extends NodeDataBase {
  type: 'computer-use-word';
  instruction?: string;
  task_tips?: string;
  model?: string;
  steps?: string[];
  detailed_steps?: DetailedStep[];
  cover_img?: string;
}

// Computer Use PowerPoint 节点
export interface ComputerUsePowerPointNodeData extends NodeDataBase {
  type: 'computer-use-powerpoint';
  instruction?: string;
  task_tips?: string;
  model?: string;
  steps?: string[];
  detailed_steps?: DetailedStep[];
  cover_img?: string;
}

// Computer Use PPT 节点 (PowerPoint 别名)
export interface ComputerUsePptNodeData extends NodeDataBase {
  type: 'computer-use-ppt';
  instruction?: string;
  task_tips?: string;
  model?: string;
  steps?: string[];
  detailed_steps?: DetailedStep[];
  cover_img?: string;
}

// Browser Use 节点（轻量占位）
export interface BrowserUseNodeData extends NodeDataBase {
  type: 'browser-use';
  instruction?: string;
}

// Human in the Loop 节点（轻量占位）
export interface HumanInTheLoopNodeData extends NodeDataBase {
  type: 'human-in-the-loop';
  instruction?: string;
}

// Code Use 节点（轻量占位）
export interface CodeUseNodeData extends NodeDataBase {
  type: 'code-use';
  instruction?: string;
}

// 联合类型
export type NodeData =
  | StartNodeData
  | EndNodeData
  | ToolUseNodeData
  | ComputerUseNodeData
  | ComputerUseGuiNodeData
  | ComputerUseBrowserNodeData
  | ComputerUseExcelNodeData
  | ComputerUseWordNodeData
  | ComputerUsePowerPointNodeData
  | ComputerUsePptNodeData
  | BrowserUseNodeData
  | HumanInTheLoopNodeData
  | CodeUseNodeData
  | IfElseNodeData
  | LoopNodeData
  | LoopStartNodeData
  | LoopEndNodeData
  | McpUseNodeData
  | AgentNodeData;

// ==================== React Flow 节点 ====================

export interface WorkflowNode {
  id: string;
  type: 'custom';
  data: NodeData;
  position: Position;
  positionAbsolute: Position;
  targetPosition?: HandlePosition;
  sourcePosition?: HandlePosition;
  width?: number;
  height?: number;
  style?: React.CSSProperties;
  selected: boolean;
  selectable?: boolean;
  draggable?: boolean;
  parentNode?: string;
  extent?: 'parent' | 'coordinate' | { x: number; y: number; width: number; height: number };
}

// ==================== React Flow 连线 ====================

export interface EdgeData {
  sourceType: NodeType;
  targetType?: NodeType;
  isInLoop: boolean;
  isInIteration?: boolean;
}

export interface WorkflowEdge {
  id: string;
  type: 'custom';
  source: string;
  target: string;
  sourceHandle: string;
  targetHandle: string;
  data: EdgeData;
  zIndex: number;
}

// ==================== Graph 根对象 ====================

export interface Graph {
  nodes: WorkflowNode[];
  edges: WorkflowEdge[];
  viewport: Viewport;
}

// ==================== Bundled Assets ====================

export interface BundledAsset {
  s3_key: string;
  filename: string;
  relative_path: string;
  size_bytes: number;
  content_type: string;
}

// ==================== 数据库模型 ====================

export type WorkflowStatus = 'draft' | 'pending' | 'published' | 'archived';

export interface Workflow {
  id: string;
  owner_id: string;
  name: string;
  description: string | null;
  version: string;
  definition: Graph;
  is_public: boolean;
  created_at: string;
  updated_at: string;
  /** Quick start messages shown in chat when no messages exist */
  quick_start_messages?: string[];
}

/** Publication metadata stored in workflow_publications table */
export interface WorkflowPublication {
  workflow_id: string;
  status: WorkflowStatus;
  is_featured: boolean;
  featured_at: string | null;
  sort_order: number;
  category: string | null;
  tags: string[];
  icon: string | null;
  cover_url: string | null;
  fork_count: number;
  run_count: number;
  bundled_skills: BundledAsset[];
  example_files: BundledAsset[];
  created_at: string;
  updated_at: string;
}

/** Minimal item for the user's own workflow list (My Workflows) */
export interface WorkflowListItem {
  id: string;
  name: string;
  description: string | null;
  updated_at: string;
  is_public: boolean;
}

/** Extended item for public/featured workflows (includes flattened publication data) */
export interface PublicWorkflowListItem extends WorkflowListItem {
  status: WorkflowStatus;
  is_featured: boolean;
  sort_order: number;
  category: string | null;
  tags: string[];
  icon: string | null;
  cover_url: string | null;
  fork_count: number;
  run_count: number;
  bundled_skills?: BundledAsset[];
  example_files?: BundledAsset[];
  quick_start_messages?: string[];
}

// ==================== API 请求/响应类型 ====================

export interface CreateWorkflowParams {
  name: string;
  description?: string;
  definition?: Graph;
  /** Copied when forking/duplicating; omit for blank new workflows */
  quick_start_messages?: string[] | null;
}

export interface UpdateWorkflowParams {
  name?: string;
  description?: string;
  definition?: Graph;
  is_public?: boolean;
  quick_start_messages?: string[];
}

export interface UpdatePublicationParams {
  status?: WorkflowStatus;
  category?: string | null;
  tags?: string[];
  icon?: string | null;
  cover_url?: string | null;
  bundled_skills?: BundledAsset[];
  example_files?: BundledAsset[];
}

// ==================== 节点配置 ====================

export interface NodeConfig {
  type: NodeType;
  defaultTitle: string;
  color: string;
  icon: string;
  defaultWidth: number;
  defaultHeight: number;
  definition?: string;
}

export const NODE_CONFIGS: Record<NodeType, NodeConfig> = {
  'start': {
    type: 'start',
    defaultTitle: 'Start',
    color: '#22c55e',
    icon: 'PlayCircle',
    defaultWidth: 240,
    defaultHeight: 48,
    definition: 'Define the input of the workflow',
  },
  'end': {
    type: 'end',
    defaultTitle: 'End',
    color: '#ef4444',
    icon: 'StopCircle',
    defaultWidth: 240,
    defaultHeight: 48,
    definition: 'Return the output of the workflow',
  },
  'tool-use': {
    type: 'tool-use',
    defaultTitle: 'Tool Use',
    color: '#a855f7',
    icon: 'Sparkles',
    defaultWidth: 240,
    defaultHeight: 160,
    definition: 'Invoke Large Language Model',
  },
  'computer-use': {
    type: 'computer-use',
    defaultTitle: 'Computer Use',
    color: '#0ea5e9',
    icon: 'MousePointer2',
    defaultWidth: 240,
    defaultHeight: 160,
    definition: 'Control computer via screenshots',
  },
  'computer-use-gui': {
    type: 'computer-use-gui',
    defaultTitle: 'Computer Use (GUI)',
    color: '#0ea5e9',
    icon: 'MousePointer2',
    defaultWidth: 240,
    defaultHeight: 160,
    definition: 'Control GUI applications',
  },
  'computer-use-browser': {
    type: 'computer-use-browser',
    defaultTitle: 'Computer Use (Browser)',
    color: '#0ea5e9',
    icon: 'Globe',
    defaultWidth: 240,
    defaultHeight: 160,
    definition: 'Control browser applications',
  },
  'computer-use-excel': {
    type: 'computer-use-excel',
    defaultTitle: 'Computer Use (Excel)',
    color: '#0ea5e9',
    icon: 'Table',
    defaultWidth: 240,
    defaultHeight: 160,
    definition: 'Control Excel applications',
  },
  'computer-use-word': {
    type: 'computer-use-word',
    defaultTitle: 'Computer Use (Word)',
    color: '#0ea5e9',
    icon: 'FileText',
    defaultWidth: 240,
    defaultHeight: 160,
    definition: 'Control Word applications',
  },
  'computer-use-powerpoint': {
    type: 'computer-use-powerpoint',
    defaultTitle: 'Computer Use (PowerPoint)',
    color: '#0ea5e9',
    icon: 'Presentation',
    defaultWidth: 240,
    defaultHeight: 160,
    definition: 'Control PowerPoint applications',
  },
  'computer-use-ppt': {
    type: 'computer-use-ppt',
    defaultTitle: 'Computer Use (PPT)',
    color: '#0ea5e9',
    icon: 'Presentation',
    defaultWidth: 240,
    defaultHeight: 160,
    definition: 'Control PPT applications',
  },
  'browser-use': {
    type: 'browser-use',
    defaultTitle: 'Browser Use',
    color: '#22c55e',
    icon: 'PanelTop',
    defaultWidth: 240,
    defaultHeight: 160,
    definition: 'Use browser to explore information',
  },
  'human-in-the-loop': {
    type: 'human-in-the-loop',
    defaultTitle: 'Human in the Loop',
    color: '#f59e0b',
    icon: 'UserCheck',
    defaultWidth: 240,
    defaultHeight: 160,
    definition: 'Pause for human verification',
  },
  'code-use': {
    type: 'code-use',
    defaultTitle: 'Code Use',
    color: '#6366f1',
    icon: 'Code',
    defaultWidth: 240,
    defaultHeight: 160,
    definition: 'Execute custom code',
  },
  'if-else': {
    type: 'if-else',
    defaultTitle: 'IF / ELSE',
    color: '#64748b',
    icon: 'Split',
    defaultWidth: 240,
    defaultHeight: 140,
    definition: 'Conditional branching',
  },
  'loop': {
    type: 'loop',
    defaultTitle: 'Loop',
    color: '#64748b',
    icon: 'Infinity',
    defaultWidth: 800,
    defaultHeight: 400,
    definition: 'Iterate over items',
  },
  'loop-start': {
    type: 'loop-start',
    defaultTitle: 'Start',
    color: '#22c55e',
    icon: 'PlayCircle',
    defaultWidth: 100,
    defaultHeight: 48,
    definition: 'Loop start point',
  },
  'loop-end': {
    type: 'loop-end',
    defaultTitle: 'End',
    color: '#3b82f6',
    icon: 'StopCircle',
    defaultWidth: 100,
    defaultHeight: 48,
    definition: 'Loop end point',
  },
  'mcp-use': {
    type: 'mcp-use',
    defaultTitle: 'MCP Use',
    color: '#f97316',
    icon: 'Cpu',
    defaultWidth: 240,
    defaultHeight: 301,
    definition: 'Execute MCP tools',
  },
  'agent': {
    type: 'agent',
    defaultTitle: 'Agent',
    color: '#f59e0b',
    icon: 'Orbit',
    defaultWidth: 240,
    defaultHeight: 160,
    definition: 'Autonomous AI agent (orchestrator loop)',
  },
};

// ==================== 默认值 ====================

export const DEFAULT_VIEWPORT: Viewport = {
  x: 0,
  y: 0,
  zoom: 1,
};

export const DEFAULT_GRAPH: Graph = {
  nodes: [],
  edges: [],
  viewport: DEFAULT_VIEWPORT,
};

// ==================== 工具函数类型 ====================

export type NodeDataByType<T extends NodeType> =
  T extends 'start' ? StartNodeData :
  T extends 'end' ? EndNodeData :
  T extends 'tool-use' ? ToolUseNodeData :
  T extends 'computer-use' ? ComputerUseNodeData :
  T extends 'computer-use-gui' ? ComputerUseGuiNodeData :
  T extends 'computer-use-browser' ? ComputerUseBrowserNodeData :
  T extends 'computer-use-excel' ? ComputerUseExcelNodeData :
  T extends 'computer-use-word' ? ComputerUseWordNodeData :
  T extends 'computer-use-powerpoint' ? ComputerUsePowerPointNodeData :
  T extends 'computer-use-ppt' ? ComputerUsePptNodeData :
  T extends 'browser-use' ? BrowserUseNodeData :
  T extends 'human-in-the-loop' ? HumanInTheLoopNodeData :
  T extends 'code-use' ? CodeUseNodeData :
  T extends 'if-else' ? IfElseNodeData :
  T extends 'loop' ? LoopNodeData :
  T extends 'loop-start' ? LoopStartNodeData :
  T extends 'loop-end' ? LoopEndNodeData :
  T extends 'mcp-use' ? McpUseNodeData :
  T extends 'agent' ? AgentNodeData :
  never;

