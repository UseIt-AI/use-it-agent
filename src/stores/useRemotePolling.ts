/**
 * 远程轮询状态管理
 * 
 * 用于控制远程任务轮询的开启/关闭
 */
import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import { remoteTaskPoller } from '../services/remoteTaskPoller';
import { REMOTE_CONTROL_ENABLED } from '@/config/runtimeEnv';

interface RemotePollingStore {
  // 是否启用远程轮询
  enabled: boolean;
  // 当前是否正在轮询（运行时状态）
  isPolling: boolean;
  // 当前用户 ID
  userId: string | null;

  // Actions
  setEnabled: (enabled: boolean) => void;
  toggle: () => void;
  
  // 内部方法：启动/停止轮询
  startPolling: (userId: string) => void;
  stopPolling: () => void;
}

export const useRemotePolling = create<RemotePollingStore>()(
  persist(
    (set, get) => ({
      enabled: true, // 默认开启
      isPolling: false,
      userId: null,

      setEnabled: (enabled) => {
        const { userId, isPolling } = get();
        set({ enabled });
        
        if (enabled && userId && !isPolling) {
          // 开启轮询
          remoteTaskPoller.start(userId);
          set({ isPolling: true });
        } else if (!enabled && isPolling) {
          // 关闭轮询
          remoteTaskPoller.stop();
          set({ isPolling: false });
        }
      },

      toggle: () => {
        const { enabled, setEnabled } = get();
        setEnabled(!enabled);
      },

      startPolling: (userId) => {
        if (!REMOTE_CONTROL_ENABLED) return;
        const { enabled } = get();
        set({ userId });
        
        if (enabled) {
          remoteTaskPoller.start(userId);
          set({ isPolling: true });
        }
      },

      stopPolling: () => {
        remoteTaskPoller.stop();
        set({ isPolling: false, userId: null });
      },
    }),
    {
      name: 'useit-remote-polling',
      version: 1,
      // 只持久化 enabled 状态，不持久化运行时状态
      partialize: (state) => ({ enabled: state.enabled }),
    }
  )
);
