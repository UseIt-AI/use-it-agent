export type ConnectionType = 'local' | 'cloud';

export type AutoConnectStep =
  | 'idle'
  | 'checking'
  | 'starting'
  | 'waiting_ip'
  | 'connecting'
  | 'connected'
  | 'error';

export interface ScreenConfig {
  vmName: string;
  host: string;
  username: string;
  password: string;
  // OS 内部登录密码（例如 Windows 登录），用于自动输入
  osPassword: string;
  width: number;
  height: number;
  vncPort: number;
  wsPort: number;
}


