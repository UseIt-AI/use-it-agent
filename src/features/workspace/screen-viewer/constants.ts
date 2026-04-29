import type { AutoConnectStep, ScreenConfig } from './types';

export const DEFAULT_VM_NAME = 'UseIt-Dev-VM';

export const DEFAULT_SCREEN_CONFIG: ScreenConfig = {
  vmName: DEFAULT_VM_NAME,
  host: '',
  username: '',
  password: '12345678',
  osPassword: '123456',
  width: 1280,
  height: 720,
  vncPort: 5900,
  wsPort: 16080,
};

export const STEP_LABELS: Record<AutoConnectStep, string> = {
  idle: 'Ready',
  checking: 'Checking VM status...',
  starting: 'Starting virtual machine...',
  waiting_ip: 'Waiting for IP address...',
  connecting: 'Connecting to VNC...',
  connected: 'Connected',
  error: 'Connection failed',
};


