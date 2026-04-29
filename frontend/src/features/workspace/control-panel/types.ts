export type ControlTab = 'workflow';

export interface DesktopConnection {
  id: string;
  name: string;
}

// Agent 可操控的目标类型（当前仅本机）
export type AgentTargetType = 'local';

export interface AgentTarget {
  id: string;
  type: AgentTargetType;
  name: string;
  deletable?: boolean;
  available: boolean;
}



