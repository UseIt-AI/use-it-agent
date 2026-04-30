/**
 * 工作流单次运行中的节点与动作（与是否使用云端存储无关）
 */

export interface RunNode {
  id: string;
  run_id: string;
  node_id: string;
  node_type: 'computer-use' | 'tool' | 'rag' | 'export' | 'llm' | 'general';
  title?: string;
  instruction?: string;
  step_index: number;
  status: 'pending' | 'running' | 'completed' | 'failed' | 'skipped';
  reasoning?: string;
  output?: string;
  progress_current?: number;
  progress_total?: number;
  progress_message?: string;
  error_message?: string;
  tokens_used?: number;
  started_at?: string;
  completed_at?: string;
}

export interface NodeAction {
  id: string;
  node_id: string;
  action_type: 'cua_step' | 'tool_call' | 'llm_thought';
  step_index: number;
  status: 'pending' | 'running' | 'completed' | 'failed';
  title?: string;
  reasoning?: string;
  content?: string;
  input?: Record<string, any>;
  output?: Record<string, any>;
  error_message?: string;
  duration_ms?: number;
  screenshot_url?: string;
  screenshot_path?: string;
  screenshot_expires_at?: number;
  action_detail?: {
    type: 'click' | 'type' | 'key' | 'scroll' | 'screenshot' | 'wait';
    x?: number;
    y?: number;
    text?: string;
    key?: string;
  };
  tool_name?: string;
  started_at?: string;
  completed_at?: string;
}
