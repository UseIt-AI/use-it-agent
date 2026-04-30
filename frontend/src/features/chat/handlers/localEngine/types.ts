/**
 * Local Engine Handler 类型定义
 * 
 * 定义与 Local Engine 通信相关的所有类型
 */

import { Message } from '../types';

// ==================== 通用类型 ====================

/**
 * Handler 上下文
 */
export interface LocalEngineContext {
  /** Local Engine URL */
  localEngineUrl: string;
  /** 获取最新的 Local Engine URL（VM IP 可能变化） */
  getLocalEngineUrlFresh?: () => Promise<string>;
  /** 更新消息的函数 */
  setMessages: React.Dispatch<React.SetStateAction<Message[]>>;
  /** 当前 bot 消息 ID */
  botMessageId: string;
  /** 用户 ID */
  userId?: string;
  /** 聊天 ID */
  chatId?: string;
  /** 工作流运行 ID */
  workflowRunId?: string;
}

/**
 * 执行结果
 */
export interface ExecutionResult {
  success: boolean;
  data: any;
  error?: string;
}

// ==================== Client Request 类型（旧格式，保留兼容） ====================

/**
 * Client Request 事件
 * 
 * 用于 GUI 操作：截图、执行动作、屏幕信息
 * 
 * @deprecated 将逐步迁移到 ToolCallEvent
 */
export interface ClientRequestEvent {
  type: 'client_request';
  requestId: string;
  action: 'screenshot' | 'execute' | 'execute_actions' | 'screen_info';
  params?: any;
}

// ==================== Tool Call 类型（新标准格式） ====================

/**
 * Tool Call 目标类型
 *
 * `user` 为特殊 target：表示该 tool_call 不是调度给 Local Engine / App，而是
 * 由 Orchestrator 的 `ask_user` 工具发起的"向用户提问"请求。前端需要弹对话框，
 * 等用户给出答复后再回调 Backend。详见 handlers/userInteractionHandler.ts。
 */
export type ToolCallTarget =
  | 'gui'
  | 'word'
  | 'excel'
  | 'ppt'
  | 'browser'
  | 'autocad'
  | 'app'
  | 'workflow'
  | 'code'
  | 'user';

/**
 * GUI 动作名称
 */
export type GUIActionName = 
  | 'click'
  | 'double_click'
  | 'type'
  | 'key'
  | 'scroll'
  | 'drag'
  | 'move'
  | 'screenshot'
  | 'wait'
  | 'stop';

/**
 * Office 动作名称
 */
export type OfficeActionName = 'execute_action' | 'execute_code' | 'execute_script' | 'step' | 'stop';

/**
 * AutoCAD 动作名称
 */
export type AutoCADActionName =
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
 * Browser 动作名称
 */
export type BrowserActionName =
  // 连接管理（单例模式）
  | 'connect'
  | 'attach'
  | 'disconnect'
  | 'status'
  // Session 管理（多实例模式）
  | 'create_session'
  | 'attach_session'
  | 'list_sessions'
  | 'close_session'
  // Tab 管理
  | 'list_tabs'
  | 'create_tab'
  | 'switch_tab'
  | 'close_tab'
  // 导航
  | 'go_to_url'
  | 'go_back'
  | 'go_forward'
  | 'refresh'
  // 元素交互
  | 'click_element'
  | 'input_text'
  // 滚动
  | 'scroll_down'
  | 'scroll_up'
  // 键盘
  | 'press_key'
  // 其他
  | 'wait'
  | 'screenshot'
  | 'extract_content'
  | 'page_state'
  | 'stop';

/**
 * Code 动作名称
 */
export type CodeActionName = 'execute_python' | 'stop';

// ==================== Ask User（target = "user"）类型 ====================

/**
 * `ask_user` inline-question 渲染模式。
 * - `confirm`:       2~3 个选项的单选（默认项高亮，点按即提交）
 * - `choose`:        ≥2 个选项的单选（垂直一行一个，点按即提交）
 * - `multi_choose`:  ≥2 个选项的多选（复选框 + Submit 按钮）
 * - `input`:         自由文本输入框（`allow_free_text` 后端保证为 true）
 */
export type AskUserKind = 'confirm' | 'choose' | 'multi_choose' | 'input';

/**
 * `ask_user` 一个选项。
 * `id` 由 Backend 保证是非空稳定字符串，回调时原样送回。
 */
export interface AskUserOption {
  id: string;
  label: string;
}

/**
 * `ask_user` tool_call 的 `args` 载荷。
 */
export interface AskUserArgs {
  /** 给用户看的问题正文，可含多行 / Markdown 级的换行。 */
  prompt: string;
  /** 渲染模式。 */
  kind: AskUserKind;
  /** 选项列表。confirm/choose 必须 ≥2；input 可以为空。 */
  options: AskUserOption[];
  /** 回车默认触发的选项 id；不在 options 中时视为 null。 */
  default_option_id?: string | null;
  /** 是否同时显示自由文本输入框。kind === 'input' 时始终为 true。 */
  allow_free_text: boolean;
  /** 倒计时秒数；0 表示无限期等待，>0 则到期自动 `dismissed`。 */
  timeout_seconds: number;
}

/**
 * 用户答复，回传给 Backend 的核心负载（匹配 ask_user 前端契约）。
 *
 * - 单选（confirm/choose/input）：`selected_option_id` 为选中的 id 或 null，
 *   `selected_option_ids` 为 `[id]` 或 `[]`。
 * - 多选（multi_choose）：`selected_option_ids` 为被选中的 id 数组（可能为空），
 *   `selected_option_id` 取首个 id（没有则 null），用作后端不理解多选时的回退。
 */
export interface AskUserResponse {
  /** 单选命中的选项 id；未选中任何选项时为 null。多选时为数组首项。 */
  selected_option_id: string | null;
  /** 选中的选项 id 数组（多选使用；单选时为 [id] 或 []）。 */
  selected_option_ids: string[];
  /** 自由文本输入（没有或未启用时为空串）。 */
  free_text: string;
  /** true 表示用户按 Esc/关闭/超时；此时其余字段应为默认值。 */
  dismissed: boolean;
}

/**
 * `ask_user` tool_call 事件（target === 'user'）。
 */
export interface AskUserToolCallEvent extends ToolCallEvent {
  target: 'user';
  name: 'ask_user';
  args: AskUserArgs;
}

/**
 * 标准 Tool Call 事件
 * 
 * 统一的 tool_call 格式，用于 GUI 和 Office 操作
 * 
 * 格式：
 * {
 *   type: "tool_call",
 *   id: "call_xxx",
 *   target: "gui" | "word" | "excel" | "ppt",
 *   name: "click" | "execute_code" | ...,
 *   args: { ... }
 * }
 */
export interface ToolCallEvent {
  type: 'tool_call';
  /** 唯一标识，用于回调 */
  id: string;
  /** 目标应用 */
  target: ToolCallTarget;
  /** 动作名称 */
  name: string;
  /** 动作参数 */
  args: Record<string, any>;
}

/**
 * GUI Tool Call 事件
 */
export interface GUIToolCallEvent extends ToolCallEvent {
  target: 'gui';
  name: GUIActionName;
  args: {
    coordinate?: [number, number];
    text?: string;
    key?: string;
    direction?: 'up' | 'down' | 'left' | 'right';
    amount?: number;
    start_coordinate?: [number, number];
    end_coordinate?: [number, number];
  };
}

/**
 * Office Tool Call 事件
 */
export interface OfficeToolCallEvent extends ToolCallEvent {
  target: 'word' | 'excel' | 'ppt';
  name: OfficeActionName;
  args: {
    // execute_action 模式 (PPT)
    actions?: Array<Record<string, any>>;
    // execute_code 模式
    code?: string;
    language?: string;
    file_path?: string;
    sheet_name?: string;
    operation_intent?: string;
    timeout?: number;
    // execute_script 模式
    skill_id?: string;
    script_path?: string;
    parameters?: Record<string, any>;
  };
}

/**
 * AutoCAD Tool Call 事件
 */
export interface AutoCADToolCallEvent extends ToolCallEvent {
  target: 'autocad';
  name: AutoCADActionName;
  args: {
    // draw_from_json
    data?: {
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
    };
    // execute_python_com
    code?: string;
    // 通用
    timeout?: number;
    return_screenshot?: boolean;
    // snapshot
    include_content?: boolean;
    include_screenshot?: boolean;
    only_visible?: boolean;
    max_entities?: number;
    // open
    file_path?: string;
    read_only?: boolean;
    // close
    save?: boolean;
    // new
    template?: string;
    // activate
    name?: string;
    index?: number;
    // standard_parts
    part_type?: string;
    preset?: string;
    parameters?: Record<string, any>;
    position?: [number, number];
  };
}

/**
 * Browser Tool Call 事件
 */
export interface BrowserToolCallEvent extends ToolCallEvent {
  target: 'browser';
  name: BrowserActionName;
  args: {
    // Session 管理
    session_id?: string;         // 操作哪个 session（不提供则使用单例）
    browser_type?: string;       // create_session 用: 'chrome' | 'edge' | 'auto'
    cdp_url?: string;            // attach_session 用
    headless?: boolean;          // create_session 用
    profile_directory?: string;  // create_session 用
    initial_url?: string;        // create_session 用

    // Tab 管理
    tab_id?: string;
    switch_to?: boolean;

    // 导航
    url?: string;

    // 元素交互
    index?: number;
    text?: string;

    // 滚动
    amount?: number;

    // 键盘
    key?: string;

    // 等待
    seconds?: number;

    // 提取内容
    selector?: string;

    // 页面状态选项
    include_screenshot?: boolean;
    max_elements?: number;
  };
}

/**
 * Code Tool Call 事件
 */
export interface CodeToolCallEvent extends ToolCallEvent {
  target: 'code';
  name: CodeActionName;
  args: {
    code?: string;
    timeout?: number;
    cwd_mode?: 'project' | 'temp';
    /** 相对项目根目录的 .py 路径，落盘后执行并保留 */
    script_path?: string;
    artifacts_glob?: string[];
    max_output_chars?: number;
  };
}

// ==================== 类型守卫函数 ====================

/**
 * 判断是否是标准 tool_call 事件
 */
export function isToolCallEvent(event: any): event is ToolCallEvent {
  return (
    event?.type === 'tool_call' &&
    typeof event?.id === 'string' &&
    typeof event?.target === 'string' &&
    typeof event?.name === 'string'
  );
}

/**
 * 判断是否是 GUI tool_call
 */
export function isGUIToolCall(event: any): event is GUIToolCallEvent {
  return isToolCallEvent(event) && event.target === 'gui';
}

/**
 * 判断是否是 Office tool_call
 */
export function isOfficeToolCall(event: any): event is OfficeToolCallEvent {
  return (
    isToolCallEvent(event) &&
    (event.target === 'word' || event.target === 'excel' || event.target === 'ppt')
  );
}

/**
 * 判断是否是 Browser tool_call
 */
export function isBrowserToolCall(event: any): event is BrowserToolCallEvent {
  return isToolCallEvent(event) && event.target === 'browser';
}

/**
 * 判断是否是 AutoCAD tool_call
 */
export function isAutoCADToolCall(event: any): event is AutoCADToolCallEvent {
  return isToolCallEvent(event) && event.target === 'autocad';
}

/**
 * 判断是否是 Code tool_call
 */
export function isCodeToolCall(event: any): event is CodeToolCallEvent {
  return isToolCallEvent(event) && event.target === 'code';
}

/**
 * 判断是否是 App tool_call（控制应用自身的 UI/功能）
 */
export function isAppToolCall(event: any): event is ToolCallEvent {
  return isToolCallEvent(event) && event.target === 'app';
}

/**
 * 判断是否是 ask_user tool_call（target === 'user'）。
 */
export function isAskUserToolCall(event: any): event is AskUserToolCallEvent {
  return (
    isToolCallEvent(event) &&
    event.target === 'user' &&
    event.name === 'ask_user' &&
    !!event.args &&
    typeof (event.args as any).prompt === 'string'
  );
}

// ==================== 旧格式兼容（将废弃） ====================

/**
 * 旧格式 Office Tool Call 事件
 * 
 * @deprecated 使用新的 ToolCallEvent 格式
 */
export interface LegacyOfficeToolCallEvent {
  type: 'tool_call';
  content?: {
    action: {
      type: 'word_execute_code' | 'excel_execute_code' | 'ppt_execute_code';
      payload?: Record<string, any>;
    };
  };
  action?: {
    type: string;
    [key: string]: any;
  };
  requestId?: string;
}

/**
 * 判断是否是旧格式的 Office tool_call
 * 
 * @deprecated 将逐步移除
 */
export function isLegacyOfficeToolCall(event: any): event is LegacyOfficeToolCallEvent {
  if (event?.type !== 'tool_call') return false;
  
  // 新格式有 target 字段
  if (event?.target) return false;
  
  // 旧格式：content.action.type
  const actionType = event?.content?.action?.type;
  if (actionType && ['word_execute_code', 'excel_execute_code', 'ppt_execute_code'].includes(actionType)) {
    return true;
  }
  
  return false;
}
