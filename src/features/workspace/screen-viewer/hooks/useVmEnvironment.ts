import { useCallback, useEffect, useState } from 'react';
import { checkHyperVEnabled, checkVmExists, vmCheckEnvironment } from '../services/vmElectronApi';
import { classifyVmError } from '../services/vmErrorClassifier';
import { DEFAULT_VM_NAME } from '../constants';

export type VmEnvironmentStatus = 
  | 'checking'
  | 'unsupported_system'
  | 'no_hyperv'      // Hyper-V 未启用
  | 'permission_required'
  | 'no_vm'          // VM 不存在
  | 'ready'          // 一切就绪
  | 'error';

export interface VmEnvironmentState {
  status: VmEnvironmentStatus;
  hyperVEnabled: boolean;
  vmExists: boolean;
  vmName: string | null;
  error: string | null;
}

export function useVmEnvironment(vmNamePattern: string = DEFAULT_VM_NAME) {
  const [state, setState] = useState<VmEnvironmentState>({
    status: 'checking',
    hyperVEnabled: false,
    vmExists: false,
    vmName: null,
    error: null,
  });

  const checkEnvironment = useCallback(async () => {
    // 非 Electron 环境
    if (!window.electron) {
      setState({
        status: 'error',
        hyperVEnabled: false,
        vmExists: false,
        vmName: null,
        error: 'Desktop app required',
      });
      return;
    }

    setState(prev => ({ ...prev, status: 'checking', error: null }));

    try {
      // Step 0: 检查系统版本是否支持 Hyper-V（例如 Home 版不支持）
      try {
        const env = await vmCheckEnvironment();
        if (!env.isProOrEnterprise) {
          setState({
            status: 'unsupported_system',
            hyperVEnabled: false,
            vmExists: false,
            vmName: null,
            error: `Current system does not support local virtual machines (${env.windowsVersion || 'Windows edition unsupported'}). Please use Windows Pro/Enterprise/Education.`,
          });
          return;
        }
      } catch {
        // vmCheckEnvironment 不可用时忽略，沿用现有检查逻辑
      }

      // Step 1: 检查 Hyper-V
      let hyperVEnabled = false;
      try {
        hyperVEnabled = await checkHyperVEnabled();
      } catch (e: any) {
        // API 不可用时假设已启用（让后续操作去验证）
        if (e.message?.includes('not available')) {
          hyperVEnabled = true;
        } else {
          throw e;
        }
      }

      if (!hyperVEnabled) {
        setState({
          status: 'no_hyperv',
          hyperVEnabled: false,
          vmExists: false,
          vmName: null,
          error: null,
        });
        return;
      }

      // Step 2: 检查 VM 是否存在
      let vmExists = false;
      let vmName: string | null = null;
      try {
        const result = await checkVmExists(vmNamePattern);
        vmExists = result.exists;
        vmName = result.vmName;
      } catch (e: any) {
        // API 不可用时假设存在（让后续操作去验证）
        if (e.message?.includes('not available')) {
          vmExists = true;
          vmName = vmNamePattern;
        } else {
          throw e;
        }
      }

      if (!vmExists) {
        setState({
          status: 'no_vm',
          hyperVEnabled: true,
          vmExists: false,
          vmName: null,
          error: null,
        });
        return;
      }

      // 一切就绪
      setState({
        status: 'ready',
        hyperVEnabled: true,
        vmExists: true,
        vmName,
        error: null,
      });
    } catch (e: any) {
      const classifiedError = classifyVmError(e, 'Failed to check VM environment');
      const rawMessage = (classifiedError.rawMessage || '').toLowerCase();
      const isVmFeatureDisabled =
        rawMessage.includes('get-vm') &&
        (rawMessage.includes('not recognized') || rawMessage.includes('commandnotfoundexception'));

      setState(prev => ({
        ...prev,
        status: classifiedError.isPermissionError
          ? 'permission_required'
          : isVmFeatureDisabled
          ? 'no_hyperv'
          : 'error',
        error: isVmFeatureDisabled ? null : classifiedError.userMessage,
      }));
    }
  }, [vmNamePattern]);

  useEffect(() => {
    checkEnvironment();
  }, [checkEnvironment]);

  return { ...state, recheckEnvironment: checkEnvironment };
}














