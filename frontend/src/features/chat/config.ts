export interface AgentConfig {
  /**
   * 前端选择用的 key（历史上等同于 AgentMode）
   * - builtin: 'general' | 'excel-processor' | 'computer-use' | 'workflow' | ...
   * - dynamic workflow: 'workflow:{workflowId}'
   * - orchestrator: 'orchestrator'
   */
  id: string;
  /**
   * 统一的工作流标识：
   * - builtin agent：这里也给一个随机/自定义的 workflow_id（用于统一口径）
   * - My Workflows：workflow_id = Supabase workflows.id
   * - Orchestrator：空字符串 (orchestrator 不绑定固定 workflow)
   */
  workflow_id: string;

  label: string;
  desc: string;
  icon: any;
  color: string;
  welcomeMessage: string;

  /** backend endpoint path (without API_URL prefix) */
  endpoint: string;

  /** When true, the agent is the AI-native orchestrator (not a fixed workflow). */
  isOrchestrator?: boolean;
}

/** ID used for the built-in orchestrator agent. */
export const ORCHESTRATOR_AGENT_ID = 'orchestrator';

/**
 * 内置 Agents：包含 AI Native Orchestrator。
 */
export const BUILTIN_AGENTS: AgentConfig[] = [];

/**
 * 向后兼容：旧代码仍从 `AGENTS` 读取内置配置。
 * 动态的 My Workflow Agents 由 UI 层（下拉菜单）合并注入，不在这里静态维护。
 */
export const AGENTS = BUILTIN_AGENTS;

/**
 * AgentId 类型：所有可能的 agent id
 * - 动态 workflow 格式为 `workflow:{uuid}`
 */
export type AgentId = string;
