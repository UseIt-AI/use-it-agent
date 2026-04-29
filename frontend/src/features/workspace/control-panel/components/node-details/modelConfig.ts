import type { MenuOption } from './InlineMenuSelect';

export const AGENT_MODELS: MenuOption[] = [
  { value: 'gemini-3.1-pro-preview', label: 'Gemini 3 Pro' },
  { value: 'gemini-3-flash-preview', label: 'Gemini 3 Flash', recommended: true },
  { value: 'gpt-5.4', label: 'GPT-5.4' },
  { value: 'gpt-5.3-codex', label: 'GPT-5.3 Codex' },
  { value: 'claude-opus-4-6', label: 'Claude Opus 4.6' },
  { value: 'claude-opus-4-7', label: 'Claude Opus 4.7' },
  { value: 'claude-sonnet-4-6', label: 'Claude Sonnet 4.6' },
  // { value: 'glm-5', label: 'GLM-5' },
  // { value: 'kimi-k2.5', label: 'Kimi K2.5' },
  // { value: 'qwen3.5-27b', label: 'Qwen3.5 27B (reasoning)' },
];

export const DEFAULT_MODEL = 'gemini-3-flash-preview';

/** Agent 节点（orchestrator）：与后台 `data.model` / `AgentNodeHandler._resolve_model` 一致
 * 暂时仅保留 Lite；UseIt High 先下线 */
export const ORCHESTRATOR_AGENT_MODELS: MenuOption[] = [
  { value: 'gemini-3-flash-preview', label: 'Lite', recommended: true },
];

export const ORCHESTRATOR_AGENT_DEFAULT_MODEL = 'gemini-3-flash-preview';
