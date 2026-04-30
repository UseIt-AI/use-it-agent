"""
Word API 端点 —— Microsoft Word 自动化

主要端点:
- GET  /api/v1/word/status     获取 Word 状态
- POST /api/v1/word/open       打开 Word 文档
- POST /api/v1/word/close      关闭 Word 文档
- POST /api/v1/word/snapshot   获取文档快照（多 scope 支持）
- POST /api/v1/word/step       三选一：actions / code / skill，执行后回传快照

## /step 三种模式（跟 PPT 对齐）
- 传 actions:                走结构化 Action（Layer 1，目前为占位）
- 传 code:                   原始代码执行（Layer 3 兜底）
- 传 skill_id + script_path: 预置 Skill 脚本（Layer 2）

## 向后兼容
StepRequest / SnapshotRequest 保留旧的 `current_page_only: bool` 字段。
没传新 `scope` 时：current_page_only=True → scope="current_page"；False → "full"。
"""

import logging
from typing import Any, Dict, List, Literal, Optional, Tuple

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from controllers.word.controller import WordController

from .project import format_tree_as_text

logger = logging.getLogger(__name__)
router = APIRouter()

_controller: Optional[WordController] = None


def _get_controller() -> WordController:
    global _controller
    if _controller is None:
        _controller = WordController()
    return _controller


# ==================== 请求模型 ====================


# scope 文档值集中写一处
SNAPSHOT_SCOPE_VALUES = [
    "outline_only",     # 只返回标题树（最小载荷）
    "current_page",     # 当前页
    "current_section",  # 当前 section
    "selection",        # 当前选区
    "paragraph_range",  # 指定段落 index 区间
    "full",             # 全文（显式请求才返回）
]


def _resolve_scope(
    scope: Optional[str],
    current_page_only: Optional[bool],
    default_when_both_none: str,
) -> str:
    """
    兼容层：优先 scope；没 scope 看 current_page_only。

    调用方需要：
    - default_when_both_none="current_page"（step 用）
    - default_when_both_none="full"（snapshot 用，保持老的行为）
    """
    if scope:
        if scope not in SNAPSHOT_SCOPE_VALUES:
            raise ValueError(f"invalid scope: {scope!r}; allowed: {SNAPSHOT_SCOPE_VALUES}")
        return scope
    if current_page_only is True:
        return "current_page"
    if current_page_only is False:
        return "full"
    return default_when_both_none


class SnapshotRequest(BaseModel):
    """
    获取文档快照请求。

    新字段（推荐）:
    - scope: 6 种模式之一，见 SNAPSHOT_SCOPE_VALUES
    - paragraph_range: scope=paragraph_range 时必传 [start, end]
    - include_outline / include_styles / include_bookmarks / include_toc

    旧字段（保留兼容）:
    - current_page_only: true → scope=current_page, false → scope=full
    """

    # 新字段
    scope: Optional[str] = Field(default=None, description=f"快照范围：{'/'.join(SNAPSHOT_SCOPE_VALUES)}")
    paragraph_range: Optional[List[int]] = Field(
        default=None, description="scope=paragraph_range 时用，[start_index, end_index]（1-based 闭区间）"
    )
    max_paragraphs: Optional[int] = Field(default=None, description="scope=full 时的段落上限")
    include_content: bool = Field(default=True, description="是否返回段落/表格等内容")
    include_screenshot: bool = Field(default=True, description="是否返回截图")
    include_outline: bool = Field(default=False, description="是否附带大纲树（heading 列表）")
    include_styles: bool = Field(default=False, description="是否附带命名样式清单")
    include_bookmarks: bool = Field(default=False, description="是否附带书签列表")
    include_toc: bool = Field(default=False, description="是否附带目录（TablesOfContents）")

    # 兼容字段（旧客户端）
    current_page_only: Optional[bool] = Field(
        default=None,
        description="[deprecated] 旧字段；新请求请用 scope。true → current_page, false → full",
    )

    # Project files
    include_project_files: bool = Field(default=False, description="是否附带项目文件列表")
    project_path: Optional[str] = Field(default=None, description="项目根目录")
    project_max_depth: int = Field(default=4, ge=1, le=10, description="项目文件遍历最大深度")
    project_max_files: int = Field(default=500, ge=1, le=2000, description="项目文件最大数量")


class StepRequest(BaseModel):
    """
    统一执行请求 —— actions / code / skill 三选一（跟 PPT 对齐）。

    模式 A: 结构化 Actions（Layer 1，batch 2 启用）
    模式 B: 原始代码（Layer 3，subprocess 执行）
    模式 C: 预置 Skill 脚本（Layer 2）
    """

    # 模式 A: 结构化 Actions（目前为占位）
    actions: Optional[List[Dict[str, Any]]] = Field(default=None, description="结构化 Action 列表")
    dry_run: Optional[bool] = Field(default=None, description="actions 模式：仅预演不真改（Layer 1 启用后生效）")

    # 模式 B: 原始代码
    code: Optional[str] = Field(default=None, description="要执行的代码")

    # 模式 C: Skill 脚本
    skill_id: Optional[str] = Field(default=None, description="Skill ID")
    script_path: Optional[str] = Field(default=None, description="脚本相对路径")
    parameters: Optional[Dict[str, Any]] = Field(default=None, description="脚本参数")

    # 共享
    language: str = Field(default="PowerShell", description="语言：PowerShell 或 Python")
    timeout: int = Field(default=120, description="超时时间（秒）")

    # 快照控制
    return_screenshot: bool = Field(default=True, description="是否返回截图")
    snapshot_scope: Optional[str] = Field(
        default=None,
        description=f"执行后快照的范围：{'/'.join(SNAPSHOT_SCOPE_VALUES)}",
    )

    # 兼容字段
    current_page_only: Optional[bool] = Field(
        default=None,
        description="[deprecated] 旧字段；新请求请用 snapshot_scope",
    )

    # Project files
    include_project_files: bool = Field(default=False, description="是否包含项目文件列表")
    project_path: Optional[str] = Field(default=None, description="项目根目录")
    project_max_depth: int = Field(default=4, ge=1, le=10, description="项目文件遍历最大深度")


class OpenDocumentRequest(BaseModel):
    file_path: str = Field(..., description="文档路径")
    read_only: bool = Field(default=False, description="是否以只读方式打开")


class CloseDocumentRequest(BaseModel):
    save: bool = Field(default=False, description="是否保存文档")


# ==================== API 端点 ====================


@router.get("/status")
async def get_status() -> Dict[str, Any]:
    """检查 Word 是否运行 + 当前文档信息。"""
    logger.info("[Word API] status")
    try:
        status = await _get_controller().get_status()
        return {"success": True, "data": status}
    except Exception as e:
        logger.error(f"[Word API] status error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/open")
async def open_document(request: OpenDocumentRequest) -> Dict[str, Any]:
    """打开 Word 文档（已打开则激活）。"""
    logger.info(f"[Word API] open: file_path={request.file_path}, read_only={request.read_only}")
    try:
        result = await _get_controller().open_document(
            file_path=request.file_path, read_only=request.read_only
        )
        if result["success"]:
            return {"success": True, "data": {"document_info": result["document_info"]}}
        raise HTTPException(status_code=400, detail=result["error"])
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[Word API] open error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/close")
async def close_document(request: CloseDocumentRequest = None) -> Dict[str, Any]:
    """关闭当前文档。"""
    if request is None:
        request = CloseDocumentRequest()
    logger.info(f"[Word API] close: save={request.save}")
    try:
        result = await _get_controller().close_document(save=request.save)
        if result["success"]:
            return {"success": True, "data": {"closed_document": result["closed_document"]}}
        raise HTTPException(status_code=400, detail=result["error"])
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[Word API] close error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/snapshot")
async def get_snapshot(request: SnapshotRequest = None) -> Dict[str, Any]:
    """
    获取文档快照 —— 支持多种 scope，避免大文档返回全文。

    典型用法：
    1. AI 初次进文档：scope='outline_only' + include_outline=true
       → 拿到标题树（几 KB）
    2. 定位到要改的章节：scope='paragraph_range' + paragraph_range=[50, 80]
    3. 改完后验证：scope='current_page'
    """
    if request is None:
        request = SnapshotRequest()

    try:
        scope = _resolve_scope(
            request.scope, request.current_page_only, default_when_both_none="full"
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    paragraph_range: Optional[Tuple[int, int]] = None
    if request.paragraph_range:
        if len(request.paragraph_range) != 2:
            raise HTTPException(
                status_code=400,
                detail="paragraph_range must be [start_index, end_index]",
            )
        paragraph_range = (int(request.paragraph_range[0]), int(request.paragraph_range[1]))

    logger.info(
        f"[Word API] snapshot: scope={scope}, paragraph_range={paragraph_range}, "
        f"content={request.include_content}, screenshot={request.include_screenshot}, "
        f"outline={request.include_outline}, styles={request.include_styles}, "
        f"bookmarks={request.include_bookmarks}, toc={request.include_toc}"
    )

    try:
        snapshot = await _get_controller().get_snapshot(
            scope=scope,
            paragraph_range=paragraph_range,
            max_paragraphs=request.max_paragraphs,
            include_content=request.include_content,
            include_screenshot=request.include_screenshot,
            include_outline=request.include_outline,
            include_styles=request.include_styles,
            include_bookmarks=request.include_bookmarks,
            include_toc=request.include_toc,
        )

        if request.include_project_files and request.project_path:
            try:
                snapshot["project_files"] = format_tree_as_text(
                    project_path=request.project_path,
                    max_depth=request.project_max_depth,
                )
            except Exception as e:
                logger.warning(f"[Word API] Failed to get project files: {e}")
                snapshot["project_files"] = f"Error: {str(e)}"

        return {"success": True, "data": snapshot}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"[Word API] snapshot error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/step")
async def step(request: StepRequest) -> Dict[str, Any]:
    """
    统一执行入口 —— actions / code / skill 三选一。

    模式 A: 结构化 Actions（Layer 1，batch 2 启用，当前返回占位错误）
    ```json
    {"actions": [{"action": "apply_style", "target": {"type": "paragraph", "index": 3}, "style_name": "Heading 1"}]}
    ```

    模式 B: 原始代码（Layer 3）
    ```json
    {"code": "$word = ...", "language": "PowerShell"}
    ```

    模式 C: 预置 Skill 脚本（Layer 2）
    ```json
    {"skill_id": "66666666", "script_path": "scripts/format_resume.ps1", "parameters": {"Path": "resume.docx"}}
    ```
    """
    try:
        snapshot_scope = _resolve_scope(
            request.snapshot_scope,
            request.current_page_only,
            default_when_both_none="current_page",
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    controller = _get_controller()

    try:
        if request.actions:
            logger.info(
                f"[Word API] step(actions): {len(request.actions)} actions, "
                f"scope={snapshot_scope}, dry_run={request.dry_run}"
            )
            result = await controller.execute_actions(
                actions=request.actions,
                return_screenshot=request.return_screenshot,
                snapshot_scope=snapshot_scope,
                dry_run=bool(request.dry_run),
            )
        elif request.code:
            logger.info(
                f"[Word API] step(code): lang={request.language}, "
                f"code_len={len(request.code)}, scope={snapshot_scope}"
            )
            result = await controller.execute_code(
                code=request.code,
                language=request.language,
                timeout=request.timeout,
                return_screenshot=request.return_screenshot,
                snapshot_scope=snapshot_scope,
            )
        elif request.skill_id and request.script_path:
            logger.info(
                f"[Word API] step(skill): skill_id={request.skill_id}, "
                f"script_path={request.script_path}, lang={request.language}"
            )
            result = await controller.execute_script(
                skill_id=request.skill_id,
                script_path=request.script_path,
                parameters=request.parameters,
                language=request.language,
                timeout=request.timeout,
                return_screenshot=request.return_screenshot,
                snapshot_scope=snapshot_scope,
            )
        else:
            raise HTTPException(
                status_code=400,
                detail=(
                    "StepRequest requires one of: actions / code / (skill_id + script_path)"
                ),
            )

        if request.include_project_files and request.project_path:
            try:
                project_tree = format_tree_as_text(
                    project_path=request.project_path,
                    max_depth=request.project_max_depth,
                )
                result["snapshot"]["project_files"] = project_tree
                logger.info(f"[Word API] step: 附带项目文件列表，长度={len(project_tree)}")
            except Exception as e:
                logger.warning(f"[Word API] Failed to get project files: {e}")
                result["snapshot"]["project_files"] = f"Error: {str(e)}"

        success = result["execution"]["success"]
        return {
            "success": success,
            "data": result,
            "error": result["execution"]["error"] if not success else None,
        }

    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"[Word API] step error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
