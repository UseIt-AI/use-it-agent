"""
UseIt Studio Backend（开源本地版）

职责：作为 AI_Run 的网关，提供 Agent 的 NDJSON/SSE 流式 API
与客户端回调（/workflow/callback）。

本地默认（``APP_ENV=local``）在已安装 agent 依赖时于本进程挂载 ``/ai-run``，
并启用网关↔AI_Run 进程内直连（不经本机 HTTP）。
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from useit_studio.gateway.settings import (
    get_backend_host,
    get_backend_port,
    load_local_dotenv,
)

load_local_dotenv()

APP_ENV = os.getenv("APP_ENV", "local").strip().lower()
print(f"Starting in environment: {APP_ENV}")

_logger = logging.getLogger(__name__)


def _should_try_embed_ai_run() -> bool:
    if APP_ENV != "local":
        return False
    v = os.getenv("USEIT_GATEWAY_EMBED_AI_RUN", "1").strip().lower()
    if v in ("0", "false", "no", "off"):
        return False
    return True


_ai_run_web = None
_added_unified_env = False

if _should_try_embed_ai_run():
    if "USEIT_UNIFIED_SERVER" not in os.environ:
        os.environ["USEIT_UNIFIED_SERVER"] = "1"
        _added_unified_env = True
    try:
        from useit_studio.ai_run import web_app as _ai_run_web  # noqa: E402
    except Exception as exc:  # noqa: BLE001
        _logger.warning(
            "未嵌入 AI_Run（需安装可选依赖后重试）：pip install -e \".[agent]\" — %s",
            exc,
        )
        if _added_unified_env:
            os.environ.pop("USEIT_UNIFIED_SERVER", None)


class SuppressNoiseFilter(logging.Filter):
    """过滤掉频繁的轮询日志"""

    def filter(self, record: logging.LogRecord) -> bool:
        if "/pending-tasks/" in record.getMessage():
            return False
        return True


logging.getLogger("uvicorn.access").addFilter(SuppressNoiseFilter())

from useit_studio.gateway.api.v1.endpoints import workflow  # noqa: E402


@asynccontextmanager
async def _lifespan(_: FastAPI):
    if _ai_run_web is not None:
        async with _ai_run_web.ai_run_lifespan(_ai_run_web.app):
            print("UseIt Studio Backend (OSS) started — AI_Run embedded, gateway↔agent in-process")
            yield
    else:
        print("UseIt Studio Backend (OSS) started")
        yield
    print("UseIt Studio Backend shutdown")


_desc = (
    "本地开源网关：工作流与 Agent 流式 API；"
    + (
        "AI_Run 已嵌入本进程（/ai-run），默认进程内调用。"
        if _ai_run_web is not None
        else "请安装 agent 可选依赖以嵌入 AI_Run；或设置 USEIT_GATEWAY_EMBED_AI_RUN=0 并本机另启 AI_Run（默认端口 8326）。"
    )
)

app = FastAPI(
    title="UseIt Studio Backend (OSS)",
    description=_desc,
    version="2.2.0-oss",
    lifespan=_lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(workflow.router, prefix="/api/v1", tags=["agent"])

if _ai_run_web is not None:
    app.mount("/ai-run", _ai_run_web.app)


@app.get("/health", tags=["health"])
async def health_check():
    body: dict = {
        "status": "ok",
        "service": "useit-studio-backend",
        "ai_run": (
            {"mode": "embedded", "mount": "/ai-run", "gateway_to_agent": "in-process"}
            if _ai_run_web is not None
            else {"mode": "external", "gateway_to_agent": "http"}
        ),
    }
    return body


def run() -> None:
    port = get_backend_port()
    host = get_backend_host()
    print(f"Starting UseIt Studio Backend on {host}:{port}...")
    if _ai_run_web is not None:
        print(f"  AI_Run: embedded at http://127.0.0.1:{port}/ai-run (orchestrator in-process)")
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    run()
