"""
Workflow 模块 - AI_Run 工作流执行系统

主要功能：
1. 向 AI_Run 服务发送请求
2. 转发 AI_Run 的消息给前端
3. 管理工作流执行状态

模块结构：
- executor.py: 核心调度器
- ai_run_client.py: AI_Run HTTP 客户端
- interaction_manager.py: 异步交互管理
- constants.py: 常量配置
- handlers/: 事件处理器
  - screenshot_handler.py: 截图处理
  - tool_call_handler.py: tool_call 处理
  - cua_handler.py: CUA 请求处理
- utils/: 工具函数
  - message_logger.py: 消息落盘
  - loop_detector.py: 循环检测
  - action_normalizer.py: 动作格式转换

示例使用：

```python
from useit_studio.gateway.services.workflow import WorkflowExecutor, WorkflowInteractionManager

# 创建执行器
executor = WorkflowExecutor()
interaction_manager = WorkflowInteractionManager()

# 执行工作流
async for event in executor.execute(
    workflow_id="xxx",
    user_input="用户输入",
    interaction_manager=interaction_manager,
):
    print(event)
```
"""

from .models import (
    InputType,
    StepInput,
    StepType,
    WorkflowConfig,
    WorkflowStep,
    create_cua_then_rag_workflow,
    create_channel_comparison_workflow,
)
from .executor import WorkflowExecutor, AIRunWorkflowExecutor
from .interaction_manager import WorkflowInteractionManager
from .ai_run_client import AIRunClient, CUAEventConverter
from .exceptions import (
    WorkflowExecutionError,
    ScreenshotAcquisitionError,
    NetworkError,
    AIRunServiceError,
    InfiniteLoopError,
    WorkflowValidationError,
)

# Handlers (可选导出，用于高级用例)
from .handlers import ScreenshotHandler, ToolCallHandler, ActionExecutor, CUARequestHandler

# Utils (可选导出，用于高级用例)
from .utils import LoopDetector, log_message, normalize_action_for_local_engine

__all__ = [
    # Models
    "InputType",
    "StepInput",
    "StepType",
    "WorkflowConfig",
    "WorkflowStep",
    # Executor
    "WorkflowExecutor",
    "AIRunWorkflowExecutor",
    # Interaction Manager
    "WorkflowInteractionManager",
    # AI_Run Integration
    "AIRunClient",
    "CUAEventConverter",
    # Exceptions
    "WorkflowExecutionError",
    "ScreenshotAcquisitionError",
    "NetworkError",
    "AIRunServiceError",
    "InfiniteLoopError",
    "WorkflowValidationError",
    # Handlers
    "ScreenshotHandler",
    "ToolCallHandler",
    "ActionExecutor",
    "CUARequestHandler",
    # Utils
    "LoopDetector",
    "log_message",
    "normalize_action_for_local_engine",
    # Helper functions (Legacy)
    "create_cua_then_rag_workflow",
    "create_channel_comparison_workflow",
]
