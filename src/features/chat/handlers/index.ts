/**
 * Command Handlers 统一导出
 * 
 * Handler 分类：
 * - localEngine/: 与 Local Engine 通信的所有 handler
 *   - router.ts: 事件路由入口
 *   - guiHandler.ts: GUI 操作（截图、鼠标、键盘等）
 *   - officeHandler.ts: Office COM 自动化（Word、Excel、PPT）
 * - eventHandler.ts: UI 事件处理（纯函数）
 * - persistenceHandler.ts: 数据持久化
 */

export * from './types';

// 事件处理器（UI 更新，纯函数）
export {
  processEvent,
  createEmptyAssistantMessage,
  hasRunningCard,
  getLastCuaCard
} from './eventHandler';

// Local Engine 通信（统一入口）
export {
  // 路由函数
  handleToolCall,
  handleClientRequest,
  isToolCallEvent,
  isGUIToolCall,
  isOfficeToolCall,
  isAskUserToolCall,
  // 类型
  type LocalEngineContext,
  type ExecutionResult,
  type ClientRequestEvent,
  type ToolCallEvent,
  type GUIToolCallEvent,
  type OfficeToolCallEvent,
  type AskUserToolCallEvent,
  type AskUserArgs,
  type AskUserKind,
  type AskUserOption,
  type AskUserResponse,
  type ToolCallTarget,
  type GUIActionName,
  type OfficeActionName,
  // 子模块（如需直接使用）
  guiHandler,
  officeHandler,
} from './localEngine';

// Ask-user / 用户交互回调
export { handleAskUserCall } from './userInteractionHandler';

// 持久化处理器
export {
  createPersistenceContext,
  handleEventPersistence,
  persistNodeStart,
  persistNodeEnd,
  persistCuaStepStart,
  persistCuaStepEnd,
  persistToolStart,
  persistToolEnd,
  type PersistenceContext,
} from './persistenceHandler';
