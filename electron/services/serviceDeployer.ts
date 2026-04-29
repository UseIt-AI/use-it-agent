/**
 * Service Deployer
 * 负责将 Local Engine 部署到 VM 中
 * 
 * 注意：Local Engine 已整合 Computer Server 功能，需要访问桌面（截图、鼠标、键盘），
 * 必须以登录用户身份在交互式会话中运行。
 * 
 * 功能：
 * 1. 将打包好的 exe 复制到 VM
 * 2. 在 VM 中注册为 Windows 任务（Task Scheduler）
 * 3. 启动服务
 * 4. 检查服务状态
 * 5. 更新服务
 */

import { exec, spawn } from 'child_process';
import { promisify } from 'util';
import * as path from 'path';
import * as fs from 'fs';
import { BrowserWindow, app } from 'electron';

const execAsync = promisify(exec);

// ============================================================
// 配置
// ============================================================

export interface ServiceConfig {
  name: string;           // 服务名称
  displayName: string;    // 显示名称
  dirName: string;        // 服务目录名
  exeName: string;        // exe 文件名
  port: number;           // 服务端口
}

export const SERVICES: Record<string, ServiceConfig> = {
  local_engine: {
    name: 'UseItLocalEngine',
    displayName: 'UseIt Local Engine',
    dirName: 'local_engine',
    exeName: 'local_engine.exe',
    port: 8324,
  },
};

// VM 中的安装路径
const VM_BASE_PATH = 'C:\\UseIt';
const VM_INSTALL_PATH = `${VM_BASE_PATH}\\services`;
const VM_LOG_PATH = `${VM_BASE_PATH}\\logs`;
const VM_CONFIG_PATH = `${VM_BASE_PATH}\\config`;

// ============================================================
// 类型定义
// ============================================================

export interface DeployProgress {
  step: string;
  stepIndex: number;
  totalSteps: number;
  percent: number;
  message: string;
  messageKey?: string;  // i18n key for frontend translation
  messageParams?: Record<string, string | number>;  // i18n interpolation params
  error?: string;
}

export interface ServiceStatus {
  installed: boolean;
  running: boolean;
  version?: string;
  port?: number;
  error?: string;
}

export interface DeployResult {
  success: boolean;
  error?: string;
  services?: Record<string, ServiceStatus>;
}

// ============================================================
// Service Deployer 类
// ============================================================

export class ServiceDeployer {
  private win: BrowserWindow | null = null;
  private resourcesPath: string;

  constructor() {
    // 获取资源目录路径
    const isDev = process.env.NODE_ENV === 'development' || !app.isPackaged;
    
    if (isDev) {
      // 开发环境: frontend/resources/services
      const appPath = app.getAppPath();
      const possiblePaths = [
        path.join(appPath, 'resources', 'services'),
        path.join(appPath, 'frontend', 'resources', 'services'),
        path.join(__dirname, '../../resources/services'),
        path.join(__dirname, '../../../resources/services'),
      ];
      
      this.resourcesPath = possiblePaths.find(p => {
        try {
          return fs.existsSync(p);
        } catch {
          return false;
        }
      }) || possiblePaths[0];
    } else {
      // 生产环境
      this.resourcesPath = path.join(process.resourcesPath, 'resources', 'services');
    }
    
    console.log('[ServiceDeployer] Resources path:', this.resourcesPath);
  }

  /**
   * 设置窗口引用，用于发送进度通知
   */
  setWindow(win: BrowserWindow) {
    this.win = win;
  }

  /**
   * 发送部署进度到渲染进程
   */
  private sendProgress(progress: DeployProgress) {
    if (this.win && !this.win.isDestroyed()) {
      this.win.webContents.send('service-deploy-progress', progress);
    }
  }

  /**
   * 获取本地服务目录路径
   */
  private getLocalServiceDir(serviceName: string): string | null {
    const service = SERVICES[serviceName];
    if (!service) return null;

    // 服务目录：services/{dirName}/
    const serviceDir = path.join(this.resourcesPath, service.dirName);
    const exePath = path.join(serviceDir, service.exeName);
    
    if (fs.existsSync(serviceDir) && fs.existsSync(exePath)) {
      return serviceDir;
    }

    console.warn(`[ServiceDeployer] Service dir not found: ${serviceDir} or exe not found: ${exePath}`);
    return null;
  }

  /**
   * 获取本地 exe 文件路径 (向后兼容)
   */
  private getLocalExePath(serviceName: string): string | null {
    const serviceDir = this.getLocalServiceDir(serviceName);
    if (!serviceDir) return null;
    
    const service = SERVICES[serviceName];
    return path.join(serviceDir, service.exeName);
  }

  /**
   * 获取本地服务版本
   */
  getLocalVersion(): string | null {
    try {
      const versionPath = path.join(this.resourcesPath, 'version.json');
      if (fs.existsSync(versionPath)) {
        const content = fs.readFileSync(versionPath, 'utf8');
        const json = JSON.parse(content);
        return json.version;
      }
    } catch (e) {
      console.error('[ServiceDeployer] Failed to read version.json:', e);
    }
    return null;
  }

  /**
   * 检查服务文件是否存在
   */
  hasServiceFiles(): boolean {
    for (const key of Object.keys(SERVICES)) {
      if (!this.getLocalServiceDir(key)) {
        return false;
      }
    }
    return true;
  }

  /**
   * 需要跳过的目录和文件模式
   */
  private readonly SKIP_PATTERNS = {
    // 跳过的目录名
    directories: ['logs', '__pycache__', '.git', 'node_modules', '.venv', 'venv'],
    // 跳过的文件扩展名
    extensions: ['.log', '.pyc', '.pyo', '.tmp', '.temp'],
    // 跳过的文件名
    files: ['.DS_Store', 'Thumbs.db', '.gitignore', '.gitkeep'],
  };

  /**
   * 检查是否应该跳过该文件/目录
   */
  private shouldSkipFile(relativePath: string, isDirectory: boolean): boolean {
    const name = path.basename(relativePath);
    const ext = path.extname(relativePath).toLowerCase();
    
    if (isDirectory) {
      return this.SKIP_PATTERNS.directories.includes(name);
    }
    
    // 检查文件名
    if (this.SKIP_PATTERNS.files.includes(name)) {
      return true;
    }
    
    // 检查扩展名
    if (this.SKIP_PATTERNS.extensions.includes(ext)) {
      return true;
    }
    
    // 检查是否在跳过的目录中
    const pathParts = relativePath.split(/[/\\]/);
    for (const dir of this.SKIP_PATTERNS.directories) {
      if (pathParts.includes(dir)) {
        return true;
      }
    }
    
    return false;
  }

  /**
   * 递归获取目录中的所有文件
   */
  private getAllFilesInDir(dirPath: string, basePath: string = dirPath): { relativePath: string; absolutePath: string }[] {
    const files: { relativePath: string; absolutePath: string }[] = [];
    
    const entries = fs.readdirSync(dirPath, { withFileTypes: true });
    for (const entry of entries) {
      const fullPath = path.join(dirPath, entry.name);
      const relativePath = path.relative(basePath, fullPath);
      
      // 检查是否应该跳过
      if (this.shouldSkipFile(relativePath, entry.isDirectory())) {
        continue;
      }
      
      if (entry.isDirectory()) {
        // 递归获取子目录中的文件
        files.push(...this.getAllFilesInDir(fullPath, basePath));
      } else {
        files.push({ relativePath, absolutePath: fullPath });
      }
    }
    
    return files;
  }

  /**
   * 运行 PowerShell 脚本
   */
  /**
   * 从 PowerShell CLIXML 错误输出中提取关键错误信息
   */
  private extractPowerShellError(stderr: string): string {
    // Try extracting VM Command Error from CLIXML
    const vmErrorMatch = stderr.match(/VM Command Error:\s*([^_\r\n]+)/);
    if (vmErrorMatch) {
      return vmErrorMatch[1].trim();
    }

    // Try extracting <S S="Error"> lines from CLIXML
    if (stderr.includes('CLIXML')) {
      const errorLines: string[] = [];
      const regex = /<S S="Error">([^<]+)<\/S>/g;
      let match;
      while ((match = regex.exec(stderr)) !== null) {
        let line = match[1]
          .replace(/_x000D__x000A_/g, '')
          .replace(/\s+/g, ' ')
          .trim();
        if (!line) continue;
        // Skip stack trace / metadata lines
        if (/^(At line:|[+~]|\s*CategoryInfo|\s*FullyQualifiedErrorId)/.test(line)) continue;
        // Strip cmdlet prefix ("Start-VM : "), Instance/VM IDs, and redundant detail
        line = line
          .replace(/^\S+-\S+\s*:\s*/, '')
          .replace(/\(Instance ID [0-9a-fA-F-]+\)/g, '')
          .replace(/\(Virtual machine ID [0-9a-fA-F-]+\)/g, '')
          .replace(/\s{2,}/g, ' ')
          .trim();
        if (line) errorLines.push(line);
      }
      // Deduplicate: later lines often repeat the first error
      const seen = new Set<string>();
      const unique = errorLines.filter(l => {
        const key = l.toLowerCase();
        if (seen.has(key)) return false;
        // Also skip if a previous line already contains the core message
        for (const s of seen) {
          if (s.includes(key) || key.includes(s)) return false;
        }
        seen.add(key);
        return true;
      });
      if (unique.length > 0) {
        return unique.slice(0, 2).join(' ');
      }
    }

    // Try common error patterns
    const errorPatterns = [
      /The virtual machine [^\s]+ is not in running state/,
      /Cannot connect to VM/,
      /Access is denied/,
      /The operation has timed out/,
      /failed to start/i,
      /The process cannot access the file/,
    ];
    for (const pattern of errorPatterns) {
      const match = stderr.match(pattern);
      if (match) {
        return match[0];
      }
    }

    if (stderr.includes('CLIXML')) {
      return 'PowerShell command failed (see debug logs for details)';
    }
    return stderr.substring(0, 200);
  }

  private async runPowerShell(script: string, debug: boolean = false): Promise<string> {
    if (debug) {
      console.log('[ServiceDeployer] Running PowerShell script:\n', script);
    }
    const encodedCommand = Buffer.from(script, 'utf16le').toString('base64');
    try {
      const { stdout, stderr } = await execAsync(`powershell -EncodedCommand ${encodedCommand}`, {
        maxBuffer: 10 * 1024 * 1024, // 10MB buffer
      });
      if (debug) {
        console.log('[ServiceDeployer] PowerShell stdout:', stdout);
        if (stderr) console.log('[ServiceDeployer] PowerShell stderr:', stderr);
      }
      if (stderr && !stdout && !stderr.includes('CLIXML')) {
        throw new Error(stderr);
      }
      return stdout;
    } catch (error: any) {
      // 提取简洁的错误信息，避免输出大量 CLIXML 内容
      const errorMsg = this.extractPowerShellError(error.stderr || error.message);
      console.error('[ServiceDeployer] PowerShell error:', errorMsg);
      if (debug) {
        // 仅在 debug 模式下输出完整错误
        if (error.stdout) console.log('[ServiceDeployer] Error stdout:', error.stdout);
        if (error.stderr) console.log('[ServiceDeployer] Error stderr:', error.stderr);
      }
      throw error;
    }
  }

  /**
   * 通过 PowerShell Direct 在 VM 中执行命令
   */
  private async runInVm(
    vmName: string,
    username: string,
    password: string,
    scriptBlock: string,
    debug: boolean = false
  ): Promise<string> {
    const script = `
      $ErrorActionPreference = 'Stop'
      $secPassword = ConvertTo-SecureString '${password}' -AsPlainText -Force
      $cred = New-Object System.Management.Automation.PSCredential ('${username}', $secPassword)
      try {
        $result = Invoke-Command -VMName '${vmName}' -Credential $cred -ScriptBlock {
          ${scriptBlock}
        } -ErrorAction Stop
        Write-Output $result
      } catch {
        Write-Error "VM Command Error: $_"
        throw
      }
    `;
    return this.runPowerShell(script, debug);
  }

  /**
   * 确保 VM Guest Service Interface 已启用
   */
  private async ensureGuestServiceEnabled(vmName: string): Promise<void> {
    console.log(`[ServiceDeployer] ensureGuestServiceEnabled: Starting for VM '${vmName}'`);
    
    // Guest Service Interface 在不同语言的 Windows 上可能有不同名称
    // 英文: Guest Service Interface
    // 中文: 来宾服务
    const script = `
      $ErrorActionPreference = 'Stop'
      
      Write-Host "[DEBUG] Getting VM '${vmName}'..."
      $vm = Get-VM -Name '${vmName}' -ErrorAction Stop
      Write-Host "[DEBUG] VM found: $($vm.Name), State: $($vm.State)"
      
      Write-Host "[DEBUG] Listing all Integration Services..."
      $allServices = $vm | Get-VMIntegrationService
      $allServices | ForEach-Object {
        Write-Host "[DEBUG]   Service: $($_.Name), Enabled: $($_.Enabled), Status: $($_.OperationalStatus)"
      }
      
      # 尝试找到 Guest Service Interface (支持中英文)
      Write-Host "[DEBUG] Looking for Guest Service Interface..."
      $guestService = $allServices | Where-Object { 
        $_.Name -eq 'Guest Service Interface' -or 
        $_.Name -like '*Guest*' -or 
        $_.Name -eq '来宾服务' 
      } | Select-Object -First 1
      
      if (-not $guestService) {
        Write-Host "[WARNING] Guest Service Interface not found! Available services:"
        $allServices | ForEach-Object { Write-Host "  - $($_.Name)" }
        Write-Output 'NOTFOUND'
        return
      }
      
      Write-Host "[DEBUG] Found service: $($guestService.Name), Enabled: $($guestService.Enabled)"
      
      if (-not $guestService.Enabled) {
        Write-Host "[DEBUG] Enabling Guest Service Interface..."
        try {
          Enable-VMIntegrationService -VM $vm -Name $guestService.Name -ErrorAction Stop
          Write-Host "[DEBUG] Waiting 2 seconds..."
          Start-Sleep -Seconds 2
          Write-Host "[DEBUG] Service enabled successfully"
        } catch {
          Write-Host "[ERROR] Failed to enable service: $_"
          throw
        }
      } else {
        Write-Host "[DEBUG] Service is already enabled"
      }
      
      Write-Output 'OK'
    `;
    
    try {
      console.log(`[ServiceDeployer] ensureGuestServiceEnabled: Executing PowerShell script...`);
      const result = await this.runPowerShell(script, true);
      console.log(`[ServiceDeployer] ensureGuestServiceEnabled: Result = '${result.trim()}'`);
      
      if (result.trim() === 'NOTFOUND') {
        console.warn(`[ServiceDeployer] Guest Service Interface not found, but continuing...`);
      }
    } catch (error: any) {
      console.error(`[ServiceDeployer] ensureGuestServiceEnabled: Error:`, error.message);
      throw error;
    }
  }

  /**
   * 在 VM 中确保目录存在
   */
  private async ensureVmDirectoryExists(
    vmName: string,
    username: string,
    password: string,
    dirPath: string
  ): Promise<void> {
    const script = `
      $dirPath = '${dirPath}'
      if (-not (Test-Path -LiteralPath $dirPath)) {
        New-Item -Path $dirPath -ItemType Directory -Force | Out-Null
      }
      'OK'
    `;
    await this.runInVm(vmName, username, password, script, false);
  }

  /**
   * 复制文件到 VM
   */
  private async copyFileToVm(
    vmName: string,
    localPath: string,
    vmPath: string,
    debug: boolean = false
  ): Promise<void> {
    // 规范化路径 - 确保使用反斜杠
    const normalizedLocalPath = localPath.replace(/\//g, '\\');
    const normalizedVmPath = vmPath.replace(/\//g, '\\');
    
    if (debug) {
      console.log(`[ServiceDeployer] copyFileToVm: local="${normalizedLocalPath}" -> vm="${normalizedVmPath}"`);
    }
    
    // 使用 Copy-VMFile (Hyper-V 内置)
    // 注意：PowerShell 中单引号内的路径不需要转义反斜杠
    const script = `
      $ErrorActionPreference = 'Stop'
      
      $sourcePath = '${normalizedLocalPath}'
      $destPath = '${normalizedVmPath}'
      
      # 检查源文件是否存在
      if (-not (Test-Path -LiteralPath $sourcePath)) {
        throw "Source file not found: $sourcePath"
      }
      
      # 获取源文件信息
      $sourceFile = Get-Item -LiteralPath $sourcePath
      Write-Host "Copying: $($sourceFile.Name) ($($sourceFile.Length) bytes) -> $destPath"
      
      # 复制文件到 VM
      try {
        Copy-VMFile -Name '${vmName}' -SourcePath $sourcePath -DestinationPath $destPath -CreateFullPath -FileSource Host -Force -ErrorAction Stop
        Write-Output 'OK'
      } catch {
        Write-Host "Copy-VMFile Error Details:"
        Write-Host "  Source: $sourcePath"
        Write-Host "  Dest: $destPath"
        Write-Host "  Exception: $($_.Exception.Message)"
        Write-Host "  FullError: $_"
        throw "Copy-VMFile failed for $($sourceFile.Name): $($_.Exception.Message)"
      }
    `;
    
    await this.runPowerShell(script, debug);
  }

  // ZIP 缓存目录
  private zipCacheDir: string = '';

  /**
   * 获取 ZIP 缓存目录
   */
  private getZipCacheDir(): string {
    if (!this.zipCacheDir) {
      this.zipCacheDir = path.join(app.getPath('userData'), 'deploy_cache');
      if (!fs.existsSync(this.zipCacheDir)) {
        fs.mkdirSync(this.zipCacheDir, { recursive: true });
      }
    }
    return this.zipCacheDir;
  }

  /**
   * 计算目录的简单哈希（基于文件列表和修改时间）
   */
  private getDirHash(dirPath: string): string {
    const files = this.getAllFilesInDir(dirPath);
    // 按路径排序确保一致性
    files.sort((a, b) => a.relativePath.localeCompare(b.relativePath));
    
    // 获取每个文件的修改时间
    const hashData = files.map(f => {
      try {
        const stat = fs.statSync(f.absolutePath);
        return `${f.relativePath}:${stat.mtimeMs}:${stat.size}`;
      } catch {
        return f.relativePath;
      }
    }).join('|');
    
    // 简单哈希
    let hash = 0;
    for (let i = 0; i < hashData.length; i++) {
      const char = hashData.charCodeAt(i);
      hash = ((hash << 5) - hash) + char;
      hash = hash & hash;
    }
    return Math.abs(hash).toString(16);
  }

  /**
   * 获取或创建服务的 ZIP 缓存
   */
  private async getOrCreateServiceZip(serviceName: string, localServiceDir: string): Promise<string> {
    const normalizedLocalDir = localServiceDir.replace(/\//g, '\\');
    const cacheDir = this.getZipCacheDir();
    const dirHash = this.getDirHash(localServiceDir);
    const zipFileName = `${serviceName}_${dirHash}.zip`;
    const zipPath = path.join(cacheDir, zipFileName);

    // 检查缓存是否存在且有效
    if (fs.existsSync(zipPath)) {
      const stat = fs.statSync(zipPath);
      if (stat.size > 0) {
        console.log(`[ServiceDeployer] Using cached ZIP: ${zipPath}`);
        console.log(`[ServiceDeployer]   Size: ${(stat.size / 1024 / 1024).toFixed(2)} MB`);
        return zipPath;
      }
    }

    // 清理旧的缓存文件（同一服务的其他版本）
    const oldCaches = fs.readdirSync(cacheDir).filter(f => f.startsWith(`${serviceName}_`) && f.endsWith('.zip'));
    for (const oldCache of oldCaches) {
      const oldPath = path.join(cacheDir, oldCache);
      if (oldPath !== zipPath) {
        console.log(`[ServiceDeployer] Removing old cache: ${oldCache}`);
        try {
          fs.unlinkSync(oldPath);
        } catch (e) {
          // 忽略删除错误
        }
      }
    }

    console.log(`[ServiceDeployer] Creating new ZIP cache: ${zipPath}`);

    // 使用 PowerShell 创建 ZIP（排除不需要的文件）
    const createZipScript = `
      $ErrorActionPreference = 'Stop'
      
      $sourceDir = '${normalizedLocalDir}'
      $zipPath = '${zipPath.replace(/\\/g, '\\\\')}'
      
      # 删除已存在的 ZIP
      if (Test-Path $zipPath) {
        Remove-Item $zipPath -Force
      }
      
      # 获取要压缩的文件（排除日志等）
      $excludeDirs = @('logs', '__pycache__', '.git', 'node_modules', '.venv', 'venv')
      $excludeExts = @('.log', '.pyc', '.pyo', '.tmp', '.temp')
      $excludeFiles = @('.DS_Store', 'Thumbs.db', '.gitignore', '.gitkeep')
      
      # 创建临时目录用于筛选文件
      $tempCopyDir = Join-Path $env:TEMP "useit_zip_temp_$(Get-Random)"
      New-Item -Path $tempCopyDir -ItemType Directory -Force | Out-Null
      
      # 使用 robocopy 复制文件（排除不需要的）
      $excludeDirArgs = $excludeDirs | ForEach-Object { "/XD", $_ }
      $excludeFileArgs = $excludeExts | ForEach-Object { "*$_" }
      $excludeFileArgs += $excludeFiles
      
      # robocopy 参数: /E 递归 /XD 排除目录 /XF 排除文件
      $robocopyArgs = @($sourceDir, $tempCopyDir, '/E', '/NFL', '/NDL', '/NJH', '/NJS', '/NC', '/NS', '/NP')
      $robocopyArgs += $excludeDirArgs
      $robocopyArgs += '/XF'
      $robocopyArgs += $excludeFileArgs
      
      $robocopyResult = & robocopy @robocopyArgs
      
      # 压缩临时目录
      Compress-Archive -Path "$tempCopyDir\\*" -DestinationPath $zipPath -Force
      
      # 清理临时目录
      Remove-Item $tempCopyDir -Recurse -Force
      
      # 输出 ZIP 信息
      $zipFile = Get-Item $zipPath
      Write-Output "ZIP_SIZE:$($zipFile.Length)"
    `;

    const zipResult = await this.runPowerShell(createZipScript, false);
    const sizeMatch = zipResult.match(/ZIP_SIZE:(\d+)/);
    const zipSize = sizeMatch ? parseInt(sizeMatch[1]) : 0;
    console.log(`[ServiceDeployer]   ZIP created: ${(zipSize / 1024 / 1024).toFixed(2)} MB`);

    return zipPath;
  }

  /**
   * 复制整个服务目录到 VM（使用压缩传输 + 缓存，大幅提升速度）
   */
  private async copyServiceDirToVm(
    vmName: string,
    username: string,
    password: string,
    localServiceDir: string,
    vmServiceDir: string,
    onProgress?: (copied: number, total: number) => void
  ): Promise<void> {
    // 规范化路径
    const normalizedVmServiceDir = vmServiceDir.replace(/\//g, '\\');
    const serviceName = path.basename(localServiceDir);

    console.log(`[ServiceDeployer] ========================================`);
    console.log(`[ServiceDeployer] Copying service directory (ZIP mode with cache)`);
    console.log(`[ServiceDeployer] Local: ${localServiceDir}`);
    console.log(`[ServiceDeployer] VM: ${normalizedVmServiceDir}`);
    console.log(`[ServiceDeployer] ========================================`);

    if (onProgress) onProgress(1, 10);

    // 1. 获取或创建 ZIP 缓存
    console.log(`[ServiceDeployer] Step 1: Preparing ZIP archive...`);
    let localZipPath: string;
    try {
      localZipPath = await this.getOrCreateServiceZip(serviceName, localServiceDir);
    } catch (error: any) {
      console.error(`[ServiceDeployer] Failed to create ZIP:`, error.message);
      throw error;
    }

    const zipFileName = path.basename(localZipPath);
    const vmZipPath = `C:\\UseIt\\temp\\${zipFileName}`;

    if (onProgress) onProgress(3, 10);

    // 2. 确保 VM 中的临时目录存在
    console.log(`[ServiceDeployer] Step 2: Preparing VM temp directory...`);
    await this.runInVm(vmName, username, password, `
      $tempDir = 'C:\\UseIt\\temp'
      if (-not (Test-Path $tempDir)) {
        New-Item -Path $tempDir -ItemType Directory -Force | Out-Null
      }
      'OK'
    `, false);

    if (onProgress) onProgress(4, 10);

    // 3. 复制 ZIP 到 VM（单个大文件，比多个小文件快得多）
    console.log(`[ServiceDeployer] Step 3: Copying ZIP to VM...`);
    console.log(`[ServiceDeployer]   From: ${localZipPath}`);
    console.log(`[ServiceDeployer]   To: ${vmZipPath}`);
    await this.copyFileToVm(vmName, localZipPath, vmZipPath, false);

    if (onProgress) onProgress(7, 10);

    // 4. 在 VM 中解压
    console.log(`[ServiceDeployer] Step 4: Extracting ZIP in VM...`);
    const extractScript = `
      $ErrorActionPreference = 'Stop'
      
      $zipPath = '${vmZipPath}'
      $destDir = '${normalizedVmServiceDir}'
      
      # 确保目标目录存在
      if (-not (Test-Path $destDir)) {
        New-Item -Path $destDir -ItemType Directory -Force | Out-Null
      }
      
      # 解压（覆盖已存在的文件）
      Expand-Archive -Path $zipPath -DestinationPath $destDir -Force
      
      # 删除 VM 中的 ZIP 文件
      Remove-Item $zipPath -Force
      
      # 统计文件数
      $fileCount = (Get-ChildItem -Path $destDir -Recurse -File).Count
      Write-Output "EXTRACTED:$fileCount"
    `;

    try {
      const extractResult = await this.runInVm(vmName, username, password, extractScript, false);
      const countMatch = extractResult.match(/EXTRACTED:(\d+)/);
      const fileCount = countMatch ? parseInt(countMatch[1]) : 0;
      console.log(`[ServiceDeployer]   Extracted ${fileCount} files to VM`);
    } catch (error: any) {
      console.error(`[ServiceDeployer] Failed to extract ZIP in VM:`, error.message);
      throw error;
    }

    if (onProgress) onProgress(10, 10);

    console.log(`[ServiceDeployer] ========================================`);
    console.log(`[ServiceDeployer] Completed copying to ${normalizedVmServiceDir}`);
    console.log(`[ServiceDeployer] (ZIP cache retained for future deployments)`);
    console.log(`[ServiceDeployer] ========================================`);
  }

  /**
   * 清理 ZIP 缓存
   */
  clearZipCache(): void {
    const cacheDir = this.getZipCacheDir();
    console.log(`[ServiceDeployer] Clearing ZIP cache: ${cacheDir}`);
    
    try {
      const files = fs.readdirSync(cacheDir);
      for (const file of files) {
        if (file.endsWith('.zip')) {
          fs.unlinkSync(path.join(cacheDir, file));
          console.log(`[ServiceDeployer]   Deleted: ${file}`);
        }
      }
    } catch (e) {
      console.error(`[ServiceDeployer] Failed to clear cache:`, e);
    }
  }

  /**
   * 在 VM 中创建目录
   */
  private async createVmDirectory(
    vmName: string,
    username: string,
    password: string,
    dirPath: string
  ): Promise<void> {
    await this.runInVm(vmName, username, password, `
      if (-not (Test-Path '${dirPath}')) {
        New-Item -Path '${dirPath}' -ItemType Directory -Force | Out-Null
      }
      'OK'
    `);
  }

  /**
   * 在 VM 中注册服务 (使用 Task Scheduler，更简单可靠)
   * 
   * 重要：local_engine 现在整合了 computer_server 的功能，需要访问桌面（截图、鼠标、键盘），
   * 必须以登录用户身份在交互式会话中运行，不能用 SYSTEM 账户！
   */
  private async registerServiceInVm(
    vmName: string,
    username: string,
    password: string,
    serviceKey: string
  ): Promise<void> {
    const service = SERVICES[serviceKey];
    if (!service) throw new Error(`Unknown service: ${serviceKey}`);

    // 新目录结构：C:\ProgramData\UseIt\services\{dirName}\{exeName}
    const serviceDir = `${VM_INSTALL_PATH}\\${service.dirName}`;
    const exePath = `${serviceDir}\\${service.exeName}`;
    const taskName = service.name;

    // local_engine 整合了 computer_server 功能，需要访问桌面，必须以登录用户身份运行
    const needsInteractiveSession = true;
    
    // 将布尔值转换为 PowerShell 字符串，避免模板字符串插值问题
    const needsInteractivePsValue = '$true';

    // 调试日志
    console.log(`[ServiceDeployer] registerServiceInVm: ${serviceKey}, interactive=${needsInteractiveSession}`);

    // 使用 Task Scheduler 创建开机自启动任务
    // 隐藏控制台窗口，但保留日志文件功能
    const hideWindow = true;
    
    // 构建 action 命令 - 使用 cmd /c start /min 隐藏窗口
    const actionScript = `$action = New-ScheduledTaskAction -Execute 'cmd.exe' -Argument '/c start /min "" "${exePath}"' -WorkingDirectory '${serviceDir}'`;
    
    const result = await this.runInVm(vmName, username, password, `
      $ErrorActionPreference = 'Stop'
      $taskName = '${taskName}'
      
      # 删除已存在的任务
      Get-ScheduledTask -TaskName $taskName -EA SilentlyContinue | Unregister-ScheduledTask -Confirm:$false -EA SilentlyContinue
      
      # 创建任务
      ${actionScript}
      $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)
      
      # 使用交互式会话，以登录用户身份运行（需要访问桌面）
      $trigger = New-ScheduledTaskTrigger -AtLogon
      $principal = New-ScheduledTaskPrincipal -UserId '${username}' -LogonType Interactive -RunLevel Highest
      
      Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Force | Out-Null
      
      # 验证
      $t = Get-ScheduledTask -TaskName $taskName
      Write-Host "Registered: $taskName, User=$($t.Principal.UserId), Logon=$($t.Principal.LogonType)"
      'OK'
    `);
    
    console.log(`[ServiceDeployer] registerServiceInVm result: ${result.trim()}`);
  }

  /**
   * 在 VM 中启动服务
   */
  private async startServiceInVm(
    vmName: string,
    username: string,
    password: string,
    serviceKey: string
  ): Promise<void> {
    const service = SERVICES[serviceKey];
    if (!service) throw new Error(`Unknown service: ${serviceKey}`);

    await this.runInVm(vmName, username, password, `
      $taskName = '${service.name}'
      
      # 先停止已运行的进程
      $process = Get-Process -Name '${service.exeName.replace('.exe', '')}' -ErrorAction SilentlyContinue
      if ($process) {
        Stop-Process -Name '${service.exeName.replace('.exe', '')}' -Force -ErrorAction SilentlyContinue
        Start-Sleep -Seconds 1
      }
      
      # 启动任务
      Start-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
      
      # 等待启动
      Start-Sleep -Seconds 3
      
      # 检查是否启动成功
      $process = Get-Process -Name '${service.exeName.replace('.exe', '')}' -ErrorAction SilentlyContinue
      if ($process) {
        Write-Output 'RUNNING'
      } else {
        Write-Output 'FAILED'
      }
    `);
  }

  /**
   * 检查 VM 中的服务状态
   */
  async checkServiceStatus(
    vmName: string,
    username: string,
    password: string,
    serviceKey: string
  ): Promise<ServiceStatus> {
    const service = SERVICES[serviceKey];
    if (!service) {
      return { installed: false, running: false, error: 'Unknown service' };
    }

    // 新目录结构
    const serviceDir = `${VM_INSTALL_PATH}\\${service.dirName}`;
    const exePath = `${serviceDir}\\${service.exeName}`;

    try {
      const result = await this.runInVm(vmName, username, password, `
        $exePath = '${exePath}'
        $taskName = '${service.name}'
        
        $status = @{
          installed = $false
          running = $false
          version = ''
        }
        
        # 检查文件是否存在
        if (Test-Path $exePath) {
          $status.installed = $true
        }
        
        # 检查进程是否运行
        $process = Get-Process -Name '${service.exeName.replace('.exe', '')}' -ErrorAction SilentlyContinue
        if ($process) {
          $status.running = $true
        }
        
        # 检查版本文件
        $versionFile = '${VM_INSTALL_PATH}\\version.json'
        if (Test-Path $versionFile) {
          $versionJson = Get-Content $versionFile -Raw | ConvertFrom-Json
          $status.version = $versionJson.version
        }
        
        $status | ConvertTo-Json -Compress
      `);

      const status = JSON.parse(result.trim());
      return {
        installed: status.installed,
        running: status.running,
        version: status.version || undefined,
        port: service.port,
      };
    } catch (error: any) {
      return {
        installed: false,
        running: false,
        error: error.message,
      };
    }
  }

  /**
   * 部署服务到 VM
   */
  async deploy(
    vmName: string,
    username: string = 'useit',
    password: string = '12345678'
  ): Promise<DeployResult> {
    const totalSteps = 8;
    let currentStep = 0;

    try {
      // Step 1: 检查本地文件
      currentStep = 1;
      this.sendProgress({
        step: 'check_files',
        stepIndex: currentStep,
        totalSteps,
        percent: 5,
        message: 'Checking service files...',
        messageKey: 'deploy.checkingFiles',
      });

      if (!this.hasServiceFiles()) {
        throw new Error('Service files not found, please build services first');
      }

      // Step 2: 检查 VM 状态
      currentStep = 2;
      console.log(`[ServiceDeployer] ========== Step 2: Check VM Status ==========`);
      this.sendProgress({
        step: 'check_vm',
        stepIndex: currentStep,
        totalSteps,
        percent: 10,
        message: 'Checking VM status...',
        messageKey: 'deploy.checkingVm',
      });

      console.log(`[ServiceDeployer] Checking VM '${vmName}' status...`);
      const vmStatus = await this.runPowerShell(`(Get-VM -Name '${vmName}').State`, true);
      const vmStateTrimmed = vmStatus.trim().toLowerCase();
      console.log(`[ServiceDeployer] VM Status: '${vmStateTrimmed}'`);

      if (!vmStateTrimmed.includes('running')) {
        this.sendProgress({
          step: 'start_vm',
          stepIndex: currentStep,
          totalSteps,
          percent: 12,
          message: 'Starting VM...',
          messageKey: 'deploy.startingVm',
        });
        console.log(`[ServiceDeployer] VM is not running, starting...`);

        // Stop other running VMs that may hold a lock on shared/differencing disks
        try {
          const runningVms = await this.runPowerShell(
            `Get-VM | Where-Object { $_.State -eq 'Running' -and $_.Name -ne '${vmName}' } | Select-Object -ExpandProperty Name`
          );
          const vmNames = runningVms.trim().split(/\r?\n/).map(n => n.trim()).filter(Boolean);
          if (vmNames.length > 0) {
            console.log(`[ServiceDeployer] Stopping other running VMs to release disk locks: ${vmNames.join(', ')}`);
            this.sendProgress({
              step: 'stop_other_vms',
              stepIndex: currentStep,
              totalSteps,
              percent: 13,
              message: `Stopping ${vmNames.join(', ')} to release disk locks...`,
              messageKey: 'deploy.stoppingOtherVms',
            });
            for (const other of vmNames) {
              try {
                await this.runPowerShell(`Stop-VM -Name '${other}' -Force`);
                console.log(`[ServiceDeployer] Stopped VM '${other}'`);
              } catch (stopErr: any) {
                console.warn(`[ServiceDeployer] Failed to stop VM '${other}':`, stopErr.message);
              }
            }
            await new Promise(resolve => setTimeout(resolve, 3000));
          }
        } catch {
          // Non-critical — continue with Start-VM anyway
        }

        try {
          await this.runPowerShell(`Start-VM -Name '${vmName}'`);
        } catch (startErr: any) {
          const cleanMsg = this.extractPowerShellError(startErr.stderr || startErr.message || '');
          throw new Error(`Failed to start VM '${vmName}': ${cleanMsg}`);
        }

        // Wait for VM to reach Running state
        const vmStartDeadline = Date.now() + 60_000;
        while (Date.now() < vmStartDeadline) {
          const state = await this.runPowerShell(`(Get-VM -Name '${vmName}').State`);
          if (state.trim().toLowerCase().includes('running')) break;
          await new Promise(resolve => setTimeout(resolve, 3000));
        }

        // Wait for OS to boot and PowerShell Direct to be ready
        this.sendProgress({
          step: 'wait_vm_ready',
          stepIndex: currentStep,
          totalSteps,
          percent: 15,
          message: 'Waiting for VM to be ready...',
          messageKey: 'deploy.waitingVmReady',
        });
        console.log(`[ServiceDeployer] Waiting for PowerShell Direct to be available...`);

        const psReadyDeadline = Date.now() + 120_000;
        let psReady = false;
        while (Date.now() < psReadyDeadline) {
          try {
            const result = await this.runInVm(vmName, username, password, `'ready'`);
            if (result.includes('ready')) {
              psReady = true;
              break;
            }
          } catch {
            // VM OS not yet accepting connections
          }
          await new Promise(resolve => setTimeout(resolve, 5000));
        }

        if (!psReady) {
          throw new Error('VM started but OS did not become ready within 2 minutes');
        }
        console.log(`[ServiceDeployer] VM is now running and accepting connections`);
      }

      console.log(`[ServiceDeployer] VM is running`);

      // Step 3: 创建 VM 目录
      currentStep = 3;
      console.log(`[ServiceDeployer] ========== Step 3: Create VM Directories ==========`);
      this.sendProgress({
        step: 'create_dirs',
        stepIndex: currentStep,
        totalSteps,
        percent: 20,
        message: 'Creating install directories...',
        messageKey: 'deploy.creatingDirs',
      });

      console.log(`[ServiceDeployer] Creating directory: ${VM_INSTALL_PATH}`);
      await this.createVmDirectory(vmName, username, password, VM_INSTALL_PATH);
      console.log(`[ServiceDeployer] Creating directory: ${VM_LOG_PATH}`);
      await this.createVmDirectory(vmName, username, password, VM_LOG_PATH);
      console.log(`[ServiceDeployer] Creating directory: ${VM_CONFIG_PATH}`);
      await this.createVmDirectory(vmName, username, password, VM_CONFIG_PATH);
      console.log(`[ServiceDeployer] All directories created successfully`);

      // Step 4: 确保 Guest Service Interface 已启用
      currentStep = 4;
      console.log(`[ServiceDeployer] ========== Step 4: Enable Guest Service Interface ==========`);
      this.sendProgress({
        step: 'enable_guest_service',
        stepIndex: currentStep,
        totalSteps,
        percent: 25,
        message: 'Enabling Guest Service Interface...',
        messageKey: 'deploy.enablingGuestService',
      });

      try {
        console.log(`[ServiceDeployer] Calling ensureGuestServiceEnabled...`);
        await this.ensureGuestServiceEnabled(vmName);
        console.log(`[ServiceDeployer] ensureGuestServiceEnabled completed successfully`);
      } catch (error: any) {
        console.error(`[ServiceDeployer] ensureGuestServiceEnabled failed:`, error.message);
        // 即使 Guest Service Interface 启用失败，我们也可以尝试继续
        // 因为 Copy-VMFile 有自己的 -CreateFullPath 参数
        console.warn(`[ServiceDeployer] Continuing despite Guest Service Interface error...`);
      }

      // Step 5: 复制服务目录（使用 ZIP 压缩传输）
      currentStep = 5;
      console.log(`[ServiceDeployer] ========== Step 5: Copy Service Files (ZIP mode) ==========`);
      const serviceKeys = Object.keys(SERVICES);
      const totalServices = serviceKeys.length;
      let servicesCopied = 0;

      // 复制每个服务目录
      for (const serviceKey of serviceKeys) {
        const localServiceDir = this.getLocalServiceDir(serviceKey);
        if (localServiceDir) {
          const service = SERVICES[serviceKey];
          const vmServiceDir = `${VM_INSTALL_PATH}\\${service.dirName}`;
          
          console.log(`[ServiceDeployer] Copying ${localServiceDir} to ${vmServiceDir}`);
          
          await this.copyServiceDirToVm(
            vmName,
            username,
            password, 
            localServiceDir, 
            vmServiceDir,
            (step, totalStepsInCopy) => {
              // 计算总体进度 (30% - 60%)
              // 每个服务占用 30% / totalServices 的进度空间
              const serviceProgress = servicesCopied / totalServices;
              const stepProgress = step / totalStepsInCopy / totalServices;
              const percent = 30 + Math.round((serviceProgress + stepProgress) * 30);
              
              // 根据 step 显示不同的消息和 key
              let message = `Deploying ${service.displayName}...`;
              let messageKey = 'deploy.deploying';
              if (step <= 2) {
                message = `${service.displayName}: Preparing archive...`;
                messageKey = 'deploy.preparingArchive';
              } else if (step <= 4) {
                message = `${service.displayName}: Preparing transfer...`;
                messageKey = 'deploy.preparingTransfer';
              } else if (step <= 7) {
                message = `${service.displayName}: Transferring to VM...`;
                messageKey = 'deploy.transferring';
              } else {
                message = `${service.displayName}: Extracting and installing...`;
                messageKey = 'deploy.extracting';
              }
              
              this.sendProgress({
                step: 'copy_files',
                stepIndex: currentStep,
                totalSteps,
                percent,
                message,
                messageKey,
                messageParams: { serviceName: service.displayName },
              });
            }
          );
          
          servicesCopied++;
        }
      }

      // 复制 version.json
      const versionPath = path.join(this.resourcesPath, 'version.json');
      if (fs.existsSync(versionPath)) {
        await this.copyFileToVm(vmName, versionPath, `${VM_INSTALL_PATH}\\version.json`);
      }

      // Step 6: 配置防火墙（VM 内部 + 宿主机）
      currentStep = 6;
      this.sendProgress({
        step: 'configure_firewall',
        stepIndex: currentStep,
        totalSteps,
        percent: 65,
        message: 'Configuring firewall rules...',
        messageKey: 'deploy.configuringFirewall',
      });

      // 6.1 在 VM 内部配置防火墙规则（允许入站连接）
      console.log('[ServiceDeployer] Configuring VM firewall rules...');
      await this.runInVm(vmName, username, password, `
        $ErrorActionPreference = 'Continue'
        
        # 删除旧规则（如果存在）
        Remove-NetFirewallRule -DisplayName 'UseIt Local Engine' -ErrorAction SilentlyContinue
        Remove-NetFirewallRule -DisplayName 'UseIt Computer Server' -ErrorAction SilentlyContinue
        
        # Local Engine (端口 ${SERVICES.local_engine.port})
        New-NetFirewallRule -DisplayName 'UseIt Local Engine' -Direction Inbound -LocalPort ${SERVICES.local_engine.port} -Protocol TCP -Action Allow -Profile Any | Out-Null
        Write-Host "Created firewall rule for Local Engine on port ${SERVICES.local_engine.port}"
        
        'OK'
      `, false);

      // 6.2 在宿主机配置防火墙规则（允许出站到 VM）
      console.log('[ServiceDeployer] Configuring host firewall rules...');
      const hostFirewallScript = `
        $ErrorActionPreference = 'Continue'
        
        # 删除旧规则（如果存在）
        Remove-NetFirewallRule -DisplayName 'UseIt VM Local Engine Access' -ErrorAction SilentlyContinue
        Remove-NetFirewallRule -DisplayName 'UseIt VM Computer Server Access' -ErrorAction SilentlyContinue
        
        # 允许访问 VM 的 Local Engine 端口
        New-NetFirewallRule -DisplayName 'UseIt VM Local Engine Access' -Direction Outbound -RemotePort ${SERVICES.local_engine.port} -Protocol TCP -Action Allow -Profile Any | Out-Null

        Write-Host "Host firewall rules configured for port ${SERVICES.local_engine.port}"
        'OK'
      `;
      
      try {
        await this.runPowerShell(hostFirewallScript, false);
        console.log('[ServiceDeployer] Host firewall rules configured successfully');
      } catch (error: any) {
        // 宿主机防火墙配置失败不应阻止部署
        console.warn('[ServiceDeployer] Failed to configure host firewall rules:', error.message);
        console.warn('[ServiceDeployer] This may require running as administrator');
      }

      // Step 7: 注册服务
      currentStep = 7;
      this.sendProgress({
        step: 'register_services',
        stepIndex: currentStep,
        totalSteps,
        percent: 75,
        message: 'Registering services...',
        messageKey: 'deploy.registeringServices',
      });

      // 只注册 Local Engine（已整合 Computer Server 功能）
      await this.registerServiceInVm(vmName, username, password, 'local_engine');

      // Step 8: 启动服务
      currentStep = 8;
      this.sendProgress({
        step: 'start_services',
        stepIndex: currentStep,
        totalSteps,
        percent: 85,
        message: 'Starting services...',
        messageKey: 'deploy.startingServices',
      });

      // 启动 Local Engine
      await this.startServiceInVm(vmName, username, password, 'local_engine');

      // 完成
      this.sendProgress({
        step: 'complete',
        stepIndex: totalSteps,
        totalSteps,
        percent: 100,
        message: 'Service deployment complete!',
        messageKey: 'deploy.complete',
      });

      // 获取最终状态
      const services: Record<string, ServiceStatus> = {};
      for (const serviceKey of Object.keys(SERVICES)) {
        services[serviceKey] = await this.checkServiceStatus(vmName, username, password, serviceKey);
      }

      return { success: true, services };

    } catch (error: any) {
      this.sendProgress({
        step: 'error',
        stepIndex: currentStep,
        totalSteps,
        percent: 0,
        message: 'Deployment failed',
        messageKey: 'deploy.failed',
        error: error.message,
      });
      return { success: false, error: error.message };
    }
  }

  /**
   * 停止 VM 中的服务
   */
  async stopServices(
    vmName: string,
    username: string = 'useit',
    password: string = '12345678'
  ): Promise<DeployResult> {
    try {
      for (const serviceKey of Object.keys(SERVICES)) {
        const service = SERVICES[serviceKey];
        await this.runInVm(vmName, username, password, `
          Stop-Process -Name '${service.exeName.replace('.exe', '')}' -Force -ErrorAction SilentlyContinue
          'OK'
        `);
      }
      return { success: true };
    } catch (error: any) {
      return { success: false, error: error.message };
    }
  }

  /**
   * 重启 VM 中的服务
   */
  async restartServices(
    vmName: string,
    username: string = 'useit',
    password: string = '12345678'
  ): Promise<DeployResult> {
    await this.stopServices(vmName, username, password);
    await new Promise(resolve => setTimeout(resolve, 2000));
    
    try {
      await this.startServiceInVm(vmName, username, password, 'local_engine');
      return { success: true };
    } catch (error: any) {
      return { success: false, error: error.message };
    }
  }

  /**
   * 测试 VM 连接和文件复制功能
   * 用于调试部署问题
   */
  async testVmConnection(
    vmName: string,
    username: string = 'useit',
    password: string = '12345678'
  ): Promise<{ success: boolean; details: string[] }> {
    const details: string[] = [];
    
    try {
      // 1. 检查 VM 状态
      details.push('=== Step 1: Check VM Status ===');
      const vmStatus = await this.runPowerShell(`(Get-VM -Name '${vmName}').State`, true);
      details.push(`VM State: ${vmStatus.trim()}`);
      
      if (!vmStatus.trim().toLowerCase().includes('running')) {
        details.push('ERROR: VM is not running');
        return { success: false, details };
      }
      details.push('OK: VM is running');
      
      // 2. 检查 Guest Service Interface
      details.push('\n=== Step 2: Check Guest Service Interface ===');
      const guestServiceScript = `
        $vm = Get-VM -Name '${vmName}'
        $guestService = $vm | Get-VMIntegrationService | Where-Object { $_.Name -eq 'Guest Service Interface' }
        if ($guestService) {
          Write-Output "Guest Service Interface: Enabled=$($guestService.Enabled)"
        } else {
          Write-Output "Guest Service Interface: NOT FOUND"
        }
      `;
      const guestServiceResult = await this.runPowerShell(guestServiceScript, true);
      details.push(guestServiceResult.trim());
      
      // 3. 尝试在 VM 中执行命令
      details.push('\n=== Step 3: Test VM Command Execution ===');
      const testCmdResult = await this.runInVm(vmName, username, password, `
        Write-Output "Hello from VM"
        Write-Output "Current User: $env:USERNAME"
        Write-Output "Computer Name: $env:COMPUTERNAME"
        Write-Output "Current Directory: $(Get-Location)"
      `, true);
      details.push(testCmdResult.trim());
      details.push('OK: VM command execution works');
      
      // 4. 测试在 VM 中创建目录
      details.push('\n=== Step 4: Test Directory Creation in VM ===');
      const testDir = 'C:\\UseIt\\test_deploy';
      const createDirResult = await this.runInVm(vmName, username, password, `
        $testDir = '${testDir}'
        if (Test-Path $testDir) {
          Remove-Item $testDir -Recurse -Force
        }
        New-Item -Path $testDir -ItemType Directory -Force | Out-Null
        if (Test-Path $testDir) {
          Write-Output "OK: Directory created at $testDir"
        } else {
          Write-Output "FAILED: Could not create directory"
        }
      `, true);
      details.push(createDirResult.trim());
      
      // 5. 测试 Copy-VMFile
      details.push('\n=== Step 5: Test Copy-VMFile ===');
      
      // 创建一个临时测试文件
      const tempDir = path.join(app.getPath('temp'), 'useit_deploy_test');
      const testFilePath = path.join(tempDir, 'test.txt');
      
      if (!fs.existsSync(tempDir)) {
        fs.mkdirSync(tempDir, { recursive: true });
      }
      fs.writeFileSync(testFilePath, 'Test file content from host', 'utf8');
      details.push(`Created test file: ${testFilePath}`);
      
      const vmTestFilePath = `${testDir}\\test.txt`;
      try {
        await this.copyFileToVm(vmName, testFilePath, vmTestFilePath, true);
        details.push(`OK: File copied to VM: ${vmTestFilePath}`);
        
        // 验证文件
        const verifyResult = await this.runInVm(vmName, username, password, `
          $filePath = '${vmTestFilePath}'
          if (Test-Path $filePath) {
            $content = Get-Content $filePath -Raw
            Write-Output "OK: File exists, content: $content"
          } else {
            Write-Output "FAILED: File not found at $filePath"
          }
        `, true);
        details.push(verifyResult.trim());
      } catch (error: any) {
        details.push(`FAILED: Copy-VMFile error: ${error.message}`);
        
        // 尝试获取更多错误信息
        details.push('\n=== Detailed Error Info ===');
        const errorCheckScript = `
          $ErrorActionPreference = 'Continue'
          
          # 检查 Integration Services 状态
          $vm = Get-VM -Name '${vmName}'
          Write-Output "VM Integration Services:"
          $vm | Get-VMIntegrationService | ForEach-Object {
            Write-Output "  $($_.Name): Enabled=$($_.Enabled), OperationalStatus=$($_.OperationalStatus)"
          }
          
          # 检查权限
          Write-Output ""
          Write-Output "Current User: $([System.Security.Principal.WindowsIdentity]::GetCurrent().Name)"
          Write-Output "Is Admin: $([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltinRole]::Administrator)"
        `;
        const errorInfo = await this.runPowerShell(errorCheckScript, true);
        details.push(errorInfo.trim());
        
        return { success: false, details };
      }
      
      // 6. 清理测试目录
      details.push('\n=== Step 6: Cleanup ===');
      await this.runInVm(vmName, username, password, `
        Remove-Item -Path '${testDir}' -Recurse -Force -ErrorAction SilentlyContinue
        Write-Output "Cleaned up test directory"
      `, false);
      fs.rmSync(tempDir, { recursive: true, force: true });
      details.push('OK: Cleanup completed');
      
      details.push('\n=== All Tests Passed ===');
      return { success: true, details };
      
    } catch (error: any) {
      details.push(`\nERROR: ${error.message}`);
      return { success: false, details };
    }
  }
}

// 单例导出
export const serviceDeployer = new ServiceDeployer();


