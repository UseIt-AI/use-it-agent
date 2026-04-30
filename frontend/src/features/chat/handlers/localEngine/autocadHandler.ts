/**
 * AutoCAD Handler - AutoCAD V2 COM 自动化处理
 *
 * 处理 AutoCAD 图纸的 COM 自动化操作。
 *
 * 支持的动作：
 * - launch: 启动或连接 AutoCAD（不打开/新建文档）
 * - draw_from_json: 绘制 JSON 结构化数据（线、圆、弧、多段线、文字、标注）
 * - execute_python_com: 执行 Python COM 代码
 * - snapshot: 获取图纸快照
 * - open/close/new/activate: 图纸管理
 * - standard_parts: 标准件操作
 *
 * 调用 Local Engine API:
 * - POST /api/v1/autocad/v2/launch
 * - POST /api/v1/autocad/v2/step
 * - GET/POST /api/v1/autocad/v2/snapshot
 * - POST /api/v1/autocad/v2/open
 * - POST /api/v1/autocad/v2/close
 * - POST /api/v1/autocad/v2/new
 * - POST /api/v1/autocad/v2/activate
 * - GET /api/v1/autocad/v2/status
 * - GET /api/v1/autocad/v2/standard_parts
 * - POST /api/v1/autocad/v2/standard_parts/{type}/draw
 */

import { ExecutionResult } from './types';
import { Message } from '../types';
import { logRouter, logHandler } from '@/utils/logger';

// API 前缀
const API_PREFIX = '/api/v1/autocad/v2';

// ==================== 通用执行函数 ====================

/**
 * 执行 AutoCAD step 动作
 *
 * @param currentUrl Local Engine URL
 * @param action 动作类型 (draw_from_json | execute_python_com)
 * @param payload 动作参数
 * @param timeout 超时时间
 * @param returnScreenshot 是否返回截图
 * @param setMessages 更新消息的函数
 * @param botMessageId 当前 bot 消息 ID
 * @returns 执行结果
 */
async function executeAutoCADStep(
  currentUrl: string,
  action: 'draw_from_json' | 'execute_python_com',
  payload: Record<string, any>,
  timeout: number,
  returnScreenshot: boolean,
  setMessages: React.Dispatch<React.SetStateAction<Message[]>>,
  botMessageId: string
): Promise<ExecutionResult> {
  logRouter('autocad step: action=%s, timeout=%d', action, timeout);

  try {
    const requestBody: Record<string, any> = {
      action,
      timeout,
      return_screenshot: returnScreenshot,
      ...payload,
    };

    const url = `${currentUrl}${API_PREFIX}/step`;
    console.log('[autocad_step] POST:', url);
    console.log('[autocad_step] requestBody:', requestBody);
    logHandler('[autocad_step] POST %s', url);
    logHandler('[autocad_step] requestBody: %O', requestBody);

    const response = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(requestBody),
    });

    if (!response.ok) {
      const errMsg = `AutoCAD API error: ${response.status} ${response.statusText}`;
      logHandler('[autocad_step] response ERROR: %s', errMsg);
      throw new Error(errMsg);
    }

    const result = await response.json();
    console.log('[autocad_step] response:', {
      success: result.success,
      hasScreenshot: !!result.data?.screenshot,
      hasError: !!result.error,
    });
    logHandler(
      '[autocad_step] response: success=%s, hasScreenshot=%s, hasError=%s',
      result.success,
      !!result.data?.screenshot,
      !!result.error
    );

    // 如果有截图，更新到消息中
    if (result.data?.screenshot) {
      setMessages((prev) =>
        prev.map((msg) => {
          if (msg.id !== botMessageId) return msg;
          const screenshots = msg.screenshots || [];
          return {
            ...msg,
            screenshots: [...screenshots, result.data.screenshot],
          };
        })
      );
      logHandler('[autocad_step] screenshot captured');
    }

    return {
      success: result.success !== false,
      data: result.data || result,
      error: result.error,
    };
  } catch (error: any) {
    logHandler('[autocad_step] FAILED: %s', error.message);
    console.error('[AutoCADHandler] step failed:', error);
    return {
      success: false,
      data: null,
      error: error.message,
    };
  }
}

/**
 * 获取 AutoCAD 快照
 *
 * @param currentUrl Local Engine URL
 * @param options 快照选项
 * @param setMessages 更新消息的函数
 * @param botMessageId 当前 bot 消息 ID
 * @returns 执行结果
 */
async function getAutoCADSnapshot(
  currentUrl: string,
  options: {
    include_content?: boolean;
    include_screenshot?: boolean;
    only_visible?: boolean;
    max_entities?: number;
  },
  setMessages: React.Dispatch<React.SetStateAction<Message[]>>,
  botMessageId: string
): Promise<ExecutionResult> {
  logHandler('[autocad_snapshot] options: %O', options);

  try {
    const url = `${currentUrl}${API_PREFIX}/snapshot`;
    console.log('[autocad_snapshot] POST:', url);
    logHandler('[autocad_snapshot] POST %s', url);

    const response = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(options),
    });

    if (!response.ok) {
      const errMsg = `AutoCAD snapshot API error: ${response.status} ${response.statusText}`;
      logHandler('[autocad_snapshot] response ERROR: %s', errMsg);
      throw new Error(errMsg);
    }

    const result = await response.json();
    console.log('[autocad_snapshot] response:', {
      success: result.success,
      hasScreenshot: !!result.data?.screenshot,
      hasContent: !!result.data?.content,
    });
    logHandler(
      '[autocad_snapshot] response: success=%s, hasScreenshot=%s, hasContent=%s',
      result.success,
      !!result.data?.screenshot,
      !!result.data?.content
    );

    // 如果有截图，更新到消息中
    if (result.data?.screenshot) {
      setMessages((prev) =>
        prev.map((msg) => {
          if (msg.id !== botMessageId) return msg;
          const screenshots = msg.screenshots || [];
          return {
            ...msg,
            screenshots: [...screenshots, result.data.screenshot],
          };
        })
      );
      logHandler('[autocad_snapshot] screenshot captured');
    }

    return {
      success: result.success !== false,
      data: result.data || result,
      error: result.error,
    };
  } catch (error: any) {
    logHandler('[autocad_snapshot] FAILED: %s', error.message);
    console.error('[AutoCADHandler] snapshot failed:', error);
    return {
      success: false,
      data: null,
      error: error.message,
    };
  }
}

/**
 * 执行 AutoCAD 图纸管理操作
 *
 * @param currentUrl Local Engine URL
 * @param operation 操作类型 (open | close | new | activate | status)
 * @param params 操作参数
 * @returns 执行结果
 */
async function executeAutoCADDocumentOperation(
  currentUrl: string,
  operation: 'launch' | 'open' | 'close' | 'new' | 'activate' | 'status',
  params?: Record<string, any>
): Promise<ExecutionResult> {
  logHandler('[autocad_%s] params: %O', operation, params);

  try {
    const url = `${currentUrl}${API_PREFIX}/${operation}`;
    const method = operation === 'status' ? 'GET' : 'POST';

    console.log(`[autocad_${operation}] ${method}:`, url);
    logHandler('[autocad_%s] %s %s', operation, method, url);

    const fetchOptions: RequestInit = {
      method,
      headers: { 'Content-Type': 'application/json' },
    };

    if (method === 'POST' && params) {
      fetchOptions.body = JSON.stringify(params);
    }

    const response = await fetch(url, fetchOptions);

    if (!response.ok) {
      const errMsg = `AutoCAD ${operation} API error: ${response.status} ${response.statusText}`;
      logHandler('[autocad_%s] response ERROR: %s', operation, errMsg);
      throw new Error(errMsg);
    }

    const result = await response.json();
    console.log(`[autocad_${operation}] response:`, { success: result.success });
    logHandler('[autocad_%s] response: success=%s', operation, result.success);

    return {
      success: result.success !== false,
      data: result.data || result,
      error: result.error,
    };
  } catch (error: any) {
    logHandler('[autocad_%s] FAILED: %s', operation, error.message);
    console.error(`[AutoCADHandler] ${operation} failed:`, error);
    return {
      success: false,
      data: null,
      error: error.message,
    };
  }
}

/**
 * 执行 AutoCAD 标准件操作
 *
 * @param currentUrl Local Engine URL
 * @param operation 操作类型 (list | presets | draw)
 * @param partType 标准件类型（draw 和 presets 时必需）
 * @param params 绘制参数（draw 时必需）
 * @param setMessages 更新消息的函数
 * @param botMessageId 当前 bot 消息 ID
 * @returns 执行结果
 */
async function executeAutoCADStandardParts(
  currentUrl: string,
  operation: 'list' | 'presets' | 'draw',
  partType?: string,
  params?: {
    preset?: string;
    parameters?: Record<string, any>;
    position?: [number, number];
  },
  setMessages?: React.Dispatch<React.SetStateAction<Message[]>>,
  botMessageId?: string
): Promise<ExecutionResult> {
  logHandler('[autocad_standard_parts] operation=%s, type=%s, params=%O', operation, partType, params);

  try {
    let url: string;
    let method: string;
    let body: string | undefined;

    if (operation === 'list') {
      url = `${currentUrl}${API_PREFIX}/standard_parts`;
      method = 'GET';
    } else if (operation === 'presets') {
      if (!partType) {
        throw new Error('partType is required for presets operation');
      }
      url = `${currentUrl}${API_PREFIX}/standard_parts/${partType}/presets`;
      method = 'GET';
    } else {
      // draw
      if (!partType) {
        throw new Error('partType is required for draw operation');
      }
      url = `${currentUrl}${API_PREFIX}/standard_parts/${partType}/draw`;
      method = 'POST';
      body = JSON.stringify(params || {});
    }

    console.log(`[autocad_standard_parts] ${method}:`, url);
    logHandler('[autocad_standard_parts] %s %s', method, url);

    const fetchOptions: RequestInit = {
      method,
      headers: { 'Content-Type': 'application/json' },
    };

    if (body) {
      fetchOptions.body = body;
    }

    const response = await fetch(url, fetchOptions);

    if (!response.ok) {
      const errMsg = `AutoCAD standard_parts API error: ${response.status} ${response.statusText}`;
      logHandler('[autocad_standard_parts] response ERROR: %s', errMsg);
      throw new Error(errMsg);
    }

    const result = await response.json();
    console.log('[autocad_standard_parts] response:', {
      success: result.success,
      hasScreenshot: !!result.data?.screenshot,
    });
    logHandler('[autocad_standard_parts] response: success=%s', result.success);

    // 如果有截图（draw 操作），更新到消息中
    if (result.data?.screenshot && setMessages && botMessageId) {
      setMessages((prev) =>
        prev.map((msg) => {
          if (msg.id !== botMessageId) return msg;
          const screenshots = msg.screenshots || [];
          return {
            ...msg,
            screenshots: [...screenshots, result.data.screenshot],
          };
        })
      );
      logHandler('[autocad_standard_parts] screenshot captured');
    }

    return {
      success: result.success !== false,
      data: result.data || result,
      error: result.error,
    };
  } catch (error: any) {
    logHandler('[autocad_standard_parts] FAILED: %s', error.message);
    console.error('[AutoCADHandler] standard_parts failed:', error);
    return {
      success: false,
      data: null,
      error: error.message,
    };
  }
}

// ==================== Tool Call 处理（新标准格式） ====================

/**
 * AutoCAD 动作名称类型
 */
export type AutoCADActionName =
  | 'launch'
  | 'draw_from_json'
  | 'execute_python_com'
  | 'snapshot'
  | 'open'
  | 'close'
  | 'new'
  | 'activate'
  | 'status'
  | 'list_standard_parts'
  | 'get_standard_part_presets'
  | 'draw_standard_part'
  | 'stop';

/**
 * 处理 AutoCAD tool_call（新标准格式）
 *
 * @param currentUrl Local Engine URL
 * @param name 动作名称
 * @param args 动作参数
 * @param setMessages 更新消息的函数
 * @param botMessageId 当前 bot 消息 ID
 * @returns 执行结果
 */
export async function handleAutoCADToolCall(
  currentUrl: string,
  name: string,
  args: Record<string, any>,
  setMessages: React.Dispatch<React.SetStateAction<Message[]>>,
  botMessageId: string
): Promise<ExecutionResult> {
  console.log('[AutoCAD] ===== DISPATCH =====');
  console.log('[AutoCAD] name:', name);
  console.log('[AutoCAD] args:', args);
  console.log('[AutoCAD] ========================');
  logHandler('[AutoCAD] dispatch: name=%s, args=%O', name, args);

  // 停止动作
  if (name === 'stop') {
    logHandler('[AutoCAD] action: stop');
    return { success: true, data: { message: 'Task completed' } };
  }

  // launch: 启动或连接 AutoCAD
  if (name === 'launch') {
    logHandler('[AutoCAD] action: launch');
    return executeAutoCADDocumentOperation(currentUrl, 'launch');
  }

  // draw_from_json: 绘制 JSON 结构化数据
  if (name === 'draw_from_json') {
    logHandler('[AutoCAD] action: draw_from_json');
    return executeAutoCADStep(
      currentUrl,
      'draw_from_json',
      { data: args.data },
      args.timeout || 60,
      args.return_screenshot !== false,
      setMessages,
      botMessageId
    );
  }

  // execute_python_com: 执行 Python COM 代码
  if (name === 'execute_python_com') {
    logHandler('[AutoCAD] action: execute_python_com, code=%d chars', (args.code || '').length);
    return executeAutoCADStep(
      currentUrl,
      'execute_python_com',
      { code: args.code },
      args.timeout || 60,
      args.return_screenshot !== false,
      setMessages,
      botMessageId
    );
  }

  // snapshot: 获取图纸快照
  if (name === 'snapshot') {
    logHandler('[AutoCAD] action: snapshot');
    return getAutoCADSnapshot(
      currentUrl,
      {
        include_content: args.include_content,
        include_screenshot: args.include_screenshot,
        only_visible: args.only_visible,
        max_entities: args.max_entities,
      },
      setMessages,
      botMessageId
    );
  }

  // 图纸管理操作
  if (name === 'open') {
    logHandler('[AutoCAD] action: open, file_path=%s', args.file_path);
    return executeAutoCADDocumentOperation(currentUrl, 'open', {
      file_path: args.file_path,
      read_only: args.read_only,
    });
  }

  if (name === 'close') {
    logHandler('[AutoCAD] action: close, save=%s', args.save);
    return executeAutoCADDocumentOperation(currentUrl, 'close', {
      save: args.save,
    });
  }

  if (name === 'new') {
    logHandler('[AutoCAD] action: new, template=%s', args.template);
    return executeAutoCADDocumentOperation(currentUrl, 'new', {
      template: args.template,
    });
  }

  if (name === 'activate') {
    logHandler('[AutoCAD] action: activate, name=%s, index=%s', args.name, args.index);
    return executeAutoCADDocumentOperation(currentUrl, 'activate', {
      name: args.name,
      index: args.index,
    });
  }

  if (name === 'status') {
    logHandler('[AutoCAD] action: status');
    return executeAutoCADDocumentOperation(currentUrl, 'status');
  }

  // 标准件操作
  if (name === 'list_standard_parts') {
    logHandler('[AutoCAD] action: list_standard_parts');
    return executeAutoCADStandardParts(currentUrl, 'list');
  }

  if (name === 'get_standard_part_presets') {
    logHandler('[AutoCAD] action: get_standard_part_presets, type=%s', args.part_type);
    return executeAutoCADStandardParts(currentUrl, 'presets', args.part_type);
  }

  if (name === 'draw_standard_part') {
    logHandler('[AutoCAD] action: draw_standard_part, type=%s, preset=%s', args.part_type, args.preset);
    return executeAutoCADStandardParts(
      currentUrl,
      'draw',
      args.part_type,
      {
        preset: args.preset,
        parameters: args.parameters,
        position: args.position,
      },
      setMessages,
      botMessageId
    );
  }

  // 未知动作
  logHandler('[AutoCAD] UNKNOWN action: %s', name);
  return {
    success: false,
    data: null,
    error: `Unknown AutoCAD action: ${name}`,
  };
}

// ==================== 便捷函数 ====================

/**
 * 绘制 JSON 数据到 AutoCAD
 *
 * @param currentUrl Local Engine URL
 * @param data 绘制数据
 * @param setMessages 更新消息的函数
 * @param botMessageId 当前 bot 消息 ID
 * @param timeout 超时时间
 * @returns 执行结果
 */
export async function drawFromJSON(
  currentUrl: string,
  data: {
    layer_colors?: Record<string, number>;
    elements: {
      lines?: Array<{ start: number[]; end: number[]; layer?: string; color?: number }>;
      circles?: Array<{ center: number[]; radius: number; layer?: string; color?: number }>;
      arcs?: Array<{
        center: number[];
        radius: number;
        start_angle: number;
        end_angle: number;
        layer?: string;
        color?: number;
      }>;
      polylines?: Array<{ vertices: number[][]; closed?: boolean; layer?: string; color?: number }>;
      texts?: Array<{ text: string; position: number[]; height?: number; layer?: string; color?: number }>;
      dimensions?: Array<Record<string, any>>;
    };
  },
  setMessages: React.Dispatch<React.SetStateAction<Message[]>>,
  botMessageId: string,
  timeout: number = 60
): Promise<ExecutionResult> {
  return handleAutoCADToolCall(
    currentUrl,
    'draw_from_json',
    { data, timeout },
    setMessages,
    botMessageId
  );
}

/**
 * 执行 Python COM 代码
 *
 * @param currentUrl Local Engine URL
 * @param code Python 代码
 * @param setMessages 更新消息的函数
 * @param botMessageId 当前 bot 消息 ID
 * @param timeout 超时时间
 * @returns 执行结果
 */
export async function executePythonCOM(
  currentUrl: string,
  code: string,
  setMessages: React.Dispatch<React.SetStateAction<Message[]>>,
  botMessageId: string,
  timeout: number = 60
): Promise<ExecutionResult> {
  return handleAutoCADToolCall(
    currentUrl,
    'execute_python_com',
    { code, timeout },
    setMessages,
    botMessageId
  );
}

/**
 * 获取 AutoCAD 快照
 *
 * @param currentUrl Local Engine URL
 * @param setMessages 更新消息的函数
 * @param botMessageId 当前 bot 消息 ID
 * @param options 快照选项
 * @returns 执行结果
 */
export async function getSnapshot(
  currentUrl: string,
  setMessages: React.Dispatch<React.SetStateAction<Message[]>>,
  botMessageId: string,
  options?: {
    include_content?: boolean;
    include_screenshot?: boolean;
    only_visible?: boolean;
    max_entities?: number;
  }
): Promise<ExecutionResult> {
  return handleAutoCADToolCall(
    currentUrl,
    'snapshot',
    options || {},
    setMessages,
    botMessageId
  );
}

/**
 * 获取 AutoCAD 状态
 *
 * @param currentUrl Local Engine URL
 * @returns 执行结果
 */
export async function getStatus(currentUrl: string): Promise<ExecutionResult> {
  return executeAutoCADDocumentOperation(currentUrl, 'status');
}
