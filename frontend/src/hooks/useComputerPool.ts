/**
 * 电脑池管理 Hook
 * 从 app-config 的 environments 获取可用环境
 * 与 ControlPanel 的 AgentTarget 系统保持一致
 */

import { useState, useEffect, useCallback, useRef } from 'react';
import type { ComputerWithStatus, ComputerStatus } from '../types/computer';

export interface UseComputerPoolReturn {
  computers: ComputerWithStatus[];
  loading: boolean;
  error: string | null;
  lastUsedComputer: string;
  refresh: () => Promise<void>;
  isOccupied: (computerName: string) => Promise<{ occupied: boolean; occupiedBy?: string }>;
  openConfig: () => void;
}

interface EnvironmentConfig {
  id: string;
  type: 'local';
  name: string;
  deletable?: boolean;
}

export function useComputerPool(): UseComputerPoolReturn {
  const [computers, setComputers] = useState<ComputerWithStatus[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastUsedComputer, setLastUsedComputer] = useState<string>('This PC');
  const loadingRef = useRef(false);

  const refresh = useCallback(async () => {
    if (loadingRef.current) return;
    loadingRef.current = true;

    try {
      setLoading(true);
      setError(null);

      let envs: EnvironmentConfig[] = [];
      if (window.electron?.getAppConfig) {
        const config = await window.electron.getAppConfig();
        const raw = (config?.environments as Array<{ id: string; type?: string; name: string; deletable?: boolean }>) || [];
        envs = raw.filter((e) => e.type === 'local') as EnvironmentConfig[];
      }

      const hasLocal = envs.some((e) => e.id === 'local' || e.type === 'local');
      if (!hasLocal) {
        envs = [{ id: 'local', type: 'local', name: 'This PC', deletable: false }, ...envs];
      }

      const computersWithStatus: ComputerWithStatus[] = [];

      for (const env of envs) {
        if (env.type !== 'local') continue;
        computersWithStatus.push({
          name: env.name,
          type: 'thispc',
          host: 'localhost',
          localEnginePort: 8324,
          computerServerPort: 8080,
          vncPort: 5900,
          wsPort: 16080,
          tags: [],
          capabilities: [],
          status: 'online' as ComputerStatus,
          resolvedHost: 'localhost',
        });
      }

      setComputers(computersWithStatus);

      if (window.electron?.getAppConfig) {
        const savedLastUsed = await window.electron.getAppConfig('lastUsedComputer');
        if (savedLastUsed) {
          setLastUsedComputer(savedLastUsed as string);
        }
      }
    } catch (e: any) {
      console.error('[useComputerPool] Error loading environments:', e);
      setError(e.message || 'Failed to load environments');
      setComputers([
        {
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
        },
      ]);
    } finally {
      setLoading(false);
      loadingRef.current = false;
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  useEffect(() => {
    const handler = () => {
      void refresh();
    };
    window.addEventListener('environments-updated', handler);
    return () => window.removeEventListener('environments-updated', handler);
  }, [refresh]);

  const isOccupied = useCallback(async (_computerName: string) => {
    return { occupied: false, occupiedBy: undefined };
  }, []);

  const openConfig = useCallback(() => {
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
