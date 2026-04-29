import { contextBridge, ipcRenderer } from 'electron';

// VM 安装进度类型
export interface VmInstallProgress {
  step: string;
  stepIndex: number;
  totalSteps: number;
  percent: number;
  message: string;
  error?: string;
}

export interface Project {
  id: string;
  name: string;
  path: string;
  lastModified: number;
}

// 环境检查结果类型
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

contextBridge.exposeInMainWorld('electron', {
  minimize: () => ipcRenderer.send('window-minimize'),
  maximize: () => ipcRenderer.send('window-maximize'),
  toggleMaximize: () => ipcRenderer.send('window-toggle-maximize'),
  close: () => ipcRenderer.send('window-close'),
  expandWindow: () => ipcRenderer.send('window-expand'),
  shrinkWindow: () => ipcRenderer.send('window-shrink'),
  restoreWindowSize: () => ipcRenderer.send('window-restore-size'),
  
  // App Config API
  getAppConfig: async (key?: string) => {
    const result = await ipcRenderer.invoke('get-app-config', key);
    if (result.success) return key ? result.value : result.config;
    throw new Error(result.error);
  },
  setAppConfig: async (newConfig: any) => {
    const result = await ipcRenderer.invoke('set-app-config', newConfig);
    if (result.success) return true;
    throw new Error(result.error);
  },
  getPath: async (name: string) => {
    const result = await ipcRenderer.invoke('get-path', name);
    if (result.success) return result.path;
    throw new Error(result.error);
  },

  // Project Management API
  createProject: async (name: string) => {
    const result = await ipcRenderer.invoke('create-project', { name });
    if (result.success) return { projectId: result.projectId, projectPath: result.projectPath };
    throw new Error(result.error);
  },
  
  getRecentProjects: async (): Promise<Project[]> => {
    const result = await ipcRenderer.invoke('get-recent-projects');
    if (result.success) return result.projects;
    throw new Error(result.error);
  },
  
  openProject: async (projectId: string) => {
    const result = await ipcRenderer.invoke('open-project',{ projectId });
    if (result.success) return result.project;
    throw new Error(result.error);
  },
  
  importProjectFolder: async () => {
    const result = await ipcRenderer.invoke('import-project-folder');
    if (result.canceled) return null;
    if (result.success) return result.project;
    throw new Error(result.error);
  },

  deleteProject: async (projectId: string) => {
    const result = await ipcRenderer.invoke('delete-project',{ projectId });
    if (result.success) return { success: true };
    return { success: false, error: result.error };
  },

  // 选择要复制到工作区的文件（多选）
  showAddFilesToWorkspaceDialog: async () => {
    const result = await ipcRenderer.invoke('show-add-files-to-workspace-dialog');
    if (!result.success) throw new Error(result.error);
    return { canceled: result.canceled, filePaths: result.filePaths || [] };
  },

  // VM 环境检查 API
  checkHyperVEnabled: async () => {
    const result = await ipcRenderer.invoke('check-hyperv-enabled');
    if (result.success) return result.enabled as boolean;
    throw new Error(result.error);
  },
  checkVmExists: async (vmNamePattern: string) => {
    const result = await ipcRenderer.invoke('check-vm-exists', vmNamePattern);
    if (result.success) return { exists: result.exists as boolean, vmName: result.vmName as string | null };
    throw new Error(result.error);
  },

  // VM 管理 API
  getVmIp: async (vmName: string) => {
    const result = await ipcRenderer.invoke('get-vm-ip', vmName);
    if (result.success) return result.ip;
    throw new Error(result.error);
  },
  getVmStatus: async (vmName: string) => {
    const result = await ipcRenderer.invoke('get-vm-status', vmName);
    if (result.success) return result.state as string;
    throw new Error(result.error);
  },
  startVm: async (vmName: string) => {
    const result = await ipcRenderer.invoke('start-vm', vmName);
    if (result.success) return true;
    throw new Error(result.error);
  },
  stopVm: async (vmName: string) => {
    const result = await ipcRenderer.invoke('stop-vm', vmName);
    if (result.success) return true;
    throw new Error(result.error);
  },
  deleteVm: async (vmName: string) => {
    const result = await ipcRenderer.invoke('delete-vm', vmName);
    if (result.success) return true;
    throw new Error(result.error);
  },
  vmSelectExportDir: async (): Promise<{ path: string | null; canceled: boolean }> => {
    const result = await ipcRenderer.invoke('vm-select-export-dir');
    if (result.canceled) return { path: null, canceled: true };
    if (result.success) return { path: result.path, canceled: false };
    throw new Error(result.error);
  },
  vmExportToFolder: async (config: { vmName: string; exportDir: string }): Promise<{ success: boolean; error?: string; vmName?: string; exportPath?: string }> => {
    const result = await ipcRenderer.invoke('vm-export-to-folder', config);
    return result;
  },
  ensureVmVnc: async (args: { vmName: string; username?: string; password?: string }) => {
    const result = await ipcRenderer.invoke('vm-ensure-vnc', args);
    if (result.success) {
      return {
        vmName: result.vmName as string,
        installed: !!result.installed,
        alreadyInstalled: !!result.alreadyInstalled,
      };
    }
    throw new Error(result.error);
  },
  fixHyperVPermission: async () => {
    const result = await ipcRenderer.invoke('fix-hyperv-permission');
    if (result.success) return true;
    throw new Error(result.error);
  },
  getVmSpecs: async (vmName: string) => {
    const result = await ipcRenderer.invoke('get-vm-specs', vmName);
    if (result.success) return result.specs;
    throw new Error(result.error);
  },
  setVmSpecs: async (config: { vmName: string; cpuCores: number; memoryGB: number; isDynamicMemory: boolean }) => {
    const result = await ipcRenderer.invoke('set-vm-specs', config);
    if (result.success) return true;
    throw new Error(result.error);
  },
  listVmSnapshots: async (vmName: string) => {
    const result = await ipcRenderer.invoke('list-vm-snapshots', vmName);
    if (result.success) return result.snapshots as Array<{
      Id: string;
      Name: string;
      ParentCheckpointId?: string;
      CreationTime?: string;
      CheckpointType?: string;
    }>;
    throw new Error(result.error);
  },
  createVmSnapshot: async (args: { vmName: string; snapshotName: string; saveState: boolean }) => {
    const result = await ipcRenderer.invoke('create-vm-snapshot', args);
    if (result.success) return true;
    throw new Error(result.error);
  },
  restoreVmSnapshot: async (args: { vmName: string; snapshotId: string }) => {
    const result = await ipcRenderer.invoke('restore-vm-snapshot', args);
    if (result.success) return true;
    throw new Error(result.error);
  },

  // ==================== VM 安装 API ====================
  
  // 环境检查
  vmCheckEnvironment: async (installDir?: string): Promise<EnvironmentCheckResult> => {
    const result = await ipcRenderer.invoke('vm-check-environment', installDir);
    if (result.success) return result.data;
    throw new Error(result.error);
  },

  // 启用 Hyper-V
  vmEnableHyperV: async (): Promise<{ success: boolean; needsReboot: boolean }> => {
    const result = await ipcRenderer.invoke('vm-enable-hyperv');
    return { success: result.success, needsReboot: result.needsReboot || false };
  },

  // 选择 ISO 文件
  vmSelectIso: async (): Promise<{ path: string | null; canceled: boolean }> => {
    const result = await ipcRenderer.invoke('vm-select-iso');
    if (result.canceled) return { path: null, canceled: true };
    if (result.success) return { path: result.path, canceled: false };
    throw new Error(result.error);
  },

  // 选择 VM 安装目录
  vmSelectInstallDir: async (): Promise<{ path: string | null; canceled: boolean }> => {
    const result = await ipcRenderer.invoke('vm-select-install-dir');
    if (result.canceled) return { path: null, canceled: true };
    if (result.success) return { path: result.path, canceled: false };
    throw new Error(result.error);
  },
  vmSelectRestoreDir: async (): Promise<{ path: string | null; canceled: boolean }> => {
    const result = await ipcRenderer.invoke('vm-select-restore-dir');
    if (result.canceled) return { path: null, canceled: true };
    if (result.success) return { path: result.path, canceled: false };
    throw new Error(result.error);
  },

  // 验证 ISO 文件
  vmValidateIso: async (isoPath: string): Promise<{ valid: boolean; error?: string }> => {
    const result = await ipcRenderer.invoke('vm-validate-iso', isoPath);
    return { valid: result.success, error: result.error };
  },

  // 开始安装 VM
  vmInstall: async (config: {
    vmName?: string;
    isoPath: string;
    memorySizeGB?: number;
    cpuCount?: number;
    diskSizeGB?: number;
  }): Promise<{ success: boolean; error?: string }> => {
    const result = await ipcRenderer.invoke('vm-install', config);
    return result;
  },
  vmRestoreFromFolder: async (config: {
    vmName?: string;
    folderPath: string;
  }): Promise<{ success: boolean; error?: string; vmName?: string; checkpointCount?: number; restoreMode?: string }> => {
    const result = await ipcRenderer.invoke('vm-restore-from-folder', config);
    return result;
  },

  // 取消安装
  vmInstallCancel: async (): Promise<void> => {
    await ipcRenderer.invoke('vm-install-cancel');
  },

  // 监听安装进度
  onVmInstallProgress: (callback: (progress: VmInstallProgress) => void) => {
    const handler = (_event: Electron.IpcRendererEvent, progress: VmInstallProgress) => {
      callback(progress);
    };
    ipcRenderer.on('vm-install-progress', handler);
    // 返回清理函数
    return () => {
      ipcRenderer.removeListener('vm-install-progress', handler);
    };
  },

  // ==================== 服务部署 API ====================

  // 检查服务文件是否存在
  serviceHasFiles: async (): Promise<boolean> => {
    const result = await ipcRenderer.invoke('service-has-files');
    return result.hasFiles;
  },

  // 获取本地服务版本
  serviceGetLocalVersion: async (): Promise<{ success: boolean; version?: string }> => {
    const result = await ipcRenderer.invoke('service-get-local-version');
    return result;
  },

  // 部署服务到 VM
  serviceDeploy: async (config: {
    vmName: string;
    username?: string;
    password?: string;
  }): Promise<{ success: boolean; error?: string; services?: any }> => {
    const result = await ipcRenderer.invoke('service-deploy', config);
    return result;
  },

  // 检查服务状态
  serviceCheckStatus: async (config: {
    vmName: string;
    serviceKey: string;
    username?: string;
    password?: string;
  }): Promise<{ success: boolean; status?: any; error?: string }> => {
    const result = await ipcRenderer.invoke('service-check-status', config);
    return result;
  },

  // 停止服务
  serviceStop: async (config: {
    vmName: string;
    username?: string;
    password?: string;
  }): Promise<{ success: boolean; error?: string }> => {
    const result = await ipcRenderer.invoke('service-stop', config);
    return result;
  },

  // 重启服务
  serviceRestart: async (config: {
    vmName: string;
    username?: string;
    password?: string;
  }): Promise<{ success: boolean; error?: string }> => {
    const result = await ipcRenderer.invoke('service-restart', config);
    return result;
  },

  // 监听服务部署进度
  onServiceDeployProgress: (callback: (progress: {
    step: string;
    stepIndex: number;
    totalSteps: number;
    percent: number;
    message: string;
    error?: string;
  }) => void) => {
    const handler = (_event: Electron.IpcRendererEvent, progress: any) => {
      callback(progress);
    };
    ipcRenderer.on('service-deploy-progress', handler);
    return () => {
      ipcRenderer.removeListener('service-deploy-progress', handler);
    };
  },

  // ==================== VM 共享文件夹 API ====================

  vmShareEnsure: async (config: {
    vmName: string;
    username?: string;
    password?: string;
    projectsRootPath: string;
  }): Promise<{ success: boolean; driveLetter: string; error?: string }> => {
    return await ipcRenderer.invoke('vm-share-ensure', config);
  },

  vmShareHealth: async (config: {
    vmName: string;
    username?: string;
    password?: string;
  }): Promise<{ success: boolean; healthy: boolean; shareExists?: boolean; driveMapped?: boolean; error?: string }> => {
    return await ipcRenderer.invoke('vm-share-health', config);
  },

  vmShareTeardown: async (config: {
    vmName: string;
    username?: string;
    password?: string;
  }): Promise<{ success: boolean; error?: string }> => {
    return await ipcRenderer.invoke('vm-share-teardown', config);
  },

  vmShareGetVmPath: async (projectName: string): Promise<string> => {
    const result = await ipcRenderer.invoke('vm-share-get-vm-path', { projectName });
    return result.vmPath;
  },

  // ==================== 文件系统 API ====================
  
  // 获取项目根目录路径
  fsGetProjectRoot: async (projectId?: string) => {
    const result = await ipcRenderer.invoke('fs-get-project-root', projectId);
    if (result.success) return result.path;
    throw new Error(result.error);
  },

  // 获取 Skills 根目录路径
  fsGetSkillsRoot: async (userId?: string) => {
    const result = await ipcRenderer.invoke('fs-get-skills-root', userId);
    if (result.success) return result.path;
    throw new Error(result.error);
  },

  // 读取目录内容
  fsReadDirectory: async (dirPath: string) => {
    const result = await ipcRenderer.invoke('fs-read-directory', dirPath);
    if (result.success) return result.children;
    throw new Error(result.error);
  },

  // 读取完整目录树
  fsReadDirectoryTree: async (rootPath: string) => {
    const result = await ipcRenderer.invoke('fs-read-directory-tree', rootPath);
    if (result.success) return result.tree;
    throw new Error(result.error);
  },

  // 开始监听目录变化
  fsWatchDirectory: async (dirPath: string) => {
    const result = await ipcRenderer.invoke('fs-watch-directory', dirPath);
    if (result.success) return true;
    throw new Error(result.error);
  },

  // 停止监听目录变化
  fsUnwatchDirectory: async (dirPath: string) => {
    const result = await ipcRenderer.invoke('fs-unwatch-directory', dirPath);
    if (result.success) return true;
    throw new Error(result.error);
  },

  // 监听目录变化事件
  onFsDirectoryChanged: (callback: (data: { dirPath: string; eventType: string; filename: string }) => void) => {
    const handler = (_event: Electron.IpcRendererEvent, data: { dirPath: string; eventType: string; filename: string }) => {
      callback(data);
    };
    ipcRenderer.on('fs-directory-changed', handler);
    // 返回清理函数
    return () => {
      ipcRenderer.removeListener('fs-directory-changed', handler);
    };
  },

  // 文件系统操作 API
  fsCreateFile: async (filePath: string) => {
    const result = await ipcRenderer.invoke('fs-create-file', filePath);
    if (result.success) return true;
    throw new Error(result.error);
  },

  fsCreateFolder: async (dirPath: string) => {
    const result = await ipcRenderer.invoke('fs-create-folder', dirPath);
    if (result.success) return true;
    throw new Error(result.error);
  },

  fsRename: async (oldPath: string, newName: string) => {
    const result = await ipcRenderer.invoke('fs-rename', oldPath, newName);
    if (result.success) return result.newPath;
    throw new Error(result.error);
  },

  fsDelete: async (targetPath: string) => {
    const result = await ipcRenderer.invoke('fs-delete', targetPath);
    if (result.success) return true;
    throw new Error(result.error);
  },

  fsCopy: async (sourcePath: string, destPath: string) => {
    const result = await ipcRenderer.invoke('fs-copy', sourcePath, destPath);
    if (result.success) return result.newPath;
    throw new Error(result.error);
  },

  fsMove: async (sourcePath: string, destPath: string) => {
    const result = await ipcRenderer.invoke('fs-move', sourcePath, destPath);
    if (result.success) return result.newPath;
    throw new Error(result.error);
  },

  fsReadFile: async (filePath: string) => {
    const result = await ipcRenderer.invoke('fs-read-file', filePath);
    if (result.success) return result;
    throw new Error(result.error);
  },

  fsWriteFile: async (filePath: string, content: string, encoding?: string) => {
    const result = await ipcRenderer.invoke('fs-write-file', filePath, content, encoding);
    if (result.success) return result;
    throw new Error(result.error);
  },

  fsShowInFolder: async (filePath: string) => {
    const result = await ipcRenderer.invoke('fs-show-in-folder', filePath);
    if (result.success) return true;
    throw new Error(result.error);
  },

  fsOpenWithDefaultApp: async (filePath: string) => {
    const result = await ipcRenderer.invoke('fs-open-with-default-app', filePath);
    if (result.success) return true;
    throw new Error(result.error);
  },

  fsGetClipboardFilePaths: async () => {
    const result = await ipcRenderer.invoke('fs-get-clipboard-file-paths');
    if (result.success) return { paths: result.paths as string[], operation: result.operation as 'copy' | 'cut' };
    throw new Error(result.error);
  },

  // ==================== Recording API ====================
  recorderRefreshSources: async () => {
    const result = await ipcRenderer.invoke('recorder:refreshSources');
    if (result.success) return result.sources as any[];
    throw new Error(result.error || 'Failed to refresh sources');
  },
  recorderStart: async (args?: { sourceId?: string; title?: string }) => {
    const result = await ipcRenderer.invoke('recorder:start', args || {});
    if (result.success) return true;
    return false;
  },
  recorderInitiateStop: async () => {
    const result = await ipcRenderer.invoke('recorder:initiateStop');
    return result as { success: boolean; filePath?: string };
  },
  recorderGetStopStatus: async () => {
    const result = await ipcRenderer.invoke('recorder:getStopStatus');
    if (result.success) return result.data as any;
    throw new Error(result.error || 'Failed to get stop status');
  },
  recorderGetStatus: async () => {
    const result = await ipcRenderer.invoke('recorder:getStatus');
    if (result.success) return result.status as any;
    throw new Error(result.error || 'Failed to get status');
  },
  onRecordingStopComplete: (callback: (payload: any) => void) => {
    const handler = (_event: Electron.IpcRendererEvent, payload: any) => callback(payload);
    ipcRenderer.on('recording-stop-complete', handler);
    return () => ipcRenderer.removeListener('recording-stop-complete', handler);
  },
  onRecordingStopInitiated: (callback: (payload: any) => void) => {
    const handler = (_event: Electron.IpcRendererEvent, payload: any) => callback(payload);
    ipcRenderer.on('recording-stop-initiated', handler);
    return () => ipcRenderer.removeListener('recording-stop-initiated', handler);
  },

  // ==================== S3 Presigned Upload ====================
  uploadPresignedPut: async (args: { requestId: string; filePath: string; uploadUrl: string; method?: string; headers?: Record<string, string> }) => {
    const result = await ipcRenderer.invoke('s3:uploadPresignedPut', args);
    return result as { success: boolean; etag?: string; error?: string };
  },
  onS3UploadProgress: (callback: (payload: { requestId: string; loaded: number; total: number; percent: number }) => void) => {
    const handler = (_event: Electron.IpcRendererEvent, payload: any) => callback(payload);
    ipcRenderer.on('s3:upload-progress', handler);
    return () => ipcRenderer.removeListener('s3:upload-progress', handler);
  },

  // ==================== 电脑池管理 API ====================

  // 获取电脑池（所有电脑 + 状态）
  computerPoolGet: async () => {
    const result = await ipcRenderer.invoke('computer-pool-get');
    if (result.success) return result.pool;
    throw new Error(result.error);
  },

  // 获取单个电脑配置
  computerPoolGetComputer: async (name: string) => {
    const result = await ipcRenderer.invoke('computer-pool-get-computer', name);
    if (result.success) return result.computer;
    throw new Error(result.error);
  },

  // 检查电脑状态
  computerPoolCheckStatus: async (name: string) => {
    const result = await ipcRenderer.invoke('computer-pool-check-status', name);
    if (result.success) return { status: result.status, resolvedHost: result.resolvedHost };
    throw new Error(result.error);
  },

  // 获取电脑的 Local Engine URL
  computerPoolGetLocalEngineUrl: async (name: string) => {
    const result = await ipcRenderer.invoke('computer-pool-get-local-engine-url', name);
    if (result.success) return result.url;
    throw new Error(result.error);
  },

  // 获取上次使用的电脑
  computerPoolGetLastUsed: async () => {
    const result = await ipcRenderer.invoke('computer-pool-get-last-used');
    if (result.success) return result.computer;
    throw new Error(result.error);
  },

  // 设置上次使用的电脑
  computerPoolSetLastUsed: async (name: string) => {
    const result = await ipcRenderer.invoke('computer-pool-set-last-used', name);
    if (result.success) return true;
    throw new Error(result.error);
  },

  // 绑定 Session 到电脑
  computerPoolBindSession: async (chatId: string, computerName: string) => {
    const result = await ipcRenderer.invoke('computer-pool-bind-session', chatId, computerName);
    if (result.success) return true;
    throw new Error(result.error);
  },

  // 解绑 Session
  computerPoolUnbindSession: async (chatId: string) => {
    const result = await ipcRenderer.invoke('computer-pool-unbind-session', chatId);
    if (result.success) return true;
    throw new Error(result.error);
  },

  // 获取 Session 绑定的电脑
  computerPoolGetSessionComputer: async (chatId: string) => {
    const result = await ipcRenderer.invoke('computer-pool-get-session-computer', chatId);
    if (result.success) return result.computer;
    throw new Error(result.error);
  },

  // 检查电脑是否被占用
  computerPoolIsOccupied: async (computerName: string) => {
    const result = await ipcRenderer.invoke('computer-pool-is-occupied', computerName);
    if (result.success) return { occupied: result.occupied, occupiedBy: result.occupiedBy };
    throw new Error(result.error);
  },

  // 添加到队列
  computerPoolAddToQueue: async (chatId: string, computerName: string) => {
    const result = await ipcRenderer.invoke('computer-pool-add-to-queue', chatId, computerName);
    if (result.success) return result.position;
    throw new Error(result.error);
  },

  // 从队列移除
  computerPoolRemoveFromQueue: async (chatId: string) => {
    const result = await ipcRenderer.invoke('computer-pool-remove-from-queue', chatId);
    if (result.success) return true;
    throw new Error(result.error);
  },

  // 获取队列位置
  computerPoolGetQueuePosition: async (chatId: string, computerName: string) => {
    const result = await ipcRenderer.invoke('computer-pool-get-queue-position', chatId, computerName);
    if (result.success) return result.position;
    throw new Error(result.error);
  },

  // 打开配置文件
  computerPoolOpenConfig: async () => {
    const result = await ipcRenderer.invoke('computer-pool-open-config');
    if (result.success) return true;
    throw new Error(result.error);
  },

  // 重新加载配置
  computerPoolReloadConfig: async () => {
    const result = await ipcRenderer.invoke('computer-pool-reload-config');
    if (result.success) return true;
    throw new Error(result.error);
  },

  // 监听电脑状态变化
  onComputerStatusChanged: (callback: (data: { computerName: string; status: string; resolvedHost?: string }) => void) => {
    const handler = (_event: Electron.IpcRendererEvent, data: any) => callback(data);
    ipcRenderer.on('computer-status-changed', handler);
    return () => ipcRenderer.removeListener('computer-status-changed', handler);
  },

  // ==================== S3 Presigned Download ====================
  
  downloadPresignedGet: async (args: { requestId: string; filePath: string; downloadUrl: string; headers?: Record<string, string> }) => {
    const result = await ipcRenderer.invoke('s3:downloadPresignedGet', args);
    return result as { success: boolean; error?: string };
  },
  onS3DownloadProgress: (callback: (payload: { requestId: string; loaded: number; total: number; percent: number }) => void) => {
    const handler = (_event: Electron.IpcRendererEvent, payload: any) => callback(payload);
    ipcRenderer.on('s3:download-progress', handler);
    return () => ipcRenderer.removeListener('s3:download-progress', handler);
  },

  // ==================== File Metadata ====================
  getFileMetadata: async (filePath: string) => {
    const result = await ipcRenderer.invoke('fs:getFileMetadata', filePath);
    return result as { size: number; lastModified: number; etag?: string } | null;
  },

  // ==================== OAuth 登录 ====================
  startGoogleOAuth: async (oauthUrl: string) => {
    const result = await ipcRenderer.invoke('oauth:startGoogleLogin', oauthUrl);
    return result as { success: boolean; url?: string; error?: string };
  },

  // ==================== API Key 本地存储 ====================
  saveApiKey: async (args: { provider: string; apiKey: string; isEnabled: boolean; exclusive?: boolean }) => {
    const result = await ipcRenderer.invoke('save-api-key', args);
    if (result.success) return true;
    throw new Error(result.error);
  },
  loadApiKeys: async (): Promise<Record<string, { apiKey: string; savedAt: string }>> => {
    const result = await ipcRenderer.invoke('load-api-keys');
    if (result.success) return result.providers;
    throw new Error(result.error);
  },
  deleteApiKey: async (provider: string) => {
    const result = await ipcRenderer.invoke('delete-api-key', { provider });
    if (result.success) return true;
    throw new Error(result.error);
  },
  updateProviderEnabled: async (args: { provider: string; isEnabled: boolean; exclusive?: boolean }) => {
    const result = await ipcRenderer.invoke('update-provider-enabled', args);
    if (result.success) return true;
    throw new Error(result.error);
  },

  // ==================== Dev Tools ====================
  toggleDevTools: () => ipcRenderer.send('toggle-dev-tools'),

  // ==================== Auto Updater ====================
  onUpdateProgress: (callback: (data: { percent: string | number; status: string }) => void) => {
    const handler = (_event: Electron.IpcRendererEvent, data: any) => callback(data);
    ipcRenderer.on('update-download-progress', handler);
    return () => ipcRenderer.removeListener('update-download-progress', handler);
  },
});
