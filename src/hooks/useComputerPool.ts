/**
 * 电脑池管理 Hook
 * 从 app-config 的 environments 获取可用环境
 * 与 ControlPanel 的 AgentTarget 系统保持一致
 */

import { useState, useEffect, useCallback, useRef } from 'react';
import type { ComputerWithStatus, ComputerStatus } from '../types/computer';
import { VM_ENABLED } from '@/config/runtimeEnv';

export interface UseComputerPoolReturn {
  // 状态
  computers: ComputerWithStatus[];
  loading: boolean;
  error: string | null;
  lastUsedComputer: string;

  // 操作
  refresh: () => Promise<void>;
  isOccupied: (computerName: string) => Promise<{ occupied: boolean; occupiedBy?: string }>;
  openConfig: () => void;
}

// 环境配置类型（与 ControlPanel 保持一致）
interface EnvironmentConfig {
  id: string;
  type: 'local' | 'vm';
  name: string;
  vmName?: string;
  deletable?: boolean;
}

export function useComputerPool(): UseComputerPoolReturn {
  const [computers, setComputers] = useState<ComputerWithStatus[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastUsedComputer, setLastUsedComputer] = useState<string>('This PC');
  
  // 防止重复加载
  const loadingRef = useRef(false);

  // 加载电脑池（从 app-config 的 environments）
  const refresh = useCallback(async () => {
    if (loadingRef.current) return;
    loadingRef.current = true;

    try {
      setLoading(true);
      setError(null);
      
      console.log('[useComputerPool] Loading environments from app-config...');
      
      // 从 app-config 获取 environments
      let envs: EnvironmentConfig[] = [];
      if (window.electron?.getAppConfig) {
        const config = await window.electron.getAppConfig();
        envs = (config?.environments as EnvironmentConfig[]) || [];
      }

      if (!VM_ENABLED) {
        envs = envs.filter(e => e.type !== 'vm');
      }

      // 确保有 This PC
      const hasLocal = envs.some(e => e.id === 'local' || e.type === 'local');
      if (!hasLocal) {
        envs = [
          { id: 'local', type: 'local', name: 'This PC', deletable: false },
          ...envs,
        ];
      }

      console.log('[useComputerPool] Environments loaded:', envs.length);

      // 检查每个环境的状态
      const computersWithStatus: ComputerWithStatus[] = [];
      
      for (const env of envs) {
        let status: ComputerStatus = 'offline';
        let resolvedHost: string | undefined;

        if (env.type === 'local') {
          // This PC 总是在线
          status = 'online';
          resolvedHost = 'localhost';
        } else if (env.type === 'vm' && env.vmName) {
          // 检查 VM 状态
          try {
            if (window.electron?.getVmStatus) {
              const vmState = await window.electron.getVmStatus(env.vmName);
              if (vmState?.toLowerCase() === 'running') {
                // VM 运行中，检查服务是否可用
                if (window.electron?.getVmIp) {
                  try {
                    const ip = await window.electron.getVmIp(env.vmName);
                    if (ip) {
                      resolvedHost = ip;
                      // 检查 Local Engine 是否响应
                      try {
                        const response = await fetch(`http://${ip}:8324/health`, {
                          signal: AbortSignal.timeout(3000)
                        });
                        status = response.ok ? 'online' : 'offline';
                      } catch {
                        status = 'offline'; // 服务未响应
                      }
                    }
                  } catch {
                    // 获取 IP 失败
                  }
                }
              }
            }
          } catch (e) {
            console.warn(`[useComputerPool] Failed to check VM status for ${env.vmName}:`, e);
          }
        }

        computersWithStatus.push({
          name: env.name,
          type: env.type === 'local' ? 'thispc' : 'vm',
          host: resolvedHost || (env.type === 'local' ? 'localhost' : 'auto'),
          localEnginePort: 8324,
          computerServerPort: 8080,
          vncPort: 5900,
          wsPort: 16080,
          tags: [],
          capabilities: [],
          vmName: env.vmName,
          status,
          resolvedHost,
        });
      }

      setComputers(computersWithStatus);
      
      // 获取上次使用的电脑
      if (window.electron?.getAppConfig) {
        const savedLastUsed = await window.electron.getAppConfig('lastUsedComputer');
        if (savedLastUsed) {
          setLastUsedComputer(savedLastUsed as string);
        }
      }
      
    } catch (e: any) {
      console.error('[useComputerPool] Error loading environments:', e);
      setError(e.message || 'Failed to load environments');
      // 至少提供 This PC
      setComputers([{
        name: 'This PC',
        type: 'thispc',
        host: 'localhost',
        localEnginePort: 8324,
        computerServerPort: 8080,
        vncPort: 5900,
        wsPort: 16080,
        tags: [],
        capabilities: [],
        status: 'online',
        resolvedHost: 'localhost',
      }]);
    } finally {
      setLoading(false);
      loadingRef.current = false;
    }
  }, []);

  // 初始加载
  useEffect(() => {
    refresh();
  }, [refresh]);

  // 监听 environments 更新事件
  useEffect(() => {
    const handler = () => {
      console.log('[useComputerPool] Environments updated, refreshing...');
      refresh();
    };
    window.addEventListener('environments-updated', handler);
    return () => window.removeEventListener('environments-updated', handler);
  }, [refresh]);

  // 检查是否被占用（暂时简单实现）
  const isOccupied = useCallback(async (_computerName: string) => {
    // TODO: 实现真正的占用检查
    return { occupied: false, occupiedBy: undefined };
  }, []);

  // 打开 Agent Environment 设置
  const openConfig = useCallback(() => {
    // 触发事件让 ControlPanel 切换到 VM tab
    window.dispatchEvent(new CustomEvent('open-agent-environment'));
  }, []);

  return {
    computers,
    loading,
    error,
    lastUsedComputer,
    refresh,
    isOccupied,
    openConfig,
  };
}

