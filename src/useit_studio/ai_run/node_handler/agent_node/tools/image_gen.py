"""tool_image_gen —— GPT-Image-2 图像生成与编辑（inline）。

独立 inline tool：只要 OPENAI_API_KEY 可用就启用，不依赖任何软件 snapshot。
auto-discovery 会把单文件 module 直接视为一个独立 tool
（路径：tools/image_gen.py → `TOOL` 常量）。

能力
----
- `action="generate"`：纯 prompt 生成图像（调用 /v1/images/generations）。
- `action="edit"`：带参考图的编辑/合成（调用 /v1/images/edits）。

输出
----
1. **保存到本地**：写入 `<log_folder>/generated_images/<timestamp>_<uuid>.<ext>`，
   返回绝对路径——这样下游的 `ppt_insert(action="media")` 或 PPT `<image href=...>`
   可直接引用。
2. **（可选）上传 S3**：当 `project_id` 可用时，上传到
   `projects/{project_id}/outputs/images/<filename>`；失败不致命。
3. **文本结果**：返回给 Planner 的字符串里包含 `local_path` / `s3_url` / 元数据，
   便于下一轮 tool_call 直接使用。

典型用法
--------
>>> tool_image_gen(action="generate",
...                prompt="A clean, minimal illustration of a rocket launch",
...                size="1536x1024", quality="high")
→ local_path=/.../generated_images/20260424_abc123.png

>>> tool_image_gen(action="edit",
...                prompt="Add a city skyline behind the subject",
...                image_paths=["/abs/path/photo.png"],
...                size="1024x1024")
"""

from __future__ import annotations

import base64
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from useit_studio.ai_run.utils.logger_utils import LoggerUtils

from .protocol import InlineTool, PermissionResult

if TYPE_CHECKING:
    from useit_studio.ai_run.node_handler.base_v2 import NodeContext

logger = LoggerUtils(component_name="Tool.image_gen")

UTC_PLUS_8 = timezone(timedelta(hours=8))

_SUPPORTED_SIZES = {"1024x1024", "1024x1536", "1536x1024", "auto"}
_SUPPORTED_QUALITIES = {"low", "medium", "high", "auto"}
_SUPPORTED_FORMATS = {"png", "jpeg", "webp"}
_MODEL = "gpt-image-2"


class ImageGenTool(InlineTool):
    name = "tool_image_gen"
    group = ""
    router_hint = (
        "Generate or edit an image with OpenAI gpt-image-2 and save the PNG locally "
        "so downstream tools (e.g. ppt_insert media_path) can reference it. "
        "Params: action ('generate'|'edit', default 'generate'), prompt (str, required), "
        "image_paths (list[str], required for edit), size "
        "('1024x1024'|'1024x1536'|'1536x1024'|'auto', default '1024x1024'), "
        "quality ('low'|'medium'|'high'|'auto', default 'medium'), "
        "output_format ('png'|'jpeg'|'webp', default 'png'), "
        "n (int 1-4, default 1)."
    )
    router_detail = (
        "### tool_image_gen\n"
        "Use when the user needs a *new* illustration / photo / icon / diagram image "
        "that must end up on disk as a real file (e.g. to insert into a slide, embed "
        "into a document, or save into the project outputs). Do NOT call this tool "
        "just to describe an image; only call when a generated image file is actually "
        "consumed by a later step.\n\n"
        "**Params**\n"
        "- `action` (`generate` | `edit`): `generate` uses the prompt alone; `edit` "
        "requires `image_paths` and produces a variant / composite guided by the prompt.\n"
        "- `prompt` (str, required): English prompt works best. Describe style, subject, "
        "composition, color palette. Keep under ~800 characters.\n"
        "- `image_paths` (list[str], required when `action='edit'`): absolute local paths "
        "to the reference image(s). Up to 4.\n"
        "- `size` (`1024x1024` | `1024x1536` | `1536x1024` | `auto`, default `1024x1024`).\n"
        "- `quality` (`low` | `medium` | `high` | `auto`, default `medium`).\n"
        "- `output_format` (`png` | `jpeg` | `webp`, default `png`). Use `png` for PPT so "
        "transparent backgrounds survive.\n"
        "- `n` (int 1-4, default 1): how many variants to produce.\n\n"
        "**Returns** a short text summary containing `local_path` for each image, plus "
        "`s3_url` when a project_id is available. Downstream tools should consume "
        "`local_path` (absolute) to embed the generated image.\n\n"
        "**Example**\n"
        "```json\n"
        "{\"action\": \"generate\", \"prompt\": \"flat vector icon of a shield with a "
        "checkmark, navy and teal, centered on transparent background\", "
        "\"size\": \"1024x1024\", \"quality\": \"medium\", \"output_format\": \"png\"}\n"
        "```\n"
    )
    is_read_only = False
    is_destructive = False
    input_schema = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["generate", "edit"],
                "default": "generate",
            },
            "prompt": {"type": "string", "minLength": 1, "maxLength": 4000},
            "image_paths": {
                "type": "array",
                "items": {"type": "string"},
                "minItems": 1,
                "maxItems": 4,
                "description": "Required when action='edit': absolute local paths to reference images.",
            },
            "size": {
                "type": "string",
                "enum": sorted(_SUPPORTED_SIZES),
                "default": "1024x1024",
            },
            "quality": {
                "type": "string",
                "enum": sorted(_SUPPORTED_QUALITIES),
                "default": "medium",
            },
            "output_format": {
                "type": "string",
                "enum": sorted(_SUPPORTED_FORMATS),
                "default": "png",
            },
            "n": {"type": "integer", "minimum": 1, "maximum": 4, "default": 1},
        },
        "required": ["prompt"],
    }

    # ------------------------------------------------------------------ enable
    def is_enabled(self, ctx: "NodeContext") -> bool:
        keys = ctx.planner_api_keys or {}
        return bool(keys.get("OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY"))

    def check_permission(
        self, ctx: "NodeContext", params: Dict[str, Any]
    ) -> PermissionResult:
        if not self.is_enabled(ctx):
            return PermissionResult(
                decision="deny", reason="OPENAI_API_KEY not configured"
            )
        if not (params.get("prompt") or "").strip():
            return PermissionResult(decision="deny", reason="prompt required")

        action = (params.get("action") or "generate").lower()
        if action == "edit":
            image_paths = params.get("image_paths") or []
            if not image_paths:
                return PermissionResult(
                    decision="deny",
                    reason="action='edit' requires 'image_paths'",
                )
            missing = [p for p in image_paths if not os.path.isfile(p)]
            if missing:
                return PermissionResult(
                    decision="deny",
                    reason=f"image_paths not found on disk: {missing}",
                )
        elif action != "generate":
            return PermissionResult(
                decision="deny",
                reason=f"unsupported action '{action}' (expected 'generate' or 'edit')",
            )
        return PermissionResult()

    # --------------------------------------------------------------------- run
    async def run(self, params: Dict[str, Any], ctx: "NodeContext") -> str:
        api_keys = ctx.planner_api_keys or {}
        api_key = api_keys.get("OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY", "")
        if not api_key:
            return "[image_gen] OPENAI_API_KEY not configured"

        prompt = (params.get("prompt") or "").strip()
        if not prompt:
            return "[image_gen] missing 'prompt' param"

        action = (params.get("action") or "generate").lower()
        size = params.get("size") or "1024x1024"
        quality = params.get("quality") or "medium"
        output_format = (params.get("output_format") or "png").lower()
        try:
            n = max(1, min(4, int(params.get("n") or 1)))
        except (TypeError, ValueError):
            n = 1

        if size not in _SUPPORTED_SIZES:
            return f"[image_gen] unsupported size '{size}' (allowed: {sorted(_SUPPORTED_SIZES)})"
        if quality not in _SUPPORTED_QUALITIES:
            return (
                f"[image_gen] unsupported quality '{quality}' "
                f"(allowed: {sorted(_SUPPORTED_QUALITIES)})"
            )
        if output_format not in _SUPPORTED_FORMATS:
            return (
                f"[image_gen] unsupported output_format '{output_format}' "
                f"(allowed: {sorted(_SUPPORTED_FORMATS)})"
            )

        try:
            from openai import AsyncOpenAI
        except ImportError as e:
            return f"[image_gen] openai SDK not installed: {e}"

        client = AsyncOpenAI(api_key=api_key)

        try:
            if action == "edit":
                image_paths: List[str] = list(params.get("image_paths") or [])
                logger.logger.info(
                    f"[image_gen] edit: n={n} size={size} quality={quality} "
                    f"refs={len(image_paths)}"
                )
                resp = await self._call_edit(
                    client=client,
                    prompt=prompt,
                    image_paths=image_paths,
                    size=size,
                    quality=quality,
                    output_format=output_format,
                    n=n,
                )
            else:
                logger.logger.info(
                    f"[image_gen] generate: n={n} size={size} quality={quality} "
                    f"format={output_format}"
                )
                resp = await client.images.generate(
                    model=_MODEL,
                    prompt=prompt,
                    size=size,
                    quality=quality,
                    output_format=output_format,
                    n=n,
                )
        except Exception as e:  # noqa: BLE001
            logger.logger.warning(f"[image_gen] OpenAI call failed: {e}")
            return f"[image_gen] OpenAI call failed: {e}"

        data = getattr(resp, "data", None) or []
        if not data:
            return "[image_gen] empty response from OpenAI"

        log_folder = getattr(ctx, "log_folder", None) or os.getenv("USEIT_LOG_DIR") or "./logs"
        out_dir = os.path.abspath(os.path.join(log_folder, "generated_images"))
        try:
            os.makedirs(out_dir, exist_ok=True)
        except OSError as e:
            return f"[image_gen] failed to create output dir {out_dir!r}: {e}"

        timestamp = datetime.now(UTC_PLUS_8).strftime("%Y%m%d_%H%M%S")
        saved: List[Dict[str, Any]] = []

        for idx, item in enumerate(data):
            b64 = getattr(item, "b64_json", None)
            if not b64:
                logger.logger.warning(f"[image_gen] item {idx} has no b64_json; skipping")
                continue
            try:
                raw = base64.b64decode(b64)
            except (ValueError, TypeError) as e:
                logger.logger.warning(f"[image_gen] base64 decode failed for item {idx}: {e}")
                continue

            stem = f"{timestamp}_{uuid.uuid4().hex[:8]}_{idx}"
            filename = f"{stem}.{output_format}"
            local_path = os.path.join(out_dir, filename)
            try:
                with open(local_path, "wb") as f:
                    f.write(raw)
            except OSError as e:
                logger.logger.warning(f"[image_gen] failed to write {local_path}: {e}")
                continue

            entry: Dict[str, Any] = {
                "local_path": local_path,
                "size_bytes": len(raw),
                "format": output_format,
            }

            revised_prompt = getattr(item, "revised_prompt", None)
            if revised_prompt:
                entry["revised_prompt"] = revised_prompt

            s3_url = await self._maybe_upload_s3(
                local_path=local_path,
                filename=filename,
                project_id=ctx.project_id,
                content_type=_content_type_for(output_format),
            )
            if s3_url:
                entry["s3_url"] = s3_url

            saved.append(entry)

        if not saved:
            return "[image_gen] OpenAI returned data but nothing was saved locally"

        usage = getattr(resp, "usage", None)
        usage_dict: Optional[Dict[str, Any]] = None
        if usage is not None:
            try:
                if hasattr(usage, "model_dump"):
                    usage_dict = usage.model_dump()
                elif isinstance(usage, dict):
                    usage_dict = dict(usage)
            except Exception:  # noqa: BLE001
                usage_dict = None

        return _format_for_llm(
            saved=saved,
            action=action,
            prompt=prompt,
            size=size,
            quality=quality,
            output_format=output_format,
            model=_MODEL,
            usage=usage_dict,
        )

    # -------------------------------------------------------------- edit call
    async def _call_edit(
        self,
        *,
        client: Any,
        prompt: str,
        image_paths: List[str],
        size: str,
        quality: str,
        output_format: str,
        n: int,
    ) -> Any:
        """Wrap /v1/images/edits; the openai SDK expects file handles that stay
        open across the awaited call, so we open them here and close deterministically."""
        handles = []
        try:
            for p in image_paths:
                handles.append(open(p, "rb"))
            kwargs: Dict[str, Any] = {
                "model": _MODEL,
                "prompt": prompt,
                "size": size,
                "quality": quality,
                "output_format": output_format,
                "n": n,
            }
            # openai SDK accepts either a single file or a list for multi-image edits.
            kwargs["image"] = handles if len(handles) > 1 else handles[0]
            return await client.images.edit(**kwargs)
        finally:
            for h in handles:
                try:
                    h.close()
                except Exception:  # noqa: BLE001
                    pass

    # ----------------------------------------------------------- s3 (optional)
    async def _maybe_upload_s3(
        self,
        *,
        local_path: str,
        filename: str,
        project_id: Optional[str],
        content_type: str,
    ) -> Optional[str]:
        if not project_id or not project_id.strip():
            return None
        try:
            from useit_studio.ai_run.utils.s3_uploader import _get_s3_client, get_s3_uploader
        except ImportError:
            return None

        try:
            if _get_s3_client() is None:
                return None
            uploader = get_s3_uploader()
            s3_key = f"projects/{project_id.strip()}/outputs/images/{filename}"
            ok = await uploader.upload_file_async(
                local_path=local_path,
                s3_key=s3_key,
                content_type=content_type,
            )
            if ok:
                return f"s3://{uploader.bucket_name}/{s3_key}"
        except Exception as e:  # noqa: BLE001
            logger.logger.warning(f"[image_gen] S3 upload failed: {e}")
        return None


# =============================================================================
# helpers
# =============================================================================


def _content_type_for(output_format: str) -> str:
    return {
        "png": "image/png",
        "jpeg": "image/jpeg",
        "webp": "image/webp",
    }.get(output_format, "application/octet-stream")


def _format_for_llm(
    *,
    saved: List[Dict[str, Any]],
    action: str,
    prompt: str,
    size: str,
    quality: str,
    output_format: str,
    model: str,
    usage: Optional[Dict[str, Any]],
) -> str:
    """Format the result into a compact block that the next Planner turn can
    easily extract `local_path` / `s3_url` from."""
    lines: List[str] = []
    lines.append(
        f"[image_gen] {action} OK — {len(saved)} image(s) with {model} "
        f"({size}, quality={quality}, format={output_format})."
    )
    lines.append(f"Prompt: {prompt[:400]}{'…' if len(prompt) > 400 else ''}")
    lines.append("")
    for i, entry in enumerate(saved, 1):
        lines.append(f"**Image {i}**")
        lines.append(f"- local_path: {entry['local_path']}")
        if entry.get("s3_url"):
            lines.append(f"- s3_url: {entry['s3_url']}")
        lines.append(f"- size_bytes: {entry['size_bytes']}")
        if entry.get("revised_prompt"):
            lines.append(f"- revised_prompt: {entry['revised_prompt']}")
        lines.append("")
    if usage:
        lines.append(f"Usage: {usage}")
    lines.append(
        "Use the absolute `local_path` above as `media_path` / `href` in the next tool call."
    )
    return "\n".join(lines).strip()


TOOL = ImageGenTool()
