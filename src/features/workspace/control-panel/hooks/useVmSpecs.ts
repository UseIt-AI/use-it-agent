import { useEffect, useState, useCallback } from 'react';
import { getVmSpecs, getVmStatus, checkVmExists } from '../../screen-viewer/services/vmElectronApi';

export type VmSpecsStatus = 'loading' | 'ready' | 'vm_not_found' | 'error';

export interface VmSpecsState {
  status: VmSpecsStatus;
  name: string;
  os: string;
  cpuCores: number;
  cpuUsage: number;
  memoryGB: number;
  memoryDemandGB: number;
  isDynamicMemory: boolean;
  storageGB: number;
  storageUsedGB: number;
  state: 'running' | 'off' | 'unknown';
  uptime: string;
  error: string | null;
}

const DEFAULT_VM_NAME = 'UseIt-Dev-VM';

export function useVmSpecs(vmName: string = DEFAULT_VM_NAME) {
  const makeInitialSpecs = useCallback(
    (name: string): VmSpecsState => ({
      status: 'loading',
      name,
      os: 'Windows 11 Pro',
      cpuCores: 0,
      cpuUsage: 0,
      memoryGB: 0,
      memoryDemandGB: 0,
      isDynamicMemory: false,
      storageGB: 0,
      storageUsedGB: 0,
      state: 'unknown',
      uptime: '',
      error: null,
    }),
    []
  );

  const [specs, setSpecs] = useState<VmSpecsState>(() => makeInitialSpecs(vmName));

  // 当 vmName 变化时，立刻重置 specs，避免短暂显示上一个 VM 的数据（信息隔离）
  useEffect(() => {
    setSpecs(makeInitialSpecs(vmName));
  }, [vmName, makeInitialSpecs]);

  /*
    旧的初始值（保留，避免误删逻辑）：
    const [specs, setSpecs] = useState<VmSpecsState>({
    status: 'loading',
    name: vmName,
    os: 'Windows 11 Pro',
    cpuCores: 0,
    cpuUsage: 0,
    memoryGB: 0,
    memoryDemandGB: 0,
    isDynamicMemory: false,
    storageGB: 0,
    storageUsedGB: 0,
    state: 'unknown',
    uptime: '',
    error: null,
  });
  */

  const fetchSpecs = useCallback(async () => {
    // 非 Electron 环境
    if (!window.electron) {
      setSpecs(prev => ({
        ...prev,
        status: 'error',
        error: 'Desktop app required',
      }));
      return;
    }

    try {
      setSpecs(prev => ({ ...prev, status: 'loading', error: null }));

      // 先检查 VM 是否存在
      let vmExists = false;
      let actualVmName = vmName;
      
      if (window.electron.checkVmExists) {
        try {
          const result = await checkVmExists(vmName);
          vmExists = result.exists;
          if (result.vmName) {
            actualVmName = result.vmName;
          }
        } catch {
          // API 调用失败，尝试直接获取状态来判断
          vmExists = true; // 假设存在，让后续调用去验证
        }
      } else {
        // checkVmExists 不可用，假设存在
        vmExists = true;
      }

      if (!vmExists) {
        setSpecs(prev => ({
          ...prev,
          status: 'vm_not_found',
          name: vmName,
          cpuCores: 0,
          cpuUsage: 0,
          memoryGB: 0,
          memoryDemandGB: 0,
          storageGB: 0,
          storageUsedGB: 0,
          state: 'unknown',
          uptime: '',
          error: null,
        }));
        return;
      }

      // VM 存在，获取详细信息
      // 先获取状态
      let state: 'running' | 'off' | 'unknown' = 'unknown';
      try {
        const statusStr = await getVmStatus(actualVmName);
        state = statusStr === 'Running' ? 'running' : statusStr === 'Off' ? 'off' : 'unknown';
      } catch {
        // ignore
      }

      // 尝试获取详细规格
      if (window.electron.getVmSpecs) {
        try {
          const vmSpecs = await getVmSpecs(actualVmName);
          // console.log('[useVmSpecs] Raw specs from backend:', vmSpecs); // Debug log
          setSpecs({
            status: 'ready',
            name: actualVmName,
            os: 'Windows 11 Pro',
            cpuCores: vmSpecs.cpuCores,
            cpuUsage: vmSpecs.cpuUsage,
            memoryGB: Math.round(vmSpecs.memoryMB / 1024),
            memoryDemandGB: Math.round(vmSpecs.memoryDemandMB / 1024 * 10) / 10,
            isDynamicMemory: vmSpecs.isDynamicMemory,
            storageGB: vmSpecs.diskSizeGB,
            storageUsedGB: vmSpecs.diskUsedGB,
            state,
            uptime: vmSpecs.uptime,
            error: null,
          });
        } catch (err: any) {
          // getVmSpecs 失败，可能是 VM 不存在或其他错误
          const errorMsg = (err.message || '').toLowerCase();
          // 检测常见的 "VM 不存在" 错误模式
          const isVmNotFound = 
            errorMsg.includes('not find') || 
            errorMsg.includes('does not exist') || 
            errorMsg.includes('cannot be processed') ||
            errorMsg.includes('parameter cannot') ||
            errorMsg.includes('get-vm') ||
            errorMsg.includes('cannot find') ||
            errorMsg.includes('clixml');  // PowerShell 错误输出格式
          
          if (isVmNotFound) {
            setSpecs(prev => ({
              ...prev,
              status: 'vm_not_found',
              error: null,
            }));
          } else {
            // 其他错误，仍然显示基本信息
            setSpecs(prev => ({
              ...prev,
              status: 'ready',
              name: actualVmName,
              state,
              error: null, // 不显示错误，只是缺少详细信息
            }));
          }
        }
      } else {
        // getVmSpecs 不可用，只显示状态
        setSpecs(prev => ({
          ...prev,
          status: 'ready',
          name: actualVmName,
          state,
          error: null,
        }));
      }
    } catch (err: any) {
      const errorMsg = (err.message || '').toLowerCase();
      // 检测常见的 "VM 不存在" 错误模式
      const isVmNotFound = 
        errorMsg.includes('not find') || 
        errorMsg.includes('does not exist') || 
        errorMsg.includes('cannot be processed') ||
        errorMsg.includes('parameter cannot') ||
        errorMsg.includes('get-vm') ||
        errorMsg.includes('cannot find') ||
        errorMsg.includes('clixml');  // PowerShell 错误输出格式
      
      if (isVmNotFound) {
        setSpecs(prev => ({
          ...prev,
          status: 'vm_not_found',
          error: null,
        }));
      } else {
        setSpecs(prev => ({
          ...prev,
          status: 'error',
          error: err.message || 'Failed to fetch VM specs',
        }));
      }
    }
  }, [vmName]);

  useEffect(() => {
    // 监听全局关机请求事件，刷新状态
    const handleShutdownRequest = () => {
        // 延迟一点刷新，给 VM 关机一点时间（虽然只是发起请求，但这里主要是为了感知状态变化）
        setTimeout(fetchSpecs, 1000);
        setTimeout(fetchSpecs, 3000);
    };

    // 监听全局 VM 启动/连接事件 (新增)
    const handleVmConnected = (e: Event) => {
        const customEvent = e as CustomEvent<{ vmName: string }>;
        if (!customEvent.detail || customEvent.detail.vmName === vmName) {
            console.log('[useVmSpecs] VM connected, refreshing specs...');
            fetchSpecs();
            // 额外再刷新一次以确保获取到最新的 CPU/内存使用率
            setTimeout(fetchSpecs, 2000);
        }
    };

    window.addEventListener('request-vm-shutdown', handleShutdownRequest);
    window.addEventListener('vm-connected', handleVmConnected);
    
    return () => {
      window.removeEventListener('request-vm-shutdown', handleShutdownRequest);
      window.removeEventListener('vm-connected', handleVmConnected);
    };
  }, [fetchSpecs, vmName]);

  // 仅当 VM 存在且正在运行时才自动刷新
  useEffect(() => {
    // VM 不存在或已关闭时不刷新
    if (specs.status === 'vm_not_found' || specs.status === 'error') {
      return;
    }

    // VM 存在时每 30 秒刷新一次
    const interval = setInterval(fetchSpecs, 30000);
    return () => clearInterval(interval);
  }, [specs.status, fetchSpecs]);

  return { specs, refresh: fetchSpecs };
}
