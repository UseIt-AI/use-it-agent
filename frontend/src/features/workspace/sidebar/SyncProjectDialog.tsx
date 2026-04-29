import { AlertCircle, Cloud, Loader2 } from "lucide-react";
import { useCallback, useState } from "react";
import { LOCAL_OFFLINE_USER_ID } from "@/services/localOfflineStore";

interface SyncProjectDialogProps {
  project: { id: string; name: string };
  onClose: () => void;
  onSyncComplete: () => void;
}

export function SyncProjectDialog({ project, onClose, onSyncComplete }: SyncProjectDialogProps) {
  const [isSyncing, setIsSyncing] = useState(false);
  const [syncProgress, setSyncProgress] = useState(0);
  const [downloadedCount, setDownloadedCount] = useState(0);
  const [totalCount, setTotalCount] = useState(0);
  const [currentFile, setCurrentFile] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  const handleSync = useCallback(async () => {
    const electron = window.electron as any;
    if (!electron) {
      setError('Electron API 不可用');
      return;
    }

    setIsSyncing(true);
    setSyncProgress(0);
    setDownloadedCount(0);
    setTotalCount(0);
    setCurrentFile('');
    setError(null);
    setSuccessMessage(null);

    try {
      // 1. 确定本地基础路径
      setCurrentFile('正在创建本地项目目录...');
      let baseDir = '';

      // 优先用新路径结构：Documents/UseitAgent/useitid_xxx/projects
      try {
        const userId = LOCAL_OFFLINE_USER_ID;
        const documentsPath = await electron.getPath?.('documents');
        if (documentsPath) {
          const sep = documentsPath.includes('\\') ? '\\' : '/';
          baseDir = `${documentsPath}${sep}UseitAgent${sep}useitid_${userId}${sep}projects`;
        }
      } catch {
        // fall through to next strategy
      }

      // 回退：从已有项目配置推断
      if (!baseDir) {
        const config = await electron.getAppConfig?.();
        const projects = config?.projects ? Object.values(config.projects) : [];
        const firstProject = projects[0] as any;
        if (firstProject?.path) {
          const parts = firstProject.path.split(/[/\\]/);
          parts.pop();
          baseDir = parts.join(firstProject.path.includes('\\') ? '\\' : '/');
        }
      }

      if (!baseDir) {
        throw new Error('无法确定项目路径。请先创建一个本地项目，或联系管理员配置项目路径。');
      }

      const sep = baseDir.includes('\\') ? '\\' : '/';
      const projectPath = `${baseDir}${sep}${project.name}`;

      // 2. 创建项目目录及子目录
      for (const folder of ['', 'uploads', 'outputs', 'downloads', 'workspace']) {
        const path = folder ? `${projectPath}\\${folder}` : projectPath;
        try { await electron.fsCreateFolder?.(path); } catch { /* already exists */ }
      }

      // 3. 写入 project.json
      setCurrentFile('正在创建项目元数据...');
      try {
        const cuaDir = `${projectPath}${sep}.cua`;
        try { await electron.fsCreateFolder?.(cuaDir); } catch { /* already exists */ }

        const meta = {
          id: project.id,
          name: project.name,
          createdAt: Date.now(),
          version: '1.0',
        };
        await electron.fsWriteFile?.(
          `${cuaDir}${sep}project.json`,
          JSON.stringify(meta, null, 2),
          'utf-8'
        );
      } catch (e) {
        console.warn('[Sync] 写入 project.json 失败:', e);
      }

      // 4. 更新本地项目配置
      setCurrentFile('正在更新项目配置...');
      const config = await electron.getAppConfig?.();
      if (config && electron.setAppConfig) {
        const projects = config.projects || {};
        projects[project.id] = {
          id: project.id,
          name: project.name,
          path: projectPath,
          lastModified: Date.now(),
        };
        await electron.setAppConfig({ projects });
      }

      // 5. 本地模式：项目目录已就绪，不再从云端 batch-presign / 下载
      setCurrentFile('');
      setSuccessMessage('本地项目已创建完成（文件均在本地 projects 目录，无需从云端下载）');
      setIsSyncing(false);
      setTimeout(() => {
        onSyncComplete();
        onClose();
      }, 1500);
    } catch (e: any) {
      console.error('[Sync] 同步失败:', e);
      setError(e.message || '同步失败，请重试');
      setIsSyncing(false);
    }
  }, [project, onClose, onSyncComplete]);

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-white border border-black/20 shadow-lg max-w-md w-full mx-4 p-6">
        {/* Title */}
        <div className="flex items-center gap-3 mb-4">
          <Cloud className="w-5 h-5 text-blue-600" />
          <h3 className="text-base font-bold text-black/90">同步项目</h3>
        </div>

        {/* Description */}
        <p className="text-sm text-black/70 mb-1">
          在本地创建项目 <span className="font-bold">"{project.name}"</span>？
        </p>
        <p className="text-xs text-black/40 mb-4">将在本机 projects 目录下创建项目文件夹与元数据（不连接远程对象存储）。</p>

        {/* Progress */}
        {isSyncing && (
          <div className="mb-4 space-y-2">
            <div className="flex items-center justify-between text-xs text-black/60">
              <span className="truncate flex-1 mr-2">{currentFile || '准备中...'}</span>
              <span className="flex-shrink-0">{downloadedCount}/{totalCount}</span>
            </div>
            <div className="w-full bg-black/5 h-1.5">
              <div
                className="bg-blue-600 h-full transition-all duration-300"
                style={{ width: `${syncProgress}%` }}
              />
            </div>
            <div className="text-xs text-black/40 text-center">{syncProgress}%</div>
          </div>
        )}

        {/* Error */}
        {error && (
          <div className="mb-4 p-3 bg-red-50 border border-red-200 flex items-start gap-2 text-red-700 text-sm">
            <AlertCircle className="w-4 h-4 flex-shrink-0 mt-0.5" />
            <span>{error}</span>
          </div>
        )}

        {/* Success */}
        {successMessage && (
          <div className="mb-4 p-3 bg-green-50 border border-green-200 text-green-700 text-sm">
            {successMessage}
          </div>
        )}

        {/* Actions */}
        <div className="flex items-center justify-end gap-2">
          <button
            onClick={onClose}
            disabled={isSyncing}
            className="px-4 py-2 text-sm text-black/60 hover:text-black/80 hover:bg-black/5 transition-colors disabled:opacity-50"
          >
            取消
          </button>
          {!isSyncing && !successMessage && (
            <button
              onClick={handleSync}
              className="px-4 py-2 text-sm bg-blue-600 text-white hover:bg-blue-700 transition-colors font-medium flex items-center gap-2"
            >
              开始同步
            </button>
          )}
          {isSyncing && (
            <button disabled className="px-4 py-2 text-sm bg-blue-600 text-white opacity-70 flex items-center gap-2">
              <Loader2 className="w-3.5 h-3.5 animate-spin" />
              同步中...
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
