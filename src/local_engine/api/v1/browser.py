"""
Browser API 端点 - 浏览器自动化

基于 browser-use 库实现浏览器控制

## Session 管理（多浏览器实例）
- POST /api/v1/browser/sessions                    创建新 Session
- GET  /api/v1/browser/sessions                    列出所有 Sessions
- GET  /api/v1/browser/sessions/{session_id}       获取 Session 详情
- DELETE /api/v1/browser/sessions/{session_id}     关闭 Session

## Tab 管理（同一浏览器内多标签页）
- GET  /api/v1/browser/sessions/{session_id}/tabs           获取所有 Tabs
- POST /api/v1/browser/sessions/{session_id}/tabs           新建 Tab
- POST /api/v1/browser/sessions/{session_id}/tabs/{tab_id}/focus  切换到 Tab
- DELETE /api/v1/browser/sessions/{session_id}/tabs/{tab_id}      关闭 Tab

## 操作执行
- POST /api/v1/browser/sessions/{session_id}/step  执行操作（可选 tab_id）

## 兼容旧 API（单例模式，向后兼容）
- GET  /api/v1/browser/status           获取连接状态
- GET  /api/v1/browser/browsers         获取已安装浏览器
- GET  /api/v1/browser/profiles         获取浏览器 Profile 列表
- POST /api/v1/browser/connect          启动新浏览器并连接
- POST /api/v1/browser/attach           接管已有浏览器（CDP）
- POST /api/v1/browser/disconnect       断开连接
- POST /api/v1/browser/page_state       获取页面状态
- POST /api/v1/browser/step             执行操作
- POST /api/v1/browser/screenshot       截图
"""

from fastapi import APIRouter, HTTPException, Query, Path
from pydantic import BaseModel, Field
from typing import Dict, Any, List, Optional
import logging

from agent_ndjson_debug import write_agent_ndjson_line as _agent_log

from .project import format_tree_as_text

logger = logging.getLogger(__name__)
router = APIRouter()

# 尝试导入 browser_use 控制器
try:
    from controllers.browser_use.config import BrowserConfig, BrowserType
    from controllers.browser_use.controller import BrowserController, get_controller, reset_controller
    from controllers.browser_use.session_manager import BrowserSessionManager, get_session_manager
    BROWSER_USE_AVAILABLE = True
except ImportError as e:
    logger.warning(f"browser-use not available: {e}")
    BROWSER_USE_AVAILABLE = False
    BrowserConfig = None
    BrowserType = None
    BrowserController = None
    get_controller = None
    reset_controller = None
    BrowserSessionManager = None
    get_session_manager = None


# ==================== 请求模型 ====================

class ConnectRequest(BaseModel):
    """启动新浏览器连接请求"""
    browser_type: str = Field(default="auto", description="浏览器类型: chrome, edge, auto")
    profile_directory: str = Field(default="Default", description="Profile 目录名")
    headless: bool = Field(default=False, description="是否无头模式")
    highlight_elements: bool = Field(default=True, description="是否高亮显示交互元素")


class AttachRequest(BaseModel):
    """接管已有浏览器请求"""
    cdp_url: str = Field(
        default="http://localhost:9222",
        description="CDP URL，如 http://localhost:9222"
    )
    highlight_elements: bool = Field(default=True, description="是否高亮显示交互元素")
    target_url: Optional[str] = Field(default=None, description="目标页面 URL，用于精确匹配要操作的标签页")


class StepRequest(BaseModel):
    """执行操作请求"""
    actions: List[Dict[str, Any]] = Field(..., description="Action 列表")
    # Page state 相关参数
    max_elements: int = Field(default=100, ge=50, le=1000, description="最大元素数量")
    # Project files 相关参数
    include_project_files: bool = Field(default=False, description="是否包含项目文件列表")
    project_path: Optional[str] = Field(default=None, description="项目根目录路径（include_project_files=true 时必填）")
    project_max_depth: int = Field(default=4, ge=1, le=10, description="项目文件遍历最大深度")


class PageStateRequest(BaseModel):
    """获取页面状态请求"""
    include_screenshot: bool = Field(default=True, description="是否包含截图")
    max_elements: int = Field(default=100, description="最大元素数量")


class ScreenshotRequest(BaseModel):
    """截图请求"""
    full_page: bool = Field(default=False, description="是否全页面截图")


# ==================== Session 管理请求模型 ====================

class CreateSessionRequest(BaseModel):
    """创建 Session 请求"""
    browser_type: str = Field(default="auto", description="浏览器类型: chrome, edge, auto")
    profile_directory: str = Field(default="Default", description="Profile 目录名")
    headless: bool = Field(default=False, description="是否无头模式")
    highlight_elements: bool = Field(default=True, description="是否高亮显示交互元素")
    initial_url: Optional[str] = Field(default=None, description="初始 URL")


class AttachSessionRequest(BaseModel):
    """通过 CDP 创建 Session 请求"""
    cdp_url: str = Field(
        default="http://localhost:9222",
        description="CDP URL，如 http://localhost:9222"
    )
    highlight_elements: bool = Field(default=True, description="是否高亮显示交互元素")


class CreateTabRequest(BaseModel):
    """创建 Tab 请求"""
    url: str = Field(default="about:blank", description="新 Tab 的 URL")
    switch_to: bool = Field(default=True, description="是否切换到新 Tab")


class SessionStepRequest(BaseModel):
    """Session 操作请求"""
    actions: List[Dict[str, Any]] = Field(..., description="Action 列表")
    tab_id: Optional[str] = Field(default=None, description="指定 Tab ID，不指定则使用当前 Tab")
    return_screenshot: bool = Field(default=True, description="是否返回截图")
    max_elements: int = Field(default=100, ge=50, le=1000, description="最大元素数量")


# ==================== 辅助函数 ====================

def _check_available():
    """检查 browser-use 是否可用"""
    if not BROWSER_USE_AVAILABLE:
        raise HTTPException(
            status_code=503,
            detail="browser-use library not installed. Run: pip install browser-use"
        )


def _check_connected(controller):
    """检查是否已连接"""
    if not controller.is_connected:
        raise HTTPException(
            status_code=400,
            detail="Not connected to browser. Call /connect or /attach first."
        )


def _get_session_or_404(session_id: str):
    """获取 Session 或返回 404"""
    manager = get_session_manager()
    session = manager.get_session(session_id)
    if not session:
        raise HTTPException(
            status_code=404,
            detail=f"Session {session_id} not found"
        )
    return session


# ==================== Session 管理 API ====================

@router.post("/sessions")
async def create_session(request: CreateSessionRequest) -> Dict[str, Any]:
    """
    创建新的浏览器 Session
    
    每个 Session 是一个独立的浏览器实例，可以同时管理多个 Session。
    
    Returns:
        {
            "success": true,
            "data": {
                "session_id": "abc12345",
                "browser_type": "chrome",
                "profile": "Default",
                "created_at": "2024-01-01T00:00:00"
            }
        }
    """
    _check_available()
    
    manager = get_session_manager()
    result = await manager.create_session(
        browser_type=request.browser_type,
        profile_directory=request.profile_directory,
        headless=request.headless,
        highlight_elements=request.highlight_elements,
        initial_url=request.initial_url,
    )
    
    if not result.get("success"):
        raise HTTPException(status_code=500, detail=result.get("error", "Failed to create session"))
    
    return {"success": True, "data": result}


@router.post("/sessions/attach")
async def attach_session(request: AttachSessionRequest) -> Dict[str, Any]:
    """
    通过 CDP 接管已有浏览器创建 Session
    
    ⚠️ 使用前，用户需要用以下命令启动 Chrome：
    ```
    chrome.exe --remote-debugging-port=9222
    ```
    
    Returns:
        {
            "success": true,
            "data": {
                "session_id": "abc12345",
                "cdp_url": "http://localhost:9222",
                "current_url": "...",
                "current_title": "..."
            }
        }
    """
    _check_available()
    
    manager = get_session_manager()
    result = await manager.attach_session(
        cdp_url=request.cdp_url,
        highlight_elements=request.highlight_elements,
    )
    
    if not result.get("success"):
        raise HTTPException(status_code=500, detail=result.get("error", "Failed to attach session"))
    
    return {"success": True, "data": result}


@router.get("/sessions")
async def list_sessions() -> Dict[str, Any]:
    """
    列出所有 Sessions
    
    Returns:
        {
            "success": true,
            "data": {
                "sessions": [
                    {"session_id": "abc12345", "connected": true, ...},
                    ...
                ]
            }
        }
    """
    _check_available()
    
    manager = get_session_manager()
    sessions = manager.list_sessions()
    
    return {"success": True, "data": {"sessions": sessions}}


@router.get("/sessions/{session_id}")
async def get_session_status(
    session_id: str = Path(..., description="Session ID")
) -> Dict[str, Any]:
    """
    获取 Session 详细状态
    
    Returns:
        {
            "success": true,
            "data": {
                "session_id": "abc12345",
                "connected": true,
                "current_url": "...",
                "current_title": "...",
                ...
            }
        }
    """
    _check_available()
    
    manager = get_session_manager()
    status = await manager.get_session_status(session_id)
    
    if not status:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")
    
    return {"success": True, "data": status}


@router.delete("/sessions/{session_id}")
async def close_session(
    session_id: str = Path(..., description="Session ID")
) -> Dict[str, Any]:
    """
    关闭并删除 Session
    
    Returns:
        {"success": true, "data": {"session_id": "abc12345"}}
    """
    _check_available()
    
    manager = get_session_manager()
    result = await manager.close_session(session_id)
    
    if not result.get("success"):
        raise HTTPException(status_code=404, detail=result.get("error", "Failed to close session"))
    
    return {"success": True, "data": result}


# ==================== Tab 管理 API ====================

@router.get("/sessions/{session_id}/tabs")
async def get_tabs(
    session_id: str = Path(..., description="Session ID")
) -> Dict[str, Any]:
    """
    获取 Session 的所有 Tabs
    
    Returns:
        {
            "success": true,
            "data": {
                "tabs": [
                    {"tab_id": "xxx", "url": "...", "title": "...", "is_active": true},
                    ...
                ]
            }
        }
    """
    _check_available()
    _get_session_or_404(session_id)
    
    manager = get_session_manager()
    tabs = await manager.get_tabs(session_id)
    
    if tabs is None:
        raise HTTPException(status_code=500, detail="Failed to get tabs")
    
    return {"success": True, "data": {"tabs": tabs}}


@router.post("/sessions/{session_id}/tabs")
async def create_tab(
    session_id: str = Path(..., description="Session ID"),
    request: CreateTabRequest = None,
) -> Dict[str, Any]:
    """
    在 Session 中创建新 Tab
    
    Returns:
        {
            "success": true,
            "data": {
                "tab_id": "xxx",
                "url": "about:blank",
                "is_active": true
            }
        }
    """
    _check_available()
    _get_session_or_404(session_id)
    
    if request is None:
        request = CreateTabRequest()
    
    manager = get_session_manager()
    result = await manager.create_tab(
        session_id=session_id,
        url=request.url,
        switch_to=request.switch_to,
    )
    
    if not result or not result.get("success"):
        raise HTTPException(status_code=500, detail=result.get("error") if result else "Failed to create tab")
    
    return {"success": True, "data": result}


@router.post("/sessions/{session_id}/tabs/{tab_id}/focus")
async def switch_to_tab(
    session_id: str = Path(..., description="Session ID"),
    tab_id: str = Path(..., description="Tab ID"),
) -> Dict[str, Any]:
    """
    切换到指定 Tab
    
    Returns:
        {"success": true, "data": {"tab_id": "xxx"}}
    """
    _check_available()
    _get_session_or_404(session_id)
    
    manager = get_session_manager()
    result = await manager.switch_tab(session_id, tab_id)
    
    if not result or not result.get("success"):
        raise HTTPException(status_code=500, detail=result.get("error") if result else "Failed to switch tab")
    
    return {"success": True, "data": result}


@router.delete("/sessions/{session_id}/tabs/{tab_id}")
async def close_tab(
    session_id: str = Path(..., description="Session ID"),
    tab_id: str = Path(..., description="Tab ID"),
) -> Dict[str, Any]:
    """
    关闭指定 Tab
    
    Returns:
        {"success": true, "data": {"tab_id": "xxx"}}
    """
    _check_available()
    _get_session_or_404(session_id)
    
    manager = get_session_manager()
    result = await manager.close_tab(session_id, tab_id)
    
    if not result or not result.get("success"):
        raise HTTPException(status_code=500, detail=result.get("error") if result else "Failed to close tab")
    
    return {"success": True, "data": result}


# ==================== Session 操作执行 API ====================

@router.post("/sessions/{session_id}/step")
async def session_step(
    session_id: str = Path(..., description="Session ID"),
    request: SessionStepRequest = None,
) -> Dict[str, Any]:
    """
    在指定 Session 中执行操作
    
    支持的 Action 类型:
    
    **导航**:
    - `{"action": "go_to_url", "url": "https://example.com"}`
    - `{"action": "go_back"}`
    - `{"action": "go_forward"}`
    - `{"action": "refresh"}`
    
    **元素交互**:
    - `{"action": "click_element", "index": 5}`
    - `{"action": "input_text", "index": 3, "text": "hello"}`
    
    **滚动**:
    - `{"action": "scroll_down", "amount": 500}`
    - `{"action": "scroll_up", "amount": 500}`
    
    **键盘**:
    - `{"action": "press_key", "key": "Enter"}`
    
    **其他**:
    - `{"action": "wait", "seconds": 2}`
    - `{"action": "screenshot"}`
    
    Args:
        session_id: Session ID
        request.actions: Action 列表
        request.tab_id: 可选，指定 Tab ID
        request.return_screenshot: 是否返回截图
    
    Returns:
        {
            "success": true,
            "data": {
                "action_results": [...],
                "page_state": {...}
            }
        }
    """
    _check_available()
    session = _get_session_or_404(session_id)
    
    if request is None:
        raise HTTPException(status_code=400, detail="Request body required")
    
    controller = session.controller
    _check_connected(controller)
    
    try:
        # 如果指定了 tab_id，先切换到该 Tab
        if request.tab_id:
            manager = get_session_manager()
            switch_result = await manager.switch_tab(session_id, request.tab_id)
            if not switch_result or not switch_result.get("success"):
                raise HTTPException(
                    status_code=400,
                    detail=f"Failed to switch to tab {request.tab_id}: {switch_result.get('error') if switch_result else 'Unknown error'}"
                )
        
        # 执行所有操作
        results = []
        for action in request.actions:
            result = await controller.execute_action(action)
            results.append(result)
            if not result.get("success"):
                break
        
        # 获取最终页面状态
        page_state = await controller.get_page_state(
            include_screenshot=request.return_screenshot,
            max_elements=request.max_elements,  # 使用请求参数，默认 100
        )
        
        # 构建返回结果
        result = {
            "success": True,
            "data": {
                "action_results": results,
                "page_state": page_state,
            }
        }
        
        # 把 snapshot 添加到 data 中，方便 AI_Run 读取
        # 注意：始终添加，即使为空字符串（避免条件判断导致丢失）
        result["data"]["snapshot"] = page_state.get("snapshot", "")
        
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sessions/{session_id}/page_state")
async def session_page_state(
    session_id: str = Path(..., description="Session ID"),
    request: PageStateRequest = None,
) -> Dict[str, Any]:
    """
    获取 Session 的页面状态
    """
    _check_available()
    session = _get_session_or_404(session_id)
    
    if request is None:
        request = PageStateRequest()
    
    controller = session.controller
    _check_connected(controller)
    
    try:
        state = await controller.get_page_state(
            include_screenshot=request.include_screenshot,
            max_elements=request.max_elements,
        )
        return {"success": True, "data": state}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ==================== 兼容旧 API（单例模式）====================

@router.get("/status")
async def get_status() -> Dict[str, Any]:
    """
    获取浏览器控制器状态
    
    Returns:
        {
            "connected": bool,
            "browser_type": str,
            "profile": str,
            "current_url": str,
            "current_title": str
        }
    """
    _check_available()
    controller = get_controller()
    return await controller.get_status()


@router.get("/browsers")
async def get_installed_browsers() -> Dict[str, Any]:
    """
    获取已安装的浏览器列表
    
    Returns:
        {
            "browsers": [
                {"type": "chrome", "path": "...", "user_data_dir": "..."},
                {"type": "edge", "path": "...", "user_data_dir": "..."}
            ]
        }
    """
    _check_available()
    browsers = BrowserConfig.get_installed_browsers()
    return {"success": True, "data": {"browsers": browsers}}


@router.get("/profiles")
async def get_profiles(
    browser_type: str = Query("auto", description="浏览器类型: chrome, edge, auto")
) -> Dict[str, Any]:
    """
    获取浏览器的所有 Profile 列表
    
    Args:
        browser_type: "chrome", "edge", 或 "auto"
    
    Returns:
        {
            "profiles": [
                {"directory": "Default", "name": "用户1", "email": "..."},
                {"directory": "Profile 5", "name": "Difei", "email": "..."}
            ]
        }
    """
    _check_available()
    bt = BrowserType(browser_type.lower()) if browser_type.lower() in ["chrome", "edge", "auto"] else BrowserType.AUTO
    config = BrowserConfig(browser_type=bt)
    profiles = config.get_profiles()
    
    return {
        "success": True,
        "data": {
            "profiles": [
                {
                    "directory": p.directory,
                    "name": p.name,
                    "email": p.email,
                }
                for p in profiles
            ]
        }
    }


@router.post("/connect")
async def connect(request: ConnectRequest) -> Dict[str, Any]:
    """
    启动新浏览器并连接（复制 Profile 到临时目录）
    
    适用场景：需要独立的浏览器实例，不影响用户正在使用的浏览器
    """
    _check_available()
    
    bt = BrowserType(request.browser_type.lower()) if request.browser_type.lower() in ["chrome", "edge", "auto"] else BrowserType.AUTO
    
    config = BrowserConfig(
        browser_type=bt,
        profile_directory=request.profile_directory,
        headless=request.headless,
        highlight_elements=request.highlight_elements,
    )
    
    # 重置控制器
    controller = await reset_controller(config=config)
    
    # 连接
    result = await controller.connect()
    
    if not result.get("success"):
        raise HTTPException(status_code=500, detail=result.get("error", "Connection failed"))
    
    return {"success": True, "data": result}


@router.post("/attach")
async def attach(request: AttachRequest) -> Dict[str, Any]:
    """
    接管用户正在使用的浏览器（通过 CDP 连接）
    
    ⚠️ 使用前，用户需要用以下命令启动 Chrome：
    
    Windows:
    ```
    "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe" --remote-debugging-port=9222
    ```
    """
    _check_available()
    
    controller = get_controller()
    
    # 如果已连接，先断开
    if controller.is_connected:
        await controller.disconnect()
    
    # 接管浏览器
    result = await controller.attach(
        cdp_url=request.cdp_url,
        highlight_elements=request.highlight_elements,
        target_url=request.target_url,
    )
    
    if not result.get("success"):
        raise HTTPException(status_code=500, detail=result.get("error", "Attach failed"))
    
    return {"success": True, "data": result}


@router.post("/disconnect")
async def disconnect() -> Dict[str, Any]:
    """断开与浏览器的连接并关闭浏览器"""
    _check_available()
    controller = get_controller()
    result = await controller.disconnect()
    return {"success": True, "data": result}


@router.post("/page_state")
async def get_page_state(request: PageStateRequest = None) -> Dict[str, Any]:
    """
    获取页面状态
    
    Returns:
        {
            "url": str,
            "title": str,
            "screenshot_base64": str,
            "elements": [...],
            "element_count": int
        }
    """
    _check_available()
    
    if request is None:
        request = PageStateRequest()
    
    controller = get_controller()
    _check_connected(controller)
    
    try:
        # region agent log
        _agent_log(
            hypothesisId="C",
            location="api/v1/browser.py:/page_state",
            message="page_state request received",
            data={
                "include_screenshot": bool(request.include_screenshot),
                "max_elements": int(request.max_elements),
            },
        )
        # endregion

        state = await controller.get_page_state(
            include_screenshot=request.include_screenshot,
            max_elements=request.max_elements,
        )
        # region agent log
        _agent_log(
            hypothesisId="C",
            location="api/v1/browser.py:/page_state",
            message="page_state response summary",
            data={
                "url": (state.get("url", "") or "")[:200],
                "title": (state.get("title", "") or "")[:200],
                "returned_elements_len": int(len(state.get("elements") or [])),
                "returned_first_indices": [e.get("index") for e in (state.get("elements") or [])[:5]],
            },
        )
        # endregion
        return {"success": True, "data": state}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/step")
async def step(request: StepRequest) -> Dict[str, Any]:
    """
    执行操作并返回新的页面状态
    
    支持的 Action 类型:
    
    **导航**:
    - `{"action": "go_to_url", "url": "https://example.com"}`
    - `{"action": "go_back"}`
    - `{"action": "go_forward"}`
    - `{"action": "refresh"}`
    
    **元素交互**:
    - `{"action": "click_element", "index": 5}`
    - `{"action": "input_text", "index": 3, "text": "hello"}`
    
    **滚动**:
    - `{"action": "scroll_down", "amount": 500}`
    - `{"action": "scroll_up", "amount": 500}`
    
    **键盘**:
    - `{"action": "press_key", "key": "Enter"}`
    
    **其他**:
    - `{"action": "wait", "seconds": 2}`
    - `{"action": "screenshot"}`
    """
    _check_available()
    
    controller = get_controller()
    _check_connected(controller)
    
    try:
        # region agent log
        _agent_log(
            hypothesisId="C",
            location="api/v1/browser.py:/step",
            message="step request received",
            data={
                "actions_len": int(len(request.actions or [])),
                "actions_summary": [
                    {
                        "action": (a.get("action") or ""),
                        "index": a.get("index", None),
                        "text_len": (len(a.get("text") or "") if isinstance(a.get("text"), str) else None),
                    }
                    for a in (request.actions or [])[:5]
                ],
            },
        )
        # endregion

        # 执行所有操作
        results = []
        for action in request.actions:
            result = await controller.execute_action(action)
            results.append(result)
            # 如果某个操作失败，停止执行后续操作
            if not result.get("success"):
                break
        
        # 获取最终页面状态
        page_state = await controller.get_page_state(
            include_screenshot=True,
            max_elements=request.max_elements,  # 使用请求参数，默认 100
        )

        # region agent log
        _agent_log(
            hypothesisId="C",
            location="api/v1/browser.py:/step",
            message="step response summary",
            data={
                "action_results_len": int(len(results)),
                "first_action_success": (results[0].get("success") if results else None),
                "first_action_error": (results[0].get("error") if results else None),
                "page_url": (page_state.get("url", "") or "")[:200],
            },
        )
        # endregion
        
        # 如果需要项目文件列表
        if request.include_project_files and request.project_path:
            try:
                project_tree = format_tree_as_text(
                    project_path=request.project_path,
                    max_depth=request.project_max_depth,
                )
                page_state["project_files"] = project_tree
                logger.info(f"[Browser API] step: 附带项目文件列表，长度={len(project_tree)}")
            except Exception as e:
                logger.warning(f"[Browser API] Failed to get project files: {e}")
                page_state["project_files"] = f"Error: {str(e)}"
        
        # 打印完成标志
        all_success = all(r.get("success") for r in results)
        action_summary = ", ".join(a.get("action", "unknown") for a in request.actions[:3])
        if len(request.actions) > 3:
            action_summary += f"... (+{len(request.actions) - 3} more)"
        logger.info(f"[Browser API] step done: {len(results)} actions ({action_summary}), success={all_success}")
        
        # 构建返回结果
        result = {
            "success": True,
            "data": {
                "action_results": results,
                "page_state": page_state,
            }
        }
        
        # 把 snapshot 添加到 data 中，方便 AI_Run 读取
        # 注意：始终添加，即使为空字符串（避免条件判断导致丢失）
        result["data"]["snapshot"] = page_state.get("snapshot", "")
        
        return result
    except Exception as e:
        logger.error(f"[Browser API] step failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/screenshot")
async def take_screenshot(request: ScreenshotRequest = None) -> Dict[str, Any]:
    """截图"""
    _check_available()
    
    if request is None:
        request = ScreenshotRequest()
    
    controller = get_controller()
    _check_connected(controller)
    
    try:
        result = await controller.execute_action({
            "action": "screenshot",
            "full_page": request.full_page,
        })
        return {"success": True, "data": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
