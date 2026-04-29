/**
 * 电脑路由服务
 * 根据选择的电脑获取正确的 Local Engine URL
 * 
 * 重要：VM IP 可能会变化，提供两种获取方式：
 * 1. getLocalEngineUrl - 带缓存，适合非关键操作
 * 2. getLocalEngineUrlFresh - 强制刷新，适合执行命令前
 */

import { LOCAL_ENGINE_URL } from '../config/runtimeEnv';

// 缓存已解析的 URL
const urlCache = new Map<string, { url: string; ip: string; timestamp: number }>();
const CACHE_TTL = 10000; // 10 seconds (缩短缓存时间，更快检测 IP 变化)

// 存储 computerName -> vmName 的映射，避免重复查询配置
const vmNameCache = new Map<string, string>();

/**
 * 获取 VM 名称（从配置中）
 */
async function getVmName(computerName: string): Promise<string | null> {
  // 检查缓存
  if (vmNameCache.has(computerName)) {
    return vmNameCache.get(computerName) || null;
  }

  try {
    if (window.electron?.getAppConfig) {
      const config = await window.electron.getAppConfig();
      const envs = (config?.environments || []) as Array<{
        id: string;
        type: 'local' | 'vm';
        name: string;
        vmName?: string;
      }>;
      
      const env = envs.find(e => e.name === computerName);
      if (env?.type === 'vm' && env.vmName) {
        vmNameCache.set(computerName, env.vmName);
        return env.vmName;
      }
    }
  } catch (e) {
    console.error('[ComputerRouter] Failed to get VM name for', computerName, e);
  }
  
  return null;
}

/**
 * 直接获取 VM 的当前 IP（不使用缓存）
 */
async function getVmIpDirect(vmName: string): Promise<string | null> {
  try {
    if (window.electron?.getVmIp) {
      return await window.electron.getVmIp(vmName);
    }
  } catch (e) {
    console.error('[ComputerRouter] Failed to get VM IP:', e);
  }
  return null;
}

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

  // 获取 VM 名称
  const vmName = await getVmName(computerName);
  if (!vmName) {
    console.warn(`[ComputerRouter] No VM name found for ${computerName}, using default`);
    return LOCAL_ENGINE_URL;
  }

  // 直接获取最新 IP
  const ip = await getVmIpDirect(vmName);
  if (ip) {
    const url = `http://${ip}:8324`;
    
    // 检查 IP 是否变化
    const cached = urlCache.get(computerName);
    if (cached && cached.ip !== ip) {
      console.warn(`[ComputerRouter] ⚠️ VM IP changed: ${cached.ip} -> ${ip}`);
    }
    
    // 更新缓存
    urlCache.set(computerName, { url, ip, timestamp: Date.now() });
    console.log(`[ComputerRouter] Resolved ${computerName} -> ${url} (fresh)`);
    return url;
  }

  // 回退到默认 URL
  console.warn(`[ComputerRouter] Could not resolve ${computerName}, using default`);
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

