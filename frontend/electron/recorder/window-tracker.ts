/**
 * Window Tracker - 使用 koffi 调用 Win32 API 获取当前活动窗口信息
 * 性能优化：直接调用 native API，单次调用约 0.1ms
 */

import koffi from 'koffi';

// Win32 类型定义 - 使用数值类型表示句柄
const HWND = 'uintptr_t';
const DWORD = 'uint32';
const HANDLE = 'uintptr_t';

// 加载 DLLs
const user32 = koffi.load('user32.dll');
const kernel32 = koffi.load('kernel32.dll');
const psapi = koffi.load('psapi.dll');

// Win32 API 函数声明
const GetForegroundWindow = user32.func('GetForegroundWindow', HWND, []);
const GetWindowTextLengthW = user32.func('GetWindowTextLengthW', 'int', [HWND]);
// 使用 buffer 类型接收字符串
const GetWindowTextW = user32.func('GetWindowTextW', 'int', [HWND, 'void *', 'int']);
// 使用指针接收 PID
const GetWindowThreadProcessId = user32.func('GetWindowThreadProcessId', DWORD, [HWND, 'uint32 *']);

const OpenProcess = kernel32.func('OpenProcess', HANDLE, [DWORD, 'bool', DWORD]);
const CloseHandle = kernel32.func('CloseHandle', 'bool', [HANDLE]);

// 使用 buffer 类型接收进程名
const GetModuleBaseNameW = psapi.func('GetModuleBaseNameW', DWORD, [HANDLE, HANDLE, 'void *', DWORD]);

// 常量
const PROCESS_QUERY_INFORMATION = 0x0400;
const PROCESS_VM_READ = 0x0010;

export interface ActiveWindowInfo {
  /** 窗口标题 */
  title: string;
  /** 进程名称 (如 chrome.exe) */
  processName: string;
  /** 进程 ID */
  processId: number;
  /** 窗口句柄数值 (用于比较是否同一窗口) */
  hwnd: number;
}

/**
 * 获取当前活动窗口信息
 * 性能：约 0.1-0.5ms 每次调用
 */
export function getActiveWindow(): ActiveWindowInfo | null {
  try {
    const hwnd = GetForegroundWindow() as number;
    if (!hwnd || hwnd === 0) {
      return null;
    }

    // 获取窗口标题
    let title = '';
    const titleLength = GetWindowTextLengthW(hwnd) as number;
    if (titleLength > 0) {
      // 分配 UTF-16 buffer (每个字符 2 字节)
      const titleBuffer = Buffer.alloc((titleLength + 1) * 2);
      const copied = GetWindowTextW(hwnd, titleBuffer, titleLength + 1) as number;
      if (copied > 0) {
        title = titleBuffer.toString('utf16le').replace(/\0+$/, '');
      }
    }

    // 获取进程 ID
    const pidBuffer = Buffer.alloc(4);
    GetWindowThreadProcessId(hwnd, pidBuffer);
    const processId = pidBuffer.readUInt32LE(0);

    // 获取进程名称
    let processName = '';
    if (processId > 0) {
      const hProcess = OpenProcess(PROCESS_QUERY_INFORMATION | PROCESS_VM_READ, false, processId) as number;
      if (hProcess && hProcess !== 0) {
        try {
          // MAX_PATH = 260, UTF-16 需要 520 字节
          const nameBuffer = Buffer.alloc(520);
          const nameLen = GetModuleBaseNameW(hProcess, 0, nameBuffer, 260) as number;
          if (nameLen > 0) {
            processName = nameBuffer.toString('utf16le', 0, nameLen * 2).replace(/\0+$/, '');
          }
        } finally {
          CloseHandle(hProcess);
        }
      }
    }

    return {
      title,
      processName,
      processId,
      hwnd,
    };
  } catch (e) {
    console.error('[WindowTracker] getActiveWindow error:', e);
    return null;
  }
}

/**
 * 窗口切换追踪器
 * 用于检测窗口切换并去重
 */
export class WindowSwitchTracker {
  private lastWindowInfo: ActiveWindowInfo | null = null;
  private lastCheckTime = 0;
  private throttleMs: number;

  /**
   * @param throttleMs 节流时间（毫秒），同一窗口在此时间内不重复检查
   */
  constructor(throttleMs = 50) {
    this.throttleMs = throttleMs;
  }

  /**
   * 检查是否发生了窗口切换
   * @returns 如果切换了窗口，返回新窗口信息；否则返回 null
   */
  checkSwitch(): { from: ActiveWindowInfo | null; to: ActiveWindowInfo } | null {
    const now = Date.now();
    
    // 节流：避免短时间内重复检查
    if (now - this.lastCheckTime < this.throttleMs) {
      return null;
    }
    this.lastCheckTime = now;

    const current = getActiveWindow();
    if (!current) {
      return null;
    }

    // 比较是否切换了窗口（使用进程名 + 窗口标题组合判断）
    const currentKey = `${current.processName}|${current.title}`;
    const lastKey = this.lastWindowInfo 
      ? `${this.lastWindowInfo.processName}|${this.lastWindowInfo.title}` 
      : '';

    if (currentKey !== lastKey) {
      const from = this.lastWindowInfo;
      this.lastWindowInfo = current;
      return { from, to: current };
    }

    return null;
  }

  /**
   * 获取当前追踪的窗口信息
   */
  getCurrentWindow(): ActiveWindowInfo | null {
    return this.lastWindowInfo;
  }

  /**
   * 重置追踪状态
   */
  reset(): void {
    this.lastWindowInfo = null;
    this.lastCheckTime = 0;
  }
}
