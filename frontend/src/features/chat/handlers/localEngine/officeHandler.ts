/**
 * Office Handler - Office COM 自动化处理
 * 
 * 处理 Word、Excel、PPT 等 Office 应用的 COM 自动化操作。
 * 
 * 支持两种格式：
 * - 新格式：tool_call (target=word/excel/ppt)
 * - 旧格式：tool_call (content.action.type=word_execute_code 等)
 * 
 * 调用 Local Engine API:
 * - POST /api/v1/word/step
 * - POST /api/v1/excel/step
 * - POST /api/v1/ppt/step
 */

import { ExecutionResult } from './types';
import { Message } from '../types';
import { logRouter, logHandler } from '@/utils/logger';

// 项目文件列表的默认深度
const PROJECT_FILES_MAX_DEPTH = 10;

// ==================== 路径工具 ====================

/**
 * 判断路径是不是绝对路径（兼容 Windows 与 POSIX）。
 *
 * Windows 绝对路径：
 *   - 盘符形式：`C:\foo`、`C:/foo`
 *   - UNC：`\\server\share`、`//server/share`
 * POSIX 绝对路径：
 *   - 以 `/` 开头
 *
 * 这个判断有意做得保守 —— 拿不准就当成相对路径，让上层去拼 projectPath，
 * 因为 local engine 跑在 Windows 上、cwd 又不是项目根，相对路径直接传过去几乎必然解析失败。
 */
function isAbsolutePath(p: string): boolean {
  if (!p) return false;
  if (/^[a-zA-Z]:[\\/]/.test(p)) return true; // C:\ 或 C:/
  if (p.startsWith('\\\\') || p.startsWith('//')) return true; // UNC
  if (p.startsWith('/')) return true; // POSIX
  return false;
}

/**
 * 把相对路径 `rel` 拼到 Windows 项目根 `base` 之下，结果统一用反斜杠分隔，
 * 例如 `joinWindowsPath('D:\\Workspace\\useit-studio', 'workspace/test.pptx')`
 *  → `D:\Workspace\useit-studio\workspace\test.pptx`。
 *
 * 之所以强制反斜杠：local engine 是 PowerShell + win32com，正斜杠虽然多数 API 兼容，
 * 但日志/比较时混着用容易让人误判，统一一种风格更省事。
 */
function joinWindowsPath(base: string, rel: string): string {
  const trimmedBase = base.replace(/[\\/]+$/, '');
  const normalizedRel = rel.replace(/^[\\/]+/, '').replace(/\//g, '\\');
  return `${trimmedBase}\\${normalizedRel}`;
}

// ==================== 结构化 Action 执行函数 ====================

/**
 * 执行结构化 Actions（三层架构第一层 + 第二层）
 *
 * 大模型输出结构化 JSON actions，直接通过 COM API 执行，无需启动子进程。
 *
 * @param currentUrl Local Engine URL
 * @param endpoint API 端点 (ppt)
 * @param actions Action 列表
 * @param setMessages 更新消息的函数
 * @param botMessageId 当前 bot 消息 ID
 * @param projectPath 项目路径（可选）
 * @returns 执行结果
 */
async function executeOfficeAction(
  currentUrl: string,
  endpoint: string,
  actions: Record<string, any>[],
  setMessages: React.Dispatch<React.SetStateAction<Message[]>>,
  botMessageId: string,
  projectPath?: string
): Promise<ExecutionResult> {
  logRouter('%s execute action: %d actions, projectPath=%s', endpoint, actions.length, projectPath ? 'yes' : 'no');

  try {
    const requestBody: Record<string, any> = {
      actions,
      return_screenshot: true,
      current_slide_only: true,
    };

    if (projectPath) {
      requestBody.include_project_files = true;
      requestBody.project_path = projectPath;
      requestBody.project_max_depth = PROJECT_FILES_MAX_DEPTH;
    }

    const url = `${currentUrl}/api/v1/${endpoint}/step`;
    console.log('[execute_action] POST:', url);
    console.log('[execute_action] requestBody:', requestBody);
    logHandler('[execute_action] POST %s', url);
    logHandler('[execute_action] requestBody: %O', requestBody);

    const response = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(requestBody),
    });

    if (!response.ok) {
      const errMsg = `${endpoint} action API error: ${response.status} ${response.statusText}`;
      logHandler('[execute_action] response ERROR: %s', errMsg);
      throw new Error(errMsg);
    }

    const result = await response.json();
    console.log('[execute_action] response:', {
      success: result.success,
      hasSnapshot: !!result.data?.snapshot,
      hasError: !!result.error,
      actionResults: result.data?.execution?.results?.length,
    });
    logHandler(
      '[execute_action] response: success=%s, hasSnapshot=%s, actionResults=%d',
      result.success,
      !!result.data?.snapshot,
      result.data?.execution?.results?.length || 0
    );

    // 如果有截图，更新到消息中
    if (result.data?.snapshot?.screenshot) {
      setMessages((prev) =>
        prev.map((msg) => {
          if (msg.id !== botMessageId) return msg;
          const screenshots = msg.screenshots || [];
          return {
            ...msg,
            screenshots: [...screenshots, result.data.snapshot.screenshot],
          };
        })
      );
      logHandler('[execute_action] screenshot captured for %s', endpoint);
    }

    return {
      success: result.success !== false,
      data: result.data || result,
      error: result.error,
    };
  } catch (error: any) {
    logHandler('[execute_action] FAILED: %s', error.message);
    console.error(`[OfficeHandler] ${endpoint} execute action failed:`, error);
    return {
      success: false,
      data: null,
      error: error.message,
    };
  }
}

// ==================== 通用执行函数 ====================

/**
 * 执行 Office 代码
 *
 * @param currentUrl Local Engine URL
 * @param endpoint API 端点（word/excel/ppt）
 * @param code 要执行的代码
 * @param language 代码语言
 * @param timeout 超时时间
 * @param setMessages 更新消息的函数
 * @param botMessageId 当前 bot 消息 ID
 * @param projectPath 项目路径（可选，用于附带项目文件列表）
 * @returns 执行结果
 */
async function executeOfficeCode(
  currentUrl: string,
  endpoint: string,
  code: string,
  language: string,
  timeout: number,
  setMessages: React.Dispatch<React.SetStateAction<Message[]>>,
  botMessageId: string,
  projectPath?: string
): Promise<ExecutionResult> {
  logRouter('%s execute code: %d chars, projectPath=%s', endpoint, code.length, projectPath ? 'yes' : 'no');

  try {
    // 构建请求体
    const requestBody: Record<string, any> = {
      code,
      language,
      timeout,
      return_screenshot: true,
      current_page_only: endpoint === 'word',
    };

    // 如果有 projectPath，附带项目文件列表
    if (projectPath) {
      requestBody.include_project_files = true;
      requestBody.project_path = projectPath;
      requestBody.project_max_depth = PROJECT_FILES_MAX_DEPTH;
    }

    const url = `${currentUrl}/api/v1/${endpoint}/step`;
    console.log('[execute_code] POST:', url);
    console.log('[execute_code] requestBody:', requestBody);
    logHandler('[execute_code] POST %s', url);
    logHandler('[execute_code] requestBody: %O', requestBody);

    const response = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(requestBody),
    });

    if (!response.ok) {
      const errMsg = `${endpoint} API error: ${response.status} ${response.statusText}`;
      logHandler('[execute_code] response ERROR: %s', errMsg);
      throw new Error(errMsg);
    }

    const result = await response.json();
    console.log('[execute_code] response:', { success: result.success, hasSnapshot: !!result.data?.snapshot, hasError: !!result.error });
    logHandler('[execute_code] response: success=%s, hasSnapshot=%s, hasError=%s',
      result.success, !!result.data?.snapshot, !!result.error);

    // 如果有截图，更新到消息中
    if (result.data?.snapshot?.screenshot) {
      setMessages((prev) =>
        prev.map((msg) => {
          if (msg.id !== botMessageId) return msg;
          const screenshots = msg.screenshots || [];
          return {
            ...msg,
            screenshots: [...screenshots, result.data.snapshot.screenshot],
          };
        })
      );
      logHandler('[execute_code] screenshot captured for %s', endpoint);
    }

    return {
      success: result.success !== false,
      data: result.data || result,
      error: result.error,
    };
  } catch (error: any) {
    logHandler('[execute_code] FAILED: %s', error.message);
    console.error(`[OfficeHandler] ${endpoint} execute failed:`, error);
    return {
      success: false,
      data: null,
      error: error.message,
    };
  }
}

/**
 * 执行 Office 脚本（execute_script 模式）
 *
 * @param currentUrl Local Engine URL
 * @param endpoint API 端点（word/excel/ppt）
 * @param skillId Skill ID
 * @param scriptPath 脚本相对路径
 * @param parameters 脚本参数
 * @param language 脚本语言
 * @param timeout 超时时间
 * @param setMessages 更新消息的函数
 * @param botMessageId 当前 bot 消息 ID
 * @param projectPath 项目路径（可选，用于附带项目文件列表）
 * @returns 执行结果
 */
async function executeOfficeScript(
  currentUrl: string,
  endpoint: string,
  skillId: string,
  scriptPath: string,
  parameters: Record<string, any>,
  language: string,
  timeout: number,
  setMessages: React.Dispatch<React.SetStateAction<Message[]>>,
  botMessageId: string,
  projectPath?: string
): Promise<ExecutionResult> {
  logRouter('%s execute script: skill_id=%s, script_path=%s, projectPath=%s',
    endpoint, skillId, scriptPath, projectPath ? 'yes' : 'no');

  try {
    // 构建请求体（execute_script 模式）
    const requestBody: Record<string, any> = {
      skill_id: skillId,
      script_path: scriptPath,
      parameters: parameters,
      language,
      timeout,
      return_screenshot: true,
      current_sheet_only: endpoint === 'excel',
    };

    // 如果有 projectPath，附带项目文件列表
    if (projectPath) {
      requestBody.include_project_files = true;
      requestBody.project_path = projectPath;
      requestBody.project_max_depth = PROJECT_FILES_MAX_DEPTH;
    }

    const url = `${currentUrl}/api/v1/${endpoint}/step`;
    console.log('[execute_script] POST:', url);
    console.log('[execute_script] requestBody:', requestBody);
    logHandler('[execute_script] POST %s', url);
    logHandler('[execute_script] requestBody: %O', requestBody);

    const response = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(requestBody),
    });

    if (!response.ok) {
      const errMsg = `${endpoint} API error: ${response.status} ${response.statusText}`;
      logHandler('[execute_script] response ERROR: %s', errMsg);
      throw new Error(errMsg);
    }

    const result = await response.json();
    console.log('[execute_script] response:', { success: result.success, hasSnapshot: !!result.data?.snapshot, hasError: !!result.error, error: result.error });
    if (result.data?.execution) {
      console.log('[execute_script] execution:', { returnCode: result.data.execution.return_code, outputPreview: result.data.execution.output?.slice(0, 200) });
    }
    logHandler('[execute_script] response: success=%s, hasSnapshot=%s, hasError=%s',
      result.success, !!result.data?.snapshot, !!result.error);
    if (result.error) {
      logHandler('[execute_script] error detail: %s', result.error);
    }
    if (result.data?.execution) {
      logHandler('[execute_script] execution: returnCode=%s, output=%s',
        result.data.execution.return_code, result.data.execution.output?.slice(0, 200));
    }

    // 如果有截图，更新到消息中
    if (result.data?.snapshot?.screenshot) {
      setMessages((prev) =>
        prev.map((msg) => {
          if (msg.id !== botMessageId) return msg;
          const screenshots = msg.screenshots || [];
          return {
            ...msg,
            screenshots: [...screenshots, result.data.snapshot.screenshot],
          };
        })
      );
      logHandler('[execute_script] screenshot captured for %s', endpoint);
    }

    return {
      success: result.success !== false,
      data: result.data || result,
      error: result.error,
    };
  } catch (error: any) {
    logHandler('[execute_script] FAILED: %s', error.message);
    console.error(`[OfficeHandler] ${endpoint} execute script failed:`, error);
    return {
      success: false,
      data: null,
      error: error.message,
    };
  }
}

// ==================== Tool Call 处理（新标准格式） ====================

/**
 * 处理 Word tool_call（新标准格式）
 * 
 * @param currentUrl Local Engine URL
 * @param name 动作名称（execute_code, stop）
 * @param args 动作参数
 * @param setMessages 更新消息的函数
 * @param botMessageId 当前 bot 消息 ID
 * @param projectPath 项目路径（可选，用于附带项目文件列表）
 * @returns 执行结果
 */
export async function handleWordToolCall(
  currentUrl: string,
  name: string,
  args: Record<string, any>,
  setMessages: React.Dispatch<React.SetStateAction<Message[]>>,
  botMessageId: string,
  projectPath?: string
): Promise<ExecutionResult> {
  console.log('[Word] ===== DISPATCH =====');
  console.log('[Word] name:', name);
  console.log('[Word] args:', args);
  console.log('[Word] ========================');
  logHandler('[Word] dispatch: name=%s, args=%O', name, args);

  if (name === 'stop') {
    logHandler('[Word] action: stop');
    return { success: true, data: { message: 'Task completed' } };
  }

  // `step` 是后端 endpoint 名（POST /api/v1/word/step），AI 侧已切换到这个命名。
  // 与 `execute_code` 等价 —— 两者都把 {code, language, timeout} 透传到同一个端点。
  if (name === 'execute_code' || name === 'step') {
    logHandler('[Word] action: %s, code=%d chars, lang=%s', name, (args.code || '').length, args.language || 'PowerShell');
    return executeOfficeCode(currentUrl, 'word', args.code || '', args.language || 'PowerShell', args.timeout || 120, setMessages, botMessageId, projectPath);
  }

  if (name === 'execute_script') {
    logHandler('[Word] action: execute_script, skill_id=%s, script_path=%s, params=%O',
      args.skill_id || '66666666', args.script_path || '', args.parameters || {});
    return executeOfficeScript(currentUrl, 'word', args.skill_id || '66666666', args.script_path || '', args.parameters || {}, args.language || 'PowerShell', args.timeout || 120, setMessages, botMessageId, projectPath);
  }

  logHandler('[Word] UNKNOWN action: %s', name);
  return {
    success: false,
    data: null,
    error: `Unknown Word action: ${name}`,
  };
}

/**
 * 处理 Excel tool_call（新标准格式）
 * 
 * @param currentUrl Local Engine URL
 * @param name 动作名称（execute_code, stop）
 * @param args 动作参数
 * @param setMessages 更新消息的函数
 * @param botMessageId 当前 bot 消息 ID
 * @param projectPath 项目路径（可选，用于附带项目文件列表）
 * @returns 执行结果
 */
export async function handleExcelToolCall(
  currentUrl: string,
  name: string,
  args: Record<string, any>,
  setMessages: React.Dispatch<React.SetStateAction<Message[]>>,
  botMessageId: string,
  projectPath?: string
): Promise<ExecutionResult> {
  console.log('[Excel] ===== DISPATCH =====');
  console.log('[Excel] name:', name);
  console.log('[Excel] args:', args);
  console.log('[Excel] ========================');
  logHandler('[Excel] dispatch: name=%s, args=%O', name, args);

  if (name === 'stop') {
    logHandler('[Excel] action: stop');
    return { success: true, data: { message: 'Task completed' } };
  }

  // `step` 是后端 endpoint 名（POST /api/v1/excel/step），等价 `execute_code`。
  if (name === 'execute_code' || name === 'step') {
    logHandler('[Excel] action: %s, code=%d chars, lang=%s', name, (args.code || '').length, args.language || 'PowerShell');
    return executeOfficeCode(currentUrl, 'excel', args.code || '', args.language || 'PowerShell', args.timeout || 120, setMessages, botMessageId, projectPath);
  }

  if (name === 'execute_script') {
    logHandler('[Excel] action: execute_script, skill_id=%s, script_path=%s, params=%O',
      args.skill_id || '66666666', args.script_path || '', args.parameters || {});
    return executeOfficeScript(currentUrl, 'excel', args.skill_id || '66666666', args.script_path || '', args.parameters || {}, args.language || 'PowerShell', args.timeout || 120, setMessages, botMessageId, projectPath);
  }

  logHandler('[Excel] UNKNOWN action: %s', name);
  return {
    success: false,
    data: null,
    error: `Unknown Excel action: ${name}`,
  };
}

/**
 * PPT 快照函数 — 调用 /api/v1/ppt/snapshot 读取当前演示文稿状态
 */
async function executePPTSnapshot(
  currentUrl: string,
  args: Record<string, any>,
  setMessages: React.Dispatch<React.SetStateAction<Message[]>>,
  botMessageId: string,
  projectPath?: string
): Promise<ExecutionResult> {
  try {
    const requestBody: Record<string, any> = {
      include_content: args.include_content ?? true,
      include_screenshot: args.include_screenshot ?? true,
      current_slide_only: args.current_slide_only ?? false,
      ...(args.max_slides != null && { max_slides: args.max_slides }),
    };

    if (projectPath) {
      requestBody.include_project_files = true;
      requestBody.project_path = projectPath;
      requestBody.project_max_depth = PROJECT_FILES_MAX_DEPTH;
    }

    const url = `${currentUrl}/api/v1/ppt/snapshot`;
    logHandler('[PPT snapshot] POST %s, body: %O', url, requestBody);

    const response = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(requestBody),
    });

    if (!response.ok) {
      const errMsg = `ppt snapshot API error: ${response.status} ${response.statusText}`;
      logHandler('[PPT snapshot] response ERROR: %s', errMsg);
      throw new Error(errMsg);
    }

    const result = await response.json();
    logHandler('[PPT snapshot] response: success=%s, hasContent=%s', result.success, !!result.data?.content);

    if (result.data?.screenshot) {
      setMessages((prev) =>
        prev.map((msg) => {
          if (msg.id !== botMessageId) return msg;
          const screenshots = msg.screenshots || [];
          return { ...msg, screenshots: [...screenshots, result.data.screenshot] };
        })
      );
    }

    return {
      success: result.success !== false,
      data: result.data || result,
      error: result.error,
    };
  } catch (error: any) {
    logHandler('[PPT snapshot] FAILED: %s', error.message);
    console.error('[OfficeHandler] PPT snapshot failed:', error);
    return { success: false, data: null, error: error.message };
  }
}

/**
 * PPT open — 调用 /api/v1/ppt/open 打开 .pptx 文件
 *
 * 后端约定：PowerPoint 未运行会自动启动；同路径 presentation 已经打开则直接激活，不重复打开。
 * 失败时后端返回 HTTPException(detail=...)，这里把 detail 提取出来给 planner 看，
 * 方便它针对"路径不存在"/"权限不足"等错误做下一步判断。
 */
async function executePPTOpen(
  currentUrl: string,
  args: Record<string, any>,
  setMessages: React.Dispatch<React.SetStateAction<Message[]>>,
  botMessageId: string,
  projectPath?: string
): Promise<ExecutionResult> {
  try {
    const rawFilePath: string | undefined = args.file_path || args.path;
    if (!rawFilePath) {
      const errMsg = 'ppt_document action="open" requires `file_path` (absolute path to a .pptx/.ppt file)';
      logHandler('[PPT open] %s', errMsg);
      return { success: false, data: null, error: errMsg };
    }

    // Planner 经常给出相对路径（例如 attached_files 里的 "workspace/test.pptx"），
    // 这种路径在 local engine 那边按它的 cwd 解析、在 Windows 上多半找不到文件。
    // 这里在前端就先拼到 projectPath 下，把"项目根 + 相对路径"的语义钉死在调用方。
    let filePath = rawFilePath;
    if (!isAbsolutePath(filePath)) {
      if (projectPath) {
        const resolved = joinWindowsPath(projectPath, filePath);
        logHandler('[PPT open] resolved relative path under projectPath: %s + %s -> %s',
          projectPath, filePath, resolved);
        filePath = resolved;
      } else {
        // 没有 projectPath 还给了相对路径——按原样发出去也大概率失败，但保留行为给后端报错，
        // 这样 planner 能从错误里看到"路径找不到"，再决定是 ask_user 还是换文件。
        logHandler('[PPT open] relative path without projectPath, sending as-is: %s', filePath);
      }
    }

    const requestBody: Record<string, any> = {
      file_path: filePath,
      read_only: args.read_only ?? false,
    };

    const url = `${currentUrl}/api/v1/ppt/open`;
    console.log('[PPT open] POST:', url);
    console.log('[PPT open] requestBody:', requestBody);
    logHandler('[PPT open] POST %s, body: %O', url, requestBody);

    const response = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(requestBody),
    });

    if (!response.ok) {
      let detail = `${response.status} ${response.statusText}`;
      try {
        const errBody = await response.json();
        if (errBody?.detail) detail = `${detail} - ${errBody.detail}`;
      } catch {
        // body 不是 JSON 就忽略，保留 statusText
      }
      const errMsg = `ppt open API error: ${detail}`;
      logHandler('[PPT open] response ERROR: %s', errMsg);
      return { success: false, data: null, error: errMsg };
    }

    const result = await response.json();
    logHandler(
      '[PPT open] response: success=%s, presentation=%s',
      result.success,
      result.data?.presentation_info?.name || result.data?.presentation_info?.path || '<unknown>'
    );

    // /open 不返回截图，但项目路径可在后续 snapshot 取得，这里直接消费 envelope。
    return {
      success: result.success !== false,
      data: result.data || result,
      error: result.error,
    };
  } catch (error: any) {
    logHandler('[PPT open] FAILED: %s', error.message);
    console.error('[OfficeHandler] PPT open failed:', error);
    // setMessages 暂时未用到，保留参数签名以便后续扩展（如打开后顺带 snapshot 推截图）
    void setMessages;
    return { success: false, data: null, error: error.message };
  }
}

/**
 * PPT close — 调用 /api/v1/ppt/close 关闭当前 presentation
 */
async function executePPTClose(
  currentUrl: string,
  args: Record<string, any>,
  setMessages: React.Dispatch<React.SetStateAction<Message[]>>,
  botMessageId: string,
  projectPath?: string
): Promise<ExecutionResult> {
  try {
    const requestBody: Record<string, any> = {
      save: args.save ?? false,
    };

    const url = `${currentUrl}/api/v1/ppt/close`;
    console.log('[PPT close] POST:', url);
    console.log('[PPT close] requestBody:', requestBody);
    logHandler('[PPT close] POST %s, body: %O', url, requestBody);

    const response = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(requestBody),
    });

    if (!response.ok) {
      let detail = `${response.status} ${response.statusText}`;
      try {
        const errBody = await response.json();
        if (errBody?.detail) detail = `${detail} - ${errBody.detail}`;
      } catch {
        // ignore
      }
      const errMsg = `ppt close API error: ${detail}`;
      logHandler('[PPT close] response ERROR: %s', errMsg);
      return { success: false, data: null, error: errMsg };
    }

    const result = await response.json();
    logHandler(
      '[PPT close] response: success=%s, closed=%s',
      result.success,
      result.data?.closed_presentation || '<unknown>'
    );

    return {
      success: result.success !== false,
      data: result.data || result,
      error: result.error,
    };
  } catch (error: any) {
    logHandler('[PPT close] FAILED: %s', error.message);
    console.error('[OfficeHandler] PPT close failed:', error);
    void setMessages;
    void projectPath;
    return { success: false, data: null, error: error.message };
  }
}

/**
 * PPT 统一执行函数 — 透传 args 到 /api/v1/ppt/step
 *
 * 后端 StepRequest 根据字段自动路由：
 *   actions  → 结构化 Action
 *   code     → 原始代码
 *   skill_id + script_path → 预置 Skill 脚本
 */
async function executePPTStep(
  currentUrl: string,
  args: Record<string, any>,
  setMessages: React.Dispatch<React.SetStateAction<Message[]>>,
  botMessageId: string,
  projectPath?: string
): Promise<ExecutionResult> {
  try {
    const requestBody: Record<string, any> = {
      ...args,
      return_screenshot: true,
      current_slide_only: true,
    };

    if (projectPath) {
      requestBody.include_project_files = true;
      requestBody.project_path = projectPath;
      requestBody.project_max_depth = PROJECT_FILES_MAX_DEPTH;
    }

    const url = `${currentUrl}/api/v1/ppt/step`;
    console.log('[PPT step] POST:', url);
    console.log('[PPT step] requestBody:', requestBody);
    logHandler('[PPT step] POST %s, body: %O', url, requestBody);

    const response = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(requestBody),
    });

    if (!response.ok) {
      const errMsg = `PPT step API error: ${response.status} ${response.statusText}`;
      logHandler('[PPT step] response ERROR: %s', errMsg);
      throw new Error(errMsg);
    }

    const result = await response.json();
    logHandler('[PPT step] response: success=%s, hasSnapshot=%s', result.success, !!result.data?.snapshot);

    if (result.data?.snapshot?.screenshot) {
      setMessages((prev) =>
        prev.map((msg) => {
          if (msg.id !== botMessageId) return msg;
          const screenshots = msg.screenshots || [];
          return {
            ...msg,
            screenshots: [...screenshots, result.data.snapshot.screenshot],
          };
        })
      );
    }

    return {
      success: result.success !== false,
      data: result.data || result,
      error: result.error,
    };
  } catch (error: any) {
    logHandler('[PPT step] FAILED: %s', error.message);
    console.error('[OfficeHandler] PPT step failed:', error);
    return { success: false, data: null, error: error.message };
  }
}

/**
 * 处理 PPT tool_call（新标准格式）
 *
 * 所有 name（execute_action / execute_code / execute_script）统一走 executePPTStep，
 * 直接透传 args 给后端 /step，由后端 StepRequest 自动路由。
 */
export async function handlePPTToolCall(
  currentUrl: string,
  name: string,
  args: Record<string, any>,
  setMessages: React.Dispatch<React.SetStateAction<Message[]>>,
  botMessageId: string,
  projectPath?: string
): Promise<ExecutionResult> {
  console.log('[PPT] ===== DISPATCH =====');
  console.log('[PPT] name:', name);
  console.log('[PPT] args:', args);
  console.log('[PPT] ========================');
  logHandler('[PPT] dispatch: name=%s, args=%O', name, args);

  if (name === 'stop') {
    logHandler('[PPT] action: stop');
    return { success: true, data: { message: 'Task completed' } };
  }

  if (name === 'snapshot') {
    logHandler('[PPT] → snapshot');
    return executePPTSnapshot(currentUrl, args, setMessages, botMessageId, projectPath);
  }

  // ppt_document 工具会以扁平 ToolCall(name="open"|"close", target="ppt") 形式打过来——
  // 不走 /step，因为 /step 要求 PowerPoint COM 实例已就绪，open 自身就是用来制造该前置条件的。
  if (name === 'open') {
    logHandler('[PPT] → open');
    return executePPTOpen(currentUrl, args, setMessages, botMessageId, projectPath);
  }

  if (name === 'close') {
    logHandler('[PPT] → close');
    return executePPTClose(currentUrl, args, setMessages, botMessageId, projectPath);
  }

  if (['execute_action', 'execute_code', 'execute_script', 'step'].includes(name)) {
    logHandler('[PPT] → executePPTStep (%s)', name);
    return executePPTStep(currentUrl, args, setMessages, botMessageId, projectPath);
  }

  logHandler('[PPT] UNKNOWN action: %s', name);
  return {
    success: false,
    data: null,
    error: `Unknown PPT action: ${name}`,
  };
}

// ==================== 旧格式处理（保留兼容） ====================

/**
 * 处理 Word 代码执行（旧格式）
 * 
 * @deprecated 使用 handleWordToolCall
 */
export async function handleWordExecuteCode(
  currentUrl: string,
  payload: any,
  setMessages: React.Dispatch<React.SetStateAction<Message[]>>,
  botMessageId: string
): Promise<ExecutionResult> {
  const code = payload?.generated_code || payload?.code || '';
  const language = payload?.language || 'PowerShell';
  const timeout = payload?.timeout || 120;

  return executeOfficeCode(currentUrl, 'word', code, language, timeout, setMessages, botMessageId);
}

/**
 * 处理 Excel 代码执行（旧格式）
 * 
 * @deprecated 使用 handleExcelToolCall
 */
export async function handleExcelExecuteCode(
  currentUrl: string,
  payload: any,
  setMessages: React.Dispatch<React.SetStateAction<Message[]>>,
  botMessageId: string
): Promise<ExecutionResult> {
  const code = payload?.generated_code || payload?.code || '';
  const language = payload?.language || 'PowerShell';
  const timeout = payload?.timeout || 120;

  return executeOfficeCode(currentUrl, 'excel', code, language, timeout, setMessages, botMessageId);
}

/**
 * 处理 PPT 代码执行（旧格式）
 * 
 * @deprecated 使用 handlePPTToolCall
 */
export async function handlePPTExecuteCode(
  currentUrl: string,
  payload: any,
  setMessages: React.Dispatch<React.SetStateAction<Message[]>>,
  botMessageId: string
): Promise<ExecutionResult> {
  const code = payload?.generated_code || payload?.code || '';
  const language = payload?.language || 'PowerShell';
  const timeout = payload?.timeout || 120;

  return executeOfficeCode(currentUrl, 'ppt', code, language, timeout, setMessages, botMessageId);
}
