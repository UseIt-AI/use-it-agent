import { readEnv } from '@/config/runtimeEnv';

/**
 * 可选网关鉴权（非 Supabase）。自建后端若需要 Bearer，在 .env 中设置 VITE_API_BEARER_TOKEN。
 * 本地化开源部署可不配置，请求将不带 Authorization，由后端自行决定是否鉴权。
 */
export function getOptionalApiBearerToken(): string | undefined {
  const t = readEnv('VITE_API_BEARER_TOKEN');
  return t && t.trim() ? t.trim() : undefined;
}

/** JSON 请求的 headers；仅在有 VITE_API_BEARER_TOKEN 时附加 Bearer */
export function buildJsonFetchHeaders(): Record<string, string> {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' };
  const token = getOptionalApiBearerToken();
  if (token) headers['Authorization'] = `Bearer ${token}`;
  return headers;
}
