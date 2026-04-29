import { app } from 'electron';
import { spawn, execFile, execSync } from 'child_process';
import * as fs from 'fs';
import * as http from 'http';
import * as path from 'path';

// eslint-disable-next-line @typescript-eslint/no-var-requires
const sudoPrompt = require('sudo-prompt') as {
  exec: (
    command: string,
    options: { name: string; env?: Record<string, string> },
    callback: (error?: Error, stdout?: string, stderr?: string) => void
  ) => void;
};

type StartResult =
  | { ok: true; started: true; pid: number; exePath: string }
  | { ok: true; started: false; alreadyRunning: true; exePath?: string }
  | { ok: false; error: string; exePath?: string };

let childPid: number | null = null;
let stopping = false;

const DEFAULT_PORT = 8324;

function getPort(): number {
  // 端口约定：8324。允许通过环境变量覆盖，但若你不需要覆盖请不要设置该环境变量。
  const raw = process.env.LOCAL_ENGINE_PORT || '';
  const n = Number(raw);
  return Number.isFinite(n) && n > 0 ? n : DEFAULT_PORT;
}

function httpGet(url: string, timeoutMs: number): Promise<{ statusCode?: number; body: string }> {
  return new Promise((resolve, reject) => {
    const req = http.get(url, (res) => {
      const chunks: Buffer[] = [];
      res.on('data', (d) => chunks.push(Buffer.isBuffer(d) ? d : Buffer.from(String(d))));
      res.on('end', () => resolve({ statusCode: res.statusCode, body: Buffer.concat(chunks).toString('utf8') }));
    });
    req.on('error', reject);
    req.setTimeout(timeoutMs, () => {
      req.destroy(new Error(`timeout after ${timeoutMs}ms`));
    });
  });
}

async function isHealthy(port: number): Promise<boolean> {
  try {
    const res = await httpGet(`http://127.0.0.1:${port}/health`, 800);
    return (res.statusCode || 0) >= 200 && (res.statusCode || 0) < 300;
  } catch {
    return false;
  }
}

function getLogDir(): string {
  const dir = path.join(app.getPath('userData'), 'logs');
  try {
    fs.mkdirSync(dir, { recursive: true });
  } catch {
    // ignore
  }
  return dir;
}

function createLogStream(filename: string): fs.WriteStream | null {
  try {
    const logPath = path.join(getLogDir(), filename);
    return fs.createWriteStream(logPath, { flags: 'a' });
  } catch {
    return null;
  }
}

function pickExistingFile(pathsToTry: string[]): string | null {
  for (const p of pathsToTry) {
    try {
      if (fs.existsSync(p)) return p;
    } catch {
      // ignore
    }
  }
  return null;
}

export function resolveLocalEngineExePath(): string | null {
  // 约定：打包后会把 frontend/resources/services -> <install>/resources/services
  // exe 位于子目录 local_engine/ 下，与其依赖 DLL/pyd 在同一目录
  const exeName = 'local_engine.exe';
  const serviceDir = 'local_engine';
  const isDev = process.env.NODE_ENV === 'development' || !app.isPackaged;

  const candidates: string[] = [];

  if (isDev) {
    const appPath = app.getAppPath();
    candidates.push(
      // 新结构：services/local_engine/local_engine.exe
      path.join(appPath, 'resources', 'services', serviceDir, exeName),
      path.join(appPath, 'frontend', 'resources', 'services', serviceDir, exeName),
      path.join(__dirname, '../../resources/services', serviceDir, exeName),
      path.join(__dirname, '../../../resources/services', serviceDir, exeName),
      // 旧结构兼容：services/local_engine.exe
      path.join(appPath, 'resources', 'services', exeName),
      path.join(appPath, 'frontend', 'resources', 'services', exeName),
      path.join(__dirname, '../../resources/services', exeName),
      path.join(__dirname, '../../../resources/services', exeName)
    );
  } else {
    // 生产环境
    candidates.push(
      // 新结构：services/local_engine/local_engine.exe
      path.join(process.resourcesPath, 'services', serviceDir, exeName),
      path.join(process.resourcesPath, 'resources', 'services', serviceDir, exeName),
      // 旧结构兼容
      path.join(process.resourcesPath, 'services', exeName),
      path.join(process.resourcesPath, 'resources', 'services', exeName),
      path.join(process.resourcesPath, 'bin', exeName),
      path.join(process.resourcesPath, 'resources', 'bin', exeName)
    );
  }

  return pickExistingFile(candidates);
}

function resolveResourcesBinDir(): string | null {
  const isDev = process.env.NODE_ENV === 'development' || !app.isPackaged;
  const candidates: string[] = [];

  if (isDev) {
    const appPath = app.getAppPath();
    candidates.push(
      path.join(appPath, 'resources', 'bin'),
      path.join(appPath, 'frontend', 'resources', 'bin'),
      path.join(__dirname, '../../resources/bin'),
      path.join(__dirname, '../../../resources/bin')
    );
  } else {
    candidates.push(
      path.join(process.resourcesPath, 'bin'),
      path.join(process.resourcesPath, 'resources', 'bin')
    );
  }

  for (const p of candidates) {
    try {
      if (fs.existsSync(p)) return p;
    } catch {
      // ignore
    }
  }
  return null;
}

function prependToPath(env: NodeJS.ProcessEnv, dir: string): NodeJS.ProcessEnv {
  // Windows env is case-insensitive, but Node may preserve casing.
  // Set both Path and PATH to be safe.
  const current = env.Path || env.PATH || '';
  const sep = path.delimiter;
  const next = `${dir}${sep}${current}`;
  return { ...env, Path: next, PATH: next };
}

/** Windows：当前进程是否已是管理员令牌（与 spawn 子进程权限一致）。 */
function isWindowsAdministrator(): boolean {
  if (process.platform !== 'win32') return false;
  try {
    const out = execSync(
      'powershell -NoProfile -Command "([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)"',
      { encoding: 'utf8', timeout: 8000, windowsHide: true }
    );
    return out.trim().toLowerCase() === 'true';
  } catch {
    return false;
  }
}

function sudoExec(command: string, options: { name: string; env?: Record<string, string> }): Promise<void> {
  return new Promise((resolve, reject) => {
    sudoPrompt.exec(command, options, (error?: Error) => {
      if (error) reject(error);
      else resolve();
    });
  });
}

async function killProcessTree(pid: number): Promise<void> {
  if (!pid || pid <= 0) return;
  if (process.platform === 'win32') {
    await new Promise<void>((resolve) => {
      execFile('taskkill', ['/PID', String(pid), '/T', '/F'], { windowsHide: true }, () => resolve());
    });
  } else {
    try {
      process.kill(pid, 'SIGKILL');
    } catch {
      // ignore
    }
  }
}

interface ElevatePayload {
  exePath: string;
  cwd: string;
  localEngineHost: string;
  localEnginePort: string;
  binDir: string;
  pidPath: string;
  logPath: string;
  logDir: string;
}

/**
 * sudo-prompt 会等待「命令」结束；此处用提权后的短脚本 Start-Process 拉起常驻进程后立即退出。
 * 提权子进程 stdout/stderr 无法接回 Electron，依赖 local_engine 自身日志与 logPath 中的 launcher 行。
 */
async function startLocalEngineWindowsElevated(args: {
  exePath: string;
  host: string;
  port: number;
  binDir: string | null;
  logPath: string;
  logDir: string;
}): Promise<{ pid: number } | { error: string }> {
  const { exePath, host, port, binDir, logPath, logDir } = args;
  const cwd = path.dirname(exePath);
  const userData = app.getPath('userData');
  const pidPath = path.join(userData, 'local_engine.child.pid');
  const ps1Path = path.join(userData, 'local_engine_elevate_launch.ps1');

  try {
    if (fs.existsSync(pidPath)) fs.unlinkSync(pidPath);
  } catch {
    // ignore
  }

  const payload: ElevatePayload = {
    exePath,
    cwd,
    localEngineHost: host,
    localEnginePort: String(port),
    binDir: binDir ?? '',
    pidPath,
    logPath,
    logDir,
  };
  const b64 = Buffer.from(JSON.stringify(payload), 'utf8').toString('base64');

  // 注意：Windows 自带的 powershell.exe 是 5.1，Start-Process 没有 -LiteralPath 参数；
  // Add-Content / Set-Content 的 -LiteralPath 在 5.1 上是有的，可以继续用。
  // exePath / cwd 走绝对路径，-FilePath 足够。
  const ps1 = [
    '$ErrorActionPreference = "Stop"',
    `$b64 = '${b64}'`,
    '$json = [System.Text.Encoding]::UTF8.GetString([System.Convert]::FromBase64String($b64))',
    '$cfg = $json | ConvertFrom-Json',
    '$env:LOCAL_ENGINE_HOST = $cfg.localEngineHost',
    '$env:LOCAL_ENGINE_PORT = $cfg.localEnginePort',
    '$env:LOG_DIR = $cfg.logDir',
    'if ($cfg.binDir -and $cfg.binDir.Length -gt 0) { $env:Path = $cfg.binDir + [IO.Path]::PathSeparator + $env:Path }',
    '$stamp = (Get-Date).ToString("o")',
    'Add-Content -LiteralPath $cfg.logPath -Value "`n[$stamp] local_engine (UAC elevated) launcher`nexePath=$($cfg.exePath)`n"',
    '$p = Start-Process -FilePath $cfg.exePath -WorkingDirectory $cfg.cwd -WindowStyle Hidden -PassThru',
    'if (-not $p -or -not $p.Id) { throw "Start-Process did not return a process id" }',
    'Set-Content -LiteralPath $cfg.pidPath -Value $p.Id -Encoding ascii',
  ].join('\r\n');

  try {
    fs.writeFileSync(ps1Path, ps1, 'utf8');
  } catch (e) {
    return { error: `Failed to write elevated launcher script: ${e instanceof Error ? e.message : String(e)}` };
  }

  const cmd = `powershell.exe -NoProfile -ExecutionPolicy Bypass -File "${ps1Path}"`;
  try {
    await sudoExec(cmd, { name: 'UseIt Studio Local Engine' });
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e);
    if (/did not grant permission|User did not grant permission/i.test(msg)) {
      return { error: 'Administrator approval was cancelled. local_engine needs elevated privileges to start.' };
    }
    return { error: `Elevated start failed: ${msg}` };
  } finally {
    try {
      fs.unlinkSync(ps1Path);
    } catch {
      // ignore
    }
  }

  let raw = '';
  try {
    raw = fs.readFileSync(pidPath, 'utf8').trim();
    fs.unlinkSync(pidPath);
  } catch {
    return { error: 'Elevated launcher did not write PID file.' };
  }

  const pid = parseInt(raw, 10);
  if (!Number.isFinite(pid) || pid <= 0) {
    return { error: `Elevated launcher returned invalid PID: ${raw || '(empty)'}` };
  }
  return { pid };
}

export async function ensureLocalEngineRunning(): Promise<StartResult> {
  const port = getPort();

  if (await isHealthy(port)) {
    return { ok: true, started: false, alreadyRunning: true };
  }

  const exePath = resolveLocalEngineExePath();
  if (!exePath) {
    return {
      ok: false,
      error:
        'local_engine.exe not found. Ensure it is packaged into resources/services (electron-builder extraResources).',
    };
  }

  // 再次确认：避免竞争条件（刚好被别人启动了）
  if (await isHealthy(port)) {
    return { ok: true, started: false, alreadyRunning: true, exePath };
  }

  // 与 Python 侧 LOG_DIR 下的 local_engine.log 区分，避免双进程争写同一文件
  const logStream = createLogStream('local_engine_spawn.log');
  const logPath = path.join(getLogDir(), 'local_engine_spawn.log');
  const localHost = process.env.LOCAL_ENGINE_HOST || '127.0.0.1';
  if (logStream) {
    logStream.write(`\n\n[${new Date().toISOString()}] starting local_engine\n`);
    logStream.write(`exePath=${exePath}\n`);
    logStream.write(`LOCAL_ENGINE_HOST=${localHost}\n`);
    logStream.write(`LOCAL_ENGINE_PORT=${port}\n`);
  }

  const binDir = resolveResourcesBinDir();
  if (logStream) {
    logStream.write(`resourcesBinDir=${binDir || ''}\n`);
    const p = process.env.Path || process.env.PATH || '';
    logStream.write(`parentPathPrefix=${p.slice(0, 260)}\n`);
  }

  const logDirForEngine = getLogDir();
  const childEnv: NodeJS.ProcessEnv = {
    ...(binDir ? prependToPath(process.env, binDir) : process.env),
    LOCAL_ENGINE_HOST: localHost,
    LOCAL_ENGINE_PORT: String(port),
    LOG_DIR: logDirForEngine,
  };

  // 不要用 pipe 接 stdout/stderr：Windows 上管道缓冲区有限，local_engine 启动阶段日志量大时
  // 子进程可能在写入 stdout 时阻塞，导致 uvicorn 迟迟不 bind，前端表现为 failed to fetch。
  // 日志改由 Python 侧写入 LOG_DIR（见 logging_config.py）。
  const child = spawn(exePath, [], {
    windowsHide: true,
    cwd: path.dirname(exePath),
    stdio: ['ignore'],
    detached: false, // 需要随 Electron 生命周期关掉
    env: childEnv,
  });

  /** 本路径为直接 spawn，未经 Windows UAC 提权；与 startLocalEngineWindowsElevated 分支区分。 */
  const useWindowsUacElevate = false;
  const childExitState: {
    exited: boolean;
    info: { code: number | null; signal: NodeJS.Signals | null } | null;
  } = { exited: false, info: null };

  childPid = child.pid ?? null;

  child.on('error', (err) => {
    if (logStream) {
      logStream.write(`[${new Date().toISOString()}] spawn error: ${err}\n`);
    }
    console.error('[LocalEngine] spawn error:', err);
  });

  child.once('exit', (code, signal) => {
    childExitState.exited = true;
    childExitState.info = { code, signal };
    if (logStream) {
      logStream.write(`[${new Date().toISOString()}] local_engine exit code=${code} signal=${signal}\n`);
      logStream.end();
    }
  });

  // 等待服务就绪（health）。PyInstaller one-file 冷启动会解包到 %TEMP%，首次运行尤其慢；
  // 叠加 pywin32 / Pillow / pynput 加载时间，在某些机器上 >15s。
  // 之前硬编码 10s 会把正在正常启动的进程判为失败，导致前端看到 500 / Failed to fetch。
  const healthTimeoutMs = Number(process.env.LOCAL_ENGINE_HEALTH_TIMEOUT_MS) || 45_000;
  const deadline = Date.now() + healthTimeoutMs;
  while (Date.now() < deadline) {
    if (await isHealthy(port)) {
      return { ok: true, started: true, pid: childPid ?? -1, exePath };
    }
    // 非提权分支：子进程已经退出，就没必要继续等了，快速失败能让上层尽早拿到真实错误。
    if (!useWindowsUacElevate && childExitState.exited) {
      const exitCode = childExitState.info?.code ?? null;
      const exitSignal = childExitState.info?.signal ?? null;
      if (logStream) {
        logStream.write(
          `[${new Date().toISOString()}] local_engine child exited early code=${exitCode ?? 'null'} signal=${exitSignal ?? 'null'}; abort waiting for health.\n`
        );
        logStream.end();
      }
      return {
        ok: false,
        exePath,
        error: `local_engine process exited before health check (code=${exitCode ?? 'null'}). See logs in: ${getLogDir()}`,
      };
    }
    await new Promise((r) => setTimeout(r, 500));
  }

  const failPid = childPid;
  childPid = null;
  // 提权场景下父进程通常是非管理员，taskkill 无权结束提权子进程；
  // 一旦 kill 失败又会留下一个真的在正常服务的孤儿进程，反而造成更混乱的状态。
  // 这种情况下不再主动 kill，交给 Electron 退出时通过 stopLocalEngine 处理。
  if (!useWindowsUacElevate && failPid && failPid > 0) {
    await killProcessTree(failPid);
  }
  if (logStream) {
    logStream.write(`[${new Date().toISOString()}] local_engine health check failed.\n`);
  }

  return {
    ok: false,
    exePath,
    error: `local_engine started but health check failed within ${healthTimeoutMs}ms (http://127.0.0.1:${port}/health). See logs in: ${getLogDir()} (spawn: local_engine_spawn.log, engine: local_engine.log)`,
  };
}

export async function stopLocalEngine(): Promise<void> {
  if (stopping) return;
  stopping = true;
  try {
    if (!childPid || childPid <= 0) return;
    const pid = childPid;
    await killProcessTree(pid);
  } finally {
    childPid = null;
    stopping = false;
  }
}


