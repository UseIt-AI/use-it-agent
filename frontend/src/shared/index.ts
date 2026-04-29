/**
 * Shared 模块 - 共享代码入口
 * 
 * 包含 Desktop 和 Web 共用的：
 * - 组件 (components)
 * - Hooks (hooks)
 * - API 客户端 (api)
 * - 类型定义 (types)
 * - 工具函数 (utils)
 * 
 * 未来迁移到 Monorepo 时，这个目录会变成 @useit/shared 包
 */

// 重导出各模块
export * from './components';
export * from './hooks';
export * from './api';
export * from './types';
export * from './utils';
