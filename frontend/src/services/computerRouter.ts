/**
 * 电脑路由服务
 * 根据选择的电脑获取正确的 Local Engine URL
 */

import { LOCAL_ENGINE_URL } from '../config/runtimeEnv';

// 缓存已解析的 URL
const urlCache = new Map<string, { url: string; ip: string; timestamp: number }>();
const CACHE_TTL = 10000; // 10 seconds (缩短缓存时间，更快检测 IP 变化)

/**
 * 获取指定电脑的 Local Engine URL（带缓存）
 * 适合非关键操作，如状态检查
 * @param computerName 电脑名称
 * @returns Local Engine URL
 */
export async function getLocalEngineUrl(computerName?: string): Promise<string> {
  // 如果没有指定电脑或是 This PC，返回默认 URL
  if (!computerName || computerName === 'This PC') {
    return LOCAL_ENGINE_URL;
  }

  // 检查缓存
  const cached = urlCache.get(computerName);
  if (cached && Date.now() - cached.timestamp < CACHE_TTL) {
    return cached.url;
  }

  // 获取新的 URL
  return getLocalEngineUrlFresh(computerName);
}

/**
 * 强制获取最新的 Local Engine URL（不使用缓存）
 * 适合执行命令前，确保 IP 是最新的
 * @param computerName 电脑名称
 * @returns Local Engine URL
 */
export async function getLocalEngineUrlFresh(computerName?: string): Promise<string> {
  // 如果没有指定电脑或是 This PC，返回默认 URL
  if (!computerName || computerName === 'This PC') {
    return LOCAL_ENGINE_URL;
  }

  console.warn(`[ComputerRouter] Named computer "${computerName}" has no dedicated resolver; using default Local Engine URL`);
  return LOCAL_ENGINE_URL;
}

/**
 * 验证 URL 是否仍然有效（健康检查）
 * @returns true 如果服务可达
 */
export async function validateLocalEngineUrl(url: string): Promise<boolean> {
  try {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 3000);
    
    const response = await fetch(`${url}/health`, {
      signal: controller.signal,
    });
    
    clearTimeout(timeout);
    return response.ok;
  } catch {
    return false;
  }
}

/**
 * 获取 URL 并验证，如果无效则刷新
 * 适合关键操作前使用
 */
export async function getValidLocalEngineUrl(computerName?: string): Promise<string> {
  // This PC 直接返回
  if (!computerName || computerName === 'This PC') {
    return LOCAL_ENGINE_URL;
  }

  // 先尝试缓存的 URL
  const cached = urlCache.get(computerName);
  if (cached && Date.now() - cached.timestamp < CACHE_TTL) {
    // 验证是否仍然有效
    const isValid = await validateLocalEngineUrl(cached.url);
    if (isValid) {
      return cached.url;
    }
    console.warn(`[ComputerRouter] Cached URL ${cached.url} is no longer valid, refreshing...`);
  }

  // 获取新的 URL
  const freshUrl = await getLocalEngineUrlFresh(computerName);
  
  // 验证新 URL
  const isValid = await validateLocalEngineUrl(freshUrl);
  if (!isValid) {
    console.error(`[ComputerRouter] Fresh URL ${freshUrl} is also not reachable`);
  }
  
  return freshUrl;
}

/**
 * 发送请求到指定电脑的 Local Engine
 * 使用 getValidLocalEngineUrl 确保 IP 是最新且可达的
 * @param computerName 电脑名称
 * @param path API 路径
 * @param options fetch 选项
 */
export async function fetchFromComputer(
  computerName: string | undefined,
  path: string,
  options?: RequestInit
): Promise<Response> {
  // 使用验证过的 URL，确保 IP 是最新的
  const baseUrl = await getValidLocalEngineUrl(computerName);
  const url = `${baseUrl}${path.startsWith('/') ? path : '/' + path}`;
  
  return fetch(url, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...options?.headers,
    },
  });
}

/**
 * 清除 URL 缓存
 */
export function clearUrlCache(computerName?: string): void {
  if (computerName) {
    urlCache.delete(computerName);
  } else {
    urlCache.clear();
  }
}

/**
 * 检查电脑的 Local Engine 是否在线
 */
export async function checkLocalEngineHealth(computerName?: string): Promise<boolean> {
  try {
    const response = await fetchFromComputer(computerName, '/health', {
      method: 'GET',
    });
    return response.ok;
  } catch {
    return false;
  }
}

// 导出类型
export type ComputerRouterOptions = {
  computerName?: string;
  timeout?: number;
};

