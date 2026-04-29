// Thin wrapper around window.electron VM-related APIs

export interface VmSpecs {
  cpuCores: number;
  cpuUsage: number;
  memoryMB: number;
  memoryAssignedMB: number;
  memoryDemandMB: number;
  isDynamicMemory: boolean;
  state: string;
  uptime: string;
  diskSizeGB: number;
  diskUsedGB: number;
}

export interface VmExistsResult {
  exists: boolean;
  vmName: string | null;
}

export interface EnsureVmVncResult {
  vmName: string;
  installed: boolean;
  alreadyInstalled: boolean;
}

export interface VmSnapshotRecord {
  Id: string;
  Name: string;
  ParentCheckpointId?: string;
  CreationTime?: string;
  CheckpointType?: string;
}

// VM 安装相关类型
export interface VmInstallProgress {
  step: string;
  stepIndex: number;
  totalSteps: number;
  percent: number;
  message: string;
  error?: string;
}

export interface EnvironmentCheckResult {
  hyperVEnabled: boolean;
  hyperVInstalled: boolean;
  isAdmin: boolean;
  windowsVersion: string;
  isProOrEnterprise: boolean;
  freeSpaceGB: number;
  hasSufficientSpace: boolean;
  errors: string[];
}

export interface VmInstallConfig {
  vmName?: string;
  isoPath: string;
  installDir?: string;  // 安装目录
  memorySizeGB?: number;
  cpuCount?: number;
  diskSizeGB?: number;
}

declare global {
  interface Window {
    electron?: {
      // App config
      getAppConfig?: (key?: string) => Promise<any>;
      setAppConfig?: (newConfig: any) => Promise<boolean>;
      // 环境检查
      checkHyperVEnabled?: () => Promise<boolean>;
      checkVmExists?: (vmNamePattern: string) => Promise<VmExistsResult>;
      // VM 管理
      getVmStatus?: (vmName: string) => Promise<string>;
      startVm?: (vmName: string) => Promise<void>;
      getVmIp?: (vmName: string) => Promise<string>;
      stopVm?: (vmName: string) => Promise<void>;
      deleteVm?: (vmName: string) => Promise<void>;
      vmSelectExportDir?: () => Promise<{ path: string | null; canceled: boolean }>;
      vmExportToFolder?: (config: { vmName: string; exportDir: string }) => Promise<{ success: boolean; error?: string; vmName?: string; exportPath?: string }>;
      ensureVmVnc?: (args: { vmName: string; username?: string; password?: string }) => Promise<EnsureVmVncResult>;
      fixHyperVPermission?: () => Promise<void>;
      getVmSpecs?: (vmName: string) => Promise<VmSpecs>;
      setVmSpecs?: (config: { vmName: string; cpuCores: number; memoryGB: number; isDynamicMemory: boolean }) => Promise<void>;
      listVmSnapshots?: (vmName: string) => Promise<VmSnapshotRecord[]>;
      createVmSnapshot?: (args: { vmName: string; snapshotName: string; saveState: boolean }) => Promise<void>;
      restoreVmSnapshot?: (args: { vmName: string; snapshotId: string }) => Promise<void>;
      // VM 安装
      vmCheckEnvironment?: (installDir?: string) => Promise<EnvironmentCheckResult>;
      vmEnableHyperV?: () => Promise<{ success: boolean; needsReboot: boolean }>;
      vmSelectIso?: () => Promise<{ path: string | null; canceled: boolean }>;
      vmSelectInstallDir?: () => Promise<{ path: string | null; canceled: boolean }>;
      vmSelectRestoreDir?: () => Promise<{ path: string | null; canceled: boolean }>;
      vmValidateIso?: (isoPath: string) => Promise<{ valid: boolean; error?: string }>;
      vmInstall?: (config: VmInstallConfig) => Promise<{ success: boolean; error?: string }>;
      vmRestoreFromFolder?: (config: { vmName?: string; folderPath: string }) => Promise<{ success: boolean; error?: string; vmName?: string; checkpointCount?: number; restoreMode?: string }>;
      vmInstallCancel?: () => Promise<void>;
      onVmInstallProgress?: (callback: (progress: VmInstallProgress) => void) => () => void;
    };
  }
}

const ensureElectron = () => {
  if (!window.electron) {
    throw new Error('This feature requires the desktop app');
  }
};

// 环境检查 API
export async function checkHyperVEnabled(): Promise<boolean> {
  ensureElectron();
  if (!window.electron?.checkHyperVEnabled) {
    throw new Error('checkHyperVEnabled not available');
  }
  return window.electron.checkHyperVEnabled();
}

export async function checkVmExists(vmNamePattern: string): Promise<VmExistsResult> {
  ensureElectron();
  if (!window.electron?.checkVmExists) {
    throw new Error('checkVmExists not available');
  }
  return window.electron.checkVmExists(vmNamePattern);
}

// VM 管理 API
export async function getVmStatus(vmName: string): Promise<string> {
  ensureElectron();
  if (!window.electron?.getVmStatus) {
    throw new Error('getVmStatus not available');
  }
  return window.electron.getVmStatus(vmName);
}

export async function startVm(vmName: string): Promise<void> {
  ensureElectron();
  if (!window.electron?.startVm) {
    throw new Error('startVm not available');
  }
  return window.electron.startVm(vmName);
}

export async function getVmIp(vmName: string): Promise<string> {
  ensureElectron();
  if (!window.electron?.getVmIp) {
    throw new Error('getVmIp not available');
  }
  return window.electron.getVmIp(vmName);
}

export async function stopVm(vmName: string): Promise<void> {
  ensureElectron();
  if (!window.electron?.stopVm) {
    throw new Error('stopVm not available');
  }
  return window.electron.stopVm(vmName);
}

export async function deleteVm(vmName: string): Promise<void> {
  ensureElectron();
  if (!window.electron?.deleteVm) {
    throw new Error('deleteVm not available');
  }
  return window.electron.deleteVm(vmName);
}

export async function vmSelectExportDir(): Promise<{ path: string | null; canceled: boolean }> {
  ensureElectron();
  if (!window.electron?.vmSelectExportDir) {
    throw new Error('vmSelectExportDir not available');
  }
  return window.electron.vmSelectExportDir();
}

export async function vmExportToFolder(config: { vmName: string; exportDir: string }): Promise<{
  success: boolean;
  error?: string;
  vmName?: string;
  exportPath?: string;
}> {
  ensureElectron();
  if (!window.electron?.vmExportToFolder) {
    throw new Error('vmExportToFolder not available');
  }
  return window.electron.vmExportToFolder(config);
}

export async function ensureVmVnc(args: {
  vmName: string;
  username?: string;
  password?: string;
}): Promise<EnsureVmVncResult> {
  ensureElectron();
  if (!window.electron?.ensureVmVnc) {
    throw new Error('ensureVmVnc not available');
  }
  return window.electron.ensureVmVnc(args);
}

export async function fixHyperVPermission(): Promise<void> {
  ensureElectron();
  if (!window.electron?.fixHyperVPermission) {
    throw new Error('fixHyperVPermission not available');
  }
  return window.electron.fixHyperVPermission();
}

export async function getVmSpecs(vmName: string): Promise<VmSpecs> {
  ensureElectron();
  if (!window.electron?.getVmSpecs) {
    throw new Error('getVmSpecs not available');
  }
  return window.electron.getVmSpecs(vmName);
}

export async function setVmSpecs(config: { vmName: string; cpuCores: number; memoryGB: number; isDynamicMemory: boolean }): Promise<void> {
  ensureElectron();
  if (!window.electron?.setVmSpecs) {
    throw new Error('setVmSpecs not available');
  }
  return window.electron.setVmSpecs(config);
}

export async function listVmSnapshots(vmName: string): Promise<VmSnapshotRecord[]> {
  ensureElectron();
  if (!window.electron?.listVmSnapshots) {
    throw new Error('listVmSnapshots not available');
  }
  return window.electron.listVmSnapshots(vmName);
}

export async function createVmSnapshot(args: { vmName: string; snapshotName: string; saveState: boolean }): Promise<void> {
  ensureElectron();
  if (!window.electron?.createVmSnapshot) {
    throw new Error('createVmSnapshot not available');
  }
  return window.electron.createVmSnapshot(args);
}

export async function restoreVmSnapshot(args: { vmName: string; snapshotId: string }): Promise<void> {
  ensureElectron();
  if (!window.electron?.restoreVmSnapshot) {
    throw new Error('restoreVmSnapshot not available');
  }
  return window.electron.restoreVmSnapshot(args);
}

// ==================== VM 安装 API ====================

export async function vmCheckEnvironment(installDir?: string): Promise<EnvironmentCheckResult> {
  ensureElectron();
  if (!window.electron?.vmCheckEnvironment) {
    throw new Error('vmCheckEnvironment not available');
  }
  return window.electron.vmCheckEnvironment(installDir);
}

export async function vmEnableHyperV(): Promise<{ success: boolean; needsReboot: boolean }> {
  ensureElectron();
  if (!window.electron?.vmEnableHyperV) {
    throw new Error('vmEnableHyperV not available');
  }
  return window.electron.vmEnableHyperV();
}

export async function vmSelectIso(): Promise<{ path: string | null; canceled: boolean }> {
  ensureElectron();
  if (!window.electron?.vmSelectIso) {
    throw new Error('vmSelectIso not available');
  }
  return window.electron.vmSelectIso();
}

export async function vmSelectInstallDir(): Promise<{ path: string | null; canceled: boolean }> {
  ensureElectron();
  if (!window.electron?.vmSelectInstallDir) {
    throw new Error('vmSelectInstallDir not available');
  }
  return window.electron.vmSelectInstallDir();
}

export async function vmSelectRestoreDir(): Promise<{ path: string | null; canceled: boolean }> {
  ensureElectron();
  if (!window.electron?.vmSelectRestoreDir) {
    throw new Error('vmSelectRestoreDir not available');
  }
  return window.electron.vmSelectRestoreDir();
}

export async function vmValidateIso(isoPath: string): Promise<{ valid: boolean; error?: string }> {
  ensureElectron();
  if (!window.electron?.vmValidateIso) {
    throw new Error('vmValidateIso not available');
  }
  return window.electron.vmValidateIso(isoPath);
}

export async function vmInstall(config: VmInstallConfig): Promise<{ success: boolean; error?: string }> {
  ensureElectron();
  if (!window.electron?.vmInstall) {
    throw new Error('vmInstall not available');
  }
  return window.electron.vmInstall(config);
}

export async function vmRestoreFromFolder(config: { vmName?: string; folderPath: string }): Promise<{
  success: boolean;
  error?: string;
  vmName?: string;
  checkpointCount?: number;
  restoreMode?: string;
}> {
  ensureElectron();
  if (!window.electron?.vmRestoreFromFolder) {
    throw new Error('vmRestoreFromFolder not available');
  }
  return window.electron.vmRestoreFromFolder(config);
}

export async function vmInstallCancel(): Promise<void> {
  ensureElectron();
  if (!window.electron?.vmInstallCancel) {
    throw new Error('vmInstallCancel not available');
  }
  return window.electron.vmInstallCancel();
}

export function onVmInstallProgress(callback: (progress: VmInstallProgress) => void): () => void {
  if (!window.electron?.onVmInstallProgress) {
    console.warn('onVmInstallProgress not available');
    return () => {};
  }
  return window.electron.onVmInstallProgress(callback);
}

// ==================== VM 文件共享 API ====================

export async function vmShareEnsure(config: {
  vmName: string;
  username?: string;
  password?: string;
  projectsRootPath: string;
}): Promise<{ success: boolean; driveLetter: string; error?: string }> {
  ensureElectron();
  if (!window.electron?.vmShareEnsure) {
    throw new Error('vmShareEnsure not available');
  }
  return window.electron.vmShareEnsure(config);
}

export async function vmShareHealth(config: {
  vmName: string;
  username?: string;
  password?: string;
}): Promise<{ success: boolean; healthy: boolean; error?: string }> {
  ensureElectron();
  if (!window.electron?.vmShareHealth) {
    throw new Error('vmShareHealth not available');
  }
  return window.electron.vmShareHealth(config);
}

export async function vmShareTeardown(config: {
  vmName: string;
  username?: string;
  password?: string;
}): Promise<{ success: boolean; error?: string }> {
  ensureElectron();
  if (!window.electron?.vmShareTeardown) {
    throw new Error('vmShareTeardown not available');
  }
  return window.electron.vmShareTeardown(config);
}

export async function vmShareGetVmPath(projectName: string): Promise<string> {
  ensureElectron();
  if (!window.electron?.vmShareGetVmPath) {
    throw new Error('vmShareGetVmPath not available');
  }
  return window.electron.vmShareGetVmPath(projectName);
}


