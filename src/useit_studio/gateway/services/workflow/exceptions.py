"""
工作流执行相关的自定义异常类型
"""

class WorkflowExecutionError(Exception):
    """工作流执行基础异常"""
    def __init__(self, message: str, error_code: str = None, recoverable: bool = False):
        super().__init__(message)
        self.error_code = error_code
        self.recoverable = recoverable


class ScreenshotAcquisitionError(WorkflowExecutionError):
    """截图获取失败异常"""
    def __init__(self, message: str = "无法获取有效截图"):
        super().__init__(
            message=message,
            error_code="SCREENSHOT_FAILED",
            recoverable=False
        )


class NetworkError(WorkflowExecutionError):
    """网络连接异常"""
    def __init__(self, message: str = "网络连接失败"):
        super().__init__(
            message=message,
            error_code="NETWORK_ERROR",
            recoverable=True
        )


class AIRunServiceError(WorkflowExecutionError):
    """AI_Run服务异常"""
    def __init__(self, message: str = "AI_Run服务不可用"):
        super().__init__(
            message=message,
            error_code="AI_RUN_UNAVAILABLE",
            recoverable=True
        )


class InfiniteLoopError(WorkflowExecutionError):
    """无限循环检测异常"""
    def __init__(self, message: str = "检测到无限循环"):
        super().__init__(
            message=message,
            error_code="INFINITE_LOOP_DETECTED",
            recoverable=False
        )


class WorkflowValidationError(WorkflowExecutionError):
    """工作流验证异常"""
    def __init__(self, message: str = "工作流验证失败"):
        super().__init__(
            message=message,
            error_code="WORKFLOW_VALIDATION_FAILED",
            recoverable=False
        )