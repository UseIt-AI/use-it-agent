/**
 * Logger 工具模块 - 基于 debug 库的命名空间日志系统
 * 
 * 使用方法：
 * 1. 在代码中引入对应的 logger：import { logSSE, logUI } from '@/utils/logger';
 * 2. 使用 logger：logSSE('收到事件', eventType);
 * 
 * 控制显示：
 * - 在浏览器控制台中输入：localStorage.debug = 'app:sse'  (只看 SSE 相关)
 * - 查看所有模块：localStorage.debug = 'app:*'
 * - 只看性能日志：localStorage.debug = 'app:perf'
 * - 关闭所有：localStorage.debug = ''
 * - 设置后刷新页面即可生效
 * 
 * 命名空间列表：
 * - app:perf    - 性能相关日志（SSE 延迟、回调耗时等）
 * - app:sse     - SSE 流式事件
 * - app:ui      - UI 渲染相关
 * - app:router  - Local Engine 路由
 * - app:handler - 事件处理器
 * - app:persist - Supabase 持久化（消息保存、认证等）
 */

import Debug from 'debug';

// ==================== 开发环境自动启用性能日志 ====================
// debug 库需要在模块加载前设置 localStorage.debug
// 所以这段代码必须在创建 Debug 实例之前执行
if (typeof window !== 'undefined' && import.meta.env.DEV) {
  // 开发环境默认启用性能日志（如果用户没有设置过）
  const currentDebug = localStorage.getItem('debug');
  if (!currentDebug) {
    localStorage.setItem('debug', 'app:perf');
    // 通知 debug 库重新读取配置
    Debug.enable('app:perf');
  } else {
    // 确保 debug 库使用当前配置
    Debug.enable(currentDebug);
  }
}

// ==================== 性能日志（关键路径） ====================
export const logPerf = Debug('app:perf');

// ==================== SSE 流式事件 ====================
export const logSSE = Debug('app:sse');

// ==================== UI 渲染 ====================
export const logUI = Debug('app:ui');

// ==================== Local Engine 路由 ====================
export const logRouter = Debug('app:router');

// ==================== 事件处理器 ====================
export const logHandler = Debug('app:handler');

// ==================== 截图相关 ====================
export const logScreenshot = Debug('app:screenshot');

// ==================== 持久化（Supabase） ====================
export const logPersist = Debug('app:persist');

// ==================== 辅助函数 ====================

/**
 * 格式化耗时（毫秒）
 */
export function formatDuration(ms: number): string {
  if (ms < 1000) {
    return `${ms.toFixed(0)}ms`;
  }
  return `${(ms / 1000).toFixed(2)}s`;
}

/**
 * 创建性能计时器
 * 用于精确测量代码段执行时间
 */
export function createPerfTimer(label: string) {
  const startTime = performance.now();
  const startDate = new Date().toISOString();
  
  logPerf(`⏱️ [${label}] 开始 @ ${startDate}`);
  
  return {
    /**
     * 记录中间点
     */
    checkpoint: (message: string) => {
      const elapsed = performance.now() - startTime;
      const timestamp = new Date().toISOString();
      logPerf(`📍 [${timestamp}] [${label}] ${message} [耗时: ${formatDuration(elapsed)}]`);
    },
    
    /**
     * 结束计时
     */
    end: (message?: string) => {
      const elapsed = performance.now() - startTime;
      const endMessage = message || '完成';
      const timestamp = new Date().toISOString();
      logPerf(`✅ [${timestamp}] [${label}] ${endMessage} [总耗时: ${formatDuration(elapsed)}]`);
      return elapsed;
    },
    
    /**
     * 获取已过时间（不打印日志）
     */
    elapsed: () => performance.now() - startTime,
  };
}

/**
 * 获取格式化的时间戳（精确到毫秒）
 * 格式：HH:mm:ss.SSS
 */
function getTimestamp(): string {
  const now = new Date();
  const hours = now.getUTCHours().toString().padStart(2, '0');
  const minutes = now.getUTCMinutes().toString().padStart(2, '0');
  const seconds = now.getUTCSeconds().toString().padStart(2, '0');
  const ms = now.getUTCMilliseconds().toString().padStart(3, '0');
  return `${hours}:${minutes}:${seconds}.${ms}`;
}

/**
 * 获取完整的 ISO 时间戳
 */
function getFullTimestamp(): string {
  return new Date().toISOString();
}

/**
 * 创建请求生命周期追踪器
 * 用于详细追踪一个请求从前端收到事件到回调完成的全过程
 */
export function createRequestTracker(requestType: string, requestId: string) {
  const startTime = performance.now();
  let lastCheckpoint = startTime;
  
  const log = (emoji: string, stage: string, extra?: string) => {
    const totalElapsed = performance.now() - startTime;
    const sinceLastCheckpoint = performance.now() - lastCheckpoint;
    lastCheckpoint = performance.now();
    
    const timestamp = getTimestamp();
    const extraStr = extra ? ` | ${extra}` : '';
    logPerf(
      `${emoji} [${timestamp}] [${requestType}:${requestId.slice(0, 8)}] ${stage} ` +
      `[T+${formatDuration(totalElapsed)}] [Δ${formatDuration(sinceLastCheckpoint)}]${extraStr}`
    );
  };
  
  return {
    /** 1. 收到事件 */
    eventReceived: (eventType: string) => {
      log('📥', `收到事件 (${eventType})`);
    },
    
    /** 2. 开始处理（解析参数等） */
    startProcessing: () => {
      log('🔄', '开始处理');
    },
    
    /** 3. 发起 Local Engine 请求 */
    localEngineRequestStart: (endpoint: string) => {
      log('📤', `发起 Local Engine 请求`, `endpoint: ${endpoint}`);
    },
    
    /** 4. Local Engine 返回 */
    localEngineRequestEnd: (success: boolean, dataSize?: string) => {
      const status = success ? '成功' : '失败';
      const sizeStr = dataSize ? `, size: ${dataSize}` : '';
      log('📥', `Local Engine 返回 (${status}${sizeStr})`);
    },
    
    /** 5. 开始发送回调 */
    callbackStart: () => {
      log('📤', '发送回调给后端');
    },
    
    /** 6. 回调完成 */
    callbackEnd: (success: boolean) => {
      const status = success ? '成功' : '失败';
      log('✅', `回调完成 (${status})`);
    },
    
    /** 自定义检查点 */
    checkpoint: (message: string) => {
      log('📍', message);
    },
    
    /** 获取总耗时 */
    totalElapsed: () => performance.now() - startTime,
  };
}

// 导出时间戳函数供其他模块使用
export { getTimestamp, getFullTimestamp };

// ==================== 调试提示 ====================
// 如需切换日志级别，在浏览器控制台执行：
//   localStorage.debug = 'app:*'     // 查看所有日志
//   localStorage.debug = 'app:perf'  // 只看性能日志
//   localStorage.debug = ''          // 关闭所有
// 然后刷新页面
