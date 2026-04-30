/**
 * 共享 API 客户端
 * Desktop 和 Web 都可以使用
 */

import { getApiUrl } from '../../config/runtimeEnv';

/**
 * 通用 API 配置
 */
export const apiConfig = {
  getBaseUrl: () => getApiUrl(),
};

/**
 * 可选：自建网关 Bearer（与 api/core 一致）
 */
export { getOptionalApiBearerToken } from '@/services/apiAuth';

// 未来可以添加更多 API 客户端
// export * from './workflow';
// export * from './remote';
