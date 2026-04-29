import { app } from 'electron';
import { execFile, spawn } from 'child_process';
import * as fs from 'fs';
import * as net from 'net';
import * as path from 'path';

type StartResult =
  | { ok: true; started: true; pid: number; exePath: string }
  | { ok: true; started: false; alreadyRunning: true; exePath?: string }
  | { ok: false; error: string; exePath?: string };

let childPid: number | null = null;
let stopping = false;

const DEFAULT_PORT = 8080;

function getPort(): number {
  const raw = process.env.CUA_SERVER_PORT || '';
  const n = Number(raw);
  return Number.isFinite(n) && n > 0 ? n : DEFAULT_PORT;
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

function isPortOpen(host: string, port: number, timeoutMs: number): Promise<boolean> {
  return new Promise((resolve) => {
    const sock = new net.Socket();
    let done = false;

    const finish = (ok: boolean) => {
      if (done) return;
      done = true;
      try {
        sock.destroy();
      } catch {
        // ignore
      }
      resolve(ok);
    };

    sock.setTimeout(timeoutMs);
    sock.once('connect', () => finish(true));
    sock.once('timeout', () => finish(false));
    sock.once('error', () => finish(false));

    sock.connect(port, host);
  });
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

export function resolveComputerServerExePath(): string | null {
  // exe 位于子目录 computer_server/ 下，与其依赖 DLL/pyd 在同一目录
  const exeName = 'computer_server.exe';
  const serviceDir = 'computer_server';
  const isDev = process.env.NODE_ENV === 'development' || !app.isPackaged;

  const candidates: string[] = [];

  if (isDev) {
    const appPath = app.getAppPath();
    candidates.push(
      // 新结构：services/computer_server/computer_server.exe
      path.join(appPath, 'resources', 'services', serviceDir, exeName),
      path.join(appPath, 'frontend', 'resources', 'services', serviceDir, exeName),
      path.join(__dirname, '../../resources/services', serviceDir, exeName),
      path.join(__dirname, '../../../resources/services', serviceDir, exeName),
      // 旧结构兼容：services/computer_server.exe
      path.join(appPath, 'resources', 'services', exeName),
      path.join(appPath, 'frontend', 'resources', 'services', exeName),
      path.join(__dirname, '../../resources/services', exeName),
      path.join(__dirname, '../../../resources/services', exeName)
    );
  } else {
    // 生产环境
    candidates.push(
      // 新结构：services/computer_server/computer_server.exe
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
    candidates.push(path.join(process.resourcesPath, 'bin'), path.join(process.resourcesPath, 'resources', 'bin'));
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
  const current = env.Path || env.PATH || '';
  const sep = path.delimiter;
  const next = `${dir}${sep}${current}`;
  return { ...env, Path: next, PATH: next };
}

export async function ensureComputerServerRunning(): Promise<StartResult> {
  const host = process.env.CUA_SERVER_HOST || '127.0.0.1';
  const port = getPort();

  if (await isPortOpen(host, port, 600)) {
    return { ok: true, started: false, alreadyRunning: true };
  }

  const exePath = resolveComputerServerExePath();
  if (!exePath) {
    return {
      ok: false,
      error:
        'computer_server.exe not found. Ensure it is packaged into resources/services (electron-builder extraResources).',
    };
  }

  // 再次确认：避免竞争条件
  if (await isPortOpen(host, port, 600)) {
    return { ok: true, started: false, alreadyRunning: true, exePath };
  }

  const logStream = createLogStream('computer_server.log');
  const logPath = path.join(getLogDir(), 'computer_server.log');
  if (logStream) {
    logStream.write(`\n\n[${new Date().toISOString()}] starting computer_server\n`);
    logStream.write(`exePath=${exePath}\n`);
    logStream.write(`CUA_SERVER_HOST=${host}\n`);
    logStream.write(`CUA_SERVER_PORT=${port}\n`);
  }

  const binDir = resolveResourcesBinDir();
  if (logStream) {
    logStream.write(`resourcesBinDir=${binDir || ''}\n`);
    const p = process.env.Path || process.env.PATH || '';
    logStream.write(`parentPathPrefix=${p.slice(0, 260)}\n`);
  }

  const child = spawn(exePath, [], {
    windowsHide: true,
    cwd: path.dirname(exePath),
    stdio: ['ignore', 'pipe', 'pipe'],
    detached: false,
    env: {
      ...(binDir ? prependToPath(process.env, binDir) : process.env),
      CUA_SERVER_HOST: host,
      CUA_SERVER_PORT: String(port),
    },
  });

  childPid = child.pid ?? null;

  // Pipe child output to log file (cannot pass WriteStream directly in stdio)
  if (logStream) {
    try {
      child.stdout?.pipe(logStream, { end: false });
      child.stderr?.pipe(logStream, { end: false });
    } catch {
      // ignore
    }
  }

  child.once('exit', (code, signal) => {
    if (logStream) {
      logStream.write(`[${new Date().toISOString()}] computer_server exit code=${code} signal=${signal}\n`);
      logStream.end();
    }
  });

  // 等待端口就绪，最多 ~10s
  const deadline = Date.now() + 10_000;
  while (Date.now() < deadline) {
    if (await isPortOpen(host, port, 600)) {
      return { ok: true, started: true, pid: childPid ?? -1, exePath };
    }
    await new Promise((r) => setTimeout(r, 300));
  }

  return {
    ok: false,
    exePath,
    error: `computer_server started but port not open (${host}:${port}). See log: ${logPath}`,
  };
}

export async function stopComputerServer(): Promise<void> {
  if (stopping) return;
  stopping = true;
  try {
    if (!childPid || childPid <= 0) return;

    await new Promise<void>((resolve) => {
      execFile('taskkill', ['/PID', String(childPid), '/T', '/F'], { windowsHide: true }, () => resolve());
    });
  } finally {
    childPid = null;
    stopping = false;
  }
}


