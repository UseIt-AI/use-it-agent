// Copied (with minimal changes) from the migrated recorder module.
// Runs in Electron main process.
import { uIOhook, UiohookKey, UiohookMouseEvent, UiohookKeyboardEvent, UiohookWheelEvent } from 'uiohook-napi';

// 扫描码到键名的反向映射表
// UiohookKey 提供 keyName -> keycode，我们需要 keycode -> keyName
const KEYCODE_TO_NAME: Record<number, string> = {};
for (const [name, code] of Object.entries(UiohookKey)) {
  if (typeof code === 'number') {
    KEYCODE_TO_NAME[code] = name;
  }
}
import { dialog, screen } from 'electron';
import * as fs from 'fs';
import * as path from 'path';
import * as os from 'os';
import * as crypto from 'crypto';
import { execSync } from 'child_process';
import { WindowSwitchTracker, ActiveWindowInfo } from './window-tracker';
// eslint-disable-next-line @typescript-eslint/no-var-requires
const fernet = require('fernet');
// eslint-disable-next-line @typescript-eslint/no-var-requires
const sudoPrompt = require('sudo-prompt');

interface Point {
  x: number;
  y: number;
}

interface ScreenInfo {
  [key: string]: { x0: number; y0: number; width: number; height: number; scale_factor: number };
}

interface EventData {
  timestamp: string; // SRT-like timestamp (HH:MM:SS.mmm)
  message: string;
  window: string;
  /** 进程名称 (仅 WINDOW_SWITCH 事件) */
  process?: string;
}

/** 窗口切换事件数据 */
interface WindowSwitchEventData {
  timestamp: string;
  type: 'WINDOW_SWITCH';
  from: {
    title: string;
    process: string;
  } | null;
  to: {
    title: string;
    process: string;
  };
}

export class InputListener {
  // NOTE: in the original code this field is used by recorder to "pause" on secure desktop;
  // keep it public for compatibility.
  public isRecording = false;

  private startTime: Date | null = null;
  private eventBuffer: string[] = [];
  private fernetSecret: any = null;
  private processedKey = '';
  private originalKey = '';
  private txtLogFile: fs.WriteStream | null = null;
  private srtLogFile: fs.WriteStream | null = null;
  private txtLogPath = '';
  private srtLogPath = '';

  private currentModifiers = new Set<number>();
  private lastClickTime = 0;
  private lastClickPosition: Point = { x: 0, y: 0 };
  private dragStartPos: Point | null = null;
  private isDragging = false;

  private doubleClickThreshold = 500;
  private doubleClickDistance = 5;
  private dragThreshold = 5;

  // 窗口切换追踪
  private windowTracker = new WindowSwitchTracker(50);
  private currentActiveWindow: ActiveWindowInfo | null = null;

  private readonly modifierKeys = new Set([
    UiohookKey.CtrlL,
    UiohookKey.CtrlR,
    UiohookKey.ShiftL,
    UiohookKey.ShiftR,
    UiohookKey.AltL,
    UiohookKey.AltR,
    UiohookKey.MetaL,
    UiohookKey.MetaR,
  ]);

  constructor() {
    this.setupInputHooks();

    process.on('exit', () => {
      try {
        if (this.isRecording) uIOhook.stop();
      } catch {
        // ignore on exit
      }
    });
  }

  isRecordingActive(): boolean {
    return this.isRecording;
  }

  private setupInputHooks(): void {
    uIOhook.on('keydown', this.onKeyDown.bind(this));
    uIOhook.on('keyup', this.onKeyUp.bind(this));
    uIOhook.on('mousedown', this.onMouseDown.bind(this));
    uIOhook.on('mouseup', this.onMouseUp.bind(this));
    uIOhook.on('mousemove', this.onMouseMove.bind(this));
    uIOhook.on('wheel', this.onMouseWheel.bind(this));
  }

  private async checkAdminPrivileges(): Promise<boolean> {
    try {
      if (process.platform === 'win32') {
        const testPath = path.join(process.env.WINDIR || 'C:\\Windows', 'Temp', 'useit_admin_test.tmp');
        try {
          fs.writeFileSync(testPath, 'test');
          fs.unlinkSync(testPath);
          return true;
        } catch {
          const result = execSync('whoami /groups', { encoding: 'utf8', timeout: 2000 });
          return result.includes('S-1-16-12288');
        }
      }
      return true;
    } catch {
      return false;
    }
  }

  private async requestElevatedPrivileges(): Promise<boolean> {
    return await new Promise((resolve) => {
      const options = { name: 'AutoCAD Agent - Input Monitoring' };
      const electronPath = process.execPath;
      const appPath = process.argv[1];
      const command = `"${electronPath}" "${appPath}"`;

      sudoPrompt.exec(command, options, (error: any) => {
        if (error) {
          resolve(false);
        } else {
          process.exit(0);
        }
      });
    });
  }

  /**
   * 开始录制输入事件
   * @param sharedStartTime 共享的时间基准（来自视频录制开始时间），用于确保视频和键鼠时间戳对齐
   */
  async startRecording(sharedStartTime?: Date): Promise<{ srtPath: string; txtPath: string }> {
    if (this.isRecording) throw new Error('Recording already in progress');

    const hasPrivileges = await this.checkAdminPrivileges();
    if (!hasPrivileges) {
      const response = await dialog.showMessageBox({
        type: 'warning',
        title: 'Administrator Privileges Required',
        message: 'Input monitoring requires administrator privileges to capture global keyboard and mouse events.',
        detail: 'The application will restart with elevated privileges. Please approve the UAC prompt.',
        buttons: ['Grant Privileges', 'Cancel'],
        defaultId: 0,
        cancelId: 1,
      });

      if (response.response === 0) {
        const elevated = await this.requestElevatedPrivileges();
        if (!elevated) throw new Error('Failed to obtain administrator privileges.');
      } else {
        throw new Error('Administrator privileges are required. Recording cancelled.');
      }
    }

    this.isRecording = true;
    // 使用共享时间基准（如果提供），否则使用当前时间
    // 这确保了视频和键鼠事件使用相同的时间参考点
    this.startTime = sharedStartTime || new Date();
    if (sharedStartTime) {
      console.log(`[InputListener] Using shared start time: ${sharedStartTime.toISOString()}`);
    }
    this.eventBuffer = [];
    this.currentModifiers.clear();
    this.windowTracker.reset();
    this.currentActiveWindow = null;

    const saveDir = path.join(os.homedir(), 'Downloads', 'record_save');
    if (!fs.existsSync(saveDir)) fs.mkdirSync(saveDir, { recursive: true });

    const ts = this.startTime
      .toISOString()
      .replace(/T/, '_')
      .replace(/\..+/, '')
      .replace(/:/g, '-')
      .replace(/-/g, '')
      .slice(0, 15);

    this.txtLogPath = path.join(saveDir, `action_trace_${ts}.txt`);
    this.srtLogPath = path.join(saveDir, `input_log_${ts}.srt`);

    this.txtLogFile = fs.createWriteStream(this.txtLogPath, { flags: 'w' });
    this.srtLogFile = fs.createWriteStream(this.srtLogPath, { flags: 'w' });

    const screenInfo = this.getScreenInfo();
    const headerTxt = [
      `Start Time: ${this.startTime.toISOString()}`,
      `Screen Info: ${JSON.stringify(screenInfo)}`,
      '',
    ].join(os.EOL);
    this.txtLogFile.write(headerTxt);

    // Fernet key generation (Python-compatible).
    // IMPORTANT: the first line we write is a *processedKey* (obfuscated key),
    // but the actual Fernet secret is the *originalKey*.
    this.generateEncryptionKey();

    // Write srt "header" (NOT standard SRT):
    // line1: processedKey
    // line2: encrypted screenInfo EventData
    // line3: encrypted metadata JSON
    this.srtLogFile.write(`${this.processedKey}${os.EOL}`);

    const screenInfoData: EventData = {
      timestamp: '00:00:00.000',
      message: JSON.stringify(screenInfo),
      window: 'System Info',
    };
    this.srtLogFile.write(this.encryptData(screenInfoData) + os.EOL);

    const videoTimestamp = this.startTime.toISOString();
    const meta = {
      video_start_time: videoTimestamp,
      start_message: 'Mouse and keyboard monitoring service started',
      recording_timestamp: videoTimestamp,
    };
    this.srtLogFile.write(this.encryptData(meta) + os.EOL);

    try {
      uIOhook.start();
    } catch (e) {
      this.isRecording = false;
      throw e;
    }

    return { srtPath: this.srtLogPath, txtPath: this.txtLogPath };
  }

  stopRecording(): { srtPath: string; txtPath: string } | null {
    if (!this.isRecording) return null;
    this.isRecording = false;

    const result = { srtPath: this.srtLogPath, txtPath: this.txtLogPath };

    // IMPORTANT (Windows): do NOT call uIOhook.stop() here to avoid potential deadlock.
    setImmediate(() => {
      try {
        this.flushAndClose();
      } catch (e) {
        console.warn('[InputListener] flushAndClose failed:', e);
      }
    });

    return result;
  }

  private flushAndClose() {
    try {
      this.flushEventBuffer();
    } catch {
      // ignore
    }
    if (this.txtLogFile) {
      try {
        this.txtLogFile.end();
      } catch {}
      this.txtLogFile = null;
    }
    if (this.srtLogFile) {
      try {
        this.srtLogFile.end();
      } catch {}
      this.srtLogFile = null;
    }
  }

  private getScreenInfo(): ScreenInfo {
    const displays = screen.getAllDisplays();
    const info: ScreenInfo = {};
    displays.forEach((d, idx) => {
      info[String(idx)] = {
        x0: d.bounds.x,
        y0: d.bounds.y,
        width: d.bounds.width,
        height: d.bounds.height,
        scale_factor: d.scaleFactor,
      };
    });
    return info;
  }

  private generateEncryptionKey(): void {
    // Replicate Python's key generation logic used by the old project:
    // - 16 random bytes, duplicated to 32 bytes
    // - urlsafe base64 encoding with padding ('=')
    const random16 = crypto.randomBytes(16);
    const full32 = Buffer.concat([random16, random16]);
    const base64 = full32.toString('base64'); // includes '=' padding
    const urlsafe = base64.replace(/\+/g, '-').replace(/\//g, '_');

    // processedKey: reverse first 17 chars, keep the rest unchanged
    const firstHalf = urlsafe.slice(0, 17);
    const secondHalf = urlsafe.slice(17);
    const reversedFirstHalf = firstHalf.split('').reverse().join('');

    this.originalKey = urlsafe;
    this.processedKey = reversedFirstHalf + secondHalf;

    try {
      // NOTE: Python Fernet accepts urlsafe base64 (-, _) keys.
      // The npm `fernet` package is picky in some environments and may expect standard base64 (+, /).
      // Both decode to the same 32-byte key material, so we normalize for the JS library only.
      const jsKey = this.originalKey.replace(/-/g, '+').replace(/_/g, '/');
      this.fernetSecret = new fernet.Secret(jsKey);
    } catch (e) {
      console.error('[InputListener] Failed to create Fernet secret:', e);
      this.fernetSecret = null;
    }
  }

  private encryptData(data: any): string {
    const jsonStr = JSON.stringify(data);
    try {
      if (this.fernetSecret) {
        const token = new fernet.Token({
          secret: this.fernetSecret,
          // Fernet timestamp is seconds since epoch (Python-compatible)
          time: Math.floor(Date.now() / 1000),
          ttl: 0,
        });
        return token.encode(jsonStr);
      }
      // fallback
      return Buffer.from(jsonStr).toString('base64');
    } catch (e) {
      console.error('[InputListener] Encryption error:', e);
      return Buffer.from(jsonStr).toString('base64');
    }
  }

  private formatTimestamp(ms: number): string {
    const total = Math.max(0, Math.floor(ms));
    const hours = Math.floor(total / 3600000);
    const minutes = Math.floor((total % 3600000) / 60000);
    const seconds = Math.floor((total % 60000) / 1000);
    const millis = total % 1000;
    const pad2 = (n: number) => String(n).padStart(2, '0');
    const pad3 = (n: number) => String(n).padStart(3, '0');
    return `${pad2(hours)}:${pad2(minutes)}:${pad2(seconds)}.${pad3(millis)}`;
  }

  private flushEventBuffer() {
    if (!this.srtLogFile) return;
    if (!this.eventBuffer.length) return;
    const lines = this.eventBuffer.join(os.EOL) + os.EOL;
    this.eventBuffer = [];
    this.srtLogFile.write(lines);
  }

  // ======== Window switch detection ========
  /**
   * 检查并记录窗口切换事件
   * 在用户输入事件触发时调用，实现事件驱动的窗口追踪
   */
  private checkAndRecordWindowSwitch(): void {
    if (!this.isRecording || !this.startTime) return;

    const switchInfo = this.windowTracker.checkSwitch();
    if (switchInfo) {
      this.currentActiveWindow = switchInfo.to;
      this.recordWindowSwitch(switchInfo.from, switchInfo.to);
    }
  }

  /**
   * 记录窗口切换事件
   */
  private recordWindowSwitch(from: ActiveWindowInfo | null, to: ActiveWindowInfo): void {
    if (!this.isRecording || !this.startTime) return;

    const now = new Date();
    const elapsed = now.getTime() - this.startTime.getTime();
    const timestamp = this.formatTimestamp(elapsed);

    // 构建切换事件消息
    const fromStr = from ? `${from.processName}:${from.title}` : 'null';
    const toStr = `${to.processName}:${to.title}`;
    const message = `WINDOW_SWITCH from="${fromStr}" to="${toStr}"`;

    // 写入纯文本日志
    this.txtLogFile?.write(`${timestamp}\t${message}` + os.EOL);

    // 构建结构化的窗口切换事件
    const windowSwitchData: WindowSwitchEventData = {
      timestamp,
      type: 'WINDOW_SWITCH',
      from: from ? { title: from.title, process: from.processName } : null,
      to: { title: to.title, process: to.processName },
    };

    const encrypted = this.encryptData(windowSwitchData);
    this.eventBuffer.push(encrypted);
    if (this.eventBuffer.length >= 10) this.flushEventBuffer();
  }

  // ======== Event handlers (Python-compatible logging) ========
  private pushEvent(message: string) {
    if (!this.isRecording || !this.startTime) return;

    // 先检查窗口切换
    this.checkAndRecordWindowSwitch();

    const now = new Date();
    const elapsed = now.getTime() - this.startTime.getTime();
    const timestamp = this.formatTimestamp(elapsed);

    // Keep plain-text trace for debugging (ASCII-only to avoid weird parser issues)
    const cleanMessage = message.replace(/[^\x20-\x7E]/g, '');
    this.txtLogFile?.write(`${timestamp}\t${cleanMessage}` + os.EOL);

    // 获取当前窗口信息
    const windowTitle = this.currentActiveWindow?.title || 'Unknown';
    const processName = this.currentActiveWindow?.processName || '';

    const eventData: EventData = {
      timestamp,
      message: cleanMessage,
      window: windowTitle,
      process: processName || undefined,
    };

    const encrypted = this.encryptData(eventData);
    this.eventBuffer.push(encrypted);
    if (this.eventBuffer.length >= 10) this.flushEventBuffer();
  }

  private onKeyDown(e: UiohookKeyboardEvent) {
    if (this.modifierKeys.has(e.keycode)) this.currentModifiers.add(e.keycode);
    const keyName = KEYCODE_TO_NAME[e.keycode] || `Unknown(${e.keycode})`;
    // 记录格式: KEY_DOWN keycode=30 key=A (同时保留扫描码和键名)
    this.pushEvent(`KEY_DOWN keycode=${e.keycode} key=${keyName}`);
  }

  private onKeyUp(e: UiohookKeyboardEvent) {
    if (this.modifierKeys.has(e.keycode)) this.currentModifiers.delete(e.keycode);
    const keyName = KEYCODE_TO_NAME[e.keycode] || `Unknown(${e.keycode})`;
    this.pushEvent(`KEY_UP keycode=${e.keycode} key=${keyName}`);
  }

  private onMouseDown(e: UiohookMouseEvent) {
    const now = Date.now();
    const pos = { x: e.x, y: e.y };
    const dt = now - this.lastClickTime;
    const dx = Math.abs(pos.x - this.lastClickPosition.x);
    const dy = Math.abs(pos.y - this.lastClickPosition.y);
    const isDouble = dt < this.doubleClickThreshold && dx < this.doubleClickDistance && dy < this.doubleClickDistance;
    this.dragStartPos = pos;
    this.isDragging = false;
    this.lastClickTime = now;
    this.lastClickPosition = pos;
    this.pushEvent(`${isDouble ? 'DBL_CLICK' : 'MOUSE_DOWN'} btn=${e.button} x=${e.x} y=${e.y}`);
  }

  private onMouseUp(e: UiohookMouseEvent) {
    this.pushEvent(`MOUSE_UP btn=${e.button} x=${e.x} y=${e.y}`);
    this.dragStartPos = null;
    this.isDragging = false;
  }

  private onMouseMove(e: UiohookMouseEvent) {
    if (!this.dragStartPos) return;
    const dx = Math.abs(e.x - this.dragStartPos.x);
    const dy = Math.abs(e.y - this.dragStartPos.y);
    if (!this.isDragging && (dx > this.dragThreshold || dy > this.dragThreshold)) {
      this.isDragging = true;
      this.pushEvent(`DRAG_START x=${this.dragStartPos.x} y=${this.dragStartPos.y}`);
    }
    if (this.isDragging) {
      this.pushEvent(`DRAG_MOVE x=${e.x} y=${e.y}`);
    }
  }

  private onMouseWheel(e: UiohookWheelEvent) {
    this.pushEvent(`WHEEL rotation=${e.rotation} x=${e.x} y=${e.y}`);
  }
}


