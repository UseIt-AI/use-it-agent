"""
UseIt 统一网关：在同一 FastAPI 进程中挂载

- ``useit_studio.gateway``：``/api/v1``（工作流、``/api/v1/agent``）
- ``src/local_engine/``（或并列 ``useit-studio-local-engine``）：``/api/v1/...``（与旧版一致）
- ``useit_studio.ai_run.web_app``：挂载 ``/ai-run``

安装后启动::

    useit-unified
    # 或
    python -m useit_studio.gateway.unified_main

仍需可选依赖 ``pip install -e ".[agent,local-engine]"`` 才能加载完整 AI_Run 与 Local Engine。
"""

from __future__ import annotations

import logging
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware


def _local_engine_root() -> Path:
    """自本文件向上查找 ``local_engine`` 或 ``useit-studio-local-engine``。"""
    here = Path(__file__).resolve()
    for root in here.parents:
        for name in ("local_engine", "useit-studio-local-engine"):
            candidate = root / name
            if candidate.is_dir() and (candidate / "api").is_dir():
                return candidate.resolve()
    raise RuntimeError(
        "未找到 Local Engine：请在仓库中保留 src/local_engine/，"
        "或并列放置 useit-studio-local-engine。"
    )


def _repo_root() -> Path:
    """包含 pyproject.toml 的仓库根（local_engine 在 src/ 下时与 engine 根目录不同）。"""
    here = Path(__file__).resolve()
    for root in here.parents:
        if (root / "pyproject.toml").is_file():
            return root.resolve()
    raise RuntimeError(
        "未找到仓库根目录：请从包含 pyproject.toml 的 UseIt 仓库运行 unified_main。"
    )


_REPO_ROOT = _repo_root()

sys.path.insert(0, str(_local_engine_root()))

os.environ["USEIT_UNIFIED_SERVER"] = "1"

from useit_studio.gateway.settings import (  # noqa: E402
    get_backend_host,
    get_backend_port,
    load_local_dotenv,
)

load_local_dotenv()

from useit_studio.gateway.api.v1.endpoints import workflow  # noqa: E402

from api.v1 import router as local_engine_router  # noqa: E402

from useit_studio.ai_run import web_app as ai_run_web  # noqa: E402


class SuppressNoiseFilter(logging.Filter):
    """过滤掉频繁的轮询日志"""

    def filter(self, record: logging.LogRecord) -> bool:
        if "/pending-tasks/" in record.getMessage():
            return False
        return True


logging.getLogger("uvicorn.access").addFilter(SuppressNoiseFilter())


@asynccontextmanager
async def unified_lifespan(app: FastAPI):
    async with ai_run_web.ai_run_lifespan(ai_run_web.app):
        try:
            yield
        finally:
            try:
                from core import controller_registry  # type: ignore[import-untyped]

                await controller_registry.cleanup_all()
            except Exception:
                logging.getLogger(__name__).exception(
                    "Local Engine controller_registry.cleanup_all failed"
                )


app = FastAPI(
    title="UseIt Unified (Backend + Local Engine + AI_Run)",
    description="单进程：Studio 网关、本地引擎 API、AI_Run 子应用（/ai-run）。",
    version="1.0.0",
    lifespan=unified_lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(workflow.router, prefix="/api/v1", tags=["agent"])
app.include_router(local_engine_router)

app.mount("/ai-run", ai_run_web.app)


@app.get("/health", tags=["health"])
async def health_check():
    return {
        "status": "ok",
        "service": "useit-unified",
        "repo_root": str(_REPO_ROOT),
        "local_engine": str(_local_engine_root()),
        "components": {
            "gateway": "useit_studio.gateway",
            "local_engine": "mounted at /api/v1/...",
            "ai_run": "mounted at /ai-run",
        },
    }


def run() -> None:
    host = get_backend_host()
    port = get_backend_port()
    print(f"Starting UseIt Unified on {host}:{port} ...")
    print(f"  Repo root:     {_REPO_ROOT}")
    print(f"  Local engine:  {_local_engine_root()}")
    print(f"  AI_Run mount:  http://127.0.0.1:{port}/ai-run/agent")
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    run()
