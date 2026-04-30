import { localEngineInstance } from "./core"

// ============================================================
//  Legacy
// ============================================================

export const execute_computer_use = async () => {
    const response = await localEngineInstance.post('/execute_computer_use', { actions: [{ type: 'screenshot' }] })
    return response.data;
}

// ============================================================
//  /api/v1/system/*  —— 机器环境感知
//  用途：每轮组装 agent 请求前聚合进 body.uia_data，
//  让 AI 在 prompt 里自动看到 "开了哪些窗口 / 装了什么软件"。
// ============================================================

// ---------- 原始响应类型（与 local-engine 对齐） ----------

interface EnvelopedResponse<T> {
  success: boolean;
  data: T;
}

interface WindowInfo {
  hwnd: number;
  title: string;
  class_name: string;
  pid: number;
  process_name: string;
  exe: string;
  is_visible: boolean;
  is_minimized: boolean;
  is_foreground: boolean;
  rect: { x: number; y: number; width: number; height: number };
}

interface ProcessInfo {
  pid: number;
  name: string;
  exe: string;
  username?: string;
  create_time?: number;
  cpu_percent?: number;
  memory_mb?: number;
}

interface InstalledApp {
  name: string;
  publisher?: string;
  version?: string;
  install_location?: string;
  exe_path?: string;
  source?: string;
}

// ---------- 单端点封装（带超时 + 容错） ----------

const SYSTEM_CALL_TIMEOUT_MS = 1000;
const SLOW_CALL_TIMEOUT_MS = 2500; // 注册表扫描类

async function safeGet<T>(
  path: string,
  params?: Record<string, any>,
  timeoutMs: number = SYSTEM_CALL_TIMEOUT_MS,
): Promise<T | null> {
  try {
    const res = await localEngineInstance.get<EnvelopedResponse<T>>(path, {
      params,
      timeout: timeoutMs,
    });
    if (res.data?.success && res.data?.data) {
      return res.data.data;
    }
    return null;
  } catch {
    // local engine 未运行 / 超时 / 500 —— 一律静默，不影响主流程
    return null;
  }
}

export async function listWindows(opts?: {
  process_name?: string;
  title_contains?: string;
  include_minimized?: boolean;
}) {
  return safeGet<{ success: boolean; windows: WindowInfo[]; count: number }>(
    '/api/v1/system/windows',
    opts,
  );
}

export async function getForegroundWindow() {
  // 注意：返回的 window 对象里没有 is_foreground 字段（定义上它就是前台），
  // 其余字段与 /system/windows 一致（少了 is_foreground 标记）
  return safeGet<{ success: boolean; window: Omit<WindowInfo, 'is_foreground' | 'is_visible'> | null }>(
    '/api/v1/system/foreground-window',
  );
}

export async function listProcesses(opts?: {
  name_contains?: string;
  include_system?: boolean;
  include_metrics?: boolean;
}) {
  return safeGet<{ success: boolean; processes: ProcessInfo[]; count: number }>(
    '/api/v1/system/processes',
    opts,
  );
}

export async function listInstalledSoftware(opts?: { name_contains?: string }) {
  // 注意：local-engine 这里的数组字段叫 `software`（不是 `apps`）；
  // 扫注册表 + 多来源合并，首次可能要 1-2s，所以走 slow-timeout
  return safeGet<{ success: boolean; software: InstalledApp[]; count: number }>(
    '/api/v1/system/installed-software',
    opts,
    SLOW_CALL_TIMEOUT_MS,
  );
}

// ---------- 聚合：collectMachineContext ----------
//
// 返回形如：
//   {
//     windows: [{title, process_name, is_foreground}, ...],  // 约定 key（agent 会专门渲染）
//     active_window: "xxx - PowerPoint",                      // 约定 key
//     running_apps: "预格式化 markdown（已按窗口聚合）",       // 自由 key（agent auto render）
//     installed_apps: "预格式化 markdown（10 分钟缓存）"       // 自由 key
//   }
//
// agent 侧 agent_loop._build_planning_message() 会把：
//   - windows + active_window 渲染为 "### Desktop Windows"
//   - 其他任意 key 渲染为 "### <key>\n<value>"（上限 5 个 key / 2000 字符）
// 所以把 running_apps / installed_apps 预先格式化成字符串，token 最省。

const MAX_WINDOWS = 40;
const MAX_APP_PROCESSES = 15;
const MAX_INSTALLED_APPS = 60;
const MAX_TITLE_LEN = 80; // 长窗口标题截断，控制每行宽度

// 系统级、用户不关心的进程一律过滤（不出现在 open_windows.background 里）
// —— 对 AI 有价值的只有"用户可见/用户自己启动的应用"
const UNINTERESTING_PROCS = new Set([
  // Windows 壳与桌面
  'explorer.exe', 'SearchHost.exe', 'StartMenuExperienceHost.exe',
  'TextInputHost.exe', 'ShellExperienceHost.exe', 'ApplicationFrameHost.exe',
  'RuntimeBroker.exe', 'SystemSettings.exe', 'sihost.exe', 'ctfmon.exe',
  'taskhostw.exe', 'conhost.exe', 'dllhost.exe',
  // IME / 驱动杂项
  'audiodg.exe', 'spoolsv.exe',
]);

function truncTitle(t: string): string {
  if (!t) return '';
  return t.length > MAX_TITLE_LEN ? t.slice(0, MAX_TITLE_LEN - 1) + '…' : t;
}

interface InstalledAppCache {
  at: number;
  text: string;
}
let installedAppsCache: InstalledAppCache | null = null;
const INSTALLED_APPS_TTL_MS = 10 * 60 * 1000;

/**
 * 把所有顶级窗口 + 后台应用格式化为 AI 可直接消费的 markdown。
 *
 * 每个窗口一行，包含 hwnd / pid / process / title / state。AI 后续如果要做
 * "切换到某窗口 / 关闭某窗口 / 激活某 pptx"这类操作，可以直接引用 hwnd。
 *
 * 格式样例:
 *   - [hwnd=11340742 pid=1234 POWERPNT.EXE] "Slide1.pptx - PowerPoint" (foreground)
 *   - [hwnd=11340744 pid=1234 POWERPNT.EXE] "Slide2.pptx - PowerPoint" (minimized)
 *   - [hwnd=87654321 pid=5678 chrome.exe]   "GitHub - Google Chrome"
 *
 *   _Background (no visible window)_:
 *   - Spotify.exe (pid 9999)
 *   - ...
 */
function formatOpenWindows(
  windows: WindowInfo[],
  processes: ProcessInfo[],
): string {
  const lines: string[] = [];

  const shown = windows.slice(0, MAX_WINDOWS);
  // 把 foreground 排第一位，之后按进程名排序，方便同一 app 的多窗口连在一起
  shown.sort((a, b) => {
    if (a.is_foreground !== b.is_foreground) return a.is_foreground ? -1 : 1;
    const an = (a.process_name || '').toLowerCase();
    const bn = (b.process_name || '').toLowerCase();
    if (an !== bn) return an < bn ? -1 : 1;
    return (a.title || '').localeCompare(b.title || '');
  });

  for (const w of shown) {
    if (!w.title) continue;
    const states: string[] = [];
    if (w.is_foreground) states.push('foreground');
    if (w.is_minimized) states.push('minimized');
    const stateSuffix = states.length ? ` (${states.join(', ')})` : '';
    const proc = w.process_name || 'unknown';
    lines.push(
      `- [hwnd=${w.hwnd} pid=${w.pid} ${proc}] "${truncTitle(w.title)}"${stateSuffix}`,
    );
  }

  if (windows.length > MAX_WINDOWS) {
    lines.push(`- ...(+${windows.length - MAX_WINDOWS} more windows truncated)`);
  }

  // 后台进程：给 AI 感知"托盘里开了什么"，没有 hwnd
  // 过滤规则：
  // 1) 空名字直接丢
  // 2) 已经有窗口的进程（含同名同 app 不同 pid 的子进程）不重复列
  // 3) 系统噪音进程不列
  // 4) 同 name 只保留一份（chrome / msedge 大量渲染进程去重）
  const pidsWithWindow = new Set(windows.map(w => w.pid));
  const namesWithWindow = new Set(
    windows.map(w => (w.process_name || '').toLowerCase()).filter(Boolean),
  );
  const seenBgNames = new Set<string>();
  const bgProcs: ProcessInfo[] = [];
  for (const p of processes) {
    const nm = (p.name || '').trim();
    if (!nm) continue;
    if (pidsWithWindow.has(p.pid)) continue;
    if (namesWithWindow.has(nm.toLowerCase())) continue;
    if (UNINTERESTING_PROCS.has(nm)) continue;
    if (seenBgNames.has(nm.toLowerCase())) continue;
    seenBgNames.add(nm.toLowerCase());
    bgProcs.push(p);
    if (bgProcs.length >= MAX_APP_PROCESSES) break;
  }

  if (bgProcs.length > 0) {
    lines.push('', '_Background (no visible window)_:');
    for (const p of bgProcs) {
      lines.push(`- ${p.name} (pid ${p.pid})`);
    }
  }

  return lines.length ? lines.join('\n') : '(none)';
}

function formatInstalledApps(apps: InstalledApp[]): string {
  const names = apps
    .map(a => a.name)
    .filter(Boolean)
    .slice(0, MAX_INSTALLED_APPS);
  return names.length ? names.map(n => `- ${n}`).join('\n') : '(none)';
}

async function loadInstalledAppsText(): Promise<string | null> {
  const now = Date.now();
  if (installedAppsCache && now - installedAppsCache.at < INSTALLED_APPS_TTL_MS) {
    return installedAppsCache.text;
  }
  const result = await listInstalledSoftware();
  if (!result) return null;
  const apps = result.software ?? [];
  const text = formatInstalledApps(apps);
  // 只缓存"真有东西"的结果：失败/空列表不落盘，下次继续尝试
  if (apps.length > 0) {
    installedAppsCache = { at: now, text };
  }
  return text;
}

export interface MachineContext {
  /** 前台窗口标题，agent 渲染为 "Active window: ..." */
  active_window?: string;
  /**
   * 所有顶级窗口 + 后台进程的 markdown 清单。
   * 每行带 `hwnd=... pid=... <process>` 前缀，AI 可以按 hwnd 做后续窗口操作。
   */
  open_windows?: string;
  /** 已安装软件名列表 markdown，前端 10 分钟缓存 */
  installed_apps?: string;
}

/**
 * 并发采集本机 /system/* 上下文，整合成 agent 的 `uia_data` 结构。
 *
 * - 任一调用失败/超时 → 对应字段缺省，主流程不受影响
 * - installed_apps 做 10 分钟本地缓存，避免每轮都走注册表扫描
 * - 只裁后不发全量，避免把 prompt 撑爆
 */
export async function collectMachineContext(): Promise<MachineContext> {
  const [windowsRes, fgRes, processesRes, installedText] = await Promise.all([
    listWindows({ include_minimized: true }),
    // 单独打一枪前台窗口：/system/windows 在切焦点瞬间可能一个都不标 is_foreground，
    // 这里用独立端点兜底，以 Electron 聚焦时也能稳定拿到 active_window
    getForegroundWindow(),
    listProcesses({ include_system: false, include_metrics: false }),
    loadInstalledAppsText(),
  ]);

  const ctx: MachineContext = {};

  const windows = windowsRes?.windows ?? [];
  const procs = processesRes?.processes ?? [];

  // 前台窗口兜底链：独立端点 → windows[].is_foreground → windows[0]（最后一次机会）
  const fgTitle = fgRes?.window?.title
    ?? windows.find(w => w.is_foreground)?.title
    ?? '';
  if (fgTitle) {
    ctx.active_window = fgTitle;
  }

  // 如果独立端点拿到了前台窗口，但 windows[] 里没有一条 is_foreground，
  // 说明 list_windows 那一瞬间漏掉了前台标记。手动矫正一下，让渲染结果带上 "(foreground)"。
  if (fgRes?.window && !windows.some(w => w.is_foreground)) {
    const fgHwnd = fgRes.window.hwnd;
    const match = windows.find(w => w.hwnd === fgHwnd);
    if (match) match.is_foreground = true;
  }

  if (windows.length > 0 || procs.length > 0) {
    ctx.open_windows = formatOpenWindows(windows, procs);
  }

  if (installedText) {
    ctx.installed_apps = installedText;
  }

  return ctx;
}

// ============================================================
//  写动作：/api/v1/system/activate-window  /  /system/launch-app
//  专门给 AI 的 app_action handler 调用
// ============================================================

export interface ActivateWindowResult {
  success: boolean;
  hwnd?: number;
  pid?: number;
  title?: string;
  is_foreground?: boolean;
  warning?: string | null;
  error?: string;
  /** 多窗口命中时返回的候选列表，AI 可挑一个再用 hwnd 重试 */
  candidates?: Array<{
    hwnd: number;
    title: string;
    process_name: string;
    is_minimized?: boolean;
  }>;
  criteria?: { process_name?: string; title_contains?: string };
}

export interface LaunchAppResult {
  success: boolean;
  pid?: number;
  exe?: string;
  file?: string;
  launched_via?: string;
  matched_software?: string;
  note?: string;
  error?: string;
}

/** 通用：POST 到 local-engine，不抛异常，把业务态展开成 result */
async function safePost<T extends { success: boolean; error?: string }>(
  path: string,
  body: Record<string, any>,
  timeoutMs: number = 5000,
): Promise<T> {
  try {
    const res = await localEngineInstance.post<EnvelopedResponse<T>>(path, body, {
      timeout: timeoutMs,
    });
    const data = res.data?.data;
    if (data) return data;
    return { success: false, error: 'empty response from local-engine' } as T;
  } catch (err: any) {
    const detail = err?.response?.data?.detail;
    return {
      success: false,
      error: detail || err?.message || String(err),
    } as T;
  }
}

/**
 * 把指定窗口切到前台。至少提供一个定位字段:
 * - hwnd: 最精确，推荐从 prompt 里的 open_windows 抄过来
 * - process_name: 如 "POWERPNT.EXE"（大小写不敏感）
 * - title_contains: 窗口标题子串
 *
 * 多窗口命中时 result.candidates 会有列表，AI 可再用具体 hwnd 重试。
 */
export async function activateWindow(params: {
  hwnd?: number;
  process_name?: string;
  title_contains?: string;
}): Promise<ActivateWindowResult> {
  return safePost<ActivateWindowResult>('/api/v1/system/activate-window', params, 3000);
}

/**
 * 启动软件 / 打开文件。至少提供 name / file / exe_path 之一:
 * - name: 按 installed_apps 模糊匹配（如 "PowerPoint"）
 * - file: 用系统关联程序打开文件
 * - exe_path: 精确 exe 路径
 * 组合: {name, file} => 用指定程序打开文件
 */
export async function launchApp(params: {
  name?: string;
  file?: string;
  exe_path?: string;
  args?: string[];
  cwd?: string;
}): Promise<LaunchAppResult> {
  return safePost<LaunchAppResult>('/api/v1/system/launch-app', params, 5000);
}

// ============================================================
//  统一 dispatch：给 AI tool 层用
//  /api/v1/system/window-control  /  /api/v1/system/process-control
//  一个端点 = 一个 AI tool，action 字段分发
// ============================================================

/** window_control 通用响应（不同 action 返回的 data 形状不一样，这里放宽类型） */
export interface WindowControlResult {
  success: boolean;
  error?: string;
  warning?: string | null;
  /** action 名（后端回填） */
  action?: string;
  /** 操作后的窗口信息 */
  window?: {
    hwnd: number;
    title?: string;
    pid?: number;
    is_minimized?: boolean;
    is_maximized?: boolean;
    is_topmost?: boolean;
    rect?: { x: number; y: number; width: number; height: number };
  };
  /** list 动作返回 */
  windows?: Array<Record<string, any>>;
  /** list_monitors 动作返回 */
  monitors?: Array<{
    id: number;
    is_primary: boolean;
    device?: string;
    bounds: { x: number; y: number; width: number; height: number };
    work_area: { x: number; y: number; width: number; height: number };
  }>;
  /** tile 动作返回 */
  placed?: Array<{
    hwnd: number;
    title?: string;
    rect: { x: number; y: number; width: number; height: number };
    /** 请求的目标尺寸（为便于 AI 对比）*/
    target_rect?: { x: number; y: number; width: number; height: number };
    /** 实际尺寸与目标差距超过阈值（窗口有 minWidth 限制或 DPI 缩放）*/
    size_mismatch?: boolean;
  }>;
  skipped?: Array<{ hwnd: number | string; reason: string }>;
  errors?: Array<{
    hwnd: number;
    target_rect?: { x: number; y: number; width: number; height: number };
    error: string;
  }>;
  /** activate/close/set_topmost 可能带 */
  hwnd?: number;
  pid?: number;
  title?: string;
  is_foreground?: boolean;
  /** 多窗口命中时的候选 */
  candidates?: Array<{
    hwnd: number;
    title: string;
    process_name: string;
    is_minimized?: boolean;
  }>;
  criteria?: { process_name?: string; title_contains?: string };
  /** capture 动作返回 */
  scope?: 'window' | 'monitor' | 'all_screens';
  /** capture: base64-encoded image */
  image_data?: string;
  compressed_size_kb?: number;
  compressed?: boolean;
  /** capture 的元信息：hwnd / title / monitor_id / virtual_desktop 之一 */
  context?: Record<string, any>;
  /** 其它字段放宽 */
  [key: string]: any;
}

/**
 * 窗口操作统一入口。参数形如 {action: "minimize", hwnd: 12345}。
 * 支持的 action 见后端 WindowControlRequest 注释。
 */
export async function windowControl(params: {
  action: string;
  hwnd?: number;
  process_name?: string;
  title_contains?: string;
  include_minimized?: boolean;
  on?: boolean;
  x?: number;
  y?: number;
  width?: number;
  height?: number;
  hwnds?: number[];
  layout?: string;
  monitor_id?: number;
  /** tile 非对称比例。均分 layout 长度 == hwnds；main_* 长度 == 2。例 [4, 1] = 80/20。 */
  ratios?: number[];
  /**
   * tile 完全自定义矩形。每项 {x,y,width,height} 均为 0~1 的工作区比例。
   * 传了 zones 会忽略 layout / ratios。
   */
  zones?: Array<{ x: number; y: number; width: number; height: number }>;
  force?: boolean;
  /** capture 专用：截图范围 */
  scope?: 'window' | 'monitor' | 'all_screens';
  /** capture scope=window 可选：强制 PrintWindow 路径 */
  prefer_printwindow?: boolean;
  /** capture 可选：是否压缩（默认 true） */
  compress?: boolean;
}): Promise<WindowControlResult> {
  // capture 可能返回大 base64，超时适度放宽
  const timeout = params.action === 'capture' ? 15000 : 5000;
  return safePost<WindowControlResult>('/api/v1/system/window-control', params, timeout);
}

/** process_control 响应（根据 action 返回不同 data 形状） */
export interface ProcessControlResult {
  success: boolean;
  error?: string;
  /** launch 动作返回 */
  pid?: number;
  exe?: string;
  file?: string;
  launched_via?: string;
  matched_software?: string;
  note?: string;
  /** find_exe 返回 */
  candidates?: Array<{ name: string; exe_path: string; version?: string; source?: string }>;
  /** list_installed 返回 */
  software?: Array<Record<string, any>>;
  /** list_processes 返回 */
  processes?: Array<Record<string, any>>;
  [key: string]: any;
}

/** 进程/软件操作统一入口 */
export async function processControl(params: {
  action: string;
  name?: string;
  file?: string;
  exe_path?: string;
  args?: string[];
  cwd?: string;
  name_contains?: string;
  include_system?: boolean;
  include_metrics?: boolean;
  pid?: number;
}): Promise<ProcessControlResult> {
  return safePost<ProcessControlResult>('/api/v1/system/process-control', params, 5000);
}
