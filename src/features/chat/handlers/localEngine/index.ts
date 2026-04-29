/**
 * Local Engine Handler 模块
 * 
 * 统一导出所有与 Local Engine 通信相关的 handler
 * 
 * 模块结构：
 * - router.ts: 事件路由入口
 * - guiHandler.ts: GUI 操作（截图、鼠标、键盘等）
 * - officeHandler.ts: Office COM 自动化（Word、Excel、PPT）
 * - browserHandler.ts: Browser Use 浏览器自动化
 * - types.ts: 类型定义
 */

// 路由入口（主要导出）
export {
  handleToolCall,
  handleClientRequest,
  isToolCallEvent,
  isGUIToolCall,
  isOfficeToolCall,
  isBrowserToolCall,
  isAskUserToolCall,
} from './router';

// 类型定义
export type {
  LocalEngineContext,
  ExecutionResult,
  ClientRequestEvent,
  ToolCallEvent,
  GUIToolCallEvent,
  OfficeToolCallEvent,
  BrowserToolCallEvent,
  CodeToolCallEvent,
  AskUserToolCallEvent,
  AskUserArgs,
  AskUserKind,
  AskUserOption,
  AskUserResponse,
  ToolCallTarget,
  GUIActionName,
  OfficeActionName,
  BrowserActionName,
  CodeActionName,
} from './types';

// GUI Handler（如需直接使用）
export * as guiHandler from './guiHandler';

// Office Handler（如需直接使用）
export * as officeHandler from './officeHandler';

// Browser Handler（如需直接使用）
export * as browserHandler from './browserHandler';

// Code Handler（如需直接使用）
export * as codeHandler from './codeHandler';
