"""
AI_Run LangChain 异步流式服务器 (FastAPI)

支持:
- LangChain Planner 流式输出
- LangChain Actor 流式输出
- 新CUA事件格式 (cua_start/delta/update/end)
- 角色区分 (planner/actor)
- 完整的 Token 追踪
- 统一的流式事件格式
- 配置驱动的版本切换
"""

import os
import json
import asyncio
import gc
from datetime import datetime, timedelta, timezone
from typing import Any, AsyncIterator, Dict, Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware

# 旧架构已移除：useit_loop_async_langchain
# from useit_studio.ai_run.loop.useit_loop_async_langchain import useit_loop_async_langchain

from useit_studio.ai_run.utils import LoggerUtils, save_base64_image, get_api_keys

# 事件系统（已简化，暂时保留 import 以便回滚）
# from useit_studio.ai_run.events import StreamEventManager

# CUA Request 管理
from useit_studio.ai_run.request_manager import request_manager

# 本地缓存清理
from useit_studio.ai_run.utils.cache_manager import start_cache_cleanup, get_cache_manager

from useit_studio.ai_run.app_utils import setup_directories, get_or_create_orchestrator

# State Store for elastic scaling
from useit_studio.ai_run.runtime.state_store import StateStoreFactory

# Request-level token tracking
from useit_studio.ai_run.llm_utils.request_token_tracker import (
    get_or_create as get_or_create_tracker,
    set_current as set_current_tracker,
    reset_current as reset_current_tracker,
    remove as remove_tracker,
)

# gui_v2 架构：GUIAgent 在 flow_processor.step() 中按需创建
# from useit_studio.ai_run.node_handler.functional_nodes.computer_use.gui_v2 import GUIAgent

UTC_PLUS_8 = timezone(timedelta(hours=8))

# 使用环境变量配置，支持生产环境部署
RUN_LOG_DIR = os.getenv("RUN_LOG_DIR", "logs/useit_ai_run_logs")

api_keys = get_api_keys()

# Setup
setup_directories()
app_logger = LoggerUtils(component_name="app_async_langchain")


# 未开启 USEIT_FORWARD_THINKING_SSE 时，仍下发的 cua_delta（进度类，非模型自由思考）
_CUA_DELTA_KIND_THINKING_ALLOWLIST = frozenset(
    {
        "search_progress",
        "search_result",
        "extract_progress",
        "extract_result",
        "rag_progress",
    }
)


def _forward_thinking_sse_to_client() -> bool:
    """
    仅当 USEIT_FORWARD_THINKING_SSE 为 1/true/yes/on 时，向 SSE 客户端下发模型思考类流
    （reasoning_delta；以及非白名单的 cua_delta，含 planner/actor 与 Agent 节点的 tool:*）。
    默认未设置：不推送上述内容。
    """
    v = os.getenv("USEIT_FORWARD_THINKING_SSE", "").strip().lower()
    return v in ("1", "true", "yes", "on")


def _should_drop_thinking_sse_event(event: Dict[str, Any]) -> bool:
    if _forward_thinking_sse_to_client():
        return False
    et = event.get("type", "")
    if et == "reasoning_delta":
        return True
    if et != "cua_delta":
        return False
    role = (event.get("kind") or event.get("role") or "").strip().lower()
    if role in _CUA_DELTA_KIND_THINKING_ALLOWLIST:
        return False
    return True

# 嵌入统一网关（``useit_studio.gateway.unified_main``）时由外层 FastAPI 调用 ``ai_run_lifespan``，
# 子应用本身不设 lifespan，避免与 Mount 组合时重复初始化 StateStore。
_EMBED_IN_UNIFIED_GATEWAY = os.getenv("USEIT_UNIFIED_SERVER", "").strip().lower() in (
    "1",
    "true",
    "yes",
    "on",
)


# 应用生命周期管理
@asynccontextmanager
async def ai_run_lifespan(_: FastAPI):
    """应用生命周期管理（独立进程与嵌入 unified 进程共用）"""
    # 启动
    app_logger.logger.info("AI_Run LangChain Async Streaming API starting up...")
    
    # 初始化 StateStore
    state_store = StateStoreFactory.get_store()
    store_stats = state_store.get_stats()
    app_logger.logger.info(f"StateStore initialized: type={store_stats.get('type')}, stats={store_stats}")
    
    # 启动本地缓存清理后台线程
    cache_manager = start_cache_cleanup()
    cache_stats = cache_manager.get_stats()
    app_logger.logger.info(f"CacheManager started: {cache_stats}")
    
    yield
    
    # 关闭
    app_logger.logger.info("AI_Run LangChain Async Streaming API shutting down...")
    
    # 停止缓存清理线程
    cache_manager.stop()
    
    # 关闭 StateStore
    StateStoreFactory.close_store()
    app_logger.logger.info("StateStore closed")
    
    # 强制垃圾回收以清理未关闭的连接
    collected = gc.collect()
    app_logger.logger.info(f"Garbage collection completed, collected {collected} objects")


# FastAPI app
app = FastAPI(
    title="AI_Run LangChain Async Streaming API",
    description="基于 LangChain 的异步流式 Computer Use Agent - 支持新CUA事件格式",
    version="3.1.0",
    lifespan=None if _EMBED_IN_UNIFIED_GATEWAY else ai_run_lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global state（内存缓存）；持久化由 StateStore / Orchestrator 内部处理
task_id_to_orchestrator: Dict = {}  # AgentOrchestrator 实例（POST /agent）

# CUA Request Manager (全局单例) - 从 request_manager 模块导入

# 旧组件已移除，现在使用 gui_v2 的 GUIAgent
# GUIAgent 在 flow_processor.step() 中按需创建
app_logger.logger.info("GUI V2 architecture initialized - GUIAgent created on demand")


@app.get("/")
async def root():
    """健康检查"""
    return {
        "status": "ok",
        "message": "AI_Run V2 Async Streaming API",
        "version": "4.0.0",
        "local_oss": True,
        "features": ["gui_v2", "cua_events", "streaming"],
        "event_format": "new_cua_format",
        "supported_events": ["cua_start", "cua_delta", "cua_update", "cua_end"],
    }

@app.get("/health")
async def health_check():
    """标准健康检查端点"""
    return {
        "status": "healthy",
        "service": "AI_Run LangChain Async Streaming API",
        "version": "3.1.0",
        "timestamp": datetime.now(UTC_PLUS_8).isoformat()
    }


@app.get("/config")
async def get_config():
    """获取当前配置信息"""
    state_store = StateStoreFactory.get_store()
    return {
        "architecture": "gui_v2",
        "actor_model": os.getenv("ACTOR_MODEL", "gemini-3-flash-preview"),
        "planner_model": os.getenv("PLANNER_MODEL", "gemini-3-flash-preview"),
        "environment_variables": {
            "ACTOR_MODEL": os.getenv("ACTOR_MODEL"),
            "PLANNER_MODEL": os.getenv("PLANNER_MODEL"),
        },
        "state_store": state_store.get_stats(),
    }


@app.get("/state-store/stats")
async def get_state_store_stats():
    """获取状态存储统计信息"""
    state_store = StateStoreFactory.get_store()
    return {
        "status": "ok",
        "stats": state_store.get_stats(),
        "active_tasks": state_store.list_active_tasks(),
    }


@app.get("/cache/stats")
async def get_cache_stats():
    """获取本地缓存统计信息"""
    return {"status": "ok", "cache": get_cache_manager().get_stats()}


@app.post("/cache/cleanup")
async def trigger_cache_cleanup():
    """手动触发一次缓存清理"""
    result = get_cache_manager().run_cleanup_now()
    return {"status": "ok", "result": result, "cache": get_cache_manager().get_stats()}


@app.get("/state-store/task/{task_id}")
async def get_task_state(task_id: str):
    """获取指定任务的状态（调试用）"""
    state_store = StateStoreFactory.get_store()
    
    runtime_state = state_store.load_runtime_state(task_id)
    session_progress = state_store.load_session_progress(task_id)
    
    if not runtime_state and not session_progress:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    
    return {
        "task_id": task_id,
        "has_runtime_state": runtime_state is not None,
        "has_session_progress": session_progress is not None,
        "is_alive": state_store.is_task_alive(task_id),
        "runtime_state": runtime_state,
        "session_progress": session_progress,
    }


@app.delete("/state-store/task/{task_id}")
async def delete_task_state(task_id: str):
    """删除指定任务的状态（调试用）"""
    state_store = StateStoreFactory.get_store()
    
    # 同时从内存缓存中删除
    task_id_to_orchestrator.pop(task_id, None)
    remove_tracker(task_id)

    deleted = state_store.delete_task_state(task_id)
    
    return {
        "status": "ok" if deleted else "not_found",
        "task_id": task_id,
        "deleted": deleted,
    }


async def iter_agent_orchestrator_events(
    initial_data: Dict[str, Any],
) -> AsyncIterator[Dict[str, Any]]:
    """
    与 ``POST /agent`` 相同语义的事件流（进程内直连与 HTTP SSE 共用）：
    仅驱动内置最小工作流，无编排器 LLM。

    Raises:
        ValueError: 缺少 ``task_id`` / ``query``。
    """
    data = dict(initial_data)
    for field in ("task_id", "query"):
        if field not in data:
            raise ValueError(f"Missing required field: {field}")

    original_request_data = dict(data)

    project_id = data.get("project_id")
    chat_id = data.get("chat_id")

    execution_result = data.pop("execution_result", None)
    if execution_result:
        if isinstance(execution_result, dict):
            keys = list(execution_result.keys())
            status = execution_result.get("status")
            err = execution_result.get("error") or execution_result.get("errors")
            err_preview = ""
            if err is not None:
                try:
                    err_str = (
                        err
                        if isinstance(err, str)
                        else json.dumps(err, ensure_ascii=False, default=str)
                    )
                except Exception:
                    err_str = repr(err)
                err_preview = err_str[:600]
            print(
                f"[ORCHESTRATOR] Received execution_result: keys={keys} "
                f"status={status!r} error={err_preview!r}"
            )
        else:
            print(
                f"[ORCHESTRATOR] Received execution_result: non-dict {type(execution_result).__name__}"
            )

    effective_api_keys = api_keys.copy()
    user_api_keys = data.get("user_api_keys")
    if user_api_keys and isinstance(user_api_keys, dict):
        effective_api_keys.update(user_api_keys)

    run_log_dir = os.getenv("RUN_LOG_DIR", "logs/useit_ai_run_logs")

    screenshot_base64 = data.pop("screenshot", None)
    screenshot_path = ""

    orch_model = data.get("planner_model", "gemini-3-flash-preview")
    orchestrator = get_or_create_orchestrator(
        task_id_to_orchestrator=task_id_to_orchestrator,
        task_id=data["task_id"],
        planner_model=orch_model,
        log_root=run_log_dir,
    )

    _uia = original_request_data.get("uia_data")
    _uia_keys = list(_uia.keys()) if isinstance(_uia, dict) else None
    _uia_bytes = len(json.dumps(_uia or {}, ensure_ascii=False, default=str))
    app_logger.logger.info(
        "[/agent] incoming body task_id=%s keys=%s has_uia_data=%s uia_keys=%s uia_bytes=%d has_screenshot=%s",
        data["task_id"][:24],
        sorted(original_request_data.keys()),
        bool(_uia),
        _uia_keys,
        _uia_bytes,
        bool(screenshot_base64),
    )
    try:
        orchestrator._log.log_incoming_request(request_data=original_request_data)
    except Exception as _exc:
        app_logger.logger.warning("[/agent] log_incoming_request failed: %s", _exc)

    if screenshot_base64:
        task_dir = orchestrator._log.task_dir
        screenshot_path = save_base64_image(screenshot_base64, task_dir)

    _tracker = get_or_create_tracker(data["task_id"])
    _tracker_token = set_current_tracker(_tracker)
    cancelled = False
    try:
        user_api_keys = data.get("user_api_keys")
        if not isinstance(user_api_keys, dict):
            user_api_keys = None
        _tracker.begin_step(user_api_keys=user_api_keys)

        app_logger.logger.info(
            "[/agent] SSE start task_id=%s planner=%s",
            data["task_id"][:24],
            orch_model,
        )

        async for event in orchestrator.step(
            query=data["query"],
            execution_result=execution_result,
            screenshot_path=screenshot_path,
            screenshot_base64=screenshot_base64,
            uia_data=data.get("uia_data", {}),
            action_history=data.get("action_history", {}),
            history_md=data.get("history_md"),
            log_folder=os.getenv("RUN_LOG_DIR", "logs/useit_ai_run_logs"),
            planner_model=orch_model,
            planner_api_keys=effective_api_keys,
            actor_model=data.get("actor_model", "gemini-3-flash-preview"),
            project_id=project_id,
            chat_id=chat_id,
            attached_files=data.get("attached_files"),
            attached_images=data.get("attached_images", []),
            additional_context=data.get("additional_context"),
            run_logger=None,
            app_capabilities=data.get("app_capabilities", []),
            workflow_capabilities=data.get("workflow_capabilities", []),
            selected_workflow_id=data.get("workflow_id"),
            chat_history=data.get("chat_history"),
        ):
            event_type = event.get("type", "")
            if event_type in (
                "step_start",
                "reasoning_delta",
                "plan_complete",
                "tool_call",
                "step_complete",
                "task_completed",
                "text",
                "observation",
                "workflow_complete",
                "error",
            ):
                print(f"[AGENT_LOOP STREAM] type={event_type}")
            if not _should_drop_thinking_sse_event(event):
                yield event

        token_usage_event = {
            "type": "internal.step_token_usage",
            "content": _tracker.get_summary(),
        }
        yield token_usage_event
        app_logger.logger.info(
            "[/agent] emitted internal.step_token_usage task_id=%s", data["task_id"][:24]
        )

    except asyncio.CancelledError:
        cancelled = True
        app_logger.logger.info(
            "[/agent] SSE cancelled by client task_id=%s (user stop or disconnect)",
            data["task_id"][:24],
        )
        try:
            partial_usage = _tracker.get_summary()
            partial_event = {
                "type": "internal.step_token_usage",
                "content": partial_usage,
            }
            yield partial_event
        except Exception as emit_err:  # noqa: BLE001
            app_logger.logger.warning(
                f"[/agent] failed to emit partial token usage on cancel: {emit_err}"
            )
        raise
    except Exception as e:
        app_logger.logger.error(f"Error in orchestrator event stream: {e}")
        import traceback

        traceback.print_exc()
        yield {"type": "error", "content": str(e)}
    finally:
        reset_current_tracker(_tracker_token)
        if cancelled:
            try:
                task_id_to_orchestrator.pop(data["task_id"], None)
            except Exception as cleanup_err:  # noqa: BLE001
                app_logger.logger.warning(
                    f"[/agent] orchestrator cache cleanup failed: {cleanup_err}"
                )


@app.post("/agent")
async def agent_endpoint(request: Request):
    """
    Agent 端点 (SSE)：固定最小工作流 start → agent → end，经 ``FlowProcessor`` 执行。

    Request body
    ------------
    Required: ``task_id``, ``query``
    Optional: ``screenshot``, ``execution_result``, ``planner_model``, ``actor_model``,
              ``user_api_keys``, ``project_id``, ``chat_id``, ``attached_files``,
              ``attached_images``, ``additional_context``, ``uia_data``, ``workflow_id``
              （日志标识；图结构为内置最小工作流）, ``chat_history``, ``workflow_run_id``
    """
    try:
        initial_data = await request.json()
        for field in ("task_id", "query"):
            if field not in initial_data:
                raise HTTPException(status_code=400, detail=f"Missing required field: {field}")

        async def event_stream():
            async for event in iter_agent_orchestrator_events(initial_data):
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

        return StreamingResponse(
            event_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    except HTTPException:
        raise
    except Exception as e:
        app_logger.logger.error(f"Error in agent_endpoint: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


# CUA Request 回调端点
@app.post("/ai-run/request-response/{request_id}")
async def receive_request_response(request_id: str, request: Request):
    """
    接收来自 Backend 的 cua_request 数据响应

    职责：
    - 接收 Backend 转发的数据（来自 Local Engine）
    - 解除对应的 Future 阻塞，让 AI Run Node 继续执行
    - 落盘回调数据到 logs/callback_responses/ 目录

    请求体格式:
    {
        "data": {...},  # 成功时的数据（Excel 快照、CAD 图层等）
        "error": null   # 或错误信息字符串
    }

    响应:
    {
        "status": "ok" | "error",
        "request_id": "...",
        "message": "..."  # 可选
    }
    """
    try:
        body = await request.json()
        outcome = deliver_cua_request_response(request_id, body)

        if body.get("error"):
            app_logger.logger.warning(
                f"[AI Run] Request {request_id} failed: {body['error']}"
            )
            return JSONResponse(
                content={
                    "status": "ok",
                    "request_id": request_id,
                    "message": "Error received and propagated to waiting node",
                }
            )

        if outcome == "ok":
            data = body.get("data")
            app_logger.logger.info(
                f"[AI Run] Request {request_id} completed successfully, "
                f"data size: {len(str(data)) if data else 0} bytes"
            )
            return JSONResponse(
                content={
                    "status": "ok",
                    "request_id": request_id,
                    "message": "Data received and delivered to waiting node",
                }
            )

        app_logger.logger.warning(
            f"[AI Run] Request {request_id} not found or already completed"
        )
        return JSONResponse(
            status_code=404,
            content={
                "status": "error",
                "request_id": request_id,
                "message": "Request not found or already completed",
            },
        )

    except Exception as e:
        app_logger.logger.error(
            f"[AI Run] Error handling response for {request_id}: {e}",
            exc_info=True
        )
        raise HTTPException(status_code=500, detail=str(e))


def _truncate_for_log(data: any, max_length: int = 500) -> any:
    """
    截断数据用于日志记录
    """
    if data is None:
        return None

    data_str = json.dumps(data, ensure_ascii=False) if not isinstance(data, str) else data
    if len(data_str) > max_length:
        return data_str[:max_length] + f"... (truncated, total {len(data_str)} chars)"
    return data


def _persist_callback_response(request_id: str, body: dict):
    """
    落盘回调响应数据到全局目录
    
    目录结构: logs/callback_responses/callback_{request_id}_{timestamp}.json
    """
    try:
        callback_dir = os.path.join(RUN_LOG_DIR, "callback_responses")
        os.makedirs(callback_dir, exist_ok=True)
        
        timestamp = datetime.now(UTC_PLUS_8)
        timestamp_str = timestamp.strftime("%y%m%d-%H%M%S_%f")
        
        # 截断 request_id 避免文件名过长
        safe_request_id = request_id.replace("/", "_").replace("\\", "_")[:40]
        filename = f"callback_{safe_request_id}_{timestamp_str}.json"
        
        callback_record = {
            "timestamp": timestamp.isoformat(),
            "request_id": request_id,
            "is_error": bool(body.get("error")),
            "error": body.get("error"),
            "has_data": body.get("data") is not None,
            "data_preview": _truncate_for_log(body.get("data")),
            "raw_body": body,
        }
        
        file_path = os.path.join(callback_dir, filename)
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(callback_record, f, ensure_ascii=False, indent=2)
        
        app_logger.logger.info(f"[AI Run] Callback response persisted: {file_path}")
        
    except Exception as e:
        app_logger.logger.warning(f"[AI Run] Failed to persist callback response: {e}")


def deliver_cua_request_response(request_id: str, body: Dict[str, Any]) -> str:
    """
    与 ``POST /ai-run/request-response/{id}`` 相同语义：落盘并 resolve/reject Future。

    Returns:
        ``"ok"`` | ``"error"``（``error`` 表示 resolve 时 request 未找到或已完成）
    """
    _persist_callback_response(request_id, body)
    if body.get("error"):
        request_manager.reject_request(request_id, body["error"])
        return "ok"
    data = body.get("data")
    if request_manager.resolve_request(request_id, data):
        return "ok"
    return "error"


# 旧的配置管理端点已移除（set_planner_mode）
# V2 架构不再需要动态切换 planner 模式


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", 8001))  # 使用不同的端口避免冲突
    app_logger.logger.info(f"Starting AI_Run LangChain Async Streaming server on port {port}")

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=port,
        log_level="info",
        access_log=True,
    )