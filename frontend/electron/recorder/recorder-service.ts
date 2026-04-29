import { BrowserWindow, desktopCapturer, screen } from 'electron';
import { spawn, ChildProcessWithoutNullStreams } from 'child_process';
import fs from 'fs';
import os from 'os';
import path from 'path';
import { InputListener } from './input-listener';
import type { RecorderSource, RecordingInfo, RecordingStopCompletePayload } from './types';

function safeBasenameTitle(title?: string) {
  const cleaned = (title || 'Recording').replace(/[^\w\s-]/g, '').replace(/\s+/g, '-');
  return cleaned.length ? cleaned : 'Recording';
}

function resolveFfmpegPath(): string {
  // 判断是否是打包后的环境
  const isPackaged = !process.defaultApp;

  if (isPackaged) {
    // 打包后：优先从 resources/bin 查找 ffmpeg
    const resourcePath = path.join(process.resourcesPath, 'bin', 'ffmpeg.exe');
    if (fs.existsSync(resourcePath)) {
      console.log('[Recorder] Using packaged ffmpeg:', resourcePath);
      return resourcePath;
    }
    console.warn('[Recorder] Packaged ffmpeg not found at:', resourcePath);
  }

  // 开发环境：使用 ffmpeg-static
  try {
    // eslint-disable-next-line @typescript-eslint/no-var-requires
    const p = require('ffmpeg-static');
    if (typeof p === 'string' && p && fs.existsSync(p)) {
      console.log('[Recorder] Using ffmpeg-static:', p);
      return p;
    }
  } catch {
    // ignore
  }

  // 最后 fallback 到系统 PATH
  console.warn('[Recorder] Falling back to system ffmpeg');
  return 'ffmpeg';
}

export class RecorderService {
  public currentRecording: RecordingInfo = { isRecording: false, duration: 0 };
  public recordingSources: RecorderSource[] = [];

  private inputListener = new InputListener();
  private ffmpegProcess: ChildProcessWithoutNullStreams | null = null; // 有鼠标的录制进程
  private ffmpegProcessNoMouse: ChildProcessWithoutNullStreams | null = null; // 无鼠标的录制进程
  private ffmpegPath = resolveFfmpegPath();
  private recordStartTime: Date | null = null;
  private timeUpdateInterval: NodeJS.Timeout | null = null;

  async refreshSources(): Promise<RecorderSource[]> {
    try {
      const sources = await desktopCapturer.getSources({
        types: ['screen'],
        thumbnailSize: { width: 150, height: 150 },
      });
      const displays = screen.getAllDisplays();

      this.recordingSources = sources.map((source, index) => {
        const display = displays[index];
        let displayName = source.name;
        if (display) {
          const { width, height } = display.bounds;
          const isPrimary = display.bounds.x === 0 && display.bounds.y === 0;
          displayName = `${source.name}${isPrimary ? ' (Primary)' : ''} - ${width}x${height}`;
        }
        return { id: source.id, name: displayName, thumbnail: source.thumbnail.toDataURL() };
      });

      return this.recordingSources;
    } catch (err) {
      console.error('[Recorder] refreshSources failed:', err);
      this.recordingSources = [];
      return [];
    }
  }

  getStatus(): RecordingInfo {
    return { ...this.currentRecording };
  }

  async startRecording(sourceId?: string, title?: string): Promise<boolean> {
    if (this.currentRecording.isRecording) return false;
    if (this.currentRecording.isStopping) return false;

    // Select source if not provided
    let selectedSourceId = sourceId;
    if (!selectedSourceId) {
      const sources = await desktopCapturer.getSources({ types: ['screen'] });
      const primarySource =
        sources.find((s) => s.name.includes('Primary') || s.name.includes('Display 1') || s.name.includes('主')) ??
        sources[0];
      selectedSourceId = primarySource?.id;
      if (!selectedSourceId) return false;
    }

    // Determine scaling target (1920 width)
    const displays = screen.getAllDisplays();
    const primaryDisplay = displays.find((d) => d.bounds.x === 0 && d.bounds.y === 0) || displays[0];
    const srcW = primaryDisplay?.bounds.width ?? 1920;
    const srcH = primaryDisplay?.bounds.height ?? 1080;
    const aspect = srcW / srcH;
    const targetWidth = 1920;
    const targetHeight = Math.round(targetWidth / aspect);

    const recordsDir = path.join(os.homedir(), 'Downloads', 'record_save');
    if (!fs.existsSync(recordsDir)) fs.mkdirSync(recordsDir, { recursive: true });

    const now = new Date();
    const timestamp = now.toISOString().replace(/T/, '_').replace(/\..+/, '').replace(/:/g, '-');
    const timePart = timestamp.split('_')[1];
    const prefix = safeBasenameTitle(title);
    
    // 两个输出路径：有鼠标（用于上传）和无鼠标（本地保留）
    const outputPath = path.join(recordsDir, `${prefix}-${timePart}.mkv`); // 有鼠标
    const outputPathNoMouse = path.join(recordsDir, `${prefix}-${timePart}-nomouse.mkv`); // 无鼠标

    // 有鼠标的 ffmpeg 参数
    // 使用 ddagrab (Desktop Duplication API) 替代 gdigrab，避免鼠标闪烁
    // ddagrab 输出硬件纹理，需要 hwdownload 转换为普通帧
    const ffmpegArgs = [
      '-f',
      'lavfi',
      '-i',
      `ddagrab=output_idx=0:draw_mouse=1:framerate=30`,
      '-vf',
      `hwdownload,format=bgra,scale=${targetWidth}:${targetHeight}`,
      '-c:v',
      'libx264',
      '-preset',
      'ultrafast',
      '-tune',
      'zerolatency',
      '-b:v',
      '10000k',
      '-metadata',
      `title=${prefix}`,
      '-metadata',
      `recording_time=${timestamp}`,
      outputPath,
    ];

    // 无鼠标的 ffmpeg 参数
    const ffmpegArgsNoMouse = [
      '-f',
      'lavfi',
      '-i',
      `ddagrab=output_idx=0:draw_mouse=0:framerate=30`,
      '-vf',
      `hwdownload,format=bgra,scale=${targetWidth}:${targetHeight}`,
      '-c:v',
      'libx264',
      '-preset',
      'ultrafast',
      '-tune',
      'zerolatency',
      '-b:v',
      '10000k',
      '-metadata',
      `title=${prefix} (no mouse)`,
      '-metadata',
      `recording_time=${timestamp}`,
      outputPathNoMouse,
    ];

    console.log('[Recorder] spawning ffmpeg (with mouse):', this.ffmpegPath, ffmpegArgs.join(' '));
    console.log('[Recorder] spawning ffmpeg (no mouse):', this.ffmpegPath, ffmpegArgsNoMouse.join(' '));

    this.ffmpegProcess = spawn(this.ffmpegPath, ffmpegArgs, { stdio: ['pipe', 'pipe', 'pipe'] });
    this.ffmpegProcessNoMouse = spawn(this.ffmpegPath, ffmpegArgsNoMouse, { stdio: ['pipe', 'pipe', 'pipe'] });

    return await new Promise<boolean>((resolve) => {
      let started = false;
      let noMouseStarted = false;
      let noMouseFailed = false;
      let resolved = false;

      const safeResolve = (value: boolean) => {
        if (resolved) return;
        resolved = true;
        clearTimeout(startupTimeout);
        resolve(value);
      };

      const tryResolveSuccess = () => {
        if (started && (noMouseStarted || noMouseFailed)) {
          this.onBothProcessesStarted(outputPath, outputPathNoMouse, startupTimeout);
          safeResolve(true);
        }
      };

      const startupTimeout = setTimeout(() => {
        if (resolved) return;
        if (started && !noMouseStarted) {
          console.warn('[Recorder] no-mouse ffmpeg startup timeout, continuing with mouse recording only');
          try { this.ffmpegProcessNoMouse?.kill('SIGKILL'); } catch {}
          this.ffmpegProcessNoMouse = null;
          noMouseFailed = true;
          tryResolveSuccess();
        } else if (!started) {
          console.error('[Recorder] ffmpeg startup timeout');
          try {
            this.ffmpegProcess?.kill('SIGKILL');
            this.ffmpegProcessNoMouse?.kill('SIGKILL');
          } catch {}
          this.ffmpegProcess = null;
          this.ffmpegProcessNoMouse = null;
          safeResolve(false);
        }
      }, 8000);

      // 监听有鼠标的进程
      this.ffmpegProcess!.stderr.on('data', (buf) => {
        const output = buf.toString();
        if (!started && (output.includes('frame=') || output.includes('fps=') || output.includes('time='))) {
          started = true;
          tryResolveSuccess();
        }
      });

      // 监听无鼠标的进程
      this.ffmpegProcessNoMouse!.stderr.on('data', (buf) => {
        const output = buf.toString();
        if (!noMouseStarted && (output.includes('frame=') || output.includes('fps=') || output.includes('time='))) {
          noMouseStarted = true;
          console.log('[Recorder] ffmpeg (no mouse) started');
          tryResolveSuccess();
        }
      });

      this.ffmpegProcess!.on('exit', (code) => {
        console.log('[Recorder] ffmpeg (with mouse) exited:', code);
      });

      this.ffmpegProcessNoMouse!.on('exit', (code) => {
        console.log('[Recorder] ffmpeg (no mouse) exited:', code);
        if (!noMouseStarted && !noMouseFailed) {
          noMouseFailed = true;
          this.ffmpegProcessNoMouse = null;
          console.warn('[Recorder] no-mouse ffmpeg exited before starting, continuing without it');
          tryResolveSuccess();
        }
      });

      this.ffmpegProcess!.on('error', (err) => {
        console.error('[Recorder] ffmpeg (with mouse) error:', err);
        this.ffmpegProcess = null;
        try { this.ffmpegProcessNoMouse?.kill('SIGKILL'); } catch {}
        this.ffmpegProcessNoMouse = null;
        safeResolve(false);
      });

      this.ffmpegProcessNoMouse!.on('error', (err) => {
        console.error('[Recorder] ffmpeg (no mouse) error:', err);
        console.warn('[Recorder] no-mouse recording failed, continuing with mouse recording only');
        noMouseFailed = true;
        this.ffmpegProcessNoMouse = null;
        tryResolveSuccess();
      });
    });
  }

  private onBothProcessesStarted(outputPath: string, outputPathNoMouse: string, startupTimeout: NodeJS.Timeout) {
    clearTimeout(startupTimeout);

    this.recordStartTime = new Date();
    this.currentRecording = {
      isRecording: true,
      duration: 0,
      startTime: this.recordStartTime.toISOString(),
      filePath: outputPath, // 有鼠标的视频（用于上传）
      filePathNoMouse: outputPathNoMouse, // 无鼠标的视频（本地保留）
      isStopping: false,
      stopComplete: false,
    };

    this.timeUpdateInterval = setInterval(() => {
      if (!this.recordStartTime) return;
      const elapsed = Math.floor((Date.now() - this.recordStartTime.getTime()) / 1000);
      this.currentRecording.duration = elapsed;
    }, 1000);

    // Start input listener with shared time base for accurate synchronization
    // Pass the same recordStartTime to ensure video and input events are aligned
    this.inputListener
      .startRecording(this.recordStartTime)
      .then(() => console.log('[Recorder] input listener started with shared time base'))
      .catch((e) => console.warn('[Recorder] input listener start failed (continuing):', e));
  }

  initiateStopRecording(): { initiated: boolean; filePath?: string } {
    if (!this.currentRecording.isRecording || this.currentRecording.isStopping) return { initiated: false };
    this.currentRecording.isStopping = true;
    this.currentRecording.stopComplete = false;
    const filePath = this.currentRecording.filePath;

    setImmediate(() => {
      this.performBackgroundStop().catch((e) => {
        console.error('[Recorder] background stop failed:', e);
      });
    });

    return { initiated: true, filePath };
  }

  getStopStatus(): { isStopping: boolean; stopComplete: boolean; filePath?: string } {
    return {
      isStopping: !!this.currentRecording.isStopping,
      stopComplete: !!this.currentRecording.stopComplete,
      filePath: this.currentRecording.filePath,
    };
  }

  private async performBackgroundStop(): Promise<void> {
    const videoPath = this.currentRecording.filePath;
    const videoPathNoMouse = this.currentRecording.filePathNoMouse;

    try {
      // 停止两个 ffmpeg 进程
      const stopPromises: Promise<void>[] = [];

      // 停止有鼠标的进程
      if (this.ffmpegProcess) {
        try {
          this.ffmpegProcess.stdin.write('q');
        } catch {}

        stopPromises.push(
          Promise.race([
            new Promise<void>((resolve) => {
              this.ffmpegProcess?.once('exit', () => resolve());
            }),
            new Promise<void>((_resolve, reject) => setTimeout(() => reject(new Error('ffmpeg (with mouse) stop timeout')), 10000)),
          ]).catch((e) => {
            console.warn('[Recorder] ffmpeg (with mouse) stop timeout, killing:', e);
            try {
              this.ffmpegProcess?.kill('SIGKILL');
            } catch {}
          })
        );
      }

      // 停止无鼠标的进程
      if (this.ffmpegProcessNoMouse) {
        try {
          this.ffmpegProcessNoMouse.stdin.write('q');
        } catch {}

        stopPromises.push(
          Promise.race([
            new Promise<void>((resolve) => {
              this.ffmpegProcessNoMouse?.once('exit', () => resolve());
            }),
            new Promise<void>((_resolve, reject) => setTimeout(() => reject(new Error('ffmpeg (no mouse) stop timeout')), 10000)),
          ]).catch((e) => {
            console.warn('[Recorder] ffmpeg (no mouse) stop timeout, killing:', e);
            try {
              this.ffmpegProcessNoMouse?.kill('SIGKILL');
            } catch {}
          })
        );
      }

      // 等待两个进程都停止
      await Promise.all(stopPromises);

      // Stop input recording
      const inputResult = this.inputListener.stopRecording(); // non-blocking flush strategy
      if (inputResult?.srtPath) {
        // Wait a bit for file flush (InputListener uses async close)
        await new Promise((r) => setTimeout(r, 1500));
      }

      // Attach encrypted SRT into MKV if possible (只附加到有鼠标的视频，因为这个是用于上传的)
      if (videoPath && inputResult?.srtPath && fs.existsSync(inputResult.srtPath)) {
        const srtStats = fs.statSync(inputResult.srtPath);
        if (srtStats.size > 0) {
          await this.attachEncryptedSrt(videoPath, inputResult.srtPath);
        }
      }

      console.log('[Recorder] Recording stopped. With mouse:', videoPath, '| No mouse:', videoPathNoMouse);

      this.cleanupAfterStop();
      this.emitStopComplete({ filePath: videoPath, success: true });
    } catch (err: any) {
      console.error('[Recorder] performBackgroundStop error:', err);
      this.cleanupAfterStop();
      this.emitStopComplete({
        filePath: videoPath,
        success: false,
        error: err?.message || 'Unknown error',
      });
    }
  }

  private cleanupAfterStop() {
    if (this.timeUpdateInterval) {
      clearInterval(this.timeUpdateInterval);
      this.timeUpdateInterval = null;
    }
    this.recordStartTime = null;
    this.ffmpegProcess = null;
    this.ffmpegProcessNoMouse = null;
    this.currentRecording = {
      isRecording: false,
      duration: 0,
      filePath: this.currentRecording.filePath,
      filePathNoMouse: this.currentRecording.filePathNoMouse,
      isStopping: false,
      stopComplete: true,
    };
  }

  private emitStopComplete(payload: RecordingStopCompletePayload) {
    BrowserWindow.getAllWindows().forEach((w) => {
      if (!w.isDestroyed()) w.webContents.send('recording-stop-complete', payload);
    });
  }

  private async attachEncryptedSrt(videoPath: string, srtPath: string): Promise<void> {
    const tempOutputPath = `${videoPath}.temp.mkv`;
    const filename = path.basename(srtPath);

    return await new Promise<void>((resolve, reject) => {
      const args = [
        '-y',
        '-i',
        videoPath,
        '-c',
        'copy',
        '-attach',
        srtPath,
        '-metadata:s:t:0',
        'mimetype=application/x-subrip',
        '-metadata:s:t:0',
        `filename=${filename}`,
        tempOutputPath,
      ];

      const proc = spawn(this.ffmpegPath, args, { stdio: ['ignore', 'pipe', 'pipe'] });
      proc.on('exit', (code) => {
        if (code !== 0) {
          try {
            if (fs.existsSync(tempOutputPath)) fs.unlinkSync(tempOutputPath);
          } catch {}
          return reject(new Error(`ffmpeg attach failed (code=${code})`));
        }
        try {
          fs.unlinkSync(videoPath);
          fs.renameSync(tempOutputPath, videoPath);
          // Delete original encrypted srt (now embedded)
          if (fs.existsSync(srtPath)) fs.unlinkSync(srtPath);
          resolve();
        } catch (e) {
          reject(e);
        }
      });
      proc.on('error', reject);
    });
  }
}




