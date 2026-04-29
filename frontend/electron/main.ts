import { app, BrowserWindow, shell, ipcMain, dialog, clipboard, session } from 'electron';
import * as path from 'path';
import * as fs from 'fs';
import { exec, execSync } from 'child_process';
import { promisify } from 'util';
import { RecorderService } from './recorder/recorder-service';
import { registerRecorderIpc } from './recorder/ipc';
import { uploadFileToPresignedPut } from './services/presignedUploader';
import { ensureLocalEngineRunning, stopLocalEngine } from './services/localEngineManager';
import { getComputerPoolManager } from './services/computerPoolManager';
import { downloadFileFromPresignedGet, getFileMetadata } from './services/presignedDownloader';
import { initIpcHandles } from './ipcHandle';
import { loadConfig, saveConfig } from './ipcHandle/appConfigIpcHandle';
initIpcHandles();

const execAsync = promisify(exec);

// ==================== 全局异常安全网 ====================
// 捕获未处理的异常和 Promise 拒绝，避免弹出错误对话框导致应用看似崩溃
// 常见场景：文件被 Office COM 锁定时的 EPERM 错误
process.on('uncaughtException', (error) => {
  console.error('[Main] Uncaught Exception:', error);
  // 对于文件锁定类错误，仅记录日志不弹框
  if (error && ('code' in error) && ['EPERM', 'EBUSY', 'EACCES'].includes((error as any).code)) {
    console.warn('[Main] File access error (likely locked by another process), suppressed dialog.');
    return;
  }
  // 其他未知异常仍显示对话框，但不中断进程
  console.error('[Main] Unexpected uncaught exception, process continues.');
});

process.on('unhandledRejection', (reason) => {
  console.error('[Main] Unhandled Rejection:', reason);
});

// Dev: Chromium 磁盘 HTTP 缓存损坏时会出现 net::ERR_CACHE_READ_FAILURE，Vite chunk 加载失败导致白屏。
// 必须在 app ready 之前设置；开发态关闭 HTTP 缓存并启动时清一次缓存更稳。
if (!app.isPackaged) {
  app.commandLine.appendSwitch('disable-http-cache');
}

// Recorder (main-process)
const recorderService = new RecorderService();

// 获取项目根目录路径
const getProjectRootPath = (projectId?: string): string => {
  const config = loadConfig();

  // 如果提供了 projectId，尝试从配置中查找路径
  if (projectId && config.projects && config.projects[projectId]) {
    return config.projects[projectId].path;
  }

  // 此时如果没有 projectId，或者 projectId 无效，尝试使用 lastOpenedProjectId
  if (!projectId && config.lastOpenedProjectId && config.projects && config.projects[config.lastOpenedProjectId]) {
    return config.projects[config.lastOpenedProjectId].path;
  }

  // Fallback: 默认开发目录 (保持旧逻辑兼容)
  const isDev = !app.isPackaged;
  let appRoot: string;

  if (isDev) {
    appRoot = path.resolve(__dirname, '../../..');
  } else {
    appRoot = path.resolve(process.resourcesPath, '..');
  }

  const workspaceDir = path.join(appRoot, 'workspace');
  if (!fs.existsSync(workspaceDir)) {
    fs.mkdirSync(workspaceDir, { recursive: true });
  }

  return workspaceDir;
};


function createWindow() {
  // 16:9 比例，增大尺寸至 1340x810
  const windowWidth = 1340;
  const windowHeight = 810;

  const win = new BrowserWindow({
    width: windowWidth,
    height: windowHeight,
    center: true, // 居中显示
    minWidth: 360, // 允许更窄的宽度，支持侧边栏模式
    minHeight: 400,
    frame: false, // 无边框模式
    titleBarStyle: 'hidden',
    transparent: false, // 关闭透明以恢复 Windows Aero Snap
    backgroundColor: '#F8F9FA', // 与内联骨架背景一致，避免白色闪烁
    hasShadow: true,
    thickFrame: true,
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      preload: path.join(__dirname, 'preload.js'),
    },
  });

  const isDev = !app.isPackaged;
  // 仅在开发环境下打开 DevTools，生产环境不打开
  const isDebugMode = isDev;

  // 打包后 __dirname = app.asar/dist/main/electron
  // 需要往上 2 级到 dist，再进入 renderer
  // 与 vite.config.ts server.host 一致（127.0.0.1），避免 localhost -> IPv6 等与 dev server 不一致
  const url = isDev
    ? 'http://127.0.0.1:3000'
    : `file://${path.join(__dirname, '../../renderer/index.html')}`; // dist/main/electron -> dist/renderer

  console.log(`[Main] Loading URL: ${url}`);
  console.log(`[Main] Debug mode: ${isDebugMode}, isDev: ${isDev}, isPackaged: ${app.isPackaged}`);
  console.log(`[Main] __dirname: ${__dirname}`);
  console.log(`[Main] process.resourcesPath: ${process.resourcesPath}`);

  // 加载失败重试 + 打开 DevTools 便于定位渲染层报错
  win.webContents.on('did-fail-load', (_e, errorCode, errorDescription, validatedURL) => {
    console.error('[Renderer] did-fail-load:', { errorCode, errorDescription, validatedURL });
    // 无论开发还是生产，都尝试重试一次
    setTimeout(() => {
      console.log('[Renderer] Retrying to load URL...');
      win.loadURL(url).catch((err) => console.error('[Renderer] reload failed:', err));
    }, 500);
  });

  win.loadURL(url).catch((err) => {
    console.error('[Renderer] loadURL failed:', err);
  });

  // 捕获渲染进程的控制台输出到主进程日志
  win.webContents.on('console-message', (_event, level, message, line, sourceId) => {
    const levelStr = ['verbose', 'info', 'warning', 'error'][level] || 'log';
    console.log(`[Renderer ${levelStr}] ${message} (${sourceId}:${line})`);
  });

  // F12 隐藏快捷键：连按三下打开 DevTools，单按一下关闭
  let f12PressCount = 0;
  let f12ResetTimer: ReturnType<typeof setTimeout> | null = null;
  win.webContents.on('before-input-event', (_event, input) => {
    if (input.type !== 'keyDown' || input.key !== 'F12') return;
    if (win.webContents.isDevToolsOpened()) {
      win.webContents.closeDevTools();
      f12PressCount = 0;
      return;
    }
    f12PressCount += 1;
    if (f12ResetTimer) clearTimeout(f12ResetTimer);
    if (f12PressCount >= 3) {
      win.webContents.openDevTools({ mode: 'detach' });
      f12PressCount = 0;
    } else {
      f12ResetTimer = setTimeout(() => { f12PressCount = 0; }, 600);
    }
  });

  // Open external links in default browser
  win.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url);
    return { action: 'deny' };
  });

  // ==================== 文件系统 API ====================

  // 存储文件监听器
  const fileWatchers = new Map<string, fs.FSWatcher>();

  // 获取项目根目录（带 projectId 参数）
  ipcMain.removeAllListeners('fs-get-project-root');
  ipcMain.handle('fs-get-project-root', async (_event, projectId?: string) => {
    try {
      const rootPath = getProjectRootPath(projectId);
      return { success: true, path: rootPath };
    } catch (error: any) {
      return { success: false, error: error.message };
    }
  });

  // 获取 Skills 根目录（Documents/UseitAgent/useitid_xxx/skills）
  ipcMain.removeAllListeners('fs-get-skills-root');
  ipcMain.handle('fs-get-skills-root', async (_event, userId?: string) => {
    try {
      const documentsPath = app.getPath('documents');
      const baseDir = userId
        ? path.join(documentsPath, 'UseitAgent', `useitid_${userId}`, 'skills')
        : path.join(documentsPath, 'UseitAgent', 'skills');
      fs.mkdirSync(baseDir, { recursive: true });
      return { success: true, path: baseDir };
    } catch (error: any) {
      return { success: false, error: error.message };
    }
  });

  // 读取目录结构
  ipcMain.removeAllListeners('fs-read-directory');
  ipcMain.handle('fs-read-directory', async (_event, dirPath: string) => {
    try {
      // 确保路径是绝对路径
      const absolutePath = path.isAbsolute(dirPath) ? dirPath : path.resolve(dirPath);

      if (!absolutePath || !fs.existsSync(absolutePath)) {
        return { success: false, error: 'Directory does not exist' };
      }

      const stats = fs.statSync(absolutePath);
      if (!stats.isDirectory()) {
        return { success: false, error: 'Path is not a directory' };
      }

      const entries = fs.readdirSync(absolutePath, { withFileTypes: true });
      const children = entries
        .filter(entry => {
          // 过滤掉隐藏文件和系统文件
          const name = entry.name;
          return !name.startsWith('.') && name !== 'node_modules';
        })
        .map(entry => {
          const fullPath = path.join(absolutePath, entry.name);
          const stats = fs.statSync(fullPath);
          return {
            name: entry.name,
            type: entry.isDirectory() ? 'folder' : 'file',
            path: fullPath,
            size: stats.isFile() ? stats.size : undefined,
            modified: stats.mtime.getTime(),
            children: entry.isDirectory() ? [] : undefined,
          };
        })
        .sort((a, b) => {
          // 文件夹排在前面，然后按名称排序
          if (a.type !== b.type) {
            return a.type === 'folder' ? -1 : 1;
          }
          return a.name.localeCompare(b.name);
        });

      return { success: true, children };
    } catch (error: any) {
      return { success: false, error: error.message };
    }
  });

  // 递归读取目录树
  const readDirectoryTree = (dirPath: string, maxDepth: number = 10, currentDepth: number = 0): any => {
    if (currentDepth >= maxDepth) {
      return null;
    }

    try {
      // 确保路径是绝对路径
      const absolutePath = path.isAbsolute(dirPath) ? dirPath : path.resolve(dirPath);

      if (!fs.existsSync(absolutePath)) {
        return null;
      }

      const stats = fs.statSync(absolutePath);
      if (!stats.isDirectory()) {
        return null;
      }

      const entries = fs.readdirSync(absolutePath, { withFileTypes: true });
      const children = entries
        .filter(entry => {
          const name = entry.name;
          return !name.startsWith('.') && name !== 'node_modules';
        })
        .map(entry => {
          const fullPath = path.join(dirPath, entry.name);
          const stats = fs.statSync(fullPath);

          if (entry.isDirectory()) {
            const childTree = readDirectoryTree(fullPath, maxDepth, currentDepth + 1);
            return {
              name: entry.name,
              type: 'folder' as const,
              path: fullPath,
              children: childTree?.children || [],
            };
          } else {
            return {
              name: entry.name,
              type: 'file' as const,
              path: fullPath,
              size: stats.size,
              modified: stats.mtime.getTime(),
            };
          }
        })
        .sort((a, b) => {
          if (a.type !== b.type) {
            return a.type === 'folder' ? -1 : 1;
          }
          return a.name.localeCompare(b.name);
        });

      return { children };
    } catch (error) {
      console.error(`Error reading directory ${dirPath}:`, error);
      return null;
    }
  };

  // 读取完整目录树
  ipcMain.removeAllListeners('fs-read-directory-tree');
  ipcMain.handle('fs-read-directory-tree', async (_event, rootPath: string) => {
    try {
      // 如果 rootPath 是相对路径或 'workspace'，使用默认 workspace 目录
      let absolutePath: string;
      if (!rootPath || rootPath === 'workspace' || rootPath.startsWith('backend/')) {
        // 使用默认 workspace 目录
        absolutePath = getProjectRootPath();
      } else {
        absolutePath = path.isAbsolute(rootPath) ? rootPath : path.resolve(rootPath);
      }

      if (!fs.existsSync(absolutePath)) {
        return { success: false, error: 'Directory does not exist' };
      }

      const stats = fs.statSync(absolutePath);
      if (!stats.isDirectory()) {
        return { success: false, error: 'Path is not a directory' };
      }

      const tree = readDirectoryTree(absolutePath);
      if (!tree) {
        return { success: false, error: 'Failed to read directory tree' };
      }

      // 构建根节点
      const rootName = path.basename(absolutePath) || 'PROJECT_ROOT';
      const rootNode = {
        name: rootName,
        type: 'folder' as const,
        path: absolutePath,
        children: tree.children || [],
      };

      return { success: true, tree: rootNode };
    } catch (error: any) {
      return { success: false, error: error.message };
    }
  });

  // 开始监听目录变化
  ipcMain.removeAllListeners('fs-watch-directory');
  ipcMain.handle('fs-watch-directory', async (_event, dirPath: string) => {
    try {
      // 确保路径是绝对路径
      let absolutePath: string;
      if (!dirPath || dirPath === 'workspace' || dirPath.startsWith('backend/')) {
        // 使用默认 workspace 目录
        absolutePath = getProjectRootPath();
      } else {
        absolutePath = path.isAbsolute(dirPath) ? dirPath : path.resolve(dirPath);
      }

      if (!fs.existsSync(absolutePath)) {
        return { success: false, error: 'Directory does not exist' };
      }

      // 如果已经监听，先停止旧的监听器
      if (fileWatchers.has(absolutePath)) {
        fileWatchers.get(absolutePath)?.close();
        fileWatchers.delete(absolutePath);
      }

      // 创建新的监听器
      const watcher = fs.watch(absolutePath, { recursive: true }, (eventType, filename) => {
        if (filename) {
          win.webContents.send('fs-directory-changed', {
            dirPath: absolutePath,
            eventType,
            filename,
          });
        }
      });

      fileWatchers.set(absolutePath, watcher);
      return { success: true };
    } catch (error: any) {
      return { success: false, error: error.message };
    }
  });

  // 停止监听目录变化
  ipcMain.removeAllListeners('fs-unwatch-directory');
  ipcMain.handle('fs-unwatch-directory', async (_event, dirPath: string) => {
    try {
      const watcher = fileWatchers.get(dirPath);
      if (watcher) {
        watcher.close();
        fileWatchers.delete(dirPath);
        return { success: true };
      }
      return { success: true, message: 'Watcher not found' };
    } catch (error: any) {
      return { success: false, error: error.message };
    }
  });

  // 清理所有监听器（窗口关闭时）
  win.on('closed', () => {
    fileWatchers.forEach(watcher => watcher.close());
    fileWatchers.clear();
  });

  // ==================== 电脑池管理 API ====================

  const computerPoolManager = getComputerPoolManager();

  // 获取电脑池
  ipcMain.removeAllListeners('computer-pool-get');
  ipcMain.handle('computer-pool-get', async () => {
    try {
      console.log('[IPC] computer-pool-get called');
      const pool = await computerPoolManager.getComputerPool();
      console.log('[IPC] computer-pool-get result:', {
        computersCount: pool?.computers?.length,
        state: pool?.state
      });
      return { success: true, pool };
    } catch (error: any) {
      console.error('[IPC] computer-pool-get error:', error);
      return { success: false, error: error.message };
    }
  });

  // 获取单个电脑配置
  ipcMain.removeAllListeners('computer-pool-get-computer');
  ipcMain.handle('computer-pool-get-computer', async (_event, name: string) => {
    try {
      const computer = computerPoolManager.getComputer(name);
      return { success: true, computer };
    } catch (error: any) {
      return { success: false, error: error.message };
    }
  });

  // 检查电脑状态
  ipcMain.removeAllListeners('computer-pool-check-status');
  ipcMain.handle('computer-pool-check-status', async (_event, name: string) => {
    try {
      const { status, resolvedHost } = await computerPoolManager.checkComputerStatus(name);
      return { success: true, status, resolvedHost };
    } catch (error: any) {
      return { success: false, error: error.message };
    }
  });

  // 获取电脑的 Local Engine URL
  ipcMain.removeAllListeners('computer-pool-get-local-engine-url');
  ipcMain.handle('computer-pool-get-local-engine-url', async (_event, name: string) => {
    try {
      const url = await computerPoolManager.getLocalEngineUrl(name);
      return { success: true, url };
    } catch (error: any) {
      return { success: false, error: error.message };
    }
  });

  // 获取上次使用的电脑
  ipcMain.removeAllListeners('computer-pool-get-last-used');
  ipcMain.handle('computer-pool-get-last-used', async () => {
    try {
      const computer = computerPoolManager.getLastUsedComputer();
      return { success: true, computer };
    } catch (error: any) {
      return { success: false, error: error.message };
    }
  });

  // 设置上次使用的电脑
  ipcMain.removeAllListeners('computer-pool-set-last-used');
  ipcMain.handle('computer-pool-set-last-used', async (_event, name: string) => {
    try {
      computerPoolManager.setLastUsedComputer(name);
      return { success: true };
    } catch (error: any) {
      return { success: false, error: error.message };
    }
  });

  // 绑定 Session 到电脑
  ipcMain.removeAllListeners('computer-pool-bind-session');
  ipcMain.handle('computer-pool-bind-session', async (_event, chatId: string, computerName: string) => {
    try {
      computerPoolManager.bindSession(chatId, computerName);
      // 通知状态变化
      win.webContents.send('computer-status-changed', {
        computerName,
        status: 'busy',
      });
      return { success: true };
    } catch (error: any) {
      return { success: false, error: error.message };
    }
  });

  // 解绑 Session
  ipcMain.removeAllListeners('computer-pool-unbind-session');
  ipcMain.handle('computer-pool-unbind-session', async (_event, chatId: string) => {
    try {
      const computerName = computerPoolManager.getSessionComputer(chatId);
      computerPoolManager.unbindSession(chatId);
      // 通知状态变化
      if (computerName) {
        const { status } = await computerPoolManager.checkComputerStatus(computerName);
        win.webContents.send('computer-status-changed', {
          computerName,
          status,
        });
      }
      return { success: true };
    } catch (error: any) {
      return { success: false, error: error.message };
    }
  });

  // 获取 Session 绑定的电脑
  ipcMain.removeAllListeners('computer-pool-get-session-computer');
  ipcMain.handle('computer-pool-get-session-computer', async (_event, chatId: string) => {
    try {
      const computer = computerPoolManager.getSessionComputer(chatId);
      return { success: true, computer };
    } catch (error: any) {
      return { success: false, error: error.message };
    }
  });

  // 检查电脑是否被占用
  ipcMain.removeAllListeners('computer-pool-is-occupied');
  ipcMain.handle('computer-pool-is-occupied', async (_event, computerName: string) => {
    try {
      const occupied = computerPoolManager.isComputerOccupied(computerName);
      const occupiedBy = computerPoolManager.getOccupyingSession(computerName);
      return { success: true, occupied, occupiedBy };
    } catch (error: any) {
      return { success: false, error: error.message };
    }
  });

  // 添加到队列
  ipcMain.removeAllListeners('computer-pool-add-to-queue');
  ipcMain.handle('computer-pool-add-to-queue', async (_event, chatId: string, computerName: string) => {
    try {
      const position = computerPoolManager.addToQueue(chatId, computerName);
      return { success: true, position };
    } catch (error: any) {
      return { success: false, error: error.message };
    }
  });

  // 从队列移除
  ipcMain.removeAllListeners('computer-pool-remove-from-queue');
  ipcMain.handle('computer-pool-remove-from-queue', async (_event, chatId: string) => {
    try {
      computerPoolManager.removeFromQueue(chatId);
      return { success: true };
    } catch (error: any) {
      return { success: false, error: error.message };
    }
  });

  // 获取队列位置
  ipcMain.removeAllListeners('computer-pool-get-queue-position');
  ipcMain.handle('computer-pool-get-queue-position', async (_event, chatId: string, computerName: string) => {
    try {
      const position = computerPoolManager.getQueuePosition(chatId, computerName);
      return { success: true, position };
    } catch (error: any) {
      return { success: false, error: error.message };
    }
  });

  // 打开配置文件
  ipcMain.removeAllListeners('computer-pool-open-config');
  ipcMain.handle('computer-pool-open-config', async () => {
    try {
      computerPoolManager.openConfigFile();
      return { success: true };
    } catch (error: any) {
      return { success: false, error: error.message };
    }
  });

  // 重新加载配置
  ipcMain.removeAllListeners('computer-pool-reload-config');
  ipcMain.handle('computer-pool-reload-config', async () => {
    try {
      computerPoolManager.reloadConfig();
      return { success: true };
    } catch (error: any) {
      return { success: false, error: error.message };
    }
  });

  // ==================== 文件系统操作 API ====================

  // 从系统剪贴板读取文件路径（支持 Windows File Explorer 的复制/剪切）
  ipcMain.removeAllListeners('fs-get-clipboard-file-paths');
  ipcMain.handle('fs-get-clipboard-file-paths', async () => {
    try {
      const parsePathList = (buffer: Buffer): string[] => {
        if (!buffer || buffer.length === 0) return [];

        // 优先按 DROPFILES 结构解析（Windows CF_HDROP）
        // typedef struct _DROPFILES {
        //   DWORD pFiles; POINT pt; BOOL fNC; BOOL fWide;
        // } DROPFILES;
        if (buffer.length >= 20) {
          const pFiles = buffer.readUInt32LE(0);
          const fWide = buffer.readUInt32LE(16) !== 0;
          if (pFiles >= 20 && pFiles < buffer.length) {
            const payload = buffer.subarray(pFiles);
            const raw = fWide ? payload.toString('utf16le') : payload.toString('utf8');
            const parsed = raw
              .split('\u0000')
              .map(item => item.trim())
              .filter(item => !!item && /[\\/]/.test(item));
            if (parsed.length > 0) return parsed;
          }
        }

        // 兜底：某些环境下直接给 UTF-16 路径列表
        const rawFallback = buffer.toString('utf16le');
        return rawFallback
          .split('\u0000')
          .map(item => item.trim())
          .filter(item => !!item && /[\\/]/.test(item));
      };

      const fileNameW = clipboard.readBuffer('FileNameW');
      let paths = parsePathList(fileNameW);

      // Windows Explorer 多选复制增强：通过 PowerShell FileDropList 获取列表，
      // 与原始解析结果合并，优先使用更完整的数据。
      if (process.platform === 'win32') {
        try {
          const ps = execSync(
            'powershell -NoProfile -Command "Get-Clipboard -Format FileDropList | ForEach-Object { $_.ToString() }"',
            { encoding: 'utf8', windowsHide: true }
          );
          const psPaths = String(ps || '')
            .split(/\r?\n/)
            .map(item => item.trim())
            .filter(item => !!item && /[\\/]/.test(item));
          if (psPaths.length > 0) {
            const merged = Array.from(new Set([...paths, ...psPaths]));
            paths = merged;
          }
        } catch {
          // ignore powershell fallback failures
        }
      }

      if (paths.length === 0) {
        return { success: true, paths: [], operation: 'copy' as const };
      }

      let operation: 'copy' | 'cut' = 'copy';
      try {
        // Preferred DropEffect: DWORD，bit2 表示 MOVE
        const dropEffect = clipboard.readBuffer('Preferred DropEffect');
        if (dropEffect && dropEffect.length >= 4) {
          const value = dropEffect.readUInt32LE(0);
          if ((value & 0x2) === 0x2) {
            operation = 'cut';
          }
        }
      } catch {
        // 忽略格式不支持，默认 copy
      }

      return { success: true, paths, operation };
    } catch (error: any) {
      return { success: false, error: error.message };
    }
  });

  // 创建文件
  ipcMain.removeAllListeners('fs-create-file');
  ipcMain.handle('fs-create-file', async (_event, filePath: string) => {
    try {
      const absolutePath = path.isAbsolute(filePath) ? filePath : path.resolve(filePath);
      const dir = path.dirname(absolutePath);

      // 确保目录存在
      if (!fs.existsSync(dir)) {
        fs.mkdirSync(dir, { recursive: true });
      }

      // 创建空文件
      fs.writeFileSync(absolutePath, '', 'utf8');
      return { success: true };
    } catch (error: any) {
      return { success: false, error: error.message };
    }
  });

  // 创建文件夹
  ipcMain.removeAllListeners('fs-create-folder');
  ipcMain.handle('fs-create-folder', async (_event, dirPath: string) => {
    try {
      const absolutePath = path.isAbsolute(dirPath) ? dirPath : path.resolve(dirPath);

      // 创建目录（如果不存在）
      if (!fs.existsSync(absolutePath)) {
        fs.mkdirSync(absolutePath, { recursive: true });
      }

      return { success: true };
    } catch (error: any) {
      return { success: false, error: error.message };
    }
  });

  // 重命名文件或文件夹
  ipcMain.removeAllListeners('fs-rename');
  ipcMain.handle('fs-rename', async (_event, oldPath: string, newName: string) => {
    try {
      const absoluteOldPath = path.isAbsolute(oldPath) ? oldPath : path.resolve(oldPath);
      const dir = path.dirname(absoluteOldPath);
      const absoluteNewPath = path.join(dir, newName);

      if (!fs.existsSync(absoluteOldPath)) {
        return { success: false, error: 'File or folder does not exist' };
      }

      if (fs.existsSync(absoluteNewPath)) {
        return { success: false, error: 'A file or folder with that name already exists' };
      }

      fs.renameSync(absoluteOldPath, absoluteNewPath);
      return { success: true, newPath: absoluteNewPath };
    } catch (error: any) {
      return { success: false, error: error.message };
    }
  });

  // 删除文件或文件夹
  ipcMain.removeAllListeners('fs-delete');
  ipcMain.handle('fs-delete', async (_event, targetPath: string) => {
    try {
      const absolutePath = path.isAbsolute(targetPath) ? targetPath : path.resolve(targetPath);

      if (!fs.existsSync(absolutePath)) {
        return { success: false, error: 'File or folder does not exist' };
      }

      // Move to OS Recycle Bin / Trash instead of permanent delete.
      await shell.trashItem(absolutePath);
      return { success: true };
    } catch (error: any) {
      return { success: false, error: error.message };
    }
  });

  // 复制文件或文件夹
  ipcMain.removeAllListeners('fs-copy');
  ipcMain.handle('fs-copy', async (_event, sourcePath: string, destPath: string) => {
    try {
      const absoluteSource = path.isAbsolute(sourcePath) ? sourcePath : path.resolve(sourcePath);
      const absoluteDest = path.isAbsolute(destPath) ? destPath : path.resolve(destPath);

      if (!fs.existsSync(absoluteSource)) {
        return { success: false, error: 'Source file or folder does not exist' };
      }

      if (fs.existsSync(absoluteDest)) {
        return { success: false, error: 'Destination already exists' };
      }

      const stats = fs.statSync(absoluteSource);
      if (stats.isDirectory()) {
        // 递归复制目录
        const copyDir = (src: string, dest: string) => {
          fs.mkdirSync(dest, { recursive: true });
          const entries = fs.readdirSync(src, { withFileTypes: true });

          for (const entry of entries) {
            const srcPath = path.join(src, entry.name);
            const destPath = path.join(dest, entry.name);

            if (entry.isDirectory()) {
              copyDir(srcPath, destPath);
            } else {
              fs.copyFileSync(srcPath, destPath);
            }
          }
        };

        copyDir(absoluteSource, absoluteDest);
      } else {
        // 复制文件
        // 确保目标目录存在
        const destDir = path.dirname(absoluteDest);
        if (!fs.existsSync(destDir)) {
          fs.mkdirSync(destDir, { recursive: true });
        }
        fs.copyFileSync(absoluteSource, absoluteDest);
      }

      return { success: true, newPath: absoluteDest };
    } catch (error: any) {
      return { success: false, error: error.message };
    }
  });

  // 移动文件或文件夹（重命名或移动）
  ipcMain.removeAllListeners('fs-move');
  ipcMain.handle('fs-move', async (_event, sourcePath: string, destPath: string) => {
    try {
      const absoluteSource = path.isAbsolute(sourcePath) ? sourcePath : path.resolve(sourcePath);
      const absoluteDest = path.isAbsolute(destPath) ? destPath : path.resolve(destPath);

      if (!fs.existsSync(absoluteSource)) {
        return { success: false, error: 'Source file or folder does not exist' };
      }

      if (fs.existsSync(absoluteDest)) {
        return { success: false, error: 'Destination already exists' };
      }

      // 确保目标目录存在
      const destDir = path.dirname(absoluteDest);
      if (!fs.existsSync(destDir)) {
        fs.mkdirSync(destDir, { recursive: true });
      }

      // 移动文件或文件夹
      fs.renameSync(absoluteSource, absoluteDest);

      return { success: true, newPath: absoluteDest };
    } catch (error: any) {
      return { success: false, error: error.message };
    }
  });

  // 写入文件内容
  ipcMain.removeAllListeners('fs-write-file');
  ipcMain.handle('fs-write-file', async (_event, filePath: string, content: string, encoding: string = 'utf8') => {
    try {
      const absolutePath = path.isAbsolute(filePath) ? filePath : path.resolve(filePath);

      // 确保目录存在
      const dir = path.dirname(absolutePath);
      if (!fs.existsSync(dir)) {
        fs.mkdirSync(dir, { recursive: true });
      }

      // 写入文件
      fs.writeFileSync(absolutePath, content, encoding as BufferEncoding);

      // 获取更新后的文件大小
      const stats = fs.statSync(absolutePath);

      return {
        success: true,
        size: stats.size,
      };
    } catch (error: any) {
      return { success: false, error: error.message };
    }
  });

  // 读取文件内容
  ipcMain.removeAllListeners('fs-read-file');
  ipcMain.handle('fs-read-file', async (_event, filePath: string) => {
    try {
      const absolutePath = path.isAbsolute(filePath) ? filePath : path.resolve(filePath);

      if (!fs.existsSync(absolutePath)) {
        return { success: false, error: 'File does not exist' };
      }

      const stats = fs.statSync(absolutePath);
      if (stats.isDirectory()) {
        return { success: false, error: 'Path is a directory' };
      }

      // 检查文件大小（限制为 10MB）
      const maxSize = 10 * 1024 * 1024; // 10MB
      if (stats.size > maxSize) {
        return { success: false, error: 'File is too large to read (max 10MB)' };
      }

      // 检查文件扩展名，决定读取方式
      const ext = path.extname(absolutePath).toLowerCase();
      const textExtensions = ['.txt', '.md', '.json', '.py', '.js', '.ts', '.tsx', '.jsx', '.html', '.css', '.xml', '.yaml', '.yml', '.log', '.csv', '.ini', '.conf', '.config', '.sh', '.bat', '.ps1', '.sql', '.vue', '.svelte'];
      const imageExtensions = ['.png', '.jpg', '.jpeg', '.gif', '.svg', '.bmp', '.webp', '.ico'];

      if (textExtensions.includes(ext)) {
        // 读取文本文件
        const content = fs.readFileSync(absolutePath, 'utf8');
        return {
          success: true,
          content,
          type: 'text',
          encoding: 'utf8',
          size: stats.size,
        };
      } else if (imageExtensions.includes(ext)) {
        // 读取图片文件（Base64）
        const content = fs.readFileSync(absolutePath);
        const base64 = content.toString('base64');
        const mimeType = ext === '.svg' ? 'image/svg+xml' : `image/${ext.slice(1)}`;
        return {
          success: true,
          content: `data:${mimeType};base64,${base64}`,
          type: 'image',
          size: stats.size,
        };
      } else {
        // 二进制文件，返回错误提示
        return {
          success: false,
          error: `File type "${ext}" is not supported for preview. Please download the file to view it.`,
        };
      }
    } catch (error: any) {
      return { success: false, error: error.message };
    }
  });

  // 在文件资源管理器中打开文件或文件夹
  ipcMain.removeAllListeners('fs-show-in-folder');
  ipcMain.handle('fs-show-in-folder', async (_event, filePath: string) => {
    try {
      const absolutePath = path.isAbsolute(filePath) ? filePath : path.resolve(filePath);

      if (!fs.existsSync(absolutePath)) {
        return { success: false, error: 'File or folder does not exist' };
      }

      // 使用 shell.showItemInFolder 打开文件资源管理器并选中文件/文件夹
      shell.showItemInFolder(absolutePath);

      return { success: true };
    } catch (error: any) {
      return { success: false, error: error.message };
    }
  });

  // 使用系统默认应用打开文件
  ipcMain.removeAllListeners('fs-open-with-default-app');
  ipcMain.handle('fs-open-with-default-app', async (_event, filePath: string) => {
    try {
      const absolutePath = path.isAbsolute(filePath) ? filePath : path.resolve(filePath);

      if (!fs.existsSync(absolutePath)) {
        return { success: false, error: 'File does not exist' };
      }

      const openResult = await shell.openPath(absolutePath);
      // shell.openPath 成功时返回空字符串，失败时返回错误信息
      if (openResult) {
        return { success: false, error: openResult };
      }

      return { success: true };
    } catch (error: any) {
      return { success: false, error: error.message };
    }
  });

}

// 注册自定义协议用于 OAuth 回调
const PROTOCOL_NAME = 'useit';

// 使用 app.isPackaged 判断是否为打包环境（比 NODE_ENV 更可靠）
if (!app.isPackaged) {
  // 开发环境：需要传入 electron.exe 的路径和当前脚本路径
  app.setAsDefaultProtocolClient(PROTOCOL_NAME, process.execPath, [
    path.resolve(process.argv[1])
  ]);
} else {
  // 生产环境：直接注册
  if (!app.isDefaultProtocolClient(PROTOCOL_NAME)) {
    app.setAsDefaultProtocolClient(PROTOCOL_NAME);
  }
}

// 存储 OAuth 回调的 Promise resolver
let oauthCallbackResolver: ((result: { success: boolean; url?: string; error?: string }) => void) | null = null;

// 处理自定义协议 URL（用于 OAuth 回调）
const handleProtocolUrl = (url: string) => {

  try {
    // 验证 URL 格式（支持 hash fragment 和 query string）
    // 例如: useit://auth/callback#access_token=xxx 或 useit://auth/callback?code=xxx
    if (!url.startsWith(`${PROTOCOL_NAME}://`)) {
      console.warn('[OAuth] Invalid protocol URL format:', url);
      return;
    }

    // 检查是否是 auth 回调
    if (url.includes(`${PROTOCOL_NAME}://auth/callback`)) {
      // 传递完整的回调 URL（包含 hash fragment 和 query string）
      const callbackUrl = url;

      if (oauthCallbackResolver) {
        oauthCallbackResolver({ success: true, url: callbackUrl });
        oauthCallbackResolver = null;
      } else {
        console.warn('[OAuth] Received callback URL but no resolver is waiting');
      }
    } else {
      console.warn('[OAuth] Received protocol URL but not an auth callback:', url);
    }
  } catch (error: any) {
    console.error('[OAuth] Failed to handle protocol URL:', error);
    if (oauthCallbackResolver) {
      oauthCallbackResolver({ success: false, error: error.message });
      oauthCallbackResolver = null;
    }
  }
};

// 监听应用启动时的协议 URL（Windows/Linux）
app.on('open-url', (event, url) => {
  event.preventDefault();
  handleProtocolUrl(url);
});

// 监听第二个实例启动（Windows/Linux）
app.on('second-instance', (event, commandLine) => {
  // 查找协议 URL
  const url = commandLine.find(arg => arg.startsWith(`${PROTOCOL_NAME}://`));
  if (url) {
    handleProtocolUrl(url);
  }

  // 聚焦到主窗口
  const windows = BrowserWindow.getAllWindows();
  if (windows.length > 0) {
    windows[0].focus();
  }
});

// 确保单实例运行（Windows/Linux）
const gotTheLock = app.requestSingleInstanceLock();
if (!gotTheLock) {
  app.quit();
  process.exit(0);
}

// 处理应用启动时的协议 URL（Windows/Linux）
if (process.platform !== 'darwin') {
  const protocolUrl = process.argv.find(arg => arg.startsWith(`${PROTOCOL_NAME}://`));
  if (protocolUrl) {
    // 延迟处理，等待 app.whenReady()
    app.whenReady().then(() => {
      handleProtocolUrl(protocolUrl);
    });
  }
}

app.whenReady().then(async () => {
  if (!app.isPackaged) {
    try {
      await session.defaultSession.clearCache();
    } catch (e) {
      console.warn('[Main] Dev: clearCache failed (non-fatal):', e);
    }
  }

  // Start Local Engine along with Electron (Windows). If it is already running, this is a no-op.
  // We intentionally don't block UI startup on engine boot; renderer can retry API calls.
  ensureLocalEngineRunning()
    .then((r) => {
      if (!r.ok) {
        console.error('[LocalEngine] Failed to start:', r.error);
      } else if (r.started) {
        console.log('[LocalEngine] Started:', { pid: r.pid, exePath: r.exePath });
      } else {
        console.log('[LocalEngine] Already running');
      }
    })
    .catch((e) => console.error('[LocalEngine] ensureLocalEngineRunning rejected:', e));

  // Register recorder IPC once (after app is ready)
  try {
    registerRecorderIpc(recorderService);
  } catch (e) {
    console.error('Failed to register recorder IPC:', e);
  }

  // S3 presigned upload (PUT)
  try {
    ipcMain.removeHandler('s3:uploadPresignedPut');
    ipcMain.handle(
      's3:uploadPresignedPut',
      async (event, args: { requestId: string; filePath: string; uploadUrl: string; method?: string; headers?: Record<string, string> }) => {
        const { requestId, filePath, uploadUrl, method, headers } = args || ({} as any);
        if (!requestId || !filePath || !uploadUrl) {
          return { success: false, error: 'Missing requestId/filePath/uploadUrl' };
        }
        try {
          const result = await uploadFileToPresignedPut({
            requestId,
            filePath,
            uploadUrl,
            method,
            headers,
            onProgress: (p) => {
              event.sender.send('s3:upload-progress', p);
            },
          });
          return { success: true, etag: result.etag };
        } catch (e: any) {
          return { success: false, error: e?.message || String(e) };
        }
      }
    );
  } catch (e) {
    console.error('Failed to register S3 upload IPC:', e);
  }

  // S3 presigned download (GET)
  try {
    ipcMain.removeHandler('s3:downloadPresignedGet');
    ipcMain.handle(
      's3:downloadPresignedGet',
      async (event, args: { requestId: string; filePath: string; downloadUrl: string; headers?: Record<string, string> }) => {
        const { requestId, filePath, downloadUrl, headers } = args || ({} as any);
        if (!requestId || !filePath || !downloadUrl) {
          return { success: false, error: 'Missing requestId/filePath/downloadUrl' };
        }
        try {
          await downloadFileFromPresignedGet({
            requestId,
            filePath,
            downloadUrl,
            headers,
            onProgress: (p) => {
              event.sender.send('s3:download-progress', p);
            },
          });
          return { success: true };
        } catch (e: any) {
          return { success: false, error: e?.message || String(e) };
        }
      }
    );
  } catch (e) {
    console.error('Failed to register S3 download IPC:', e);
  }

  // Get file metadata
  try {
    ipcMain.removeHandler('fs:getFileMetadata');
    ipcMain.handle(
      'fs:getFileMetadata',
      async (event, filePath: string) => {
        if (!filePath) {
          return null;
        }
        try {
          return getFileMetadata(filePath);
        } catch (e: any) {
          console.error('Failed to get file metadata:', e);
          return null;
        }
      }
    );
  } catch (e) {
    console.error('Failed to register file metadata IPC:', e);
  }

  // ==================== OAuth 登录 API ====================
  try {
    ipcMain.removeHandler('oauth:startGoogleLogin');
    ipcMain.handle('oauth:startGoogleLogin', async (_event, oauthUrl: string) => {
      try {
        // 重置 resolver
        oauthCallbackResolver = null;

        // 创建 Promise 等待回调
        const callbackPromise = new Promise<{ success: boolean; url?: string; error?: string }>((resolve) => {
          oauthCallbackResolver = resolve;

          // 设置超时（5分钟）
          setTimeout(() => {
            if (oauthCallbackResolver === resolve) {
              oauthCallbackResolver = null;
              resolve({ success: false, error: 'OAuth timeout' });
            }
          }, 5 * 60 * 1000);
        });

        // 在默认浏览器中打开 OAuth URL
        console.log('[OAuth] Opening browser with URL:', oauthUrl);
        await shell.openExternal(oauthUrl);

        // 等待回调
        const result = await callbackPromise;
        return result;
      } catch (error: any) {
        console.error('[OAuth] Error starting Google login:', error);
        return { success: false, error: error.message || String(error) };
      }
    });
  } catch (e) {
    console.error('Failed to register OAuth IPC:', e);
  }

  createWindow();

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow();
    }
  });

});

// Ensure services are stopped when Electron quits
let __stoppingServices = false;
app.on('before-quit', (e) => {
  if (__stoppingServices) return;
  __stoppingServices = true;

  // allow async stop
  e.preventDefault();
  Promise.allSettled([stopLocalEngine()])
    .then((results) => {
      const rejected = results.filter((r) => r.status === 'rejected') as PromiseRejectedResult[];
      for (const r of rejected) console.warn('[Services] stop failed:', r.reason);
    })
    .finally(() => app.quit());
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit();
  }
});
