import { useCallback, useState, useEffect } from 'react';
import { DEFAULT_VM_NAME } from '../constants';
import { stopVm } from '../services/vmElectronApi';

export interface UseVmShutdownOptions {
  vmName?: string;
  onDisconnected?: () => void;
}

export function useVmShutdown({ vmName, onDisconnected }: UseVmShutdownOptions) {
  const [showShutdownModal, setShowShutdownModal] = useState(false);
  const [isShuttingDown, setIsShuttingDown] = useState(false);
  const [shutdownError, setShutdownError] = useState('');

  const openShutdownModal = useCallback(() => {
    setShutdownError('');
    setShowShutdownModal(true);
  }, []);

  // 监听全局关机请求事件
  useEffect(() => {
    const handleShutdownRequest = (e: Event) => {
      const customEvent = e as CustomEvent<{ vmName: string }>;
      const requestedVmName = customEvent.detail?.vmName;
      const effectiveVmName = vmName || DEFAULT_VM_NAME;
      
      // 如果请求的 VM 名称匹配当前 Hook 管理的 VM，则打开弹窗
      if (requestedVmName === effectiveVmName) {
        openShutdownModal();
      }
    };

    window.addEventListener('request-vm-shutdown', handleShutdownRequest);
    return () => {
      window.removeEventListener('request-vm-shutdown', handleShutdownRequest);
    };
  }, [vmName, openShutdownModal]);

  const closeShutdownModal = useCallback(() => {
    if (isShuttingDown) return;
    setShowShutdownModal(false);
  }, [isShuttingDown]);

  const confirmShutdown = useCallback(async () => {
    const effectiveVmName = vmName || DEFAULT_VM_NAME;
    try {
      setIsShuttingDown(true);
      setShutdownError('');
      await stopVm(effectiveVmName);
      onDisconnected?.();
      setShowShutdownModal(false);
    } catch (e: any) {
      setShutdownError(e.message || 'Failed to shut down VM');
    } finally {
      setIsShuttingDown(false);
    }
  }, [onDisconnected, vmName]);

  return {
    showShutdownModal,
    isShuttingDown,
    shutdownError,
    openShutdownModal,
    closeShutdownModal,
    confirmShutdown,
  };
}


