"""
Pydantic 模型定义
"""
from typing import Any, Dict, Optional
from pydantic import BaseModel


class ActionRequest(BaseModel):
    """通用动作请求"""
    action: str
    # 鼠标相关
    x: Optional[int] = None
    y: Optional[int] = None
    button: Optional[str] = "left"
    # 键盘相关
    text: Optional[str] = None
    key: Optional[str] = None
    keys: Optional[str] = None  # 组合键，如 "ctrl+c"
    # 滚动相关
    clicks: Optional[int] = 1
    scroll_x: Optional[int] = 0
    scroll_y: Optional[int] = 0


class ActionResponse(BaseModel):
    """通用动作响应"""
    success: bool
    error: Optional[str] = None
    data: Optional[Dict[str, Any]] = None


class CmdRequest(BaseModel):
    """兼容 cua-computer-server 的命令请求格式"""
    command: str
    params: Optional[Dict[str, Any]] = None


