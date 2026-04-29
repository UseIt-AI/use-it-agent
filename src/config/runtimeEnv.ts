/**
 * 统一的运行时配置读取：
 * - Vite: 使用 import.meta.env.VITE_*
 * - （兼容）如果未来又在 Node/SSR 场景使用，也允许从 process.env 读取
 */
type AnyEnv = Record<string, any>;

function getProcessEnv(): AnyEnv | undefined {
  // eslint-disable-next-line no-undef
  if (typeof process !== 'undefined' && (process as any).env) {
    // eslint-disable-next-line no-undef
    return (process as any).env as AnyEnv;
  }
  return undefined;
}

function getViteEnv(): AnyEnv {
  // import.meta 在 TS 里是标准的（Vite 提供具体字段）
  return import.meta.env as AnyEnv;
}

export function readEnv(key: string): string | undefined {
  const viteEnv = getViteEnv();
  const v = viteEnv?.[key];
  if (typeof v === 'string' && v.trim()) return v;

  const p = getProcessEnv();
  const pv = p?.[key];
  if (typeof pv === 'string' && pv.trim()) return pv;

  return undefined;
}

/** 默认与 backend/env.example 的 BACKEND_PORT 对齐；部署/远程请用 .env 覆盖 VITE_API_URL */
export const API_URL = readEnv('VITE_API_URL') || 'http://127.0.0.1:8323';
/** 使用 127.0.0.1：Electron 打包后 Local Engine 仅监听 IPv4；Windows 上 localhost 常解析到 ::1 会导致 fetch 失败 */
export const LOCAL_ENGINE_URL = readEnv('VITE_LOCAL_ENGINE_URL') || 'http://127.0.0.1:8324';

/** 功能开关：远程控制功能是否可见（默认关闭） */
export const REMOTE_CONTROL_ENABLED = (() => {
  const raw = import.meta.env.VITE_ENABLE_REMOTE_CONTROL;
  if (raw === true || raw === false) return raw;
  const s = String(raw ?? '').trim().toLowerCase();
  return s === 'true' || s === '1' || s === 'yes';
})();

/**
 * 获取 API URL（函数形式，方便动态获取）
 */
export function getApiUrl(): string {
  return API_URL;
}

/**
 * 获取 Local Engine URL（函数形式）
 */
export function getLocalEngineUrl(): string {
  return LOCAL_ENGINE_URL;
}
