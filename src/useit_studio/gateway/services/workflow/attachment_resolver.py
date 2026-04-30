"""
Attachment Resolver

将附加图片规范为 ``{name, base64, mime_type}``，供下游 Agent 使用。

仅支持请求体内已有 ``base64``，或通过 **HTTP(S) URL** 拉取字节（例如临时签名链接）。
不包含任何云端存储 SDK 或服务商特有接口。
"""

from __future__ import annotations

import base64 as b64
import logging
from typing import Any, Dict, List

import requests

logger = logging.getLogger(__name__)

_DOWNLOAD_TIMEOUT_SECONDS = 10.0


def hydrate_attached_images(
    items: List[Dict[str, Any]],
    **_ignored: Any,
) -> List[Dict[str, Any]]:
    """返回新列表：已有 ``base64`` 的条目保持不变；否则若存在 ``url`` 则尝试下载并填入 base64。"""
    if not items:
        return list(items or [])

    out: List[Dict[str, Any]] = []
    for entry in items:
        if not isinstance(entry, dict):
            out.append(entry)
            continue
        if isinstance(entry.get("base64"), str) and entry["base64"]:
            out.append(dict(entry))
            continue

        url = entry.get("url")
        if isinstance(url, str) and url and url.startswith(("http://", "https://")):
            try:
                downloaded_bytes = _download_from_url(url)
                hydrated = dict(entry)
                hydrated["base64"] = b64.b64encode(downloaded_bytes).decode("ascii")
                hydrated.setdefault(
                    "mime_type", entry.get("mime_type") or entry.get("mimeType") or "image/png"
                )
                logger.info(
                    "[AttachmentResolver] Hydrated %s from URL (%d bytes)",
                    entry.get("name") or "<unnamed>",
                    len(downloaded_bytes),
                )
                out.append(hydrated)
                continue
            except Exception as exc:  # noqa: BLE001
                logger.warning("[AttachmentResolver] URL download failed: %s", exc)

        if entry.get("storage_path") or entry.get("storagePath"):
            logger.warning(
                "[AttachmentResolver] Skip name=%r: storage_path without inline base64 or fetchable URL",
                entry.get("name"),
            )
        else:
            logger.warning(
                "[AttachmentResolver] Could not resolve attachment name=%r (no base64, no usable url)",
                entry.get("name"),
            )
        out.append(dict(entry))

    return out


def _download_from_url(url: str) -> bytes:
    resp = requests.get(url, timeout=_DOWNLOAD_TIMEOUT_SECONDS)
    if resp.status_code != 200:
        raise RuntimeError(f"URL returned HTTP {resp.status_code}: {resp.text[:200]}")
    return resp.content
