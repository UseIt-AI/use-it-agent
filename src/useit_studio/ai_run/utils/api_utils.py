
import json
import os
from typing import Dict

from .env_utils import get_api_keys, load_dotenv_if_present


def load_api_keys(path: str = './config/api_keys.json') -> Dict[str, str]:
    """
    DEPRECATED (compatibility):
    - Production should inject secrets via environment variables (preferred).
    - Development can use `.env` (python-dotenv) or a local api_keys.json if you insist.

    This function now behaves safely:
    - Loads `.env` first (if available)
    - If `path` exists, merges keys from json WITHOUT overwriting non-empty env vars
    - If `path` is missing, silently falls back to env keys (no noisy prints)
    """
    try:
        # Load `.env` first (dev-friendly, production-safe no-op).
        load_dotenv_if_present()

        # Start with env (production style).
        merged: Dict[str, str] = get_api_keys(load_dotenv_first=False)

        # Optional legacy file merge.
        if path and os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                file_keys = json.load(f) or {}
            for k, v in file_keys.items():
                if not v:
                    continue
                # Only fill missing keys; never override injected env vars.
                merged.setdefault(k, v)

        # Mirror into env for downstream code that reads os.getenv directly.
        for k, v in merged.items():
            os.environ.setdefault(k, v)

        return merged
    except Exception:
        # Silent fallback: return env-only keys (avoid noisy logs in production).
        return get_api_keys()