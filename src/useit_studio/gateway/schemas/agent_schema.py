from pydantic import BaseModel, ConfigDict
from typing import Optional, List

class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    message: str
    images: Optional[List[str]] = None
    template_name: str = "excavated_canal"
    session_id: Optional[str] = None
    user_id: Optional[str] = None
    task_id: Optional[str] = None  # 任务 ID，用于 ProjectManager 管理工作副本
    # AI_Run 集成选项
    use_ai_run: bool = False  # 是否使用 AI_Run 后端
