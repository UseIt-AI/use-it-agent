import type { AutoConnectStep, ScreenConfig } from './types';

export const DEFAULT_SCREEN_CONFIG: ScreenConfig = {
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
  checking: 'Checking…',
  starting: 'Starting…',
  waiting_ip: 'Waiting for IP…',
  connecting: 'Connecting to VNC…',
  connected: 'Connected',
  error: 'Connection failed',
};
