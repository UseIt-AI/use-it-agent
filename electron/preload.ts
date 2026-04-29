import { contextBridge, ipcRenderer } from 'electron';


export interface Project {
  id: string;
  name: string;
  path: string;
  lastModified: number;
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
