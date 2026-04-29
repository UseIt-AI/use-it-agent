/**
 * VM Share Manager
 * 将宿主机的 projects 根目录通过 SMB 共享挂载到 Hyper-V VM 中。
 *
 * 设计思路：挂载整个 projects 父目录（而非单个 project），
 * VM 中通过 Z:\ProjectName\... 直接访问任意 project，
 * 切换 project 时零延迟（只是换个子目录路径）。
 *
 * 认证方案：
 *   在宿主机创建专用本地账户 UseItShare（UAC 提权，只需一次），
 *   VM 通过该账户的凭据访问 SMB 共享，无需交互式登录。
 */

import { exec, spawn } from 'child_process';
import { promisify } from 'util';
import * as path from 'path';
import * as fs from 'fs';
import * as os from 'os';

const execAsync = promisify(exec);

const SMB_SHARE_NAME = 'UseItProjects';
const VM_DRIVE_LETTER = 'Z';
const FIREWALL_RULE_NAME = 'UseIt SMB Share';
const SMB_USERNAME = 'UseItShare';
const SMB_PASSWORD = 'UseIt@Smb2024!';

export interface VmShareOptions {
  vmName: string;
  username: string;
  password: string;
  /** 宿主机 projects 根目录，如 Documents/UseitAgent/useitid_xxx/projects */
  projectsRootPath: string;
}

export interface ShareStatus {
  healthy: boolean;
  shareExists: boolean;
  driveMapped: boolean;
  hostIp?: string;
  error?: string;
}

export class VmShareManager {

  private cachedHostIp: string | null = null;
  private lastSharedPath: string | null = null;

  // ──────────────────────────────────────────────
  // Public API
  // ──────────────────────────────────────────────

  /**
   * 确保 projects 根目录已共享并在 VM 中映射为 Z: 盘。
   * 幂等：如果已经正确挂载，秒回。
   * 首次创建时会弹 UAC 提权框（创建账户+共享+防火墙）。
   */
  async ensureShared(opts: VmShareOptions): Promise<{ success: boolean; driveLetter: string; error?: string }> {
    const driveLetter = VM_DRIVE_LETTER;

    try {
      const shareChanged = await this.ensureHostSetup(opts.projectsRootPath);
      if (shareChanged) {
        this.cachedHostIp = null;
      }

      const hostIp = await this.resolveHostIp(opts.vmName);
      const uncPath = `\\\\${hostIp}\\${SMB_SHARE_NAME}`;
      await this.ensureDriveMapped(opts, uncPath);

      this.lastSharedPath = opts.projectsRootPath;
      console.log(`[VmShareManager] Share ready: ${opts.projectsRootPath} -> ${driveLetter}: (${uncPath})`);
      return { success: true, driveLetter };
    } catch (error: any) {
      console.error('[VmShareManager] ensureShared failed:', error.message);
      return { success: false, driveLetter, error: error.message };
    }
  }

  /**
   * 快速健康检查：Z: 盘在 VM 中是否可访问。
   */
  async checkHealth(opts: Pick<VmShareOptions, 'vmName' | 'username' | 'password'>): Promise<ShareStatus> {
    const shareExists = await this.smbShareExists();
    if (!shareExists) {
      return { healthy: false, shareExists: false, driveMapped: false, error: 'SMB share not found on host' };
    }

    try {
      const mapped = await this.isDriveMappedInVm(opts.vmName, opts.username, opts.password);
      return {
        healthy: mapped,
        shareExists: true,
        driveMapped: mapped,
        hostIp: this.cachedHostIp || undefined,
        error: mapped ? undefined : 'Drive not mapped in VM',
      };
    } catch (error: any) {
      return { healthy: false, shareExists: true, driveMapped: false, error: error.message };
    }
  }

  getVmProjectPath(projectName: string): string {
    return `${VM_DRIVE_LETTER}:\\${projectName}`;
  }

  hostPathToVmPath(hostPath: string, projectsRootPath: string): string | null {
    const normalizedHost = path.normalize(hostPath);
    const normalizedRoot = path.normalize(projectsRootPath);
    if (!normalizedHost.toLowerCase().startsWith(normalizedRoot.toLowerCase())) {
      return null;
    }
    const relative = normalizedHost.substring(normalizedRoot.length).replace(/^[/\\]+/, '');
    return `${VM_DRIVE_LETTER}:\\${relative}`;
  }

  async teardown(opts: Pick<VmShareOptions, 'vmName' | 'username' | 'password'>): Promise<void> {
    try {
      await this.unmapDriveInVm(opts.vmName, opts.username, opts.password);
    } catch { /* VM may be off */ }
    try {
      await this.runPowerShellElevated([
        `Remove-SmbShare -Name '${SMB_SHARE_NAME}' -Force -ErrorAction SilentlyContinue`,
        "Write-Output 'DONE'",
      ].join('\r\n'));
    } catch { /* already gone */ }
    this.cachedHostIp = null;
    this.lastSharedPath = null;
  }

  get currentSharedPath(): string | null {
    return this.lastSharedPath;
  }

  // ──────────────────────────────────────────────
  // Host Setup (需要管理员权限，通过 UAC)
  // ──────────────────────────────────────────────

  private async ensureHostSetup(hostPath: string): Promise<boolean> {
    const normalizedPath = hostPath.replace(/\//g, '\\');

    // 快速检查（不需要管理员）
    const checkResult = await this.runPowerShell([
      `$s = Get-SmbShare -Name '${SMB_SHARE_NAME}' -ErrorAction SilentlyContinue`,
      `$u = Get-LocalUser -Name '${SMB_USERNAME}' -ErrorAction SilentlyContinue`,
      `$fw = Get-NetFirewallRule -DisplayName '${FIREWALL_RULE_NAME}' -ErrorAction SilentlyContinue`,
      "if ($s -and $u -and $fw) {",
      `    if ($s.Path -eq '${normalizedPath}') { Write-Output 'ALL_OK' }`,
      "    else { Write-Output 'SHARE_WRONG_PATH' }",
      "} else { Write-Output 'NEEDS_SETUP' }",
    ].join('\n'));

    const status = checkResult.trim();
    console.log(`[VmShareManager] Host check: ${status}`);

    if (status === 'ALL_OK') {
      return false;
    }

    // 需要设置 —— UAC 提权
    console.log('[VmShareManager] Elevating to set up SMB share...');
    const elevatedScript = [
      "$ErrorActionPreference = 'Stop'",
      "",
      "# 1. Create dedicated SMB user (if missing)",
      `$user = Get-LocalUser -Name '${SMB_USERNAME}' -ErrorAction SilentlyContinue`,
      "if (-not $user) {",
      `    $secPwd = ConvertTo-SecureString '${SMB_PASSWORD}' -AsPlainText -Force`,
      `    New-LocalUser -Name '${SMB_USERNAME}' -Password $secPwd -Description 'UseIt VM file sharing' -PasswordNeverExpires -UserMayNotChangePassword | Out-Null`,
      "}",
      "",
      "# 2. Create / update SMB share",
      `$existing = Get-SmbShare -Name '${SMB_SHARE_NAME}' -ErrorAction SilentlyContinue`,
      "if ($existing) {",
      `    if ($existing.Path -ne '${normalizedPath}') {`,
      `        Remove-SmbShare -Name '${SMB_SHARE_NAME}' -Force`,
      `        New-SmbShare -Name '${SMB_SHARE_NAME}' -Path '${normalizedPath}' -FullAccess '${SMB_USERNAME}' | Out-Null`,
      "    }",
      "} else {",
      `    New-SmbShare -Name '${SMB_SHARE_NAME}' -Path '${normalizedPath}' -FullAccess '${SMB_USERNAME}' | Out-Null`,
      "}",
      "",
      "# 3. Grant NTFS permissions",
      `$acl = Get-Acl '${normalizedPath}'`,
      `$rule = New-Object System.Security.AccessControl.FileSystemAccessRule('${SMB_USERNAME}','FullControl','ContainerInherit,ObjectInherit','None','Allow')`,
      "$acl.AddAccessRule($rule)",
      `Set-Acl '${normalizedPath}' $acl`,
      "",
      "# 4. Firewall rule",
      `$fw = Get-NetFirewallRule -DisplayName '${FIREWALL_RULE_NAME}' -ErrorAction SilentlyContinue`,
      "if (-not $fw) {",
      `    New-NetFirewallRule -DisplayName '${FIREWALL_RULE_NAME}' -Direction Inbound -LocalPort 445 -Protocol TCP -Action Allow -Profile Private,Domain,Public | Out-Null`,
      "}",
      "",
      "Write-Output 'DONE'",
    ].join('\r\n');

    await this.runPowerShellElevated(elevatedScript);
    console.log('[VmShareManager] Host setup completed');
    return true;
  }

  private async smbShareExists(): Promise<boolean> {
    const result = await this.runPowerShell(
      `if (Get-SmbShare -Name '${SMB_SHARE_NAME}' -ErrorAction SilentlyContinue) { 'YES' } else { 'NO' }`
    );
    return result.trim() === 'YES';
  }

  // ──────────────────────────────────────────────
  // Host IP Resolution
  // ──────────────────────────────────────────────

  private async resolveHostIp(vmName: string): Promise<string> {
    if (this.cachedHostIp) return this.cachedHostIp;

    const script = [
      "$ErrorActionPreference = 'Stop'",
      `$adapter = Get-VMNetworkAdapter -VMName '${vmName}' -ErrorAction Stop`,
      "$switchName = $adapter.SwitchName",
      "",
      "if ($switchName -eq 'Default Switch') {",
      "    $ip = Get-NetIPAddress -InterfaceAlias 'vEthernet (Default Switch)' -AddressFamily IPv4 -ErrorAction SilentlyContinue | Select-Object -First 1",
      "    if ($ip) { Write-Output $ip.IPAddress; exit }",
      "}",
      "",
      "$ifs = Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue | Where-Object {",
      "    $_.InterfaceAlias -like \"*$switchName*\" -or $_.InterfaceAlias -like '*Hyper-V*'",
      "} | Where-Object { $_.IPAddress -ne '127.0.0.1' } | Select-Object -First 1",
      "if ($ifs) { Write-Output $ifs.IPAddress; exit }",
      "",
      "$fallback = Get-NetIPAddress -AddressFamily IPv4 | Where-Object {",
      "    $_.IPAddress -ne '127.0.0.1' -and $_.PrefixOrigin -ne 'WellKnown'",
      "} | Select-Object -First 1",
      "if ($fallback) { Write-Output $fallback.IPAddress }",
    ].join('\n');

    const ip = (await this.runPowerShell(script)).trim().split('\n').pop()?.trim();
    if (!ip) throw new Error('Unable to determine host IP visible to the VM');

    this.cachedHostIp = ip;
    return ip;
  }

  // ──────────────────────────────────────────────
  // Drive Mapping (VM 侧，用 UseItShare 账户凭据)
  // ──────────────────────────────────────────────

  /**
   * Maps the drive inside the VM's interactive desktop session via a scheduled task.
   * Direct `net use` from Invoke-Command runs in a non-interactive logon session
   * whose drive mappings are invisible to Explorer — the scheduled task with
   * LogonType Interactive solves this.
   */
  private async ensureDriveMapped(opts: VmShareOptions, uncPath: string): Promise<void> {
    const taskName = 'UseItMapDrive';
    const resultFile = '%TEMP%\\useit_map_result.txt';
    const resultFilePsh = '$env:TEMP\\useit_map_result.txt';

    const vmScript = [
      "$ErrorActionPreference = 'Continue'",
      "",
      "$batLines = @(",
      "    '@echo off'",
      `    'if exist ${VM_DRIVE_LETTER}:\\nul ('`,
      `    '    echo ALREADY_MAPPED > ${resultFile}'`,
      "    ') else ('",
      `    '    net use ${VM_DRIVE_LETTER}: /delete /yes 2>nul'`,
      `    '    net use ${VM_DRIVE_LETTER}: "${uncPath}" "${SMB_PASSWORD}" /user:"${SMB_USERNAME}" /persistent:yes'`,
      "    '    if %errorlevel% equ 0 ('",
      `    '        echo MAPPED > ${resultFile}'`,
      "    '    ) else ('",
      `    '        echo MAP_FAILED > ${resultFile}'`,
      "    '    )'",
      "    ')'",
      ")",
      "$batPath = Join-Path $env:TEMP 'useit_map_drive.cmd'",
      "$batLines | Set-Content -Path $batPath -Encoding ASCII",
      "",
      "$action = New-ScheduledTaskAction -Execute $batPath",
      `$principal = New-ScheduledTaskPrincipal -UserId '${opts.username}' -LogonType Interactive -RunLevel Limited`,
      "$task = New-ScheduledTask -Action $action -Principal $principal",
      `Register-ScheduledTask -TaskName '${taskName}' -InputObject $task -Force | Out-Null`,
      `Start-ScheduledTask -TaskName '${taskName}'`,
      "",
      "# Poll for result file (up to 5s)",
      "$waited = 0",
      "while ($waited -lt 5000) {",
      `    if (Test-Path '${resultFilePsh}') { break }`,
      "    Start-Sleep -Milliseconds 500",
      "    $waited += 500",
      "}",
      "",
      `$status = if (Test-Path '${resultFilePsh}') { (Get-Content '${resultFilePsh}' -ErrorAction SilentlyContinue).Trim() } else { 'TIMEOUT' }`,
      `Remove-Item '${resultFilePsh}' -Force -ErrorAction SilentlyContinue`,
      "Remove-Item $batPath -Force -ErrorAction SilentlyContinue",
      `Unregister-ScheduledTask -TaskName '${taskName}' -Confirm:$false -ErrorAction SilentlyContinue`,
      "Write-Output $status",
    ].join('\n');

    const result = (await this.runInVm(opts.vmName, opts.username, opts.password, vmScript)).trim();
    console.log(`[VmShareManager] ensureDriveMapped: ${result}`);

    if (result === 'MAP_FAILED' || result === 'TIMEOUT') {
      throw new Error(`Drive mapping failed: ${result}`);
    }
  }

  private async isDriveMappedInVm(vmName: string, username: string, password: string): Promise<boolean> {
    const vmScript = `if (Get-ItemProperty -Path 'HKCU:\\Network\\${VM_DRIVE_LETTER}' -ErrorAction SilentlyContinue) { 'YES' } else { 'NO' }`;
    const result = (await this.runInVm(vmName, username, password, vmScript)).trim();
    return result === 'YES';
  }

  private async unmapDriveInVm(vmName: string, username: string, password: string): Promise<void> {
    const taskName = 'UseItUnmapDrive';
    const vmScript = [
      "$ErrorActionPreference = 'Continue'",
      `$action = New-ScheduledTaskAction -Execute 'cmd.exe' -Argument '/c net use ${VM_DRIVE_LETTER}: /delete /yes'`,
      `$principal = New-ScheduledTaskPrincipal -UserId '${username}' -LogonType Interactive -RunLevel Limited`,
      "$task = New-ScheduledTask -Action $action -Principal $principal",
      `Register-ScheduledTask -TaskName '${taskName}' -InputObject $task -Force | Out-Null`,
      `Start-ScheduledTask -TaskName '${taskName}'`,
      "Start-Sleep -Seconds 2",
      `Unregister-ScheduledTask -TaskName '${taskName}' -Confirm:$false -ErrorAction SilentlyContinue`,
      `Remove-ItemProperty -Path 'HKCU:\\Network\\${VM_DRIVE_LETTER}' -Name '*' -Force -ErrorAction SilentlyContinue`,
      "Write-Output 'OK'",
    ].join('\n');
    await this.runInVm(vmName, username, password, vmScript);
  }

  // ──────────────────────────────────────────────
  // PowerShell Helpers
  // ──────────────────────────────────────────────

  private async runPowerShell(script: string): Promise<string> {
    const encoded = Buffer.from(script, 'utf16le').toString('base64');
    const { stdout, stderr } = await execAsync(`powershell -EncodedCommand ${encoded}`, {
      maxBuffer: 10 * 1024 * 1024,
    });
    if (stderr && !stdout && !stderr.includes('CLIXML') && !stderr.includes('Progress')) {
      throw new Error(stderr);
    }
    return stdout;
  }

  private async runPowerShellElevated(script: string): Promise<void> {
    const tempDir = os.tmpdir();
    const timestamp = Date.now();
    const scriptPath = path.join(tempDir, `useit_share_${timestamp}.ps1`);
    const logPath = path.join(tempDir, `useit_share_${timestamp}.log`);
    const errorPath = path.join(tempDir, `useit_share_${timestamp}.err`);

    const wrappedScript = [
      "$ErrorActionPreference = 'Stop'",
      "try {",
      `    ${script}`,
      `    'SUCCESS' | Out-File -FilePath '${logPath.replace(/\\/g, '\\\\')}' -Encoding UTF8`,
      "} catch {",
      `    $_.Exception.Message | Out-File -FilePath '${errorPath.replace(/\\/g, '\\\\')}' -Encoding UTF8`,
      "    exit 1",
      "}",
    ].join('\r\n');

    fs.writeFileSync(scriptPath, wrappedScript, 'utf8');

    return new Promise((resolve, reject) => {
      const proc = spawn('powershell', [
        '-Command',
        `Start-Process powershell -Verb RunAs -Wait -ArgumentList '-ExecutionPolicy','Bypass','-File','${scriptPath}'`
      ], { shell: true });

      proc.on('close', () => {
        let logContent = '';
        let errorContent = '';
        try { if (fs.existsSync(logPath)) logContent = fs.readFileSync(logPath, 'utf8').trim(); } catch {}
        try { if (fs.existsSync(errorPath)) errorContent = fs.readFileSync(errorPath, 'utf8').trim(); } catch {}
        try { fs.unlinkSync(scriptPath); } catch {}
        try { fs.unlinkSync(logPath); } catch {}
        try { fs.unlinkSync(errorPath); } catch {}

        if (logContent.includes('SUCCESS')) {
          resolve();
        } else if (errorContent) {
          reject(new Error(`Elevated script failed: ${errorContent}`));
        } else {
          reject(new Error('Elevated script failed: user cancelled UAC or unknown error'));
        }
      });

      proc.on('error', (err) => {
        try { fs.unlinkSync(scriptPath); } catch {}
        try { fs.unlinkSync(logPath); } catch {}
        try { fs.unlinkSync(errorPath); } catch {}
        reject(err);
      });
    });
  }

  private async runInVm(vmName: string, username: string, password: string, scriptBlock: string): Promise<string> {
    const wrapper = [
      "$ErrorActionPreference = 'Stop'",
      `$sec = ConvertTo-SecureString '${password}' -AsPlainText -Force`,
      `$cred = New-Object System.Management.Automation.PSCredential('${username}', $sec)`,
      `$result = Invoke-Command -VMName '${vmName}' -Credential $cred -ScriptBlock {`,
      `    ${scriptBlock}`,
      "} -ErrorAction Stop",
      "Write-Output $result",
    ].join('\n');
    return this.runPowerShell(wrapper);
  }
}

export const vmShareManager = new VmShareManager();
