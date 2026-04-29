export {};

declare global {
  interface VmExistsResult {
    exists: boolean;
    vmName: string | null;
  }

  interface VmInstallProgress {
    step: string;
    stepIndex: number;
    totalSteps: number;
    percent: number;
    message: string;
    error?: string;
  }

  interface ServiceDeployProgress {
    step: string;
    stepIndex: number;
    totalSteps: number;
    percent: number;
    message: string;
    error?: string;
  }

  interface ServiceDeployConfig {
    vmName: string;
    username: string;
    password: string;
  }

  interface ServiceStatusConfig {
    vmName: string;
    serviceKey: 'local_engine' | 'computer_server';
  }

  interface ServiceControlConfig {
    vmName: string;
    serviceKey?: 'local_engine' | 'computer_server';
  }

  interface Project {
    id: string;
    name: string;
    path: string;
    lastModified: number;
    exists?: boolean; // 本地是否存在
  }

  interface Window {
    electron: {
      minimize: () => void;
      maximize?: () => void;
      toggleMaximize?: () => void;
      close: () => void;
      expandWindow?: () => void;
      shrinkWindow?: () => void;
      restoreWindowSize: () => void;
      // App config
      getAppConfig: (key?: string) => Promise<any>;
      setAppConfig?: (newConfig: any) => Promise<boolean>;
      getPath?: (name: string) => Promise<string>;
      // Project Management
      createProject: (name: string) => Promise<{ projectId: string; projectPath: string }>;
      getRecentProjects: () => Promise<Project[]>;
      openProject: (projectId: string) => Promise<Project>;
      importProjectFolder?: () => Promise<Project | null>;
      deleteProject: (projectId: string) => Promise<{ success: boolean; error?: string }>;
      showAddFilesToWorkspaceDialog?: () => Promise<{ canceled: boolean; filePaths: string[] }>;
      // VM 管理
      checkHyperVEnabled?: () => Promise<boolean>;
      checkVmExists?: (vmNamePattern: string) => Promise<VmExistsResult>;
      getVmIp?: (vmName: string) => Promise<string>;
      getVmStatus?: (vmName: string) => Promise<string>;
      startVm?: (vmName: string) => Promise<boolean>;
      stopVm?: (vmName: string) => Promise<boolean>;
      deleteVm?: (vmName: string) => Promise<boolean>;
      fixHyperVPermission?: () => Promise<boolean>;
      getVmSpecs?: (vmName: string) => Promise<any>;
      setVmSpecs?: (config: { vmName: string; cpuCores: number; memoryGB: number; isDynamicMemory: boolean }) => Promise<boolean>;
      ensureVmVnc?: (args: { vmName: string; username?: string; password?: string }) => Promise<{ vmName: string; installed: boolean; alreadyInstalled: boolean }>;
      // VM snapshots
      listVmSnapshots?: (vmName: string) => Promise<Array<{ Id: string; Name: string; ParentCheckpointId?: string; CreationTime?: string; CheckpointType?: string }>>;
      createVmSnapshot?: (args: { vmName: string; snapshotName: string; saveState: boolean }) => Promise<void>;
      restoreVmSnapshot?: (args: { vmName: string; snapshotId: string }) => Promise<void>;
      // VM export
      vmSelectExportDir?: () => Promise<{ path: string | null; canceled: boolean }>;
      vmExportToFolder?: (config: { vmName: string; exportDir: string }) => Promise<{ success: boolean; error?: string; vmName?: string; exportPath?: string }>;
      // VM 安装
      vmCheckEnvironment?: (installDir?: string) => Promise<any>;
      vmEnableHyperV?: () => Promise<{ success: boolean; needsReboot: boolean }>;
      vmSelectIso?: () => Promise<{ path: string | null; canceled: boolean }>;
      vmSelectInstallDir?: () => Promise<{ path: string | null; canceled: boolean }>;
      vmSelectRestoreDir?: () => Promise<{ path: string | null; canceled: boolean }>;
      vmValidateIso?: (isoPath: string) => Promise<{ valid: boolean; error?: string }>;
      vmInstall?: (config: any) => Promise<{ success: boolean; error?: string }>;
      vmRestoreFromFolder?: (config: { vmName?: string; folderPath: string }) => Promise<{ success: boolean; error?: string; vmName?: string; checkpointCount?: number; restoreMode?: string }>;
      vmInstallCancel?: () => Promise<void>;
      onVmInstallProgress?: (callback: (progress: VmInstallProgress) => void) => () => void;
      // 文件系统 API
      fsGetProjectRoot?: (projectId?: string) => Promise<string>;
      fsGetSkillsRoot?: (userId?: string) => Promise<string>;
      fsReadDirectory?: (dirPath: string) => Promise<any[]>;
      fsReadDirectoryTree?: (rootPath: string) => Promise<any>;
      fsWatchDirectory?: (dirPath: string) => Promise<boolean>;
      fsUnwatchDirectory?: (dirPath: string) => Promise<boolean>;
      onFsDirectoryChanged?: (callback: (data: { dirPath: string; eventType: string; filename: string }) => void) => () => void;
      // 文件系统操作 API
      fsCreateFile?: (filePath: string) => Promise<boolean>;
      fsCreateFolder?: (dirPath: string) => Promise<boolean>;
      fsRename?: (oldPath: string, newName: string) => Promise<string>;
      fsDelete?: (targetPath: string) => Promise<boolean>;
      fsCopy?: (sourcePath: string, destPath: string) => Promise<string>;
      fsMove?: (sourcePath: string, destPath: string) => Promise<string>;
      fsReadFile?: (filePath: string) => Promise<{ content: string; type: 'text' | 'image'; encoding?: string; size: number }>;
      fsWriteFile?: (filePath: string, content: string, encoding?: string) => Promise<{ size: number }>;
      fsShowInFolder?: (filePath: string) => Promise<boolean>;
      fsOpenWithDefaultApp?: (filePath: string) => Promise<boolean>;
      fsGetClipboardFilePaths?: () => Promise<{ paths: string[]; operation: 'copy' | 'cut' }>;

      // Recording API (Electron main-process)
      recorderRefreshSources?: () => Promise<Array<{ id: string; name: string; thumbnail: string }>>;
      recorderStart?: (args?: { sourceId?: string; title?: string }) => Promise<boolean>;
      recorderInitiateStop?: () => Promise<{ success: boolean; filePath?: string }>;
      recorderGetStopStatus?: () => Promise<{ isStopping: boolean; stopComplete: boolean; filePath?: string }>;
      recorderGetStatus?: () => Promise<{ isRecording: boolean; duration: number; filePath?: string; startTime?: string; isStopping?: boolean; stopComplete?: boolean }>;
      onRecordingStopComplete?: (callback: (payload: { filePath?: string; success: boolean; error?: string }) => void) => () => void;
      onRecordingStopInitiated?: (callback: (payload: { filePath?: string; stopping: boolean }) => void) => () => void;

      // S3 presigned upload (Electron main streams file)
      uploadPresignedPut?: (args: { requestId: string; filePath: string; uploadUrl: string; method?: string; headers?: Record<string, string> }) => Promise<{ success: boolean; etag?: string; error?: string }>;
      onS3UploadProgress?: (callback: (payload: { requestId: string; loaded: number; total: number; percent: number }) => void) => () => void;

      // Service Deployment API (VM 服务部署)
      serviceHasFiles?: () => Promise<boolean>;
      serviceGetLocalVersion?: () => Promise<{ success: boolean; version?: string }>;
      serviceDeploy?: (config: ServiceDeployConfig) => Promise<{ success: boolean; error?: string }>;
      serviceCheckStatus?: (config: ServiceStatusConfig) => Promise<{ success: boolean; status: { installed: boolean; version?: string }; error?: string }>;
      serviceStart?: (config: ServiceControlConfig) => Promise<{ success: boolean; error?: string }>;
      serviceStop?: (config: ServiceControlConfig) => Promise<{ success: boolean; error?: string }>;
      serviceRestart?: (config: ServiceControlConfig) => Promise<{ success: boolean; error?: string }>;
      serviceGetLogs?: (config: ServiceStatusConfig & { lines?: number }) => Promise<string>;
      onServiceDeployProgress?: (callback: (progress: ServiceDeployProgress) => void) => () => void;

      // VM 共享文件夹 (projects 父目录挂载为 Z: 盘)
      vmShareEnsure?: (config: {
        vmName: string;
        username?: string;
        password?: string;
        projectsRootPath: string;
      }) => Promise<{ success: boolean; driveLetter: string; error?: string }>;
      vmShareHealth?: (config: {
        vmName: string;
        username?: string;
        password?: string;
      }) => Promise<{ success: boolean; healthy: boolean; shareExists?: boolean; driveMapped?: boolean; error?: string }>;
      vmShareTeardown?: (config: {
        vmName: string;
        username?: string;
        password?: string;
      }) => Promise<{ success: boolean; error?: string }>;
      vmShareGetVmPath?: (projectName: string) => Promise<string>;

      // OAuth 登录
      startGoogleOAuth?: (oauthUrl: string) => Promise<{ success: boolean; url?: string; error?: string }>;
      
      // Dev Tools
      toggleDevTools: () => void;
    };
  }
}

