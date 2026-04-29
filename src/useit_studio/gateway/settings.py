import os
from pathlib import Path
from typing import Iterable, Optional

from dotenv import load_dotenv

APP_ENV_LOCAL = "local"
APP_ENV_STAGING = "staging"
APP_ENV_PROD = "prod"
APP_ENV_ALLOWED = {APP_ENV_LOCAL, APP_ENV_STAGING, APP_ENV_PROD}

_DOTENV_LOADED = False


def _strip_env_value(v: str) -> str:
    s = str(v).strip()
    if (s.startswith('"') and s.endswith('"')) or (s.startswith("'") and s.endswith("'")):
        s = s[1:-1].strip()
    return s


def get_env_any(names: Iterable[str], default: Optional[str] = None) -> str:
    for name in names:
        v = os.getenv(name)
        if v is not None and str(v).strip():
            return _strip_env_value(v)
    if default is not None:
        return default
    raise RuntimeError(f"Missing required env var (any of): {', '.join(names)}")


def get_app_env() -> str:
    raw = os.getenv("APP_ENV", APP_ENV_LOCAL).strip().lower()
    if raw not in APP_ENV_ALLOWED:
        raise RuntimeError(
            f"Invalid APP_ENV={raw!r}. Allowed values: {sorted(APP_ENV_ALLOWED)}"
        )
    return raw


def is_local_env() -> bool:
    return get_app_env() == APP_ENV_LOCAL


def load_local_dotenv() -> None:
    global _DOTENV_LOADED
    if _DOTENV_LOADED:
        return
    if is_local_env():
        # Keep local ergonomics and avoid overriding process environment.
        load_dotenv(override=False)
    _DOTENV_LOADED = True


def get_backend_host() -> str:
    return os.getenv("BACKEND_HOST", "0.0.0.0")


def get_backend_port() -> int:
    return int(os.getenv("BACKEND_PORT", "8001"))


def get_projects_dir() -> str:
    configured = os.getenv("PROJECTS_DIR")
    if configured and configured.strip():
        return configured

    # gateway 包目录（与旧 backend 目录同级语义：.projects 放在 gateway 旁）
    gateway_dir = Path(__file__).resolve().parent
    return str(gateway_dir / ".projects")


def get_ai_run_url() -> str:
    """
    本机 AI_Run HTTP 基地址（网关在非进程内模式下会请求 ``{base_url}/agent``）。

    不支持配置远端 URL：仅解析本机统一挂载或默认本机独立 AI_Run 端口。

    - ``USEIT_UNIFIED_SERVER=1``：本机统一进程 ``/ai-run`` 挂载（``UNIFIED_PUBLIC_HOST`` + ``BACKEND_PORT``）。
    - 否则：固定 ``http://localhost:8326``（本机另启的独立 AI_Run 默认端口）。
    """
    unified = os.getenv("USEIT_UNIFIED_SERVER", "").strip().lower()
    if unified in ("1", "true", "yes", "on"):
        port = get_backend_port()
        host = (os.getenv("UNIFIED_PUBLIC_HOST", "127.0.0.1").strip() or "127.0.0.1")
        return f"http://{host}:{port}/ai-run"
    return "http://localhost:8326"


def use_in_process_ai_run() -> bool:
    """
    是否与 AI_Run 同进程并直接 Python 调用（不经本机 HTTP）。

    - ``USEIT_IN_PROCESS_AI_RUN=0/false/off``：强制走本机 HTTP（仍只连 ``get_ai_run_url()``）。
    - ``USEIT_IN_PROCESS_AI_RUN=1/true/on``：强制进程内（须与 ``web_app`` 同进程）。
    - 未显式设置时：仅当 ``USEIT_UNIFIED_SERVER=1``（统一网关或嵌入挂载）时默认进程内。

    本地 ``gateway.main`` 在可导入 ``ai_run`` 时会设置 ``USEIT_UNIFIED_SERVER`` 并挂载 ``/ai-run``。
    """
    raw = os.getenv("USEIT_IN_PROCESS_AI_RUN", "").strip().lower()
    if raw in ("0", "false", "no", "off"):
        return False
    if raw in ("1", "true", "yes", "on"):
        return True
    unified = os.getenv("USEIT_UNIFIED_SERVER", "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )
    if not unified:
        return False
    return True


def workflow_debug_enabled() -> bool:
    return os.getenv("WORKFLOW_DEBUG", "0") == "1"


def message_log_enabled() -> bool:
    return os.getenv("MESSAGE_LOG_ENABLED", "1") == "1"
