import { useState, useCallback, useRef } from 'react';

export type AgentStatus = 'unknown' | 'checking' | 'not_installed' | 'outdated' | 'up_to_date' | 'installing' | 'error';

interface ServiceDeployProgress {
  step: string;
  stepIndex: number;
  totalSteps: number;
  percent: number;
  message: string;
  messageKey?: string;  // i18n key for translation
  messageParams?: Record<string, string | number>;  // i18n interpolation params
  error?: string;
}

export interface UseAgentStatusResult {
  status: AgentStatus;
  localVersion: string | null;
  vmVersion: string | null;
  progress: ServiceDeployProgress | null;
  checkStatus: (vmName: string) => Promise<void>;
  installAgent: (vmName: string) => Promise<void>;
  error: string | null;
}

export function useAgentStatus(): UseAgentStatusResult {
  const [status, setStatus] = useState<AgentStatus>('unknown');
  const [localVersion, setLocalVersion] = useState<string | null>(null);
  const [vmVersion, setVmVersion] = useState<string | null>(null);
  const [progress, setProgress] = useState<ServiceDeployProgress | null>(null);
  const [error, setError] = useState<string | null>(null);
  
  // 防止重复检查
  const checkingRef = useRef(false);

  const checkStatus = useCallback(async (vmName: string) => {
    if (!window.electron?.serviceCheckStatus || !window.electron?.serviceGetLocalVersion) return;
    if (checkingRef.current) return;

    try {
      checkingRef.current = true;
      setStatus('checking');
      setError(null);

      // 1. 获取本地版本
      const localRes = await window.electron.serviceGetLocalVersion();
      const localVer = localRes.version || null;
      setLocalVersion(localVer);

      // 2. 检查 VM 中的服务状态
      // 我们检查 local_engine 作为一个代表，因为它们是一起部署的
      const vmStatusRes = await window.electron.serviceCheckStatus({
        vmName,
        serviceKey: 'local_engine',
      });

      if (!vmStatusRes.success) {
        // 如果检查失败（比如 VM 没启动），不报错，只是设为 unknown
        console.warn('Agent check failed:', vmStatusRes.error);
        setStatus('error');
        setError(vmStatusRes.error || 'Failed to check agent status');
        return;
      }

      const vmStatus = vmStatusRes.status;
      const vmVer = vmStatus.version || null;
      setVmVersion(vmVer);

      // 3. 确定状态
      if (!vmStatus.installed) {
        setStatus('not_installed');
      } else if (localVer && vmVer && localVer !== vmVer) {
        // 简单字符串比较，理想情况下应该用 semver
        setStatus('outdated');
      } else {
        setStatus('up_to_date');
      }

    } catch (err: any) {
      console.error('Failed to check agent status:', err);
      setStatus('error');
      setError(err.message);
    } finally {
      checkingRef.current = false;
    }
  }, []);

  const installAgent = useCallback(async (vmName: string) => {
    if (!window.electron?.serviceDeploy) return;
    
    try {
      setStatus('installing');
      setProgress({
        step: 'init',
        stepIndex: 0,
        totalSteps: 10,
        percent: 0,
        message: 'Initializing...',
      });
      setError(null);

      // 监听进度
      const cleanup = window.electron.onServiceDeployProgress?.((p) => {
        setProgress(p);
      });

      const result = await window.electron.serviceDeploy({
        vmName,
        username: 'useit',
        password: '12345678', // 默认密码，实际应该从配置读取
      });

      if (cleanup) cleanup();

      if (result.success) {
        // 部署成功后，重新检查状态
        await checkStatus(vmName);
      } else {
        setStatus('error');
        setError(result.error || 'Installation failed');
      }
    } catch (err: any) {
      setStatus('error');
      setError(err.message);
    }
  }, [checkStatus]);

  return {
    status,
    localVersion,
    vmVersion,
    progress,
    checkStatus,
    installAgent,
    error,
  };
}

