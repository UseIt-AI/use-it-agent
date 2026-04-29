/**
 * Code Handler - 本机 Python 代码执行
 */

import { ExecutionResult, CodeActionName } from './types';
import { Message } from '../types';
import { logHandler, logRouter } from '@/utils/logger';

/**
 * 处理 code target 的 tool_call
 */
export async function handleToolCall(
  currentUrl: string,
  name: string,
  args: Record<string, any>,
  _setMessages: React.Dispatch<React.SetStateAction<Message[]>>,
  _botMessageId: string,
  projectPath?: string
): Promise<ExecutionResult> {
  const action = (name || '') as CodeActionName;
  logRouter('[CodeHandler] handleToolCall: action=%s', action);

  try {
    if (action === 'stop') {
      return {
        success: true,
        data: { stopped: true },
      };
    }

    if (action !== 'execute_python') {
      return {
        success: false,
        data: null,
        error: `Unsupported code action: ${name}`,
      };
    }

    const code = typeof args?.code === 'string' ? args.code : '';
    if (!code.trim()) {
      return {
        success: false,
        data: null,
        error: 'code is empty',
      };
    }

    const requestBody: Record<string, any> = {
      code,
      timeout: typeof args?.timeout === 'number' ? args.timeout : 30,
      cwd_mode: args?.cwd_mode || (projectPath ? 'project' : 'temp'),
      artifacts_glob: Array.isArray(args?.artifacts_glob) ? args.artifacts_glob : undefined,
      max_output_chars: typeof args?.max_output_chars === 'number' ? args.max_output_chars : 65536,
      project_path: projectPath || undefined,
      // 与 PPT/Office step 一致：回传项目树，Backend 可写入 additional_context，Code Use 重试时可读
      ...(projectPath ? { include_project_files: true, project_max_depth: 4 } : {}),
    };
    if (typeof args?.script_path === 'string' && args.script_path.trim()) {
      requestBody.script_path = args.script_path.trim();
    }

    logHandler('[CodeHandler] POST /api/v1/code/step body=%O', {
      timeout: requestBody.timeout,
      cwd_mode: requestBody.cwd_mode,
      has_project_path: !!requestBody.project_path,
      code_length: code.length,
      artifacts_glob: requestBody.artifacts_glob,
      script_path: requestBody.script_path,
    });

    const response = await fetch(`${currentUrl}/api/v1/code/step`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(requestBody),
    });

    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      const detail = payload?.detail || `${response.status} ${response.statusText}`;
      throw new Error(`code API error: ${detail}`);
    }

    return {
      success: payload?.success !== false,
      data: payload?.data ?? payload,
      error: payload?.error,
    };
  } catch (error: any) {
    logHandler('[CodeHandler] FAILED: %s', error?.message || String(error));
    return {
      success: false,
      data: null,
      error: error?.message || String(error),
    };
  }
}
