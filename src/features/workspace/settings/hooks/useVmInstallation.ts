import { useState, useCallback, useEffect } from 'react';
import {
  vmCheckEnvironment,
  vmEnableHyperV,
  vmSelectIso,
  vmSelectInstallDir,
  vmValidateIso,
  vmInstall,
  vmInstallCancel,
  onVmInstallProgress,
  type EnvironmentCheckResult,
  type VmInstallProgress,
} from '../../screen-viewer/services/vmElectronApi';

export type InstallStep = 
  | 'idle'
  | 'checking_environment'
  | 'environment_ready'
  | 'environment_error'
  | 'enabling_hyperv'
  | 'hyperv_needs_reboot'
  | 'selecting_iso'
  | 'validating_iso'
  | 'iso_ready'
  | 'configuring'
  | 'installing'
  | 'complete'
  | 'error';

export interface VmInstallState {
  step: InstallStep;
  environmentCheck: EnvironmentCheckResult | null;
  isoPath: string | null;
  isoError: string | null;
  installDir: string;
  installProgress: VmInstallProgress | null;
  error: string | null;
  // VM 配置
  vmName: string;
  memorySizeGB: number;
  cpuCount: number;
  diskSizeGB: number;
}

const DEFAULT_STATE: VmInstallState = {
  step: 'idle',
  environmentCheck: null,
  isoPath: null,
  isoError: null,
  installDir: 'C:\\VMs',
  installProgress: null,
  error: null,
  vmName: 'UseIt-Dev-VM',
  memorySizeGB: 4,
  cpuCount: 4,
  diskSizeGB: 60,
};

export function useVmInstallation() {
  const [state, setState] = useState<VmInstallState>(DEFAULT_STATE);

  // 监听安装进度
  useEffect(() => {
    const cleanup = onVmInstallProgress((progress) => {
      setState(prev => ({
        ...prev,
        installProgress: progress,
        step: progress.error ? 'error' : (progress.step === 'complete' ? 'complete' : 'installing'),
        error: progress.error || null,
      }));
    });
    return cleanup;
  }, []);

  // 检查环境
  const checkEnvironment = useCallback(async () => {
    setState(prev => ({ ...prev, step: 'checking_environment', error: null }));
    
    try {
      const result = await vmCheckEnvironment(state.installDir);
      
      if (result.errors.length > 0 && !result.isProOrEnterprise) {
        setState(prev => ({
          ...prev,
          step: 'environment_error',
          environmentCheck: result,
          error: result.errors[0],
        }));
      } else if (!result.hyperVEnabled) {
        setState(prev => ({
          ...prev,
          step: 'environment_ready',
          environmentCheck: result,
        }));
      } else {
        setState(prev => ({
          ...prev,
          step: 'environment_ready',
          environmentCheck: result,
        }));
      }
    } catch (err: any) {
      setState(prev => ({
        ...prev,
        step: 'environment_error',
        error: err.message || '环境检查失败',
      }));
    }
  }, [state.installDir]);

  // 启用 VM 功能
  const enableHyperV = useCallback(async () => {
    setState(prev => ({ ...prev, step: 'enabling_hyperv', error: null }));
    
    try {
      const result = await vmEnableHyperV();
      
      if (result.success) {
        if (result.needsReboot) {
          setState(prev => ({ ...prev, step: 'hyperv_needs_reboot' }));
        } else {
          // 重新检查环境
          await checkEnvironment();
        }
      } else {
        setState(prev => ({
          ...prev,
          step: 'environment_ready',
          error: '启用虚拟机功能失败，请手动启用',
        }));
      }
    } catch (err: any) {
      setState(prev => ({
        ...prev,
        step: 'environment_ready',
        error: err.message || '启用虚拟机功能失败',
      }));
    }
  }, [checkEnvironment]);

  // 选择 ISO 文件
  const selectIso = useCallback(async () => {
    setState(prev => ({ ...prev, step: 'selecting_iso', isoError: null }));
    
    try {
      const result = await vmSelectIso();
      
      if (result.canceled || !result.path) {
        setState(prev => ({ ...prev, step: 'environment_ready' }));
        return;
      }

      setState(prev => ({ ...prev, step: 'validating_iso', isoPath: result.path }));

      // 验证 ISO
      const validation = await vmValidateIso(result.path);
      
      if (validation.valid) {
        setState(prev => ({ ...prev, step: 'iso_ready', isoError: null }));
      } else {
        setState(prev => ({
          ...prev,
          step: 'environment_ready',
          isoPath: null,
          isoError: validation.error || 'ISO 验证失败',
        }));
      }
    } catch (err: any) {
      setState(prev => ({
        ...prev,
        step: 'environment_ready',
        isoError: err.message || '选择 ISO 失败',
      }));
    }
  }, []);

  // 选择安装目录
  const selectInstallDir = useCallback(async () => {
    try {
      const result = await vmSelectInstallDir();
      
      if (result.canceled || !result.path) {
        return;
      }

      setState(prev => ({ ...prev, installDir: result.path! }));
    } catch (err: any) {
      // ignore
    }
  }, []);

  // 更新配置
  const updateConfig = useCallback((config: Partial<Pick<VmInstallState, 'vmName' | 'memorySizeGB' | 'cpuCount' | 'diskSizeGB' | 'installDir'>>) => {
    setState(prev => ({ ...prev, ...config }));
  }, []);

  // 开始安装
  const startInstall = useCallback(async () => {
    if (!state.isoPath) {
      setState(prev => ({ ...prev, error: '请先选择 ISO 文件' }));
      return;
    }

    if (!state.installDir) {
      setState(prev => ({ ...prev, error: '请先选择安装目录' }));
      return;
    }

    setState(prev => ({ ...prev, step: 'installing', error: null }));

    try {
      const result = await vmInstall({
        vmName: state.vmName,
        isoPath: state.isoPath,
        installDir: state.installDir,
        memorySizeGB: state.memorySizeGB,
        cpuCount: state.cpuCount,
        diskSizeGB: state.diskSizeGB,
      });

      if (!result.success) {
        setState(prev => ({
          ...prev,
          step: 'error',
          error: result.error || '安装失败',
        }));
      }
      // 成功的情况由 onVmInstallProgress 处理
    } catch (err: any) {
      setState(prev => ({
        ...prev,
        step: 'error',
        error: err.message || '安装失败',
      }));
    }
  }, [state.isoPath, state.installDir, state.vmName, state.memorySizeGB, state.cpuCount, state.diskSizeGB]);

  // 取消安装
  const cancelInstall = useCallback(async () => {
    try {
      await vmInstallCancel();
      setState(prev => ({ ...prev, step: 'iso_ready' }));
    } catch (err) {
      // ignore
    }
  }, []);

  // 重置状态
  const reset = useCallback(() => {
    setState(DEFAULT_STATE);
  }, []);

  // 进入配置步骤
  const goToConfig = useCallback(() => {
    setState(prev => ({ ...prev, step: 'configuring' }));
  }, []);

  // 返回 ISO 选择
  const backToIsoSelect = useCallback(() => {
    setState(prev => ({ ...prev, step: 'iso_ready' }));
  }, []);

  return {
    state,
    checkEnvironment,
    enableHyperV,
    selectIso,
    selectInstallDir,
    updateConfig,
    startInstall,
    cancelInstall,
    reset,
    goToConfig,
    backToIsoSelect,
  };
}

