/**
 * VM Installer Service
 * 负责从 Windows ISO 创建和配置 Hyper-V 虚拟机
 */

import { exec, spawn } from 'child_process';
import { promisify } from 'util';
import * as path from 'path';
import * as fs from 'fs';
import { BrowserWindow } from 'electron';

const execAsync = promisify(exec);

// VM 安装配置
export interface VmInstallConfig {
  vmName: string;
  isoPath: string;
  installDir: string;      // 安装目录
  vhdxPath?: string;       // 可选，默认自动生成
  memorySizeGB: number;    // 内存大小 (GB)
  cpuCount: number;        // CPU 核心数
  diskSizeGB: number;      // 磁盘大小 (GB)
  username: string;        // VM 用户名
  password: string;        // VM 密码
}

// 安装进度
export interface InstallProgress {
  step: string;
  stepIndex: number;
  totalSteps: number;
  percent: number;
  message: string;
  error?: string;
}

// 环境检查结果
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

// 默认配置
const DEFAULT_CONFIG: Partial<VmInstallConfig> = {
  vmName: 'UseIt-Dev-VM',
  installDir: 'C:\\VMs',
  memorySizeGB: 4,  // 降低默认内存，避免资源不足
  cpuCount: 4,
  diskSizeGB: 60,
  username: 'useit',
  password: '12345678',
};

/**
 * VM 安装器类
 */
export class VmInstaller {
  private win: BrowserWindow | null = null;
  private abortController: AbortController | null = null;
  private resourcesPath: string;

  constructor() {
    // 获取资源目录路径
    const { app } = require('electron');
    const isDev = process.env.NODE_ENV === 'development' || !app.isPackaged;
    
    if (isDev) {
      // 开发环境: 从 app 路径向上找到 frontend 目录
      // app.getAppPath() 通常是项目根目录或 frontend 目录
      const appPath = app.getAppPath();
      // 尝试多个可能的路径
      const possiblePaths = [
        path.join(appPath, 'resources'),                    // frontend/resources
        path.join(appPath, 'frontend', 'resources'),        // workspace/frontend/resources
        path.join(__dirname, '../../resources'),            // 从当前文件向上
        path.join(__dirname, '../../../resources'),         // 再向上一级
      ];
      
      this.resourcesPath = possiblePaths.find(p => {
        try {
          return fs.existsSync(path.join(p, 'bin'));
        } catch {
          return false;
        }
      }) || possiblePaths[0];
      
      console.log('[VmInstaller] Dev mode, appPath:', appPath);
      console.log('[VmInstaller] Resources path:', this.resourcesPath);
    } else {
      // 生产环境: process.resourcesPath 已指向 app/resources 目录
      // extraResources 中 "to": "bin" 会直接放在 resources/bin 下
      this.resourcesPath = process.resourcesPath;
    }
  }

  /**
   * 设置窗口引用，用于发送进度通知
   */
  setWindow(win: BrowserWindow) {
    this.win = win;
  }

  /**
   * 发送安装进度到渲染进程
   */
  private sendProgress(progress: InstallProgress) {
    if (this.win && !this.win.isDestroyed()) {
      this.win.webContents.send('vm-install-progress', progress);
    }
  }

  /**
   * 环境检查
   * @param installDir 安装目录，用于检测对应磁盘的可用空间（默认 C:\）
   */
  async checkEnvironment(installDir?: string): Promise<EnvironmentCheckResult> {
    const result: EnvironmentCheckResult = {
      hyperVEnabled: false,
      hyperVInstalled: false,
      isAdmin: false,
      windowsVersion: '',
      isProOrEnterprise: false,
      freeSpaceGB: 0,
      hasSufficientSpace: false,
      errors: [],
    };

    try {
      // 检查 Windows 版本
      // 使用 OperatingSystemSKU 判断版本，不受系统语言影响
      const { stdout: verOutput } = await execAsync(
        'powershell -Command "$os = Get-WmiObject Win32_OperatingSystem; $os.Caption + \'||\' + $os.OperatingSystemSKU"'
      );
      const [caption, skuStr] = verOutput.trim().split('||');
      result.windowsVersion = caption.trim();
      const sku = parseInt(skuStr?.trim() || '0', 10);
      const proEnterpriseSkus = new Set([
        4,    // Enterprise
        27,   // Enterprise N
        48,   // Professional
        49,   // Professional N
        84,   // Enterprise Evaluation
        112,  // Education
        113,  // Education N
        121,  // Pro Education
        122,  // Pro Education N
        125,  // Enterprise LTSC
        126,  // Enterprise LTSC N
        161,  // Pro for Workstations
        162,  // Pro for Workstations N
        175,  // Enterprise for Virtual Desktops
      ]);
      result.isProOrEnterprise = proEnterpriseSkus.has(sku);
      if (!result.isProOrEnterprise) {
        result.errors.push(`需要 Windows 10/11 Pro 或 Enterprise 版本 (当前: ${result.windowsVersion}, SKU: ${sku})`);
      }

      // 检查 Hyper-V 是否安装
      const { stdout: hvInstalled } = await execAsync(
        'powershell -Command "(Get-WindowsOptionalFeature -Online -FeatureName Microsoft-Hyper-V).State"'
      ).catch(() => ({ stdout: '' }));
      result.hyperVInstalled = hvInstalled.trim().toLowerCase() === 'enabled';

      // 检查 Hyper-V 是否可用 (服务是否运行)
      const { stdout: hvEnabled } = await execAsync(
        'powershell -Command "try { Get-VM -ErrorAction Stop | Out-Null; \'enabled\' } catch { \'disabled\' }"'
      ).catch(() => ({ stdout: 'disabled' }));
      result.hyperVEnabled = hvEnabled.trim().toLowerCase() === 'enabled';

      // 检查管理员权限
      const { stdout: adminCheck } = await execAsync(
        'powershell -Command "([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)"'
      ).catch(() => ({ stdout: 'False' }));
      result.isAdmin = adminCheck.trim().toLowerCase() === 'true';

      // 检查磁盘空间（根据安装目录所在盘符检测）
      const driveLetter = installDir?.match(/^([a-zA-Z]):/)?.[1]?.toUpperCase() || 'C';
      const { stdout: spaceOutput } = await execAsync(
        `powershell -Command "(Get-PSDrive ${driveLetter}).Free / 1GB"`
      );
      result.freeSpaceGB = Math.floor(parseFloat(spaceOutput.trim()) || 0);
      result.hasSufficientSpace = result.freeSpaceGB >= 30; // 至少需要 30GB
      if (!result.hasSufficientSpace) {
        result.errors.push(`磁盘空间不足 (${driveLetter}:)，需要至少 30GB，当前可用 ${result.freeSpaceGB}GB`);
      }

    } catch (error: any) {
      result.errors.push(`环境检查失败: ${error.message}`);
    }

    return result;
  }

  /**
   * 启用 Hyper-V (需要管理员权限，会触发 UAC)
   */
  async enableHyperV(): Promise<{ success: boolean; needsReboot: boolean; error?: string }> {
    try {
      const psScript = `
        $ErrorActionPreference = 'Stop'
        $feature = Get-WindowsOptionalFeature -Online -FeatureName Microsoft-Hyper-V
        if ($feature.State -eq 'Enabled') {
          Write-Output 'already_enabled'
        } else {
          Enable-WindowsOptionalFeature -Online -FeatureName Microsoft-Hyper-V -All -NoRestart
          Write-Output 'enabled_needs_reboot'
        }
      `;
      const encodedCommand = Buffer.from(psScript, 'utf16le').toString('base64');

      return new Promise((resolve) => {
        // 使用 UAC 提权执行
        const proc = spawn('powershell', [
          '-Command',
          `Start-Process powershell -Verb RunAs -Wait -ArgumentList '-EncodedCommand','${encodedCommand}'`
        ], { shell: true });

        proc.on('close', (code) => {
          if (code === 0) {
            resolve({ success: true, needsReboot: true });
          } else {
            resolve({ success: false, needsReboot: false, error: '用户取消或操作失败' });
          }
        });

        proc.on('error', (err) => {
          resolve({ success: false, needsReboot: false, error: err.message });
        });
      });
    } catch (error: any) {
      return { success: false, needsReboot: false, error: error.message };
    }
  }

  /**
   * 验证 ISO 文件
   */
  async validateIso(isoPath: string): Promise<{ valid: boolean; error?: string }> {
    try {
      // 检查文件是否存在
      if (!fs.existsSync(isoPath)) {
        return { valid: false, error: 'ISO 文件不存在' };
      }

      // 检查文件扩展名
      if (!isoPath.toLowerCase().endsWith('.iso')) {
        return { valid: false, error: '不是有效的 ISO 文件' };
      }

      // 检查文件大小 (Windows ISO 通常 > 4GB)
      const stats = fs.statSync(isoPath);
      const sizeGB = stats.size / (1024 * 1024 * 1024);
      if (sizeGB < 3) {
        return { valid: false, error: 'ISO 文件太小，可能不是完整的 Windows 镜像' };
      }

      // 尝试挂载 ISO 验证内容
      // 使用脚本文件方式执行，避免编码问题
      const os = require('os');
      const tempScriptPath = path.join(os.tmpdir(), 'validate_iso_' + Date.now() + '.ps1');
      const escapedIsoPath = isoPath.replace(/'/g, "''");
      
      console.log('[validateIso] ISO path:', isoPath);
      console.log('[validateIso] Temp script path:', tempScriptPath);
      
      // 使用字符串数组拼接，避免模板字符串中的反引号问题
      const scriptLines = [
        "$ErrorActionPreference = 'Stop'",
        "try {",
        "    $mountResult = Mount-DiskImage -ImagePath '" + escapedIsoPath + "' -PassThru",
        "    Start-Sleep -Milliseconds 1000",
        "    $drive = ($mountResult | Get-Volume).DriveLetter",
        "    if (-not $drive) {",
        "        $drive = (Get-DiskImage -ImagePath '" + escapedIsoPath + "' | Get-Volume).DriveLetter",
        "    }",
        "    if (-not $drive) {",
        "        Dismount-DiskImage -ImagePath '" + escapedIsoPath + "' -ErrorAction SilentlyContinue | Out-Null",
        "        Write-Output 'error: no_drive'",
        "        exit",
        "    }",
        "    $wimPath = $drive + ':\\sources\\install.wim'",
        "    $esdPath = $drive + ':\\sources\\install.esd'",
        "    $swmPath = $drive + ':\\sources\\install.swm'",
        "    $hasWim = Test-Path $wimPath",
        "    $hasEsd = Test-Path $esdPath",
        "    $hasSwm = Test-Path $swmPath",
        "    Dismount-DiskImage -ImagePath '" + escapedIsoPath + "' | Out-Null",
        "    if ($hasWim -or $hasEsd -or $hasSwm) { Write-Output 'valid' } else { Write-Output 'invalid' }",
        "} catch {",
        "    try { Dismount-DiskImage -ImagePath '" + escapedIsoPath + "' -ErrorAction SilentlyContinue | Out-Null } catch {}",
        "    Write-Output ('error: ' + $_.Exception.Message)",
        "}",
      ];
      const scriptContent = scriptLines.join('\r\n');
      fs.writeFileSync(tempScriptPath, scriptContent, 'utf8');
      
      console.log('[validateIso] Script written, executing...');
      
      try {
        const { stdout, stderr } = await execAsync(
          'powershell -ExecutionPolicy Bypass -File "' + tempScriptPath + '"',
          { timeout: 60000 }
        );
        
        console.log('[validateIso] stdout:', stdout);
        console.log('[validateIso] stderr:', stderr);
        
        const result = stdout.trim();
        
        // 清理临时脚本
        try { fs.unlinkSync(tempScriptPath); } catch {}

        console.log('[validateIso] Parsed result:', result);

        if (result.startsWith('error:')) {
          return { valid: false, error: '验证 ISO 失败: ' + result.substring(7) };
        }

        if (result !== 'valid') {
          console.log('[validateIso] Result is not "valid", returning invalid');
          return { valid: false, error: 'ISO 不包含有效的 Windows 安装文件 (需要 install.wim/esd/swm)' };
        }
      } catch (execError: any) {
        console.log('[validateIso] Execution error:', execError);
        // 清理临时脚本
        try { fs.unlinkSync(tempScriptPath); } catch {}
        throw execError;
      }

      return { valid: true };
    } catch (error: any) {
      return { valid: false, error: `验证 ISO 失败: ${error.message}` };
    }
  }

  /**
   * 创建 unattend.xml 应答文件
   * 注意：因为我们使用 Expand-WindowsImage 部署系统，不需要 windowsPE 阶段
   * 只需要 specialize 和 oobeSystem 阶段
   */
  private createUnattendXml(config: VmInstallConfig): string {
    const computerName = config.vmName.replace(/[^a-zA-Z0-9-]/g, '').substring(0, 15);
    
    return `<?xml version="1.0" encoding="utf-8"?>
<unattend xmlns="urn:schemas-microsoft-com:unattend">
  <settings pass="specialize">
    <component name="Microsoft-Windows-Deployment" processorArchitecture="amd64" publicKeyToken="31bf3856ad364e35" language="neutral" versionScope="nonSxS" xmlns:wcm="http://schemas.microsoft.com/WMIConfig/2002/State" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
      <RunSynchronous>
        <RunSynchronousCommand wcm:action="add">
          <Order>1</Order>
          <Path>net user ${config.username} ${config.password} /add</Path>
        </RunSynchronousCommand>
        <RunSynchronousCommand wcm:action="add">
          <Order>2</Order>
          <Path>net localgroup Administrators ${config.username} /add</Path>
        </RunSynchronousCommand>
      </RunSynchronous>
    </component>
    <component name="Microsoft-Windows-International-Core" processorArchitecture="amd64" publicKeyToken="31bf3856ad364e35" language="neutral" versionScope="nonSxS" xmlns:wcm="http://schemas.microsoft.com/WMIConfig/2002/State" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
      <InputLocale>0409:00000409</InputLocale>
      <SystemLocale>en-US</SystemLocale>
      <UILanguage>en-US</UILanguage>
      <UserLocale>en-US</UserLocale>
    </component>
    <component name="Microsoft-Windows-Shell-Setup" processorArchitecture="amd64" publicKeyToken="31bf3856ad364e35" language="neutral" versionScope="nonSxS" xmlns:wcm="http://schemas.microsoft.com/WMIConfig/2002/State" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
      <ComputerName>${computerName}</ComputerName>
      <TimeZone>China Standard Time</TimeZone>
    </component>
    <component name="Microsoft-Windows-TerminalServices-LocalSessionManager" processorArchitecture="amd64" publicKeyToken="31bf3856ad364e35" language="neutral" versionScope="nonSxS" xmlns:wcm="http://schemas.microsoft.com/WMIConfig/2002/State" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
      <fDenyTSConnections>false</fDenyTSConnections>
    </component>
  </settings>
  <settings pass="oobeSystem">
    <component name="Microsoft-Windows-International-Core" processorArchitecture="amd64" publicKeyToken="31bf3856ad364e35" language="neutral" versionScope="nonSxS" xmlns:wcm="http://schemas.microsoft.com/WMIConfig/2002/State" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
      <InputLocale>0409:00000409</InputLocale>
      <SystemLocale>en-US</SystemLocale>
      <UILanguage>en-US</UILanguage>
      <UserLocale>en-US</UserLocale>
    </component>
    <component name="Microsoft-Windows-Shell-Setup" processorArchitecture="amd64" publicKeyToken="31bf3856ad364e35" language="neutral" versionScope="nonSxS" xmlns:wcm="http://schemas.microsoft.com/WMIConfig/2002/State" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
      <OOBE>
        <HideEULAPage>true</HideEULAPage>
        <HideLocalAccountScreen>true</HideLocalAccountScreen>
        <HideOnlineAccountScreens>true</HideOnlineAccountScreens>
        <HideWirelessSetupInOOBE>true</HideWirelessSetupInOOBE>
        <SkipMachineOOBE>true</SkipMachineOOBE>
        <SkipUserOOBE>true</SkipUserOOBE>
        <NetworkLocation>Work</NetworkLocation>
        <ProtectYourPC>3</ProtectYourPC>
      </OOBE>
      <UserAccounts>
        <LocalAccounts>
          <LocalAccount wcm:action="add">
            <Name>${config.username}</Name>
            <DisplayName>${config.username}</DisplayName>
            <Group>Administrators</Group>
            <Password>
              <Value>${config.password}</Value>
              <PlainText>true</PlainText>
            </Password>
          </LocalAccount>
        </LocalAccounts>
      </UserAccounts>
      <AutoLogon>
        <Enabled>true</Enabled>
        <Username>${config.username}</Username>
        <Password>
          <Value>${config.password}</Value>
          <PlainText>true</PlainText>
        </Password>
        <LogonCount>5</LogonCount>
      </AutoLogon>
      <FirstLogonCommands>
        <SynchronousCommand wcm:order="1">
          <CommandLine>cmd /c powershell -ExecutionPolicy Bypass -File C:\\UseIt\\setup\\install-software.ps1</CommandLine>
          <Description>Install UseIt Software</Description>
          <RequiresUserInput>false</RequiresUserInput>
        </SynchronousCommand>
      </FirstLogonCommands>
    </component>
  </settings>
</unattend>`;
  }

  /**
   * 创建软件安装脚本
   */
  private createInstallSoftwareScript(): string {
    // 使用字符串数组避免模板字符串中的反引号冲突
    const lines = [
      "# install-software.ps1 - 在 VM 首次启动时自动执行",
      "$ErrorActionPreference = 'Continue'",
      "$SetupDir = 'C:\\UseIt\\setup'",
      "$LogFile = 'C:\\UseIt\\setup\\install.log'",
      "",
      "function Write-Log {",
      "    param([string]$Message)",
      "    $timestamp = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'",
      "    \"$timestamp - $Message\" | Out-File -Append -FilePath $LogFile",
      "    Write-Host $Message",
      "}",
      "",
      "Write-Log '========== UseIt VM Setup Started =========='",
      "",
      "# 1. 配置网络",
      "Write-Log 'Configuring network...'",
      "Set-NetConnectionProfile -NetworkCategory Private -ErrorAction SilentlyContinue",
      "",
      "# 2. 安装 TightVNC Server",
      "Write-Log 'Installing TightVNC Server...'",
      "$vncInstaller = Join-Path $SetupDir 'tightvnc.msi'",
      "if (Test-Path $vncInstaller) {",
      "    $msiArgs = '/i \"' + $vncInstaller + '\" /quiet /norestart ADDLOCAL=Server SET_USEVNCAUTHENTICATION=1 VALUE_OF_USEVNCAUTHENTICATION=1 SET_PASSWORD=1 VALUE_OF_PASSWORD=12345678 SET_USECONTROLAUTHENTICATION=1 VALUE_OF_USECONTROLAUTHENTICATION=1 SET_CONTROLPASSWORD=1 VALUE_OF_CONTROLPASSWORD=12345678'",
      "    Start-Process 'msiexec.exe' -ArgumentList $msiArgs -Wait -NoNewWindow",
      "    Write-Log 'TightVNC installed.'",
      "    Start-Sleep -Seconds 3",
      "    $service = Get-Service -Name 'tvnserver' -ErrorAction SilentlyContinue",
      "    if ($service) {",
      "        Set-Service -Name 'tvnserver' -StartupType Automatic",
      "        if ($service.Status -ne 'Running') {",
      "            Start-Service -Name 'tvnserver' -ErrorAction SilentlyContinue",
      "        }",
      "        Write-Log 'TightVNC service started.'",
      "    } else {",
      "        Write-Log 'WARNING: TightVNC service not found'",
      "    }",
      "} else {",
      "    Write-Log 'WARNING: TightVNC installer not found'",
      "}",
      "",
      "# 3. 配置防火墙规则",
      "Write-Log 'Configuring firewall rules...'",
      "New-NetFirewallRule -DisplayName 'TightVNC Server' -Direction Inbound -LocalPort 5900 -Protocol TCP -Action Allow -ErrorAction SilentlyContinue",
      "New-NetFirewallRule -DisplayName 'UseIt Service HTTP' -Direction Inbound -LocalPort 8080 -Protocol TCP -Action Allow -ErrorAction SilentlyContinue",
      "New-NetFirewallRule -DisplayName 'UseIt Service HTTPS' -Direction Inbound -LocalPort 8443 -Protocol TCP -Action Allow -ErrorAction SilentlyContinue",
      "",
      "# 4. 启用远程桌面",
      "Write-Log 'Enabling Remote Desktop...'",
      "Set-ItemProperty -Path 'HKLM:\\System\\CurrentControlSet\\Control\\Terminal Server' -Name 'fDenyTSConnections' -Value 0 -ErrorAction SilentlyContinue",
      "Enable-NetFirewallRule -DisplayGroup 'Remote Desktop' -ErrorAction SilentlyContinue",
      "",
      "# 5. 禁用 Windows Update 自动重启",
      "Write-Log 'Configuring Windows Update...'",
      "$wuPath = 'HKLM:\\SOFTWARE\\Policies\\Microsoft\\Windows\\WindowsUpdate\\AU'",
      "if (-not (Test-Path $wuPath)) { New-Item -Path $wuPath -Force | Out-Null }",
      "Set-ItemProperty -Path $wuPath -Name 'NoAutoRebootWithLoggedOnUsers' -Value 1 -Type DWord",
      "",
      "# 6. 创建完成标记",
      "Write-Log 'Creating setup completion marker...'",
      "'Setup completed' | Out-File 'C:\\UseIt\\setup-complete.txt'",
      "",
      "Write-Log '========== UseIt VM Setup Completed =========='",
      "Start-Sleep -Seconds 5",
    ];
    return lines.join('\r\n');
  }

  /**
   * 主安装流程
   */
  async install(config: Partial<VmInstallConfig>): Promise<{ success: boolean; error?: string }> {
    const fullConfig: VmInstallConfig = { ...DEFAULT_CONFIG, ...config } as VmInstallConfig;
    
    if (!fullConfig.isoPath) {
      return { success: false, error: '未指定 ISO 文件路径' };
    }

    if (!fullConfig.installDir) {
      return { success: false, error: '未指定安装目录' };
    }

    const vmDir = path.join(fullConfig.installDir, fullConfig.vmName);
    fullConfig.vhdxPath = fullConfig.vhdxPath || path.join(vmDir, `${fullConfig.vmName}.vhdx`);

    const totalSteps = 10;
    let currentStep = 0;

    try {
      // Step 1: 环境检查
      currentStep = 1;
      this.sendProgress({
        step: 'environment_check',
        stepIndex: currentStep,
        totalSteps,
        percent: 5,
        message: '正在检查系统环境...',
      });

      const envCheck = await this.checkEnvironment(fullConfig.installDir);
      if (!envCheck.hyperVEnabled) {
        return { success: false, error: 'Hyper-V 未启用，请先启用 Hyper-V 并重启系统' };
      }
      if (!envCheck.hasSufficientSpace) {
        const driveLetter = fullConfig.installDir?.match(/^([a-zA-Z]):/)?.[1]?.toUpperCase() || 'C';
        return { success: false, error: `磁盘空间不足 (${driveLetter}: 需要 30GB，当前 ${envCheck.freeSpaceGB}GB)` };
      }

      // Step 2: 验证 ISO
      currentStep = 2;
      this.sendProgress({
        step: 'validate_iso',
        stepIndex: currentStep,
        totalSteps,
        percent: 10,
        message: '正在验证 ISO 文件...',
      });

      const isoValid = await this.validateIso(fullConfig.isoPath);
      if (!isoValid.valid) {
        return { success: false, error: isoValid.error };
      }

      // Step 3: 创建 VM 目录和文件
      currentStep = 3;
      this.sendProgress({
        step: 'prepare_files',
        stepIndex: currentStep,
        totalSteps,
        percent: 15,
        message: '正在准备安装文件...',
      });

      // 创建目录
      fs.mkdirSync(vmDir, { recursive: true });
      fs.mkdirSync(path.join(vmDir, 'setup'), { recursive: true });

      // 写入 unattend.xml
      const unattendContent = this.createUnattendXml(fullConfig);
      fs.writeFileSync(path.join(vmDir, 'unattend.xml'), unattendContent, 'utf8');

      // 写入软件安装脚本
      const installScript = this.createInstallSoftwareScript();
      fs.writeFileSync(path.join(vmDir, 'setup', 'install-software.ps1'), installScript, 'utf8');

      // 创建 SetupComplete.cmd (在 Windows 安装完成后、用户登录前自动执行)
      const setupCompleteCmd = `@echo off
powershell -ExecutionPolicy Bypass -File C:\\UseIt\\setup\\install-software.ps1
`;
      fs.writeFileSync(path.join(vmDir, 'setup', 'SetupComplete.cmd'), setupCompleteCmd, 'utf8');

      // 复制 TightVNC 安装包 (如果存在)
      const vncSourcePath = path.join(this.resourcesPath, 'bin', 'tightvnc-2.8.85-gpl-setup-64bit.msi');
      console.log('[startInstall] VNC source path:', vncSourcePath);
      console.log('[startInstall] VNC source exists:', fs.existsSync(vncSourcePath));
      if (fs.existsSync(vncSourcePath)) {
        const vncDestPath = path.join(vmDir, 'setup', 'tightvnc.msi');
        fs.copyFileSync(vncSourcePath, vncDestPath);
        console.log('[startInstall] VNC copied to:', vncDestPath);
        console.log('[startInstall] VNC dest exists:', fs.existsSync(vncDestPath));
      } else {
        console.error('[startInstall] ERROR: TightVNC installer not found at:', vncSourcePath);
        return {
          success: false,
          error: `Virtual machine connector package is missing: ${vncSourcePath}. Please restore the installer and retry.`,
        };
      }

      // Step 4: 创建 VHDX 虚拟磁盘
      currentStep = 4;
      this.sendProgress({
        step: 'create_vhdx',
        stepIndex: currentStep,
        totalSteps,
        percent: 20,
        message: '正在创建虚拟磁盘...',
      });

      const createVhdxScript = `
        $ErrorActionPreference = 'Stop'
        $vhdxPath = '${fullConfig.vhdxPath!.replace(/\\/g, '\\\\')}'
        if (Test-Path $vhdxPath) {
          Remove-Item $vhdxPath -Force
        }
        New-VHD -Path $vhdxPath -SizeBytes ${fullConfig.diskSizeGB}GB -Dynamic
      `;
      await this.runPowerShell(createVhdxScript);

      // Step 5: 创建 Hyper-V VM
      currentStep = 5;
      this.sendProgress({
        step: 'create_vm',
        stepIndex: currentStep,
        totalSteps,
        percent: 30,
        message: '正在创建虚拟机...',
      });

      const createVmScript = `
        $ErrorActionPreference = 'Stop'
        $vmName = '${fullConfig.vmName}'
        $vhdxPath = '${fullConfig.vhdxPath!.replace(/\\/g, '\\\\')}'
        $isoPath = '${fullConfig.isoPath.replace(/\\/g, '\\\\')}'
        
        # 删除同名 VM (如果存在)
        $existingVm = Get-VM -Name $vmName -ErrorAction SilentlyContinue
        if ($existingVm) {
          Stop-VM -Name $vmName -Force -ErrorAction SilentlyContinue
          Remove-VM -Name $vmName -Force
        }
        
        # 创建 Generation 2 VM
        New-VM -Name $vmName -MemoryStartupBytes ${fullConfig.memorySizeGB}GB -Generation 2 -NoVHD
        
        # 配置 CPU 和动态内存
        Set-VM -Name $vmName -ProcessorCount ${fullConfig.cpuCount} -CheckpointType Standard
        # 启用动态内存: 最小 2GB, 启动 4GB, 最大 8GB
        Set-VMMemory -VMName $vmName -DynamicMemoryEnabled $true -MinimumBytes 2GB -StartupBytes ${fullConfig.memorySizeGB}GB -MaximumBytes 8GB
        
        # 添加硬盘
        Add-VMHardDiskDrive -VMName $vmName -Path $vhdxPath
        
        # 添加 DVD 驱动器并挂载 ISO
        Add-VMDvdDrive -VMName $vmName -Path $isoPath
        
        # 设置从 DVD 启动
        $dvd = Get-VMDvdDrive -VMName $vmName
        Set-VMFirmware -VMName $vmName -FirstBootDevice $dvd
        
        # 禁用安全启动 (某些 ISO 可能不兼容)
        Set-VMFirmware -VMName $vmName -EnableSecureBoot Off
        
        # 连接到网络交换机 (优先使用 External Switch，以便 Host 和 VM 互通)
        $switch = Get-VMSwitch | Where-Object { $_.SwitchType -eq 'External' } | Select-Object -First 1
        if (-not $switch) {
          # 如果没有 External Switch，则尝试 Default Switch
          $switch = Get-VMSwitch | Where-Object { $_.Name -eq 'Default Switch' } | Select-Object -First 1
        }
        if (-not $switch) {
          # 最后尝试任意可用的交换机
          $switch = Get-VMSwitch | Select-Object -First 1
        }
        if ($switch) {
          Write-Host "Connecting to switch: $($switch.Name) (Type: $($switch.SwitchType))"
          Connect-VMNetworkAdapter -VMName $vmName -SwitchName $switch.Name
        } else {
          Write-Host "WARNING: No virtual switch found, VM will have no network"
        }
        
        # 设置视频分辨率支持 (设置最大分辨率为 1920x1080，用户仍可在 Windows 中调整)
        Set-VMVideo -VMName $vmName -HorizontalResolution 1920 -VerticalResolution 1080 -ResolutionType Maximum
        
        # 启用增强会话模式支持
        Set-VM -VMName $vmName -EnhancedSessionTransportType HvSocket
        
        Write-Output "VM created successfully"
      `;
      await this.runPowerShell(createVmScript);

      // Step 6: 注入 unattend.xml 和安装文件到 VHDX
      currentStep = 6;
      this.sendProgress({
        step: 'inject_files',
        stepIndex: currentStep,
        totalSteps,
        percent: 40,
        message: '正在准备无人值守安装配置...',
      });

      // 这一步比较复杂，需要：
      // 1. 挂载 ISO 获取 Windows 映像
      // 2. 挂载 VHDX
      // 3. 应用 Windows 映像到 VHDX
      // 4. 复制 unattend.xml 和安装文件
      const escapedVmDir = vmDir.replace(/\\/g, '\\\\');
      const escapedVhdxPath = fullConfig.vhdxPath!.replace(/\\/g, '\\\\');
      const escapedIsoPath = fullConfig.isoPath.replace(/\\/g, '\\\\');
      
      const injectScriptLines = [
        "$ErrorActionPreference = 'Stop'",
        "$vmDir = '" + escapedVmDir + "'",
        "$vhdxPath = '" + escapedVhdxPath + "'",
        "$isoPath = '" + escapedIsoPath + "'",
        "",
        "$winDrive = $null",
        "$sysDrive = $null",
        "",
        "try {",
        "    Write-Host 'Mounting ISO...'",
        "    $isoMount = Mount-DiskImage -ImagePath $isoPath -PassThru",
        "    Start-Sleep -Milliseconds 500",
        "    $isoDrive = ($isoMount | Get-Volume).DriveLetter",
        "",
        "    $wimPath = $isoDrive + ':\\sources\\install.wim'",
        "    $esdPath = $isoDrive + ':\\sources\\install.esd'",
        "    $imagePath = if (Test-Path $wimPath) { $wimPath } else { $esdPath }",
        "",
        "    Write-Host ('Using image: ' + $imagePath)",
        "",
        "    Write-Host 'Mounting VHDX...'",
        "    $vhdMount = Mount-VHD -Path $vhdxPath -Passthru",
        "    $disk = $vhdMount | Get-Disk",
        "",
        "    Write-Host 'Initializing disk...'",
        "    Initialize-Disk -Number $disk.Number -PartitionStyle GPT -ErrorAction SilentlyContinue",
        "",
        "    Write-Host 'Creating partitions...'",
        "    $systemPartition = New-Partition -DiskNumber $disk.Number -Size 100MB -GptType '{c12a7328-f81f-11d2-ba4b-00a0c93ec93b}' -AssignDriveLetter",
        "    $sysDrive = $systemPartition.DriveLetter",
        "    Format-Volume -DriveLetter $sysDrive -FileSystem FAT32 -NewFileSystemLabel 'System' -Confirm:$false | Out-Null",
        "",
        "    $msrPartition = New-Partition -DiskNumber $disk.Number -Size 16MB -GptType '{e3c9e316-0b5c-4db8-817d-f92df00215ae}'",
        "",
        "    $windowsPartition = New-Partition -DiskNumber $disk.Number -UseMaximumSize -GptType '{ebd0a0a2-b9e5-4433-87c0-68b6b72699c7}' -AssignDriveLetter",
        "    $winDrive = $windowsPartition.DriveLetter",
        "    Format-Volume -DriveLetter $winDrive -FileSystem NTFS -NewFileSystemLabel 'Windows' -Confirm:$false | Out-Null",
        "",
        "    Write-Host ('System drive: ' + $sysDrive + ', Windows drive: ' + $winDrive)",
        "",
        "    Write-Host 'Applying Windows image (this may take 10-20 minutes)...'",
        "    $winPath = $winDrive + ':\\\\'",
        "    Expand-WindowsImage -ImagePath $imagePath -Index 1 -ApplyPath $winPath -LogLevel WarningsInfo",
        "",
        "    Write-Host 'Configuring boot...'",
        "    $winRoot = $winDrive + ':\\Windows'",
        "    $sysRoot = $sysDrive + ':'",
        "    bcdboot $winRoot /s $sysRoot /f UEFI",
        "",
        "    Write-Host 'Copying unattend.xml...'",
        "    $panther = $winDrive + ':\\Windows\\Panther'",
        "    New-Item -Path $panther -ItemType Directory -Force | Out-Null",
        "    Copy-Item -Path ($vmDir + '\\unattend.xml') -Destination ($panther + '\\unattend.xml') -Force",
        "",
        "    Write-Host 'Copying setup files...'",
        "    $useItDir = $winDrive + ':\\UseIt\\setup'",
        "    New-Item -Path $useItDir -ItemType Directory -Force | Out-Null",
        "    Copy-Item -Path ($vmDir + '\\setup\\*') -Destination $useItDir -Recurse -Force",
        "",
        "    Write-Host 'Installing SetupComplete.cmd for auto-run...'",
        "    $scriptsDir = $winDrive + ':\\Windows\\Setup\\Scripts'",
        "    New-Item -Path $scriptsDir -ItemType Directory -Force | Out-Null",
        "    Copy-Item -Path ($vmDir + '\\setup\\SetupComplete.cmd') -Destination ($scriptsDir + '\\SetupComplete.cmd') -Force",
        "",
        "    Write-Host 'Files injected successfully'",
        "}",
        "finally {",
        "    Write-Host 'Cleaning up...'",
        "    try { Dismount-VHD -Path $vhdxPath -ErrorAction SilentlyContinue } catch {}",
        "    try { Dismount-DiskImage -ImagePath $isoPath -ErrorAction SilentlyContinue | Out-Null } catch {}",
        "}",
        "",
        "Write-Output 'Done'",
      ];
      const injectScript = injectScriptLines.join('\r\n');

      try {
        await this.runPowerShellElevated(injectScript);
      } catch (error: any) {
        // 额外清理尝试
        await execAsync(`powershell -Command "Dismount-DiskImage -ImagePath '${fullConfig.isoPath}' -ErrorAction SilentlyContinue | Out-Null"`).catch(() => {});
        await execAsync(`powershell -Command "Dismount-VHD -Path '${fullConfig.vhdxPath}' -ErrorAction SilentlyContinue"`).catch(() => {});
        throw error;
      }

      // Step 7: 启动 VM
      currentStep = 7;
      this.sendProgress({
        step: 'start_vm',
        stepIndex: currentStep,
        totalSteps,
        percent: 85,
        message: '正在启动虚拟机...',
      });

      // 移除 DVD 驱动器 (不再需要)
      await this.runPowerShell(`
        $dvd = Get-VMDvdDrive -VMName '${fullConfig.vmName}'
        if ($dvd) {
          Remove-VMDvdDrive -VMName '${fullConfig.vmName}' -ControllerNumber $dvd.ControllerNumber -ControllerLocation $dvd.ControllerLocation
        }
        
        # 设置从硬盘启动
        $hdd = Get-VMHardDiskDrive -VMName '${fullConfig.vmName}' | Select-Object -First 1
        Set-VMFirmware -VMName '${fullConfig.vmName}' -FirstBootDevice $hdd
        
        # 启动 VM
        Start-VM -Name '${fullConfig.vmName}'
      `);

      // Step 8: 等待 Windows 启动
      currentStep = 8;
      this.sendProgress({
        step: 'wait_boot',
        stepIndex: currentStep,
        totalSteps,
        percent: 80,
        message: '正在等待 Windows 启动...',
      });

      // 等待 VM 可以接受 PowerShell Direct 连接
      await this.waitForVmReady(fullConfig);

      // Step 9: 等待 Windows 完成首次配置
      currentStep = 9;
      this.sendProgress({
        step: 'wait_oobe',
        stepIndex: currentStep,
        totalSteps,
        percent: 85,
        message: '正在等待 Windows 完成首次配置 (约2-5分钟)...',
      });

      // 等待桌面加载完成
      await this.waitForDesktopReady(fullConfig);

      // Step 10: 安装软件
      currentStep = 10;
      this.sendProgress({
        step: 'install_software',
        stepIndex: currentStep,
        totalSteps,
        percent: 92,
        message: '正在安装 VNC 服务...',
      });

      // 安装 VNC
      await this.installVncViaPSDirect(fullConfig);

      // 完成
      this.sendProgress({
        step: 'complete',
        stepIndex: totalSteps,
        totalSteps,
        percent: 100,
        message: 'VM 安装完成！VNC 服务已启动，可以连接了。',
      });

      return { success: true };

    } catch (error: any) {
      this.sendProgress({
        step: 'error',
        stepIndex: currentStep,
        totalSteps,
        percent: 0,
        message: '安装失败',
        error: error.message,
      });
      return { success: false, error: error.message };
    }
  }

  /**
   * 运行 PowerShell 脚本
   */
  private async runPowerShell(script: string): Promise<string> {
    const encodedCommand = Buffer.from(script, 'utf16le').toString('base64');
    const { stdout, stderr } = await execAsync('powershell -EncodedCommand ' + encodedCommand);
    // PowerShell 进度信息会输出到 stderr，格式为 CLIXML
    // 只有当 stderr 包含真正的错误（非 CLIXML 格式）且没有 stdout 时才认为是错误
    if (stderr && !stdout && !stderr.includes('CLIXML') && !stderr.includes('Progress')) {
      throw new Error(stderr);
    }
    return stdout;
  }

  /**
   * 等待 VM 可以接受 PowerShell Direct 连接
   */
  private async waitForVmReady(config: VmInstallConfig & { vmName: string }): Promise<void> {
    const { vmName, username, password } = config;
    const maxWaitTime = 10 * 60 * 1000; // 10 minutes
    const startTime = Date.now();

    console.log('[waitForVmReady] Waiting for VM to accept connections...');
    
    while (Date.now() - startTime < maxWaitTime) {
      try {
        const checkScript = [
          "$secPassword = ConvertTo-SecureString '" + password + "' -AsPlainText -Force",
          "$cred = New-Object System.Management.Automation.PSCredential ('" + username + "', $secPassword)",
          "$result = Invoke-Command -VMName '" + vmName + "' -Credential $cred -ScriptBlock { return 'ready' } -ErrorAction Stop",
          "Write-Output $result",
        ].join('\n');
        const result = await this.runPowerShell(checkScript);
        if (result.includes('ready')) {
          console.log('[waitForVmReady] VM is ready!');
          return;
        }
      } catch (e) {
        const elapsed = Math.round((Date.now() - startTime) / 1000);
        console.log('[waitForVmReady] VM not ready yet, elapsed:', elapsed, 's');
        await new Promise(resolve => setTimeout(resolve, 15000));
      }
    }
    
    console.log('[waitForVmReady] Timeout waiting for VM');
  }

  /**
   * 等待 Windows 桌面完全加载
   */
  private async waitForDesktopReady(config: VmInstallConfig & { vmName: string }): Promise<void> {
    const { vmName, username, password } = config;
    const maxWaitTime = 5 * 60 * 1000; // 5 minutes
    const startTime = Date.now();

    console.log('[waitForDesktopReady] Waiting for desktop to be ready...');
    
    while (Date.now() - startTime < maxWaitTime) {
      try {
        const checkScript = [
          "$secPassword = ConvertTo-SecureString '" + password + "' -AsPlainText -Force",
          "$cred = New-Object System.Management.Automation.PSCredential ('" + username + "', $secPassword)",
          "Invoke-Command -VMName '" + vmName + "' -Credential $cred -ScriptBlock {",
          "    $explorer = Get-Process -Name 'explorer' -ErrorAction SilentlyContinue",
          "    if ($explorer) { return 'desktop_ready' } else { return 'waiting' }",
          "} -ErrorAction Stop",
        ].join('\n');
        const result = await this.runPowerShell(checkScript);
        if (result.includes('desktop_ready')) {
          console.log('[waitForDesktopReady] Desktop is ready!');
          // 额外等待让系统稳定
          await new Promise(resolve => setTimeout(resolve, 3000));
          return;
        }
      } catch (e) {
        console.log('[waitForDesktopReady] Error checking desktop, retrying...');
      }
      await new Promise(resolve => setTimeout(resolve, 10000));
    }
    
    console.log('[waitForDesktopReady] Timeout waiting for desktop');
  }

  /**
   * 使用 PowerShell Direct 安装 VNC
   */
  private async installVncViaPSDirect(config: VmInstallConfig & { vmName: string }): Promise<void> {
    const { vmName, username, password } = config;

    console.log('[installVncViaPSDirect] Installing VNC via PowerShell Direct...');
    
    const installScriptLines = [
      "$secPassword = ConvertTo-SecureString '" + password + "' -AsPlainText -Force",
      "$cred = New-Object System.Management.Automation.PSCredential ('" + username + "', $secPassword)",
      "Invoke-Command -VMName '" + vmName + "' -Credential $cred -ScriptBlock {",
      "    $ErrorActionPreference = 'Continue'",
      "    $SetupDir = 'C:\\UseIt\\setup'",
      "    ",
      "    # Check if TightVNC is already installed",
      "    $vncService = Get-Service -Name 'tvnserver' -ErrorAction SilentlyContinue",
      "    if ($vncService) {",
      "        Write-Host 'TightVNC already installed'",
      "        return",
      "    }",
      "    ",
      "    # Install TightVNC",
      "    $vncInstaller = Join-Path $SetupDir 'tightvnc.msi'",
      "    if (Test-Path $vncInstaller) {",
      "        Write-Host 'Installing TightVNC...'",
      "        $msiArgs = '/i \"' + $vncInstaller + '\" /quiet /norestart ADDLOCAL=Server SET_USEVNCAUTHENTICATION=1 VALUE_OF_USEVNCAUTHENTICATION=1 SET_PASSWORD=1 VALUE_OF_PASSWORD=12345678 SET_USECONTROLAUTHENTICATION=1 VALUE_OF_USECONTROLAUTHENTICATION=1 SET_CONTROLPASSWORD=1 VALUE_OF_CONTROLPASSWORD=12345678'",
      "        Start-Process 'msiexec.exe' -ArgumentList $msiArgs -Wait -NoNewWindow",
      "        ",
      "        Start-Sleep -Seconds 3",
      "        ",
      "        # Start service",
      "        $service = Get-Service -Name 'tvnserver' -ErrorAction SilentlyContinue",
      "        if ($service) {",
      "            Set-Service -Name 'tvnserver' -StartupType Automatic",
      "            if ($service.Status -ne 'Running') {",
      "                Start-Service -Name 'tvnserver' -ErrorAction SilentlyContinue",
      "            }",
      "            Write-Host 'TightVNC installed and started'",
      "        }",
      "    } else {",
      "        Write-Host 'TightVNC installer not found'",
      "    }",
      "    ",
      "    # Configure firewall",
      "    New-NetFirewallRule -DisplayName 'TightVNC Server' -Direction Inbound -LocalPort 5900 -Protocol TCP -Action Allow -ErrorAction SilentlyContinue",
      "    ",
      "    # Enable RDP",
      "    Set-ItemProperty -Path 'HKLM:\\System\\CurrentControlSet\\Control\\Terminal Server' -Name 'fDenyTSConnections' -Value 0 -ErrorAction SilentlyContinue",
      "    Enable-NetFirewallRule -DisplayGroup 'Remote Desktop' -ErrorAction SilentlyContinue",
      "    ",
      "    Write-Host 'VNC and RDP configuration completed'",
      "}",
    ];
    
    try {
      await this.runPowerShell(installScriptLines.join('\n'));
      console.log('[installVncViaPSDirect] VNC installation completed');
    } catch (e: any) {
      console.log('[installVncViaPSDirect] Installation failed:', e.message);
    }
  }

  /**
   * 以管理员权限运行 PowerShell 脚本
   * 使用临时文件捕获详细错误信息
   */
  private async runPowerShellElevated(script: string): Promise<void> {
    const os = require('os');
    const tempDir = os.tmpdir();
    const timestamp = Date.now();
    const scriptPath = path.join(tempDir, `vm_install_${timestamp}.ps1`);
    const logPath = path.join(tempDir, `vm_install_${timestamp}.log`);
    const errorPath = path.join(tempDir, `vm_install_${timestamp}.err`);
    
    // 包装脚本以捕获输出
    const wrappedScript = `
$ErrorActionPreference = 'Stop'
try {
    ${script}
    "SUCCESS" | Out-File -FilePath '${logPath.replace(/\\/g, '\\\\')}' -Encoding UTF8
} catch {
    $_.Exception.Message | Out-File -FilePath '${errorPath.replace(/\\/g, '\\\\')}' -Encoding UTF8
    $_.ScriptStackTrace | Out-File -FilePath '${errorPath.replace(/\\/g, '\\\\')}' -Append -Encoding UTF8
    exit 1
}
`;
    
    // 写入脚本文件
    fs.writeFileSync(scriptPath, wrappedScript, 'utf8');
    console.log('[runPowerShellElevated] Script path:', scriptPath);
    
    return new Promise((resolve, reject) => {
      const proc = spawn('powershell', [
        '-Command',
        `Start-Process powershell -Verb RunAs -Wait -ArgumentList '-ExecutionPolicy','Bypass','-File','${scriptPath}'`
      ], { shell: true });

      proc.on('close', (code) => {
        // 读取日志
        let logContent = '';
        let errorContent = '';
        
        try {
          if (fs.existsSync(logPath)) {
            logContent = fs.readFileSync(logPath, 'utf8').trim();
          }
        } catch {}
        
        try {
          if (fs.existsSync(errorPath)) {
            errorContent = fs.readFileSync(errorPath, 'utf8').trim();
          }
        } catch {}
        
        // 清理临时文件
        try { fs.unlinkSync(scriptPath); } catch {}
        try { fs.unlinkSync(logPath); } catch {}
        try { fs.unlinkSync(errorPath); } catch {}
        
        console.log('[runPowerShellElevated] Exit code:', code);
        console.log('[runPowerShellElevated] Log:', logContent);
        console.log('[runPowerShellElevated] Error:', errorContent);
        
        if (logContent === 'SUCCESS') {
          resolve();
        } else if (errorContent) {
          reject(new Error(errorContent));
        } else if (code !== 0) {
          reject(new Error(`PowerShell 脚本执行失败 (exit code: ${code})`));
        } else {
          resolve();
        }
      });

      proc.on('error', (err) => {
        // 清理临时文件
        try { fs.unlinkSync(scriptPath); } catch {}
        try { fs.unlinkSync(logPath); } catch {}
        try { fs.unlinkSync(errorPath); } catch {}
        reject(err);
      });
    });
  }

  /**
   * 取消安装
   */
  cancel() {
    this.abortController?.abort();
  }
}

// 单例导出
export const vmInstaller = new VmInstaller();

