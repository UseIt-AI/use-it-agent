export type ControlTab = 'vm' | 'workflow';

export interface DesktopConnection {
  id: string;
  name: string;
}

// Agent 可操控的目标类型
export type AgentTargetType = 'local' | 'vm';

export interface AgentTarget {
  id: string;
  type: AgentTargetType;
  name: string;
  // VM 的真实 Hyper-V 名称（用于 ScreenViewer / Hyper-V API）
  // 对于 local 环境可为空
  vmName?: string;
  // 是否允许删除（This PC 永远不可删除）
  deletable?: boolean;
  available: boolean;  // 是否可用（VM 需要检测）
  status?: 'running' | 'off' | 'unknown';  // VM 状态
}



