"""
Environment / secrets utilities (production style).

Production:
- Secrets should be injected via environment variables (K8s Secret, systemd, Docker env, CI/CD, Vault, etc.).
Development:
- Optional `.env` loading (python-dotenv) to avoid hardcoding secrets in code or repo files.
"""

from __future__ import annotations

import os
from typing import Dict, Optional


def load_dotenv_if_present(dotenv_path: Optional[str] = None, *, enabled: Optional[bool] = None) -> bool:
    """
    Load `.env` if python-dotenv is installed. Safe in production (no-op if missing).

    Control:
    - `USEIT_LOAD_DOTENV=0/false/no` disables loading.
    """
    if enabled is None:
        flag = os.getenv("USEIT_LOAD_DOTENV", "1").strip().lower()
        enabled = flag not in {"0", "false", "no", "off"}

    if not enabled:
        return False

    try:
        from dotenv import load_dotenv  # type: ignore

        # override=False: never override env injected by the runtime/platform
        return bool(load_dotenv(dotenv_path=dotenv_path, override=False))
    except Exception:
        return False


def get_api_keys(*, load_dotenv_first: bool = True) -> Dict[str, str]:
    """
    Collect API keys from environment variables.

    Returns only non-empty keys. This is intentionally "production style":
    - no file reads by default
    - no printing/logging of secrets
    """
    if load_dotenv_first:
        load_dotenv_if_present()

    keys = [
        "OPENAI_API_KEY",
        "GOOGLE_API_KEY",
        "ANTHROPIC_API_KEY",
        "CLAUDE_API_KEY",
        "OPERATOR_OPENAI_API_KEY",
        "TAVILY_API_KEY",  # Web Search 工具
        "RAG_URL",  # RAG 检索服务
    ]
    out: Dict[str, str] = {}
    for k in keys:
        v = os.getenv(k)
        if v:
            out[k] = v
    return out


