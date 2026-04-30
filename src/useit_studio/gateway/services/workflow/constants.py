"""
工作流执行相关常量配置
"""
from pathlib import Path
from useit_studio.gateway.settings import get_ai_run_url, message_log_enabled, workflow_debug_enabled

# ===== 日志配置 =====
MESSAGE_LOG_DIR = Path("/tmp/workflow_messages")
MESSAGE_LOG_ENABLED = message_log_enabled()

# ===== 执行控制 =====
MAX_ITERATIONS = 130  # 最大自动循环次数
MAX_SCREENSHOT_ATTEMPTS = 3  # 截图获取最大重试次数
SCREENSHOT_RETRY_DELAY = 1.0  # 截图重试间隔（秒）
MIN_SCREENSHOT_SIZE = 1024  # 最小截图大小（bytes）
MIN_SCREENSHOT_DIMENSION = 100  # 最小截图尺寸（pixels）

# ===== 超时配置 =====
CALLBACK_TIMEOUT = 60.0  # 普通回调超时
TOOL_CALL_TIMEOUT = 120.0  # tool_call 回调超时
CUA_REQUEST_TIMEOUT = 60  # CUA 请求超时
HTTP_REQUEST_TIMEOUT = 30.0  # HTTP 请求超时

# ===== 循环检测 =====
LOOP_DETECTOR_MAX_SAME_STATE = 5  # 最大相同状态次数
LOOP_DETECTOR_HISTORY_SIZE = 6  # 状态历史记录大小

# ===== 调试开关 =====
WORKFLOW_DEBUG = workflow_debug_enabled()

# ===== 默认值 =====
# 注意：DEFAULT_WORKFLOW_ID 已弃用，不应使用字符串作为默认值
# 因为数据库期望 UUID 格式。workflow_id 应该允许为 None。
# 保留此常量仅用于向后兼容，新代码不应使用它。
DEFAULT_WORKFLOW_ID = None
DEFAULT_AI_RUN_URL = get_ai_run_url()
# 模块级快照供兼容；运行时请使用 get_ai_run_url()。

# ===== 动作类型别名映射 =====
ACTION_TYPE_ALIASES = {
    "doubleclick": "double_click",
    "double-click": "double_click",
    "rightclick": "click",
    "right-click": "click",
    "mouse_move": "move",
    "mousemove": "move",
    "key": "keypress",
    "key_press": "keypress",
    "key-press": "keypress",
}

# ===== 需要特殊处理的右键动作 =====
RIGHT_CLICK_ACTIONS = ("right_click", "rightclick", "right-click")
