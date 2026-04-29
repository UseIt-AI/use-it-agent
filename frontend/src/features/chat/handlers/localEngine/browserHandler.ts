/**
 * Browser Handler - Browser Use 操作处理
 *
 * 处理与 Local Engine 的浏览器自动化通信：
 * - 支持单例模式（简单场景，向后兼容）
 * - 支持 Session 模式（多实例场景）
 *
 * API 端点：
 * - 单例模式: POST /api/v1/browser/step
 * - Session 模式: POST /api/v1/browser/sessions/{session_id}/step
 *
 * @see browserHandler.md 设计文档
 */

import { ExecutionResult, BrowserActionName } from './types';
import { Message } from '../types';
import { logRouter } from '@/utils/logger';

// ==================== 类型定义 ====================

/** Session 信息 */
interface SessionInfo {
  session_id: string;
  connected: boolean;
  connect_type: 'connect' | 'attach';
  cdp_url?: string;
  browser_type?: string;
  profile?: string;
  created_at: string;
}

/** Tab 信息 */
interface TabInfo {
  tab_index: number;
  tab_id: string;
  url: string;
  title: string;
  is_active: boolean;
}

/** 页面元素信息 */
interface ElementInfo {
  index: number;
  tag: string;
  text: string;
  attributes: Record<string, string>;
  position?: { x: number; y: number; width: number; height: number };
}

/** 页面状态 */
interface PageState {
  url: string;
  title: string;
  elements?: ElementInfo[];
  element_count?: number;
  screenshot_base64?: string;
  // Tab 信息
  tabs?: TabInfo[];
  tab_count?: number;
  active_tab_index?: number;
}

/** 动作执行结果 */
interface ActionResult {
  index: number;
  ok: boolean;
  result?: any;
  error?: string;
}

// ==================== 动作分类 ====================

/** 单例模式连接管理动作 */
const CONNECTION_MANAGEMENT_ACTIONS: BrowserActionName[] = [
  'connect',
  'attach',
  'disconnect',
  'status',
];

/** Session 管理动作（多实例） */
const SESSION_MANAGEMENT_ACTIONS: BrowserActionName[] = [
  'create_session',
  'attach_session',
  'list_sessions',
  'close_session',
];

/** Tab 管理动作 */
const TAB_MANAGEMENT_ACTIONS: BrowserActionName[] = [
  'list_tabs',
  'create_tab',
  'switch_tab',
  'close_tab',
];

// ==================== 连接管理 API（单例模式）====================

/**
 * 启动新浏览器并连接（单例模式）
 * 连接成功后自动获取 page_state
 */
async function connect(
  currentUrl: string,
  args: Record<string, any>
): Promise<ExecutionResult> {
  try {
    const response = await fetch(`${currentUrl}/api/v1/browser/connect`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        browser_type: args.browser_type || 'auto',
        profile_directory: args.profile_directory || 'Default',
        headless: args.headless || false,
        highlight_elements: args.highlight_elements ?? true,
      }),
    });

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new Error(errorData.detail || `HTTP ${response.status}`);
    }

    const data = await response.json();

    if (!data.success) {
      throw new Error(data.error || 'Failed to connect');
    }

    // 连接成功后，自动获取 page_state
    const pageStateResponse = await fetch(`${currentUrl}/api/v1/browser/page_state`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        include_screenshot: true,
        max_elements: 100,
      }),
    });

    let pageState: Record<string, any> | null = null;
    if (pageStateResponse.ok) {
      const pageStateData = await pageStateResponse.json();
      if (pageStateData.success) {
        pageState = pageStateData.data;
      }
    }

    return {
      success: true,
      data: {
        ...data.data,
        page_state: pageState,
        screenshot: pageState?.screenshot_base64,
      },
    };
  } catch (error: any) {
    return {
      success: false,
      data: null,
      error: error.message,
    };
  }
}

/**
 * 接管用户已打开的浏览器（单例模式，通过 CDP）
 * 连接成功后自动获取 page_state
 */
async function attach(
  currentUrl: string,
  args: Record<string, any>
): Promise<ExecutionResult> {
  try {
    const response = await fetch(`${currentUrl}/api/v1/browser/attach`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        cdp_url: args.cdp_url || 'http://localhost:9222',
        highlight_elements: args.highlight_elements ?? true,
      }),
    });

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new Error(errorData.detail || `HTTP ${response.status}`);
    }

    const data = await response.json();

    if (!data.success) {
      throw new Error(data.error || 'Failed to attach');
    }

    // 连接成功后，自动获取 page_state
    const pageStateResponse = await fetch(`${currentUrl}/api/v1/browser/page_state`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        include_screenshot: true,
        max_elements: 100,
      }),
    });

    let pageState: Record<string, any> | null = null;
    if (pageStateResponse.ok) {
      const pageStateData = await pageStateResponse.json();
      if (pageStateData.success) {
        pageState = pageStateData.data;
      }
    }

    return {
      success: true,
      data: {
        ...data.data,
        page_state: pageState,
        screenshot: pageState?.screenshot_base64,
      },
    };
  } catch (error: any) {
    return {
      success: false,
      data: null,
      error: error.message,
    };
  }
}

/**
 * 断开浏览器连接（单例模式）
 */
async function disconnect(currentUrl: string): Promise<ExecutionResult> {
  try {
    const response = await fetch(`${currentUrl}/api/v1/browser/disconnect`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
    });

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new Error(errorData.detail || `HTTP ${response.status}`);
    }

    const data = await response.json();

    return {
      success: true,
      data: data.data,
    };
  } catch (error: any) {
    return {
      success: false,
      data: null,
      error: error.message,
    };
  }
}

/**
 * 获取连接状态（单例模式）
 */
async function getStatus(currentUrl: string): Promise<ExecutionResult> {
  try {
    const response = await fetch(`${currentUrl}/api/v1/browser/status`, {
      method: 'GET',
      headers: { 'Content-Type': 'application/json' },
    });

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }

    const data = await response.json();

    return {
      success: true,
      data: data,
    };
  } catch (error: any) {
    return {
      success: false,
      data: null,
      error: error.message,
    };
  }
}

// ==================== Session 管理 API ====================

/**
 * 创建新的浏览器 Session
 */
async function createSession(
  currentUrl: string,
  args: Record<string, any>
): Promise<ExecutionResult> {
  try {
    const response = await fetch(`${currentUrl}/api/v1/browser/sessions`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        browser_type: args.browser_type || 'auto',
        profile_directory: args.profile_directory || 'Default',
        headless: args.headless || false,
        highlight_elements: args.highlight_elements ?? true,
        initial_url: args.initial_url,
      }),
    });

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new Error(errorData.detail || `HTTP ${response.status}`);
    }

    const data = await response.json();

    if (!data.success) {
      throw new Error(data.error || 'Failed to create session');
    }

    return {
      success: true,
      data: {
        session_id: data.data.session_id,
        browser_type: data.data.browser_type,
        profile: data.data.profile,
        created_at: data.data.created_at,
      },
    };
  } catch (error: any) {
    return {
      success: false,
      data: null,
      error: error.message,
    };
  }
}

/**
 * 通过 CDP 接管已有浏览器
 */
async function attachSession(
  currentUrl: string,
  args: Record<string, any>
): Promise<ExecutionResult> {
  try {
    const response = await fetch(`${currentUrl}/api/v1/browser/sessions/attach`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        cdp_url: args.cdp_url || 'http://localhost:9222',
        highlight_elements: args.highlight_elements ?? true,
      }),
    });

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new Error(errorData.detail || `HTTP ${response.status}`);
    }

    const data = await response.json();

    if (!data.success) {
      throw new Error(data.error || 'Failed to attach session');
    }

    return {
      success: true,
      data: {
        session_id: data.data.session_id,
        cdp_url: data.data.cdp_url,
        current_url: data.data.current_url,
        current_title: data.data.current_title,
        created_at: data.data.created_at,
      },
    };
  } catch (error: any) {
    return {
      success: false,
      data: null,
      error: error.message,
    };
  }
}

/**
 * 列出所有 Sessions
 */
async function listSessions(currentUrl: string): Promise<ExecutionResult> {
  try {
    const response = await fetch(`${currentUrl}/api/v1/browser/sessions`, {
      method: 'GET',
      headers: { 'Content-Type': 'application/json' },
    });

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }

    const data = await response.json();

    return {
      success: true,
      data: {
        sessions: data.data?.sessions || [],
      },
    };
  } catch (error: any) {
    return {
      success: false,
      data: null,
      error: error.message,
    };
  }
}

/**
 * 关闭 Session
 */
async function closeSession(
  currentUrl: string,
  sessionId: string
): Promise<ExecutionResult> {
  try {
    const response = await fetch(
      `${currentUrl}/api/v1/browser/sessions/${sessionId}`,
      {
        method: 'DELETE',
        headers: { 'Content-Type': 'application/json' },
      }
    );

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new Error(errorData.detail || `HTTP ${response.status}`);
    }

    const data = await response.json();

    return {
      success: data.success,
      data: {
        session_id: sessionId,
        closed: true,
      },
    };
  } catch (error: any) {
    return {
      success: false,
      data: null,
      error: error.message,
    };
  }
}

// ==================== Tab 管理 API ====================

/**
 * 获取 Session 的所有 Tabs
 */
async function listTabs(
  currentUrl: string,
  sessionId: string
): Promise<ExecutionResult> {
  try {
    const response = await fetch(
      `${currentUrl}/api/v1/browser/sessions/${sessionId}/tabs`,
      {
        method: 'GET',
        headers: { 'Content-Type': 'application/json' },
      }
    );

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }

    const data = await response.json();

    return {
      success: true,
      data: {
        tabs: data.data?.tabs || [],
      },
    };
  } catch (error: any) {
    return {
      success: false,
      data: null,
      error: error.message,
    };
  }
}

/**
 * 创建新 Tab
 */
async function createTab(
  currentUrl: string,
  sessionId: string,
  args: Record<string, any>
): Promise<ExecutionResult> {
  try {
    const response = await fetch(
      `${currentUrl}/api/v1/browser/sessions/${sessionId}/tabs`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          url: args.url || 'about:blank',
          switch_to: args.switch_to ?? true,
        }),
      }
    );

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new Error(errorData.detail || `HTTP ${response.status}`);
    }

    const data = await response.json();

    return {
      success: data.success,
      data: {
        tab_id: data.data?.tab_id,
        url: data.data?.url,
        is_active: data.data?.is_active,
      },
    };
  } catch (error: any) {
    return {
      success: false,
      data: null,
      error: error.message,
    };
  }
}

/**
 * 切换到指定 Tab
 */
async function switchTab(
  currentUrl: string,
  sessionId: string,
  tabId: string
): Promise<ExecutionResult> {
  try {
    const response = await fetch(
      `${currentUrl}/api/v1/browser/sessions/${sessionId}/tabs/${tabId}/focus`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
      }
    );

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new Error(errorData.detail || `HTTP ${response.status}`);
    }

    const data = await response.json();

    return {
      success: data.success,
      data: {
        tab_id: tabId,
        switched: true,
      },
    };
  } catch (error: any) {
    return {
      success: false,
      data: null,
      error: error.message,
    };
  }
}

/**
 * 关闭指定 Tab
 */
async function closeTab(
  currentUrl: string,
  sessionId: string,
  tabId: string
): Promise<ExecutionResult> {
  try {
    const response = await fetch(
      `${currentUrl}/api/v1/browser/sessions/${sessionId}/tabs/${tabId}`,
      {
        method: 'DELETE',
        headers: { 'Content-Type': 'application/json' },
      }
    );

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new Error(errorData.detail || `HTTP ${response.status}`);
    }

    const data = await response.json();

    return {
      success: data.success,
      data: {
        tab_id: tabId,
        closed: true,
      },
    };
  } catch (error: any) {
    return {
      success: false,
      data: null,
      error: error.message,
    };
  }
}

// ==================== 操作执行 ====================

// 项目文件列表的默认深度
const PROJECT_FILES_MAX_DEPTH = 10;

/**
 * 执行浏览器操作（单例模式）
 */
async function executeStepSingleton(
  currentUrl: string,
  actions: Record<string, any>[],
  projectPath?: string
): Promise<{ success: boolean; data: any }> {
  // 构建请求体
  const requestBody: Record<string, any> = { actions };
  
  // 如果有 projectPath，附带项目文件列表
  if (projectPath) {
    requestBody.include_project_files = true;
    requestBody.project_path = projectPath;
    requestBody.project_max_depth = PROJECT_FILES_MAX_DEPTH;
  }
  
  const response = await fetch(`${currentUrl}/api/v1/browser/step`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(requestBody),
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.detail || `HTTP ${response.status}`);
  }

  const data = await response.json();
  return { success: data.success, data: data.data };
}

/**
 * 执行浏览器操作（Session 模式）
 */
async function executeStepSession(
  currentUrl: string,
  sessionId: string,
  actions: Record<string, any>[],
  tabId?: string
): Promise<{ success: boolean; data: any }> {
  const response = await fetch(
    `${currentUrl}/api/v1/browser/sessions/${sessionId}/step`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        actions,
        tab_id: tabId,
      }),
    }
  );

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.detail || `HTTP ${response.status}`);
  }

  const data = await response.json();
  return { success: data.success, data: data.data };
}

// ==================== 截图处理 ====================

/**
 * 处理截图，存入 message.screenshots
 * 
 * 复用 'cua' card type，因为 Browser Use 本质上也是一种 Computer Use Agent。
 * 找到第一个没有 screenshotIndex 的 CUA card 并关联截图。
 */
function processScreenshot(
  screenshot_base64: string,
  setMessages: React.Dispatch<React.SetStateAction<Message[]>>,
  botMessageId: string
): void {
  setMessages((prev) =>
    prev.map((msg) => {
      if (msg.id !== botMessageId) return msg;

      const screenshots = msg.screenshots || [];
      const newIndex = screenshots.length;

      // 找到最后一个 CUA card（非搜索类），更新为最新截图
      let targetBlockIndex = -1;
      for (let i = msg.blocks.length - 1; i >= 0; i--) {
        const block = msg.blocks[i];
        if (
          block.type === 'card' &&
          block.card.type === 'cua' &&
          !block.card.searchResult
        ) {
          targetBlockIndex = i;
          break;
        }
      }

      const updatedBlocks = msg.blocks.map((block, idx) => {
        if (
          idx === targetBlockIndex &&
          block.type === 'card' &&
          block.card.type === 'cua'
        ) {
          return {
            ...block,
            card: { ...block.card, screenshotIndex: newIndex },
          };
        }
        return block;
      });

      return {
        ...msg,
        screenshots: [...screenshots, screenshot_base64],
        blocks: updatedBlocks,
      };
    })
  );
}

// ==================== 主入口 ====================

/**
 * 处理 Browser tool_call（主入口）
 *
 * 根据动作类型和参数决定使用单例模式还是 Session 模式
 * 
 * @param projectPath 项目路径（可选，暂未使用，预留接口）
 */
export async function handleToolCall(
  currentUrl: string,
  name: string,
  args: Record<string, any>,
  setMessages: React.Dispatch<React.SetStateAction<Message[]>>,
  botMessageId: string,
  projectPath?: string
): Promise<ExecutionResult> {
  logRouter('browserHandler.handleToolCall: name=%s args=%o', name, args);
  // TODO: projectPath 暂未使用，浏览器截图通过 page_state 获取

  try {
    const actionName = name as BrowserActionName;
    const sessionId = args.session_id;
    const tabId = args.tab_id;

    // ==================== 连接管理动作（单例模式）====================
    if (CONNECTION_MANAGEMENT_ACTIONS.includes(actionName)) {
      switch (actionName) {
        case 'connect':
          return await connect(currentUrl, args);

        case 'attach':
          return await attach(currentUrl, args);

        case 'disconnect':
          return await disconnect(currentUrl);

        case 'status':
          return await getStatus(currentUrl);
      }
    }

    // ==================== Session 管理动作（多实例模式）====================
    if (SESSION_MANAGEMENT_ACTIONS.includes(actionName)) {
      switch (actionName) {
        case 'create_session':
          return await createSession(currentUrl, args);

        case 'attach_session':
          return await attachSession(currentUrl, args);

        case 'list_sessions':
          return await listSessions(currentUrl);

        case 'close_session':
          if (!sessionId) {
            return {
              success: false,
              data: null,
              error: 'session_id is required for close_session',
            };
          }
          return await closeSession(currentUrl, sessionId);
      }
    }

    // ==================== Tab 管理动作 ====================
    // 注意：switch_tab / close_tab 在单例模式（无 session_id）下，
    // 需要跳过此处，走普通操作路径由 controller.execute_action 处理
    if (TAB_MANAGEMENT_ACTIONS.includes(actionName)) {
      if (sessionId) {
        // Session 模式：通过 Session API 处理
        switch (actionName) {
          case 'list_tabs':
            return await listTabs(currentUrl, sessionId);

          case 'create_tab':
            return await createTab(currentUrl, sessionId, args);

          case 'switch_tab':
            if (!tabId) {
              return {
                success: false,
                data: null,
                error: 'tab_id is required for switch_tab',
              };
            }
            return await switchTab(currentUrl, sessionId, tabId);

          case 'close_tab':
            if (!tabId) {
              return {
                success: false,
                data: null,
                error: 'tab_id is required for close_tab',
              };
            }
            return await closeTab(currentUrl, sessionId, tabId);
        }
      } else if (actionName !== 'switch_tab' && actionName !== 'close_tab') {
        // list_tabs / create_tab 在单例模式下仍然需要 session_id
        return {
          success: false,
          data: null,
          error: `session_id is required for ${actionName}`,
        };
      }
      // switch_tab / close_tab 无 session_id 时，fall through 到普通操作路径
    }

    // ==================== stop 动作 ====================
    if (actionName === 'stop') {
      return {
        success: true,
        data: { stopped: true },
      };
    }

    // ==================== 普通操作 ====================
    // 构建 action 对象（移除 session_id，因为它不是动作参数）
    // 注意：tab_id 对于 switch_tab/close_tab 是必须的动作参数，不能删除
    const actionArgs = { ...args };
    delete actionArgs.session_id;
    if (actionName !== 'switch_tab' && actionName !== 'close_tab') {
      delete actionArgs.tab_id;
    }

    const action: Record<string, any> = {
      action: actionName,
      ...actionArgs,
    };

    // 对于非 screenshot/page_state 动作，追加短暂等待以便获取最新状态
    const actions: Record<string, any>[] = [action];
    if (!['screenshot', 'page_state', 'wait'].includes(actionName)) {
      actions.push({ action: 'wait', seconds: 0.3 });
    }

    // 根据是否有 session_id 选择 API
    let result: { success: boolean; data: any };

    if (sessionId) {
      // Session 模式
      result = await executeStepSession(currentUrl, sessionId, actions, tabId);
    } else {
      // 单例模式
      result = await executeStepSingleton(currentUrl, actions, projectPath);
    }

    // 处理截图
    const pageState = result.data?.page_state;
    if (pageState?.screenshot_base64) {
      processScreenshot(pageState.screenshot_base64, setMessages, botMessageId);
    }

    // 返回结果
    return {
      success: result.success,
      data: {
        action_results: result.data?.action_results,
        page_state: pageState
          ? {
              url: pageState.url,
              title: pageState.title,
              element_count: pageState.element_count,
              elements: pageState.elements,
              project_files: pageState.project_files,
              // Tab 信息（让 AI 知道当前浏览器有哪些标签页）
              tabs: pageState.tabs,
              tab_count: pageState.tab_count,
              active_tab_index: pageState.active_tab_index,
              // 截图已单独处理，不在 data 中重复返回
            }
          : undefined,
        screenshot: pageState?.screenshot_base64,
        project_files: pageState?.project_files,
      },
    };
  } catch (error: any) {
    console.error('[BrowserHandler] handleToolCall failed:', error);
    return {
      success: false,
      data: null,
      error: error.message,
    };
  }
}

// ==================== 导出辅助函数（供外部调用） ====================

export {
  // 连接管理（单例模式）
  connect,
  attach,
  disconnect,
  getStatus,
  // Session 管理（多实例模式）
  createSession,
  attachSession,
  listSessions,
  closeSession,
  // Tab 管理
  listTabs,
  createTab,
  switchTab,
  closeTab,
  // 操作执行
  executeStepSingleton,
  executeStepSession,
};

// 导出类型
export type { SessionInfo, TabInfo, ElementInfo, PageState, ActionResult };
