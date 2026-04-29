/**
 * 电脑配置类型定义
 * 用于多电脑控制功能
 */

// 电脑类型
export type ComputerType = 'thispc' | 'vm' | 'physical' | 'cloud';

// 电脑状态
export type ComputerStatus = 'online' | 'offline' | 'busy';

// 电脑配置（从配置文件解析）
export interface ComputerConfig {
  name: string;                    // 唯一标识名称
  type: ComputerType;
  vmName?: string;                 // VM 类型专用：Hyper-V 虚拟机名称
  host: string;                    // IP 地址或 "auto"（VM 自动获取）
  localEnginePort: number;         // Local Engine 端口，默认 8324
  computerServerPort: number;      // Computer Server 端口，默认 8080
  username?: string;               // VM 登录用户名
  password?: string;               // VM 登录密码
  vncPort: number;                 // VNC 端口，默认 5900
  wsPort: number;                  // WebSocket 端口，默认 16080
  osPassword?: string;             // 系统登录密码
  tags: string[];                  // 标签列表
  capabilities: string[];          // 支持的能力：excel, autocad, browser
  description?: string;            // 描述信息
}

// 电脑运行时状态（带状态信息）
export interface ComputerWithStatus extends ComputerConfig {
  status: ComputerStatus;
  resolvedHost?: string;           // 解析后的实际 IP（针对 auto）
  occupiedBy?: string;             // 被哪个 session 占用
}

// Session 绑定信息
export interface SessionBinding {
  computer: string;                // 电脑名称
  boundAt: string;                 // 绑定时间 ISO 格式
  status: 'active' | 'paused' | 'completed';
}

// 电脑池状态（持久化到本地文件）
export interface ComputerPoolState {
  lastUsedComputer: string;
  sessions: Record<string, SessionBinding>;
  queue: Record<string, string[]>; // computerId -> [chatId, ...]
}

// 电脑池（配置 + 状态）
export interface ComputerPool {
  computers: ComputerWithStatus[];
  state: ComputerPoolState;
}

// This PC 的默认配置
export const THIS_PC_CONFIG: ComputerConfig = {
  name: 'This PC',
  type: 'thispc',
  host: 'localhost',
  localEnginePort: 8324,
  computerServerPort: 8080,
  vncPort: 5900,
  wsPort: 16080,
  tags: [],
  capabilities: [],
  description: '本机',
};

// 默认端口配置
export const DEFAULT_PORTS = {
  localEngine: 8324,
  computerServer: 8080,
  vnc: 5900,
  ws: 16080,
};



