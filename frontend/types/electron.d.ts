export {};

declare global {
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

      // OAuth 登录
      startGoogleOAuth?: (oauthUrl: string) => Promise<{ success: boolean; url?: string; error?: string }>;

      // Dev Tools
      toggleDevTools: () => void;
    };
  }
}
