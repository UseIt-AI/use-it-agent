"""
Studio Backend API（OpenAPI 前缀 ``/api/v1``）

- ``POST /agent`` — AI Native Orchestrator，NDJSON SSE，转发至 AI_Run ``/agent``
- ``POST /workflow/callback/{request_id}`` — Local Engine / 前端执行结果回调
"""

import asyncio
import json
import traceback
import datetime
import time
import logging
import uuid
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from useit_studio.gateway.services.workflow import WorkflowInteractionManager
from useit_studio.gateway.services.workflow.executor import AgentExecutor
from useit_studio.gateway.services.workflow.event_adapter import create_adapter
from useit_studio.gateway.services.workflow.attachment_resolver import hydrate_attached_images


logger = logging.getLogger(__name__)


# ===== 消息落盘功能 =====
MESSAGE_LOG_DIR = Path("/tmp/workflow_messages")


def _log_callback_to_file(request_id: str, request_data: dict, result_data: dict):
    """将 callback 请求落盘"""
    try:
        MESSAGE_LOG_DIR.mkdir(parents=True, exist_ok=True)
        today = datetime.datetime.now().strftime("%Y%m%d")
        log_file = MESSAGE_LOG_DIR / f"callbacks_{today}.jsonl"
        
        log_entry = {
            "timestamp": datetime.datetime.now().isoformat(),
            "request_id": request_id,
            "request_data": request_data,
            "result_data": _sanitize_for_log(result_data),
        }
        
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(log_entry, ensure_ascii=False, default=str) + "\n")
    except Exception as e:
        print(f"[Callback Log] 落盘失败: {e}")


def _sanitize_for_log(data: Any) -> Any:
    """清理数据，移除过大的 base64 字段"""
    if isinstance(data, dict):
        result = {}
        for key, value in data.items():
            if key in ("screenshot", "screenshot_base64", "image_base64", "image"):
                if isinstance(value, str) and len(value) > 100:
                    result[key] = f"<base64_image, length={len(value)}>"
                else:
                    result[key] = value
            else:
                result[key] = _sanitize_for_log(value)
        return result
    elif isinstance(data, list):
        return [_sanitize_for_log(item) for item in data]
    else:
        return data

router = APIRouter()


# ==================== Request/Response Models ====================

class WorkflowCallbackRequest(BaseModel):
    """工作流回调请求"""
    result: Optional[Any] = Field(None, description="客户端执行结果")
    status: str = Field("success", description="执行状态: success/error")
    error: Optional[str] = Field(None, description="错误信息")


class AttachedFileInfo(BaseModel):
    """附加文件信息"""
    path: str = Field(..., description="文件相对路径")
    name: str = Field(..., description="文件名")
    type: str = Field(..., description="类型: file 或 folder")


class AttachedImageInfo(BaseModel):
    """附加图片信息"""
    name: str = Field(..., description="图片名")
    base64: str = Field(..., description="图片 base64 数据（可含 data URI 前缀）")
    mime_type: Optional[str] = Field(None, description="图片 MIME 类型")


class AgentExecuteRequest(BaseModel):
    """AI Orchestrator 请求"""
    message: str = Field(..., description="用户输入")
    project_id: Optional[str] = Field(None, description="项目 ID（透传给下游）")
    chat_id: Optional[str] = Field(None, description="会话 ID（透传给下游）")
    workflow_id: Optional[str] = Field(None, description="用户在 UI 中选择的 Workflow ID")
    user_id: Optional[str] = Field(None, description="用户 ID")
    task_id: Optional[str] = Field(None, description="任务 / 会话 ID (跨 round-trip 复用)")
    workflow_run_id: Optional[str] = Field(None, description="工作流执行实例 ID")
    trigger_message_id: Optional[str] = Field(
        None,
        description="兼容字段：本地网关不使用，可省略",
    )
    app_capabilities: Optional[list] = Field(None, description="前端 app action schema 列表")
    workflow_capabilities: Optional[list] = Field(None, description="前端可用 workflow 列表")
    attached_files: Optional[list[AttachedFileInfo]] = Field(None, description="附加文件")
    attached_images: Optional[list[AttachedImageInfo]] = Field(None, description="附加图片")
    api_key_source: Optional[dict] = Field(None, description="API key source config")
    additional_context: Optional[str] = Field(None, description="额外上下文")
    uia_data: Optional[dict] = Field(
        None,
        description=(
            "机器环境快照（由前端 local-engine 采集）。典型 key 包括 "
            "active_window / open_windows / installed_apps；agent-internal "
            "会把这些 key 渲染进 planner prompt 的 ## Current Environment State。"
        ),
    )
    chat_history_limit: Optional[int] = Field(
        20,
        description="兼容字段：本地网关不从远端加载聊天记录，可省略",
    )


# ==================== API Endpoints ====================

@router.post("/workflow/callback/{request_id}")
async def workflow_callback(request_id: str, request: WorkflowCallbackRequest):
    """
    接收客户端回调结果

    用于在远程执行模式下，客户端（Frontend/LocalEngine）将执行结果返回给服务端
    """
    # ===== 性能监测：记录回调请求到达时间 =====
    perf_callback_start = time.time()
    perf_callback_time_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    
    # 计算请求体大小（用于分析网络传输）
    result_size_kb = 0
    if request.result and isinstance(request.result, dict):
        try:
            result_size_kb = len(json.dumps(request.result)) / 1024
        except:
            pass
    
    print(f"[PERF_CALLBACK] 📥 收到回调请求 [时间: {perf_callback_time_str}] request_id={request_id[:12]}... [body_size: {result_size_kb:.1f}KB]")
    
    manager = WorkflowInteractionManager()

    # 调试：打印收到的原始数据
    print(f"[Callback] request_id={request_id}")
    print(f"[Callback] status={request.status}")
    print(f"[Callback] result type={type(request.result)}")
    if isinstance(request.result, dict):
        print(f"[Callback] result keys={list(request.result.keys())}")

    # 构造结果对象
    result_data = request.result
    if request.status == "error":
        result_data = {"status": "error", "error": request.error}
    elif isinstance(result_data, dict):
        if "status" not in result_data:
            result_data["status"] = "success"
    else:
        result_data = {"status": "success", "result": result_data}

    print(f"[Callback] final result_data keys={list(result_data.keys()) if isinstance(result_data, dict) else 'N/A'}")

    # ===== 消息落盘 =====
    _log_callback_to_file(request_id, {
        "status": request.status,
        "error": request.error,
        "result_keys": list(request.result.keys()) if isinstance(request.result, dict) else str(type(request.result)),
    }, result_data)

    # ===== 性能监测：记录 submit_result 前的时间 =====
    perf_before_submit = time.time()
    
    if manager.submit_result(request_id, result_data):
        # ===== 性能监测：记录回调处理完成时间 =====
        perf_callback_end = time.time()
        perf_callback_duration = perf_callback_end - perf_callback_start
        perf_submit_duration = perf_callback_end - perf_before_submit
        perf_end_time_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        print(f"[PERF_CALLBACK] ✅ 回调处理完成 [时间: {perf_end_time_str}] [总耗时: {perf_callback_duration*1000:.2f}ms] [submit耗时: {perf_submit_duration*1000:.2f}ms]")
        return {"status": "ok"}

    raise HTTPException(status_code=404, detail="Request ID not found or already processed")


@router.post("/agent")
async def execute_agent(request: AgentExecuteRequest):
    """
    Agent 端点：将请求转发至本机 AI_Run ``/agent``（固定最小工作流），
    以 NDJSON SSE 流式返回事件。无远端认证；上下文由请求体与 AI_Run 提供。
    """
    try:
        task_id = request.task_id or str(uuid.uuid4())
        user_id = request.user_id or "anonymous"
        user_api_keys: Optional[dict] = None
        chat_history: list = []

        executor = AgentExecutor()
        interaction_manager = WorkflowInteractionManager()
        adapter = create_adapter()

        attached_files_data = None
        if request.attached_files:
            attached_files_data = [f.model_dump() for f in request.attached_files]
        attached_images_data = None
        if request.attached_images:
            attached_images_data = [img.model_dump() for img in request.attached_images]

        if attached_images_data:
            attached_images_data = hydrate_attached_images(attached_images_data)

        async def event_generator():
            try:
                yield json.dumps({
                    "type": "project_info",
                    "content": {
                        "task_id": task_id,
                        "workflow_run_id": request.workflow_run_id,
                        "chat_id": request.chat_id,
                        "project_id": request.project_id,
                        "user_id": user_id,
                    },
                }) + "\n"

                _uia_keys = list(request.uia_data.keys()) if request.uia_data else []
                _uia_bytes = len(json.dumps(request.uia_data, ensure_ascii=False)) if request.uia_data else 0
                logger.info(
                    "[/agent] incoming uia_data task_id=%s keys=%s bytes=%s",
                    task_id, _uia_keys, _uia_bytes,
                )

                async for event in executor.execute(
                    query=request.message,
                    task_id=task_id,
                    user_id=user_id,
                    interaction_manager=interaction_manager,
                    project_id=request.project_id,
                    chat_id=request.chat_id,
                    app_capabilities=request.app_capabilities,
                    workflow_capabilities=request.workflow_capabilities,
                    attached_files=attached_files_data,
                    attached_images=attached_images_data,
                    user_api_keys=user_api_keys,
                    additional_context=request.additional_context,
                    workflow_id=request.workflow_id,
                    uia_data=request.uia_data,
                    workflow_run_id=request.workflow_run_id,
                    chat_history=chat_history,
                ):
                    adapted_events = adapter.adapt(event)
                    for adapted_event in adapted_events:
                        yield json.dumps(adapted_event) + "\n"

                for final_event in adapter.finalize():
                    yield json.dumps(final_event) + "\n"

            except asyncio.CancelledError:
                # 前端主动 abort 或客户端断连，属于正常控制流，
                # 必须 re-raise 让 Starlette/uvicorn 正常收尾 ASGI task。
                logger.info(
                    "[/agent] client cancelled SSE task_id=%s workflow_run_id=%s (user stop or disconnect)",
                    task_id,
                    request.workflow_run_id,
                )
                raise
            except Exception as e:
                traceback.print_exc()
                yield json.dumps({"type": "error", "message": str(e)}) + "\n"

        return StreamingResponse(event_generator(), media_type="application/x-ndjson")

    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
