import { app, BrowserWindow, shell, ipcMain, dialog, clipboard, session } from 'electron';
import * as path from 'path';
import * as fs from 'fs';
import { exec, execSync } from 'child_process';
import { promisify } from 'util';
import { vncProxy } from './vncProxy';
import { vmInstaller } from './services/vmInstaller';
import { serviceDeployer } from './services/serviceDeployer';
import { vmShareManager } from './services/vmShareManager';
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
const TIGHT_VNC_INSTALLER_FILENAME = 'tightvnc-2.8.85-gpl-setup-64bit.msi';

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

  // 检查 Hyper-V 是否已启用
  ipcMain.removeAllListeners('check-hyperv-enabled');
  ipcMain.handle('check-hyperv-enabled', async () => {
    try {
      // 1. 检查本地缓存，但做一次轻量命令可用性校验，避免缓存误判
      const config = loadConfig();
      if (config.hyperVVerified) {
        const cmdCheck = `powershell -NoProfile -Command "if (Get-Command Get-VM -ErrorAction SilentlyContinue) { 'available' } else { 'missing' }"`;
        const { stdout: cmdStdout } = await execAsync(cmdCheck).catch(() => ({ stdout: 'missing' }));
        const cmdAvailable = cmdStdout.trim().toLowerCase() === 'available';

        if (cmdAvailable) {
          console.log('[Hyper-V Check] Cache hit + command available');
          return { success: true, enabled: true };
        }

        console.warn('[Hyper-V Check] Cache invalidated: Get-VM command missing');
        saveConfig({ hyperVVerified: undefined });
      }

      // 2. 检查 Hyper-V 服务是否存在且可用
      const psCommand = `powershell -NoProfile -Command "try { if (-not (Get-Command Get-VM -ErrorAction SilentlyContinue)) { 'disabled' } else { Get-VM -ErrorAction Stop | Out-Null; 'enabled' } } catch { $m = $_.Exception.Message; if ($m -match 'not recognized|CommandNotFoundException|Hyper-V') { 'disabled' } else { 'enabled' } }"`;
      const { stdout } = await execAsync(psCommand);
      const result = stdout.trim().toLowerCase();
      const isEnabled = result === 'enabled';

      // 3. 如果检查通过，保存到本地配置
      if (isEnabled) {
        saveConfig({ hyperVVerified: true });
      }

      return { success: true, enabled: isEnabled };
    } catch (error: any) {
      // 如果命令失败，可能是 Hyper-V 未安装
      const msg = error.message?.toLowerCase() || '';
      if (msg.includes('hyper-v') || msg.includes('not recognized') || msg.includes('cmdlet')) {
        return { success: true, enabled: false };
      }
      return { success: false, error: error.message };
    }
  });

  // 检查指定名称的 VM 是否存在
  ipcMain.removeAllListeners('check-vm-exists');
  ipcMain.handle('check-vm-exists', async (_event, vmNamePattern: string) => {
    try {
      const normalizedPattern = normalizeVmNameInput(vmNamePattern);
      if (!normalizedPattern) {
        return { success: true, exists: false, vmName: null };
      }

      // 1. 优先检查本地配置缓存，但需要二次验证
      const config = loadConfig();
      const cacheKey = `verifiedVm_${normalizedPattern}`;
      if (config[cacheKey]) {
        try {
          const escapedCached = escapePsSingleQuoted(config[cacheKey]);
          const verifyCmd = `powershell -NoProfile -Command "try { (Get-VM -Name '${escapedCached}' -ErrorAction Stop).Name } catch { '' }"`;
          const { stdout: verifyStdout } = await execAsync(verifyCmd);
          if (verifyStdout.trim()) {
            return { success: true, exists: true, vmName: config[cacheKey] };
          }
        } catch { /* verification failed */ }
        saveConfig({ [cacheKey]: undefined });
      }

      // 2. PowerShell 检查
      // 查找名称包含指定模式的 VM
      const escapedPattern = escapePsSingleQuoted(normalizedPattern);
      const psCommand = `powershell -NoProfile -Command "Get-VM | Where-Object { $_.Name -like '*${escapedPattern}*' } | Select-Object -First 1 -ExpandProperty Name"`;
      const { stdout } = await execAsync(psCommand);
      const vmName = stdout.trim() || null;

      // 3. 如果找到，更新本地配置缓存
      if (vmName) {
        saveConfig({ [cacheKey]: vmName });
      }

      return { success: true, exists: !!vmName, vmName };
    } catch (error: any) {
      return { success: false, error: error.message };
    }
  });

  // 获取 Hyper-V VM 的 IP 地址
  ipcMain.removeAllListeners('get-vm-ip');
  ipcMain.handle('get-vm-ip', async (_event, vmName: string) => {
    try {
      const resolvedVmName = await resolveVmName(vmName);
      if (!resolvedVmName) {
        clearVmCache(vmName);
        return { success: false, error: `Virtual machine "${normalizeVmNameInput(vmName)}" not found.` };
      }

      const escapedVmName = escapePsSingleQuoted(resolvedVmName);
      const psCommand = `powershell -Command "(Get-VMNetworkAdapter -VMName '${escapedVmName}').IPAddresses | Where-Object { $_ -match '^\\d+\\.\\d+\\.\\d+\\.\\d+$' } | Select-Object -First 1"`;
      const { stdout, stderr } = await execAsync(psCommand);

      if (stderr && !stdout.trim()) {
        return { success: false, error: stderr };
      }

      const ip = stdout.trim();
      if (ip && /^\d+\.\d+\.\d+\.\d+$/.test(ip)) {
        return { success: true, ip };
      } else {
        return { success: false, error: 'No valid IPv4 address found' };
      }
    } catch (error: any) {
      return { success: false, error: error.message };
    }
  });

  // 辅助函数：如果遇到 VM 不存在的错误，清除缓存
  const handleVmError = (vmName: string, error: any) => {
    const msg = (error.message || '').toLowerCase();
    if (msg.includes('find a virtual machine') || msg.includes('not found') || msg.includes('does not exist')) {
      console.log(`[VM Cache] Cleared cache for ${vmName} due to missing VM error`);
      clearVmCache(vmName);
    }
  };

  const clearVmCache = (vmName: string) => {
    const normalized = (vmName || '').trim();
    if (normalized) {
      saveConfig({ [`verifiedVm_${normalized}`]: undefined });
    }
  };

  const normalizeVmNameInput = (vmName: string) => (vmName || '').trim();

  const escapePsSingleQuoted = (value: string) => value.replace(/'/g, "''");

  const resolveVmName = async (vmName: string): Promise<string | null> => {
    const normalized = normalizeVmNameInput(vmName);
    if (!normalized) return null;

    const escapedExact = escapePsSingleQuoted(normalized);
    const exactCommand = `powershell -NoProfile -Command "try { (Get-VM -Name '${escapedExact}' -ErrorAction Stop | Select-Object -First 1 -ExpandProperty Name) } catch { '' }"`;
    const { stdout: exactStdout } = await execAsync(exactCommand).catch(() => ({ stdout: '' }));
    const exactMatch = exactStdout.trim();
    if (exactMatch) return exactMatch;

    const escapedLike = escapePsSingleQuoted(normalized);
    const fuzzyCommand = `powershell -NoProfile -Command "Get-VM | Where-Object { $_.Name -like '*${escapedLike}*' } | Select-Object -First 1 -ExpandProperty Name"`;
    const { stdout: fuzzyStdout } = await execAsync(fuzzyCommand).catch(() => ({ stdout: '' }));
    const fuzzyMatch = fuzzyStdout.trim();
    return fuzzyMatch || null;
  };

  const getTightVncInstallerPath = (): string | null => {
    const appPath = app.getAppPath();
    const candidates = [
      path.join(appPath, 'resources', 'bin', TIGHT_VNC_INSTALLER_FILENAME),
      path.join(appPath, 'frontend', 'resources', 'bin', TIGHT_VNC_INSTALLER_FILENAME),
      path.join(__dirname, '../../resources/bin', TIGHT_VNC_INSTALLER_FILENAME),
      path.join(__dirname, '../../../resources/bin', TIGHT_VNC_INSTALLER_FILENAME),
      path.join(process.resourcesPath, 'resources', 'bin', TIGHT_VNC_INSTALLER_FILENAME),
      path.join(process.resourcesPath, 'bin', TIGHT_VNC_INSTALLER_FILENAME),
    ];

    for (const candidate of candidates) {
      try {
        if (fs.existsSync(candidate)) return candidate;
      } catch {
        // ignore
      }
    }
    return null;
  };

  const ensureVmVncInstalled = async (
    vmName: string,
    username: string = 'useit',
    password: string = '12345678'
  ): Promise<{ vmName: string; installed: boolean; alreadyInstalled: boolean }> => {
    const resolvedVmName = await resolveVmName(vmName);
    if (!resolvedVmName) {
      clearVmCache(vmName);
      throw new Error(`Virtual machine "${normalizeVmNameInput(vmName)}" not found.`);
    }

    const installerPath = getTightVncInstallerPath();
    if (!installerPath) {
      throw new Error(
        `TightVNC installer not found (${TIGHT_VNC_INSTALLER_FILENAME}). Please restore installer in frontend/resources/bin.`
      );
    }

    const escapedVmName = escapePsSingleQuoted(resolvedVmName);
    const escapedUsername = escapePsSingleQuoted(username || 'useit');
    const escapedPassword = escapePsSingleQuoted(password || '12345678');
    const escapedInstallerPath = escapePsSingleQuoted(installerPath);

    const psScript = [
      "$ErrorActionPreference = 'Stop'",
      `$vmName = '${escapedVmName}'`,
      `$username = '${escapedUsername}'`,
      `$password = '${escapedPassword}'`,
      `$installerPath = '${escapedInstallerPath}'`,
      "if (-not (Test-Path $installerPath)) { throw 'TightVNC installer missing on host: ' + $installerPath }",
      "$secPassword = ConvertTo-SecureString $password -AsPlainText -Force",
      "$cred = New-Object System.Management.Automation.PSCredential ($username, $secPassword)",
      "$session = New-PSSession -VMName $vmName -Credential $cred -ErrorAction Stop",
      "try {",
      "  $serviceExists = Invoke-Command -Session $session -ScriptBlock {",
      "    $svc = Get-Service -Name 'tvnserver' -ErrorAction SilentlyContinue",
      "    if ($svc) {",
      "      Set-Service -Name 'tvnserver' -StartupType Automatic -ErrorAction SilentlyContinue",
      "      if ($svc.Status -ne 'Running') { Start-Service -Name 'tvnserver' -ErrorAction SilentlyContinue }",
      "      return $true",
      "    }",
      "    return $false",
      "  }",
      "  if ($serviceExists) {",
      "    Write-Output 'vnc_status:already_installed'",
      "    return",
      "  }",
      "  Invoke-Command -Session $session -ScriptBlock {",
      "    New-Item -Path 'C:\\UseIt\\setup' -ItemType Directory -Force | Out-Null",
      "  }",
      "  Copy-Item -Path $installerPath -Destination 'C:\\UseIt\\setup\\tightvnc.msi' -ToSession $session -Force",
      "  Invoke-Command -Session $session -ScriptBlock {",
      "    $msi = 'C:\\UseIt\\setup\\tightvnc.msi'",
      "    if (-not (Test-Path $msi)) { throw 'Installer copy failed inside VM' }",
      "    $args = '/i \"' + $msi + '\" /quiet /norestart ADDLOCAL=Server SET_USEVNCAUTHENTICATION=1 VALUE_OF_USEVNCAUTHENTICATION=1 SET_PASSWORD=1 VALUE_OF_PASSWORD=12345678 SET_USECONTROLAUTHENTICATION=1 VALUE_OF_USECONTROLAUTHENTICATION=1 SET_CONTROLPASSWORD=1 VALUE_OF_CONTROLPASSWORD=12345678'",
      "    Start-Process 'msiexec.exe' -ArgumentList $args -Wait -NoNewWindow",
      "    Start-Sleep -Seconds 3",
      "    $svc = Get-Service -Name 'tvnserver' -ErrorAction SilentlyContinue",
      "    if (-not $svc) { throw 'TightVNC service not found after installation' }",
      "    Set-Service -Name 'tvnserver' -StartupType Automatic -ErrorAction SilentlyContinue",
      "    if ($svc.Status -ne 'Running') { Start-Service -Name 'tvnserver' -ErrorAction SilentlyContinue }",
      "    New-NetFirewallRule -DisplayName 'TightVNC Server' -Direction Inbound -LocalPort 5900 -Protocol TCP -Action Allow -ErrorAction SilentlyContinue | Out-Null",
      "  }",
      "  Write-Output 'vnc_status:installed'",
      "} finally {",
      "  if ($session) { Remove-PSSession -Session $session -ErrorAction SilentlyContinue }",
      "}",
    ].join('\n');

    const encoded = Buffer.from(psScript, 'utf16le').toString('base64');
    const { stdout, stderr } = await execAsync(`powershell -NoProfile -EncodedCommand ${encoded}`);
    if (stderr && !stdout.trim()) {
      throw new Error(stderr.trim());
    }

    const output = stdout.trim().toLowerCase();
    const alreadyInstalled = output.includes('vnc_status:already_installed');
    const installed = output.includes('vnc_status:installed');
    if (!alreadyInstalled && !installed) {
      throw new Error(`Failed to ensure TightVNC in VM "${resolvedVmName}"`);
    }

    return { vmName: resolvedVmName, installed, alreadyInstalled };
  };

  // 获取 VM 状态
  ipcMain.removeAllListeners('get-vm-status');
  ipcMain.handle('get-vm-status', async (_event, vmName: string) => {
    try {
      const resolvedVmName = await resolveVmName(vmName);
      if (!resolvedVmName) {
        clearVmCache(vmName);
        return { success: false, error: `Virtual machine "${normalizeVmNameInput(vmName)}" not found.` };
      }

      const escapedVmName = escapePsSingleQuoted(resolvedVmName);
      const psCommand = `powershell -Command "(Get-VM -Name '${escapedVmName}').State"`;
      const { stdout, stderr } = await execAsync(psCommand);

      if (stderr && !stdout.trim()) {
        throw new Error(stderr);
      }

      const state = stdout.trim();
      return { success: true, state };
    } catch (error: any) {
      handleVmError(normalizeVmNameInput(vmName), error);
      return { success: false, error: error.message };
    }
  });

  // 启动 VM
  ipcMain.removeAllListeners('start-vm');
  ipcMain.handle('start-vm', async (_event, vmName: string) => {
    try {
      const resolvedVmName = await resolveVmName(vmName);
      if (!resolvedVmName) {
        clearVmCache(vmName);
        return { success: false, error: `Virtual machine "${normalizeVmNameInput(vmName)}" not found.` };
      }

      const escapedVmName = escapePsSingleQuoted(resolvedVmName);
      const psCommand = `powershell -Command "Start-VM -Name '${escapedVmName}'"`;
      const { stderr } = await execAsync(psCommand);

      if (stderr) {
        throw new Error(stderr);
      }

      return { success: true };
    } catch (error: any) {
      handleVmError(normalizeVmNameInput(vmName), error);
      return { success: false, error: error.message };
    }
  });

  // 关闭 / 关机 VM
  ipcMain.removeAllListeners('stop-vm');
  ipcMain.handle('stop-vm', async (_event, vmName: string) => {
    try {
      const resolvedVmName = await resolveVmName(vmName);
      if (!resolvedVmName) {
        clearVmCache(vmName);
        return { success: false, error: `Virtual machine "${normalizeVmNameInput(vmName)}" not found.` };
      }

      const escapedVmName = escapePsSingleQuoted(resolvedVmName);
      // 优先尝试正常关闭，其次强制关闭
      const psCommand = `powershell -Command "Stop-VM -Name '${escapedVmName}' -TurnOff"`;
      const { stderr } = await execAsync(psCommand);

      if (stderr) {
        throw new Error(stderr);
      }

      return { success: true };
    } catch (error: any) {
      handleVmError(normalizeVmNameInput(vmName), error);
      return { success: false, error: error.message };
    }
  });

  // 删除 VM（包含 Hyper-V 实体和关联硬件文件）
  ipcMain.removeAllListeners('delete-vm');
  ipcMain.handle('delete-vm', async (_event, vmName: string) => {
    try {
      const resolvedVmName = await resolveVmName(vmName);
      if (!resolvedVmName) {
        clearVmCache(vmName);
        return { success: false, error: `Virtual machine "${normalizeVmNameInput(vmName)}" not found.` };
      }

      const escapedVmName = escapePsSingleQuoted(resolvedVmName);
      const psScript = `
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$OutputEncoding = [Console]::OutputEncoding
$vmName = '${escapedVmName}'
$vm = Get-VM -Name $vmName -ErrorAction Stop
$vhdPaths = @(
  Get-VMHardDiskDrive -VMName $vmName -ErrorAction SilentlyContinue |
  Select-Object -ExpandProperty Path
)
$configPath = $vm.ConfigurationLocation
$snapshotPath = $vm.SnapshotFileLocation
$smartPagingPath = $vm.SmartPagingFilePath
if ($vm.State -ne 'Off') {
  Stop-VM -Name $vmName -TurnOff -Force -ErrorAction SilentlyContinue | Out-Null
  Start-Sleep -Milliseconds 500
}
Remove-VM -Name $vmName -Force -ErrorAction Stop
foreach ($path in $vhdPaths) {
  if ($path -and (Test-Path $path)) {
    try { Remove-Item -Path $path -Force -ErrorAction SilentlyContinue } catch {}
  }
}
$dirPaths = @($configPath, $snapshotPath, $smartPagingPath) | Where-Object { $_ } | Select-Object -Unique
foreach ($dirPath in $dirPaths) {
  if (Test-Path $dirPath) {
    try { Remove-Item -Path $dirPath -Recurse -Force -ErrorAction SilentlyContinue } catch {}
  }
}
`;
      const encodedCommand = Buffer.from(psScript, 'utf16le').toString('base64');
      await execAsync(`powershell -NoProfile -EncodedCommand ${encodedCommand}`);

      saveConfig({
        [`verifiedVm_${normalizeVmNameInput(vmName)}`]: undefined,
        [`verifiedVm_${resolvedVmName}`]: undefined,
      });
      return { success: true, vmName: resolvedVmName };
    } catch (error: any) {
      handleVmError(normalizeVmNameInput(vmName), error);
      return { success: false, error: error.message };
    }
  });

  // 检测并安装 VM 内 TightVNC（如未安装）
  ipcMain.removeAllListeners('vm-ensure-vnc');
  ipcMain.handle(
    'vm-ensure-vnc',
    async (_event, args: { vmName: string; username?: string; password?: string }) => {
      try {
        if (!args?.vmName) {
          return { success: false, error: 'vmName is required' };
        }
        const result = await ensureVmVncInstalled(args.vmName, args.username, args.password);
        return { success: true, ...result };
      } catch (error: any) {
        handleVmError(normalizeVmNameInput(args?.vmName || ''), error);
        return { success: false, error: error.message || String(error) };
      }
    }
  );

  // 获取 VM 硬件规格
  ipcMain.removeAllListeners('get-vm-specs');
  ipcMain.handle('get-vm-specs', async (_event, vmName: string) => {
    try {
      // 分步获取 VM 信息，避免复杂的 PowerShell 脚本
      const psScript = `
$ErrorActionPreference = 'Stop'
$vm = Get-VM -Name '${vmName}'
$vhd = Get-VMHardDiskDrive -VMName '${vmName}' | Select-Object -First 1 | ForEach-Object { Get-VHD -Path $_.Path -ErrorAction SilentlyContinue }
$result = @{
  ProcessorCount = $vm.ProcessorCount
  MemoryStartup = $vm.MemoryStartup
  MemoryAssigned = if ($vm.MemoryAssigned) { $vm.MemoryAssigned } else { $vm.MemoryStartup }
  MemoryDemand = $vm.MemoryDemand
  DynamicMemoryEnabled = $vm.DynamicMemoryEnabled
  CPUUsage = $vm.CPUUsage
  State = $vm.State.ToString()
  Uptime = if ($vm.Uptime) { $vm.Uptime.ToString() } else { '00:00:00' }
  DiskSizeGB = 0
  DiskUsedGB = 0
}

if ($vhd) {
    $currentVhd = $vhd
    $result.DiskSizeGB = [math]::Round($currentVhd.Size / 1GB, 0)
    
    # Calculate total file size of the VHD chain (handling snapshots)
    $totalFileSize = $currentVhd.FileSize
    $parentPath = $currentVhd.ParentPath
    
    while ($parentPath) {
        try {
            $parentDisk = Get-VHD -Path $parentPath -ErrorAction Stop
            $totalFileSize += $parentDisk.FileSize
            $parentPath = $parentDisk.ParentPath
        } catch {
            $parentPath = $null
        }
    }
    
    $result.DiskUsedGB = [math]::Round($totalFileSize / 1GB, 1)
}

$result | ConvertTo-Json -Compress
`;
      // 将脚本编码为 Base64 以避免引号和换行问题
      const encodedCommand = Buffer.from(psScript, 'utf16le').toString('base64');
      const { stdout, stderr } = await execAsync(`powershell -EncodedCommand ${encodedCommand}`);

      if (stderr && !stdout.trim()) {
        return { success: false, error: stderr.trim() };
      }

      const output = stdout.trim();
      if (!output) {
        return { success: false, error: 'Empty response from PowerShell' };
      }

      const specs = JSON.parse(output);
      return {
        success: true,
        specs: {
          cpuCores: specs.ProcessorCount || 0,
          cpuUsage: specs.CPUUsage || 0,
          memoryMB: Math.round((specs.MemoryStartup || 0) / (1024 * 1024)),
          memoryAssignedMB: Math.round((specs.MemoryAssigned || specs.MemoryStartup || 0) / (1024 * 1024)),
          memoryDemandMB: Math.round((specs.MemoryDemand || 0) / (1024 * 1024)),
          isDynamicMemory: !!specs.DynamicMemoryEnabled,
          state: specs.State || 'Unknown',
          uptime: specs.Uptime || '00:00:00',
          diskSizeGB: specs.DiskSizeGB || 0,
          diskUsedGB: specs.DiskUsedGB || 0,
        }
      };
    } catch (error: any) {
      return { success: false, error: error.message };
    }
  });

  // 设置 VM 硬件规格
  ipcMain.removeAllListeners('set-vm-specs');
  ipcMain.handle('set-vm-specs', async (_event, { vmName, cpuCores, memoryGB, isDynamicMemory }) => {
    try {
      const memoryBytes = memoryGB * 1024 * 1024 * 1024;
      // 动态内存设置：最小 2GB，最大 8GB (或者稍微大于 Startup 以避免错误)
      const minBytes = 2 * 1024 * 1024 * 1024;
      const maxBytes = 8 * 1024 * 1024 * 1024;

      const psScript = `
        $ErrorActionPreference = 'Stop'
        $vm = Get-VM -Name '${vmName}'
        
        if ($vm.State -ne 'Off') {
          throw "VM must be stopped to change hardware settings."
        }

        # 设置 CPU
        Set-VMProcessor -VMName '${vmName}' -Count ${cpuCores}

        # 设置内存
        if ('${isDynamicMemory}' -eq 'true') {
           # 启用动态内存
           # 注意：StartupBytes 必须 >= MinimumBytes
           Set-VMMemory -VMName '${vmName}' -DynamicMemoryEnabled $true -StartupBytes ${memoryBytes} -MinimumBytes ${minBytes} -MaximumBytes ${maxBytes} -Priority 50
        } else {
           # 禁用动态内存 (静态)
           Set-VMMemory -VMName '${vmName}' -DynamicMemoryEnabled $false -StartupBytes ${memoryBytes}
        }
      `;

      const encodedCommand = Buffer.from(psScript, 'utf16le').toString('base64');
      const { stderr } = await execAsync(`powershell -EncodedCommand ${encodedCommand}`);

      if (stderr) {
        return { success: false, error: stderr };
      }
      return { success: true };
    } catch (error: any) {
      return { success: false, error: error.message };
    }
  });

  // 获取 VM 快照列表（扁平结构，前端负责组装树）
  ipcMain.removeAllListeners('list-vm-snapshots');
  ipcMain.handle('list-vm-snapshots', async (_event, vmName: string) => {
    try {
      const resolvedVmName = await resolveVmName(vmName);
      if (!resolvedVmName) {
        clearVmCache(vmName);
        return { success: false, error: `Virtual machine "${normalizeVmNameInput(vmName)}" not found.` };
      }

      const escapedVmName = escapePsSingleQuoted(resolvedVmName);
      const psScript = `
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$OutputEncoding = [Console]::OutputEncoding
$items = Get-VMCheckpoint -VMName '${escapedVmName}' -ErrorAction SilentlyContinue
if (-not $items) {
  '[]'
  return
}
$items |
  Select-Object Id, Name, ParentCheckpointId, CreationTime, CheckpointType |
  ConvertTo-Json -Depth 4 -Compress
`;

      const encodedCommand = Buffer.from(psScript, 'utf16le').toString('base64');
      const { stdout, stderr } = await execAsync(`powershell -NoProfile -EncodedCommand ${encodedCommand}`);
      if (stderr && !stdout.trim()) {
        throw new Error(stderr.trim());
      }

      const raw = stdout.trim();
      const parsed = raw ? JSON.parse(raw) : [];
      const snapshots = Array.isArray(parsed) ? parsed : [parsed];
      return { success: true, snapshots };
    } catch (error: any) {
      handleVmError(normalizeVmNameInput(vmName), error);
      return { success: false, error: error.message };
    }
  });

  // 创建 VM 快照
  ipcMain.removeAllListeners('create-vm-snapshot');
  ipcMain.handle(
    'create-vm-snapshot',
    async (_event, args: { vmName: string; snapshotName: string; saveState: boolean }) => {
      try {
        const resolvedVmName = await resolveVmName(args?.vmName || '');
        if (!resolvedVmName) {
          clearVmCache(args?.vmName || '');
          return { success: false, error: `Virtual machine "${normalizeVmNameInput(args?.vmName || '')}" not found.` };
        }

        const snapshotName = String(args?.snapshotName || '').trim();
        if (!snapshotName) {
          return { success: false, error: 'Snapshot name is required' };
        }

        const escapedVmName = escapePsSingleQuoted(resolvedVmName);
        const escapedSnapshotName = escapePsSingleQuoted(snapshotName);
        const checkpointType = args?.saveState ? 'Standard' : 'Production';

        // Compatibility:
        // 1) Some Hyper-V builds don't support Checkpoint-VM -CheckpointType.
        // 2) Some running VMs can fail Standard checkpoints (pause/resume device errors).
        // Strategy: switch VM checkpoint type via Set-VM, try requested mode first,
        // and if Standard fails, fallback to Production.
        const psScript = `
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$OutputEncoding = [Console]::OutputEncoding
$vmName = '${escapedVmName}'
$snapshotName = '${escapedSnapshotName}'
$targetType = '${checkpointType}'
$originalType = (Get-VM -Name $vmName -ErrorAction Stop).CheckpointType
$attemptTypes = @($targetType)
if ($targetType -eq 'Standard') { $attemptTypes += 'Production' }
$lastError = $null
$created = $false
try {
  foreach ($attemptType in $attemptTypes) {
    try {
      Set-VM -Name $vmName -CheckpointType $attemptType -ErrorAction Stop | Out-Null
      Checkpoint-VM -VMName $vmName -SnapshotName $snapshotName -ErrorAction Stop | Out-Null
      $created = $true
      break
    } catch {
      $lastError = $_
      continue
    }
  }
  if (-not $created) {
    throw $lastError
  }
} finally {
  if ($originalType) {
    try {
      Set-VM -Name $vmName -CheckpointType $originalType -ErrorAction Stop | Out-Null
    } catch {
      # ignore restore failures
    }
  }
}
`;
        const encodedCommand = Buffer.from(psScript, 'utf16le').toString('base64');
        const psCommand = `powershell -NoProfile -EncodedCommand ${encodedCommand}`;
        await execAsync(psCommand);

        return { success: true };
      } catch (error: any) {
        handleVmError(normalizeVmNameInput(args?.vmName || ''), error);
        return { success: false, error: error.message };
      }
    }
  );

  // 恢复 VM 到指定快照
  ipcMain.removeAllListeners('restore-vm-snapshot');
  ipcMain.handle(
    'restore-vm-snapshot',
    async (_event, args: { vmName: string; snapshotId: string }) => {
      try {
        const resolvedVmName = await resolveVmName(args?.vmName || '');
        if (!resolvedVmName) {
          clearVmCache(args?.vmName || '');
          return { success: false, error: `Virtual machine "${normalizeVmNameInput(args?.vmName || '')}" not found.` };
        }

        const snapshotId = String(args?.snapshotId || '').trim();
        if (!snapshotId) {
          return { success: false, error: 'Snapshot id is required' };
        }

        const escapedVmName = escapePsSingleQuoted(resolvedVmName);
        const escapedSnapshotId = escapePsSingleQuoted(snapshotId);
        const psScript = `
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$OutputEncoding = [Console]::OutputEncoding
$vmName = '${escapedVmName}'
$snapshotId = '${escapedSnapshotId}'
$checkpoint = $null
try {
  $guid = [Guid]$snapshotId
  $checkpoint = Get-VMCheckpoint -VMName $vmName -ErrorAction Stop | Where-Object { $_.Id -eq $guid } | Select-Object -First 1
} catch {
  # snapshotId may not parse as Guid on some environments
}
if (-not $checkpoint) {
  $checkpoint = Get-VMCheckpoint -VMName $vmName -ErrorAction Stop | Where-Object {
    ($_.Id -as [string]) -eq $snapshotId -or $_.Name -eq $snapshotId
  } | Select-Object -First 1
}
if (-not $checkpoint) {
  throw "Snapshot not found: $snapshotId"
}
Restore-VMCheckpoint -VMCheckpoint $checkpoint -Confirm:$false -ErrorAction Stop | Out-Null
`;
        const encodedCommand = Buffer.from(psScript, 'utf16le').toString('base64');
        await execAsync(`powershell -NoProfile -EncodedCommand ${encodedCommand}`);

        return { success: true };
      } catch (error: any) {
        handleVmError(normalizeVmNameInput(args?.vmName || ''), error);
        return { success: false, error: error.message };
      }
    }
  );

  // 修复 Hyper-V 权限 - 将当前用户添加到 Hyper-V Administrators 组
  ipcMain.removeAllListeners('fix-hyperv-permission');
  ipcMain.handle('fix-hyperv-permission', async () => {
    try {
      // 使用 runas 以管理员权限执行，会弹出 UAC 提示
      const psScript = `
        $group = 'Hyper-V Administrators'
        $user = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
        Add-LocalGroupMember -Group $group -Member $user -ErrorAction Stop
      `;
      // 将脚本编码为 Base64 以避免引号问题
      const encodedCommand = Buffer.from(psScript, 'utf16le').toString('base64');

      const { spawn } = require('child_process');

      return new Promise((resolve) => {
        // 使用 Start-Process 以管理员权限运行
        const proc = spawn('powershell', [
          '-Command',
          `Start-Process powershell -Verb RunAs -Wait -ArgumentList '-EncodedCommand','${encodedCommand}'`
        ], { shell: true });

        proc.on('close', (code: number) => {
          if (code === 0) {
            resolve({ success: true });
          } else {
            resolve({ success: false, error: 'User cancelled or operation failed' });
          }
        });

        proc.on('error', (err: Error) => {
          resolve({ success: false, error: err.message });
        });
      });
    } catch (error: any) {
      console.error('Failed to fix permission:', error);
      return { success: false, error: error.message };
    }
  });

  // ==================== VM 安装相关 IPC ====================

  // 设置 vmInstaller 的窗口引用
  vmInstaller.setWindow(win);

  // 环境检查
  ipcMain.removeAllListeners('vm-check-environment');
  ipcMain.handle('vm-check-environment', async (_event, installDir?: string) => {
    try {
      const result = await vmInstaller.checkEnvironment(installDir);
      return { success: true, data: result };
    } catch (error: any) {
      return { success: false, error: error.message };
    }
  });

  // 启用 Hyper-V
  ipcMain.removeAllListeners('vm-enable-hyperv');
  ipcMain.handle('vm-enable-hyperv', async () => {
    try {
      const result = await vmInstaller.enableHyperV();
      return { success: result.success, needsReboot: result.needsReboot, error: result.error };
    } catch (error: any) {
      return { success: false, error: error.message };
    }
  });

  // 选择 ISO 文件
  ipcMain.removeAllListeners('vm-select-iso');
  ipcMain.handle('vm-select-iso', async () => {
    try {
      const result = await dialog.showOpenDialog(win, {
        title: '选择 Windows ISO 文件',
        filters: [
          { name: 'ISO Files', extensions: ['iso'] },
          { name: 'All Files', extensions: ['*'] },
        ],
        properties: ['openFile'],
      });

      if (result.canceled || result.filePaths.length === 0) {
        return { success: false, canceled: true };
      }

      return { success: true, path: result.filePaths[0] };
    } catch (error: any) {
      return { success: false, error: error.message };
    }
  });

  // 选择 VM 安装目录
  ipcMain.removeAllListeners('vm-select-install-dir');
  ipcMain.handle('vm-select-install-dir', async () => {
    try {
      const result = await dialog.showOpenDialog(win, {
        title: '选择虚拟机安装目录',
        properties: ['openDirectory', 'createDirectory'],
        defaultPath: 'C:\\VMs',
      });

      if (result.canceled || result.filePaths.length === 0) {
        return { success: false, canceled: true };
      }

      return { success: true, path: result.filePaths[0] };
    } catch (error: any) {
      return { success: false, error: error.message };
    }
  });

  // 选择要恢复的 VM 根目录
  ipcMain.removeAllListeners('vm-select-restore-dir');
  ipcMain.handle('vm-select-restore-dir', async () => {
    try {
      const result = await dialog.showOpenDialog(win, {
        title: '选择要恢复的 VM 文件夹',
        properties: ['openDirectory'],
        defaultPath: 'C:\\VMs',
      });

      if (result.canceled || result.filePaths.length === 0) {
        return { success: false, canceled: true };
      }

      return { success: true, path: result.filePaths[0] };
    } catch (error: any) {
      return { success: false, error: error.message };
    }
  });

  // 选择 VM 导出目录
  ipcMain.removeAllListeners('vm-select-export-dir');
  ipcMain.handle('vm-select-export-dir', async () => {
    try {
      const result = await dialog.showOpenDialog(win, {
        title: '选择 VM 导出目录',
        properties: ['openDirectory', 'createDirectory'],
        defaultPath: 'C:\\VMs',
      });

      if (result.canceled || result.filePaths.length === 0) {
        return { success: false, canceled: true };
      }

      return { success: true, path: result.filePaths[0] };
    } catch (error: any) {
      return { success: false, error: error.message };
    }
  });

  // 选择要复制到工作区的文件（多选）
  ipcMain.removeAllListeners('show-add-files-to-workspace-dialog');
  ipcMain.handle('show-add-files-to-workspace-dialog', async () => {
    try {
      const result = await dialog.showOpenDialog(win, {
        title: '选择要复制到工作区的文件',
        properties: ['openFile', 'multiSelections'],
      });

      if (result.canceled || result.filePaths.length === 0) {
        return { success: true, canceled: true, filePaths: [] };
      }

      return { success: true, canceled: false, filePaths: result.filePaths };
    } catch (error: any) {
      return { success: false, error: error.message };
    }
  });

  // 验证 ISO 文件
  ipcMain.removeAllListeners('vm-validate-iso');
  ipcMain.handle('vm-validate-iso', async (_event, isoPath: string) => {
    try {
      const result = await vmInstaller.validateIso(isoPath);
      return { success: result.valid, error: result.error };
    } catch (error: any) {
      return { success: false, error: error.message };
    }
  });

  // 开始安装 VM
  ipcMain.removeAllListeners('vm-install');
  ipcMain.handle('vm-install', async (_event, config: {
    vmName?: string;
    isoPath: string;
    installDir?: string;
    memorySizeGB?: number;
    cpuCount?: number;
    diskSizeGB?: number;
  }) => {
    try {
      const result = await vmInstaller.install(config);

      // 安装成功后，自动更新本地配置缓存，避免再次检查
      if (result.success && config.vmName) {
        const cacheKey = `verifiedVm_${config.vmName}`;
        saveConfig({ [cacheKey]: config.vmName });
      }

      return result;
    } catch (error: any) {
      return { success: false, error: error.message };
    }
  });

  // 从已有 VM 文件夹恢复（导入）
  ipcMain.removeAllListeners('vm-restore-from-folder');
  ipcMain.handle('vm-restore-from-folder', async (_event, config: {
    vmName?: string;
    folderPath: string;
  }) => {
    try {
      const folderPath = String(config?.folderPath || '').trim();
      if (!folderPath) {
        return { success: false, error: 'VM folder path is required' };
      }
      if (!fs.existsSync(folderPath) || !fs.statSync(folderPath).isDirectory()) {
        return { success: false, error: 'Selected VM folder does not exist' };
      }

      const requestedVmName = String(config?.vmName || '').trim();
      const escapedFolderPath = escapePsSingleQuoted(folderPath);
      const escapedRequestedVmName = escapePsSingleQuoted(requestedVmName);
      const psScript = `
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$OutputEncoding = [Console]::OutputEncoding
$folderPath = '${escapedFolderPath}'
$requestedVmName = '${escapedRequestedVmName}'
$vmName = $null
$restoreMode = 'unknown'
$targetVmName = if ($requestedVmName) { $requestedVmName } else { (Split-Path -Leaf $folderPath) }
if (-not $targetVmName) { $targetVmName = 'UseIt-Dev-VM' }
if ($requestedVmName) {
  $existing = Get-VM -Name $requestedVmName -ErrorAction SilentlyContinue
  if ($existing) {
    $vmName = $existing.Name
  }
}
if (-not $vmName) {
  $vmcx = Get-ChildItem -Path $folderPath -Filter *.vmcx -File -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1
  if ($vmcx) {
    try {
      $imported = Import-VM -Path $vmcx.FullName -Register -ErrorAction Stop
    } catch {
      $importErr = $_.Exception.Message
      if ($importErr -match 'Access is denied|0x80070005') {
        # Fallback for exported folders with restricted ACL:
        # import by copy into an internal managed location.
        $safeName = ($targetVmName -replace '[^a-zA-Z0-9-_]','_')
        if (-not $safeName) { $safeName = 'UseIt_Imported_VM' }
        $importRoot = Join-Path $env:ProgramData ('UseIt\\ImportedVMs\\' + $safeName)
        $vmPath = Join-Path $importRoot 'Virtual Machines'
        $vhdPath = Join-Path $importRoot 'Virtual Hard Disks'
        $snapPath = Join-Path $importRoot 'Snapshots'
        New-Item -Path $vmPath -ItemType Directory -Force | Out-Null
        New-Item -Path $vhdPath -ItemType Directory -Force | Out-Null
        New-Item -Path $snapPath -ItemType Directory -Force | Out-Null
        $imported = Import-VM -Path $vmcx.FullName -Copy -GenerateNewId -VirtualMachinePath $vmPath -VhdDestinationPath $vhdPath -SnapshotFilePath $snapPath -ErrorAction Stop
      } else {
        throw
      }
    }
    $vmName = $imported.Name
    $restoreMode = 'import'
    if ($requestedVmName -and $requestedVmName -ne $vmName) {
      Rename-VM -Name $vmName -NewName $requestedVmName -ErrorAction Stop
      $vmName = $requestedVmName
    }
  } else {
    # fallback: restore from plain VM folder by attaching existing disk chain leaf
    $allDisks = Get-ChildItem -Path $folderPath -File -Recurse -ErrorAction SilentlyContinue |
      Where-Object { $_.Extension.ToLower() -in '.avhdx', '.vhdx', '.vhd' }
    $disk = $null
    if ($allDisks) {
      $parentPathSet = @{}
      foreach ($candidate in $allDisks) {
        try {
          $vhdInfo = Get-VHD -Path $candidate.FullName -ErrorAction Stop
          if ($vhdInfo.ParentPath) {
            $parentPathSet[$vhdInfo.ParentPath.ToLower()] = $true
          }
        } catch {
          # ignore unreadable disk metadata and continue
        }
      }
      $leafCandidates = $allDisks | Where-Object { -not $parentPathSet.ContainsKey($_.FullName.ToLower()) }
      if ($leafCandidates -and $leafCandidates.Count -gt 0) {
        $disk = $leafCandidates | Sort-Object LastWriteTime -Descending | Select-Object -First 1
      } else {
        $disk = $allDisks | Sort-Object LastWriteTime -Descending | Select-Object -First 1
      }
    }
    if (-not $disk) {
      throw 'No VM config (.vmcx) or disk (.avhdx/.vhdx/.vhd) found in selected folder.'
    }
    $existingTarget = Get-VM -Name $targetVmName -ErrorAction SilentlyContinue
    if ($existingTarget) {
      $vmName = $existingTarget.Name
      $restoreMode = 'disk_fallback'
    } else {
      New-VM -Name $targetVmName -Generation 2 -MemoryStartupBytes 4GB -NoVHD -ErrorAction Stop | Out-Null
      Add-VMHardDiskDrive -VMName $targetVmName -Path $disk.FullName -ErrorAction Stop | Out-Null
      $hdd = Get-VMHardDiskDrive -VMName $targetVmName | Select-Object -First 1
      if ($hdd) {
        Set-VMFirmware -VMName $targetVmName -FirstBootDevice $hdd -EnableSecureBoot Off -ErrorAction SilentlyContinue | Out-Null
      }
      Set-VM -Name $targetVmName -CheckpointType Standard -ErrorAction SilentlyContinue | Out-Null
      $switch = Get-VMSwitch | Where-Object { $_.SwitchType -eq 'External' } | Select-Object -First 1
      if (-not $switch) {
        $switch = Get-VMSwitch | Where-Object { $_.Name -eq 'Default Switch' } | Select-Object -First 1
      }
      if (-not $switch) {
        $switch = Get-VMSwitch | Select-Object -First 1
      }
      if ($switch) {
        Connect-VMNetworkAdapter -VMName $targetVmName -SwitchName $switch.Name -ErrorAction SilentlyContinue | Out-Null
      }
      $vmName = $targetVmName
      $restoreMode = 'disk_fallback'
    }
  }
}
$checkpointCount = 0
try {
  $checkpointCount = (Get-VMCheckpoint -VMName $vmName -ErrorAction SilentlyContinue | Measure-Object).Count
} catch {
  $checkpointCount = 0
}
[PSCustomObject]@{
  vmName = $vmName
  checkpointCount = [int]$checkpointCount
  restoreMode = $restoreMode
} | ConvertTo-Json -Compress
`;
      const os = require('os');
      const tempScriptPath = path.join(os.tmpdir(), `useit_vm_restore_${Date.now()}.ps1`);
      let stdout = '';
      try {
        fs.writeFileSync(tempScriptPath, psScript, 'utf8');
        const execResult = await execAsync(
          `powershell -NoProfile -ExecutionPolicy Bypass -File "${tempScriptPath}"`
        );
        stdout = String(execResult?.stdout || '');
      } finally {
        try {
          if (fs.existsSync(tempScriptPath)) fs.unlinkSync(tempScriptPath);
        } catch {
          // ignore cleanup failure
        }
      }
      const payloadRaw = String(stdout || '').trim();
      const parsed = payloadRaw ? JSON.parse(payloadRaw) : {};
      const importedVmName = String(parsed?.vmName || requestedVmName || '').trim();
      const checkpointCount = Number(parsed?.checkpointCount || 0);
      const restoreMode = String(parsed?.restoreMode || 'unknown');
      if (!importedVmName) {
        return { success: false, error: 'Failed to resolve restored VM name' };
      }

      const cacheKey = `verifiedVm_${importedVmName}`;
      saveConfig({ [cacheKey]: importedVmName });
      return { success: true, vmName: importedVmName, checkpointCount, restoreMode };
    } catch (error: any) {
      const raw = String(error?.stderr || error?.message || '');
      const psErrors = Array.from(raw.matchAll(/<S S="Error">([^<]+)<\/S>/g)).map((m) =>
        m[1].replace(/_x000D__x000A_/g, '\n').trim()
      );
      const readable = psErrors.find(
        (line) =>
          line &&
          !/^At line:/i.test(line) &&
          !/^\+ /.test(line) &&
          !/^CategoryInfo/i.test(line) &&
          !/^FullyQualifiedErrorId/i.test(line)
      );
      return { success: false, error: readable || raw || 'Failed to restore VM from folder' };
    }
  });

  // 导出 VM 到指定目录（Hyper-V export，包含 vmcx 元数据）
  ipcMain.removeAllListeners('vm-export-to-folder');
  ipcMain.handle('vm-export-to-folder', async (_event, config: { vmName: string; exportDir: string }) => {
    try {
      const resolvedVmName = await resolveVmName(String(config?.vmName || ''));
      if (!resolvedVmName) {
        clearVmCache(config?.vmName || '');
        return { success: false, error: `Virtual machine "${normalizeVmNameInput(config?.vmName || '')}" not found.` };
      }
      const exportDir = String(config?.exportDir || '').trim();
      if (!exportDir) {
        return { success: false, error: 'Export directory is required' };
      }

      const escapedVmName = escapePsSingleQuoted(resolvedVmName);
      const escapedExportDir = escapePsSingleQuoted(exportDir);
      const psScript = `
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$OutputEncoding = [Console]::OutputEncoding
$vmName = '${escapedVmName}'
$exportDir = '${escapedExportDir}'
if (-not (Test-Path $exportDir)) {
  New-Item -Path $exportDir -ItemType Directory -Force | Out-Null
}
$vm = Get-VM -Name $vmName -ErrorAction Stop
$wasRunning = $vm.State -eq 'Running'
$stoppedByUs = $false
$exported = $false
$lastError = $null
try {
  try {
    Export-VM -Name $vmName -Path $exportDir -ErrorAction Stop | Out-Null
    $exported = $true
  } catch {
    $lastError = $_
    # Some hosts fail export due to live checkpoint/resume device issues.
    # Fallback: stop VM and retry export.
    if ($wasRunning) {
      Stop-VM -Name $vmName -TurnOff -Force -ErrorAction SilentlyContinue | Out-Null
      $stoppedByUs = $true
      Start-Sleep -Milliseconds 800
      Export-VM -Name $vmName -Path $exportDir -ErrorAction Stop | Out-Null
      $exported = $true
    } else {
      throw
    }
  }
  if (-not $exported -and $lastError) {
    throw $lastError
  }
} finally {
  if ($wasRunning -and $stoppedByUs) {
    try {
      Start-VM -Name $vmName -ErrorAction SilentlyContinue | Out-Null
    } catch {
      # ignore restart failure after export
    }
  }
}
[PSCustomObject]@{
  vmName = $vmName
  exportPath = $exportDir
} | ConvertTo-Json -Compress
`;
      const encodedCommand = Buffer.from(psScript, 'utf16le').toString('base64');
      const { stdout } = await execAsync(`powershell -NoProfile -EncodedCommand ${encodedCommand}`);
      const payloadRaw = String(stdout || '').trim();
      const parsed = payloadRaw ? JSON.parse(payloadRaw) : {};
      return {
        success: true,
        vmName: String(parsed?.vmName || resolvedVmName),
        exportPath: String(parsed?.exportPath || exportDir),
      };
    } catch (error: any) {
      const raw = String(error?.stderr || error?.message || '');
      const psErrors = Array.from(raw.matchAll(/<S S="Error">([^<]+)<\/S>/g)).map((m) =>
        m[1].replace(/_x000D__x000A_/g, '\n').trim()
      );
      const readable = psErrors.find(
        (line) =>
          line &&
          !/^At line:/i.test(line) &&
          !/^\+ /.test(line) &&
          !/^CategoryInfo/i.test(line) &&
          !/^FullyQualifiedErrorId/i.test(line)
      );
      return { success: false, error: readable || raw || 'Failed to export VM' };
    }
  });

  // 取消安装
  ipcMain.removeAllListeners('vm-install-cancel');
  ipcMain.handle('vm-install-cancel', async () => {
    vmInstaller.cancel();
    return { success: true };
  });

  // ==================== 服务部署 API ====================

  // 设置 serviceDeployer 的窗口引用
  serviceDeployer.setWindow(win);

  // 检查服务文件是否存在
  ipcMain.removeAllListeners('service-has-files');
  ipcMain.handle('service-has-files', async () => {
    return { success: true, hasFiles: serviceDeployer.hasServiceFiles() };
  });

  // 获取本地服务版本
  ipcMain.removeAllListeners('service-get-local-version');
  ipcMain.handle('service-get-local-version', async () => {
    return { success: true, version: serviceDeployer.getLocalVersion() };
  });

  // 部署服务到 VM
  ipcMain.removeAllListeners('service-deploy');
  ipcMain.handle('service-deploy', async (_event, { vmName, username, password }: {
    vmName: string;
    username?: string;
    password?: string;
  }) => {
    try {
      const result = await serviceDeployer.deploy(vmName, username, password);
      return result;
    } catch (error: any) {
      return { success: false, error: error.message };
    }
  });

  // 检查服务状态
  ipcMain.removeAllListeners('service-check-status');
  ipcMain.handle('service-check-status', async (_event, { vmName, serviceKey, username, password }: {
    vmName: string;
    serviceKey: string;
    username?: string;
    password?: string;
  }) => {
    try {
      const status = await serviceDeployer.checkServiceStatus(
        vmName,
        username || 'useit',
        password || '12345678',
        serviceKey
      );
      return { success: true, status };
    } catch (error: any) {
      return { success: false, error: error.message };
    }
  });

  // 停止服务
  ipcMain.removeAllListeners('service-stop');
  ipcMain.handle('service-stop', async (_event, { vmName, username, password }: {
    vmName: string;
    username?: string;
    password?: string;
  }) => {
    try {
      const result = await serviceDeployer.stopServices(vmName, username, password);
      return result;
    } catch (error: any) {
      return { success: false, error: error.message };
    }
  });

  // 重启服务
  ipcMain.removeAllListeners('service-restart');
  ipcMain.handle('service-restart', async (_event, { vmName, username, password }: {
    vmName: string;
    username?: string;
    password?: string;
  }) => {
    try {
      const result = await serviceDeployer.restartServices(vmName, username, password);
      return result;
    } catch (error: any) {
      return { success: false, error: error.message };
    }
  });

  // ==================== VM 共享文件夹 API ====================
  // 挂载 projects 父目录到 VM 的 Z: 盘（一次挂载，切换 project 零延迟）

  ipcMain.removeAllListeners('vm-share-ensure');
  ipcMain.handle('vm-share-ensure', async (_event, config: {
    vmName: string;
    username?: string;
    password?: string;
    projectsRootPath: string;
  }) => {
    try {
      return await vmShareManager.ensureShared({
        vmName: config.vmName,
        username: config.username || 'useit',
        password: config.password || '12345678',
        projectsRootPath: config.projectsRootPath,
      });
    } catch (error: any) {
      return { success: false, driveLetter: 'Z', error: error.message };
    }
  });

  ipcMain.removeAllListeners('vm-share-health');
  ipcMain.handle('vm-share-health', async (_event, config: {
    vmName: string;
    username?: string;
    password?: string;
  }) => {
    try {
      const status = await vmShareManager.checkHealth({
        vmName: config.vmName,
        username: config.username || 'useit',
        password: config.password || '12345678',
      });
      return { success: true, ...status };
    } catch (error: any) {
      return { success: false, healthy: false, error: error.message };
    }
  });

  ipcMain.removeAllListeners('vm-share-teardown');
  ipcMain.handle('vm-share-teardown', async (_event, config: {
    vmName: string;
    username?: string;
    password?: string;
  }) => {
    try {
      await vmShareManager.teardown({
        vmName: config.vmName,
        username: config.username || 'useit',
        password: config.password || '12345678',
      });
      return { success: true };
    } catch (error: any) {
      return { success: false, error: error.message };
    }
  });

  ipcMain.removeAllListeners('vm-share-get-vm-path');
  ipcMain.handle('vm-share-get-vm-path', async (_event, config: {
    projectName: string;
  }) => {
    return { success: true, vmPath: vmShareManager.getVmProjectPath(config.projectName) };
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

  // 启动内置 VNC WebSocket 代理（类似 websockify），默认监听 16080
  try {
    vncProxy.start({ listenPort: 16080 });
    vncProxy.on('listening', ({ port }) => {
      console.log(`VNC proxy listening on ws://127.0.0.1:${port}`);
    });
    vncProxy.on('connection', ({ host, vncPort }) => {
      console.log(`[VNC proxy] TCP connected -> ${host}:${vncPort}`);
    });
    vncProxy.on('error', (err) => {
      console.error('VNC proxy error:', err);
    });
  } catch (e) {
    console.error('Failed to start VNC proxy:', e);
  }

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
