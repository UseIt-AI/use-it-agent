"""
System API 端点 - 服务信息 + 机器环境感知 + 窗口/进程操作

服务信息:
- GET  /api/v1/health                 健康检查
- GET  /api/v1/info                   服务信息
- GET  /api/v1/capabilities           控制器能力

机器环境感知（给 AI Agent 用）:
- GET  /api/v1/system/windows             顶级窗口列表（主力：感知"用户开了哪些文档"）
- GET  /api/v1/system/windows/grouped     按进程聚合的窗口列表
- GET  /api/v1/system/foreground-window   前台窗口快捷查询
- GET  /api/v1/system/monitors            显示器列表（含工作区，tile 用）
- GET  /api/v1/system/processes           运行中的进程
- GET  /api/v1/system/installed-software  已安装软件（HKLM + HKCU + App Paths）
- GET  /api/v1/system/find-exe            按名字查软件可执行路径
- POST /api/v1/system/activate-window     把窗口切到前台（Alt-Tab 等效）
- POST /api/v1/system/launch              启动可执行文件（精确，exe_path）
- POST /api/v1/system/launch-app          启动软件（smart，支持 name/file/exe_path）

统一 dispatch 端点（给 AI 层压缩工具数用，内部转发到上面的细粒度 handler）:
- POST /api/v1/system/window-control      {action, ...} -> 一个工具覆盖所有窗口操作
- POST /api/v1/system/process-control     {action, ...} -> 一个工具覆盖所有进程/软件操作
"""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from typing import Dict, Any, List, Optional
import os
import sys
import logging

from core import controller_registry
from controllers.system import (
    ProcessHandler,
    SystemWindowHandler,
    SoftwareHandler,
    Launcher,
)

logger = logging.getLogger(__name__)
router = APIRouter()


# ========== 服务信息 ==========

@router.get("/health")
async def health_check() -> Dict[str, Any]:
    """健康检查"""
    return {
        "status": "ok",
        "version": "2.0.0",
        "api_version": "v1",
        "controllers": controller_registry.list_controllers(),
    }


@router.get("/info")
async def get_info() -> Dict[str, Any]:
    """服务详细信息"""
    controllers_info = {}
    for name, controller in controller_registry.get_all().items():
        controllers_info[name] = controller.get_supported_actions()

    return {
        "service": "UseIt Local Engine",
        "version": "2.0.0",
        "api_version": "v1",
        "python_version": sys.version,
        "platform": sys.platform,
        "pid": os.getpid(),
        "controllers": controllers_info,
    }


@router.get("/capabilities")
async def get_capabilities() -> Dict[str, Any]:
    """所有控制器支持的操作"""
    capabilities = {}
    for name, controller in controller_registry.get_all().items():
        capabilities[name] = controller.get_supported_actions()
    return capabilities


# ========== 机器环境感知 ==========

@router.get("/system/windows")
async def list_windows(
    process_name: Optional[str] = Query(None, description="按进程名过滤，如 POWERPNT.EXE"),
    title_contains: Optional[str] = Query(None, description="标题模糊匹配"),
    include_minimized: bool = Query(True, description="是否包含最小化窗口"),
) -> Dict[str, Any]:
    """
    列出所有打开的顶级窗口（AI 感知"用户开了哪些文档"的主力端点）。

    - Office SDI 模式下，每个打开的 ppt/word/xlsx 都是独立顶级窗口
    - 自动过滤系统/工具窗口，结果跟 Alt-Tab 列表基本一致
    - 每条记录都带 pid / process_name / exe，AI 可直接反查是哪个软件

    Example:
        /system/windows?process_name=POWERPNT.EXE → 返回所有 ppt 窗口
    """
    result = SystemWindowHandler.list_windows(
        process_name=process_name,
        title_contains=title_contains,
        include_minimized=include_minimized,
    )
    if not result.get("success"):
        raise HTTPException(status_code=500, detail=result.get("error", "unknown error"))
    return {"success": True, "data": result}


@router.get("/system/windows/grouped")
async def list_windows_grouped(
    process_name: Optional[str] = Query(None),
    title_contains: Optional[str] = Query(None),
    include_minimized: bool = Query(True),
) -> Dict[str, Any]:
    """
    按进程聚合窗口。适合回答"用户开了几个 ppt / 几个 word"这类问题。

    Returns:
        {"groups": [{"process_name": "POWERPNT.EXE", "window_count": 3, "windows": [...]}], ...}
    """
    result = SystemWindowHandler.group_by_process(
        process_name=process_name,
        title_contains=title_contains,
        include_minimized=include_minimized,
    )
    if not result.get("success"):
        raise HTTPException(status_code=500, detail=result.get("error", "unknown error"))
    return {"success": True, "data": result}


@router.get("/system/foreground-window")
async def get_foreground_window() -> Dict[str, Any]:
    """前台窗口（Alt-Tab 最前面那个）"""
    result = SystemWindowHandler.get_foreground_window()
    if not result.get("success"):
        raise HTTPException(status_code=500, detail=result.get("error", "unknown error"))
    return {"success": True, "data": result}


@router.get("/system/processes")
async def list_processes(
    name_contains: Optional[str] = Query(None, description="按 exe 名模糊匹配"),
    include_system: bool = Query(False, description="是否包含 svchost 等系统进程"),
    include_metrics: bool = Query(False, description="是否采集 CPU/内存（有开销）"),
) -> Dict[str, Any]:
    """
    列出运行中的进程。

    用于感知后台/托盘类应用（没有顶级窗口的）。默认过滤掉系统噪音进程。
    """
    result = ProcessHandler.list_processes(
        name_contains=name_contains,
        include_system=include_system,
        include_metrics=include_metrics,
    )
    if not result.get("success"):
        raise HTTPException(status_code=500, detail=result.get("error", "unknown error"))
    return {"success": True, "data": result}


@router.get("/system/processes/{pid}")
async def get_process(pid: int) -> Dict[str, Any]:
    """按 PID 取单个进程详情"""
    result = ProcessHandler.get_process_info(pid)
    if not result.get("success"):
        # 进程不存在/无权访问用 404 更合适
        raise HTTPException(status_code=404, detail=result.get("error", "not found"))
    return {"success": True, "data": result}


@router.get("/system/installed-software")
async def get_installed_software(
    name_contains: Optional[str] = Query(None, description="按软件名模糊匹配"),
) -> Dict[str, Any]:
    """
    查询本机已安装的软件。

    数据源：
    - HKLM\\...\\Uninstall（系统级）
    - HKLM\\WOW6432Node\\...（32 位）
    - HKCU\\...\\Uninstall（用户级，如 VS Code user installer）
    - App Paths 注册表（补全可执行路径）

    每条记录会尽量补全 `exe_path`，可直接传给 /system/launch。
    """
    result = SoftwareHandler.list_installed(name_contains=name_contains)
    if not result.get("success"):
        raise HTTPException(status_code=500, detail=result.get("error", "unknown error"))
    return {"success": True, "data": result}


@router.get("/system/find-exe")
async def find_exe(
    name_contains: str = Query(..., description="按软件名模糊匹配"),
) -> Dict[str, Any]:
    """
    按软件名模糊匹配，返回可启动的 exe 候选列表。
    AI 用这个来决定 /system/launch 的目标 exe_path。
    """
    result = SoftwareHandler.find_exe(name_contains=name_contains)
    if not result.get("success"):
        raise HTTPException(status_code=500, detail=result.get("error", "unknown error"))
    return {"success": True, "data": result}


class ActivateWindowRequest(BaseModel):
    """激活窗口请求 —— hwnd 优先，否则用 process_name / title_contains 模糊匹配"""
    hwnd: Optional[int] = Field(
        default=None,
        description="窗口句柄（推荐，从 /system/windows 响应里拿）",
    )
    process_name: Optional[str] = Field(
        default=None,
        description="按进程名过滤，如 POWERPNT.EXE（大小写不敏感）",
    )
    title_contains: Optional[str] = Field(
        default=None,
        description="标题模糊匹配",
    )


@router.post("/system/activate-window")
async def activate_window(request: ActivateWindowRequest) -> Dict[str, Any]:
    """
    把某个窗口切到前台（等价于 Alt-Tab 切过去）。

    三种用法:
    - 精确: ``{"hwnd": 3081918}``
    - 按进程: ``{"process_name": "POWERPNT.EXE"}``
    - 按标题: ``{"title_contains": "天使轮"}``

    匹配到多个窗口时返回 ``success: false`` + ``candidates`` 列表，
    调用方（AI）根据 candidates 里的 hwnd 重新调一次就能精确激活。
    """
    if request.hwnd is None and not request.process_name and not request.title_contains:
        raise HTTPException(
            status_code=400,
            detail="provide at least one of: hwnd, process_name, title_contains",
        )
    result = SystemWindowHandler.activate_window(
        hwnd=request.hwnd,
        process_name=request.process_name,
        title_contains=request.title_contains,
    )
    # 失败（含 ambiguous 多候选）不抛 HTTP 500，业务态信息放到 data 里让调用方处理
    return {"success": bool(result.get("success")), "data": result}


class LaunchRequest(BaseModel):
    """启动进程请求（精确 exe_path）"""
    exe_path: str = Field(..., description="exe 完整路径，或 shell:... 协议")
    args: Optional[List[str]] = Field(default=None, description="命令行参数列表")
    cwd: Optional[str] = Field(default=None, description="工作目录")
    detached: bool = Field(default=True, description="是否脱离父进程独立运行")


@router.post("/system/launch")
async def launch(request: LaunchRequest) -> Dict[str, Any]:
    """
    启动一个可执行文件。

    **安全约束**:
    - 只支持 .exe / .bat / .cmd / .com / .lnk / .msi，或 shell: 协议
    - `args` 必须是 list[str]，不做 shell 拼接，不会被 shell injection

    Example:
        {"exe_path": "C:\\\\Program Files\\\\...\\\\POWERPNT.EXE", "args": ["C:\\\\temp\\\\x.pptx"]}
    """
    result = Launcher.launch(
        exe_path=request.exe_path,
        args=request.args,
        cwd=request.cwd,
        detached=request.detached,
    )
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "launch failed"))
    return {"success": True, "data": result}


class LaunchAppRequest(BaseModel):
    """智能启动请求 —— AI 友好，至少提供 name / file / exe_path 其中之一"""
    name: Optional[str] = Field(
        default=None,
        description="软件名，按 installed-software 模糊匹配，如 'PowerPoint' / 'Chrome'",
    )
    file: Optional[str] = Field(
        default=None,
        description="要打开的文件绝对路径（仅 file 时用系统关联程序打开）",
    )
    exe_path: Optional[str] = Field(
        default=None,
        description="exe 完整路径（最精确，传了就无视 name）",
    )
    args: Optional[List[str]] = Field(default=None, description="命令行参数")
    cwd: Optional[str] = Field(default=None, description="工作目录")


@router.post("/system/launch-app")
async def launch_app(request: LaunchAppRequest) -> Dict[str, Any]:
    """
    智能启动 —— 给 AI 用的友好入口，支持以下写法:

    1. ``{"name": "PowerPoint"}``
       engine 先 find-exe 再 launch。多候选时会用启发式挑一个名字最像的。
    2. ``{"file": "C:/temp/deck.pptx"}``
       用系统关联程序（.pptx -> PowerPoint）打开。
    3. ``{"name": "PowerPoint", "file": "C:/temp/deck.pptx"}``
       明确指定用 PowerPoint 打开这个 pptx。
    4. ``{"exe_path": "C:/...POWERPNT.EXE", "args": [...]}``
       精确启动（同 /system/launch）。
    """
    if not (request.name or request.file or request.exe_path):
        raise HTTPException(
            status_code=400,
            detail="provide at least one of: name, file, exe_path",
        )
    result = Launcher.launch_smart(
        name=request.name,
        file=request.file,
        exe_path=request.exe_path,
        args=request.args,
        cwd=request.cwd,
    )
    return {"success": bool(result.get("success")), "data": result}


@router.get("/system/monitors")
async def list_monitors() -> Dict[str, Any]:
    """
    列出所有显示器及其工作区（排除任务栏后的可用区域）。

    id 从 1 开始，1 = 主显示器。tile 操作可用 monitor_id 指定目标屏幕。
    """
    result = SystemWindowHandler.list_monitors()
    if not result.get("success"):
        raise HTTPException(status_code=500, detail=result.get("error", "unknown error"))
    return {"success": True, "data": result}


# ============================================================
#  统一 dispatch 端点 —— 给 AI 层压缩工具数
# ============================================================
#
# 设计原则：
# - 一个 HTTP 端点 = 一个 AI 工具
# - 请求体形如 {"action": "minimize", ...其它参数}
# - 内部转发到细粒度 handler，保持单元测试/调试友好
# - 永不 raise HTTPException（业务失败也 200 + success:false），让 AI 能拿到
#   完整的 error / candidates 信息做决策

class WindowControlRequest(BaseModel):
    """
    窗口操作统一入口。通过 action 字段分发到具体操作。

    action 枚举（大小写敏感）:
      - "list"           列窗口（可选 process_name / title_contains / include_minimized）
      - "get_foreground" 取前台窗口
      - "activate"       切到前台（需要 hwnd 或 process_name+title_contains）
      - "minimize"       最小化
      - "maximize"       最大化
      - "restore"        还原
      - "close"          关闭（可选 force=true 强杀）
      - "set_topmost"    置顶/取消置顶（需要 on: bool）
      - "move_resize"    精确摆放（需要 x, y, width, height）
      - "tile"           平铺多窗口（需要 hwnds + layout，可选 monitor_id）
      - "list_monitors"  列显示器
      - "capture"        截图。scope="window"|"monitor"|"all_screens"；不抢焦点
    """
    action: str = Field(..., description="操作名，见类注释")

    # 目标定位（任选一种；tile 用 hwnds 代替）
    hwnd: Optional[int] = Field(default=None, description="窗口句柄（推荐）")
    process_name: Optional[str] = Field(default=None, description="进程名模糊匹配")
    title_contains: Optional[str] = Field(default=None, description="标题子串")

    # list 专用
    include_minimized: bool = Field(default=True, description="list 时是否包含最小化窗口")

    # set_topmost 专用
    on: Optional[bool] = Field(default=None, description="set_topmost 的开关")

    # move_resize 专用
    x: Optional[int] = Field(default=None)
    y: Optional[int] = Field(default=None)
    width: Optional[int] = Field(default=None)
    height: Optional[int] = Field(default=None)

    # tile 专用
    hwnds: Optional[List[int]] = Field(default=None, description="tile 时要平铺的窗口句柄列表")
    layout: Optional[str] = Field(
        default=None,
        description=(
            "tile 布局。单窗口 snap: full / left_half / right_half / top_half / "
            "bottom_half / top_left / top_right / bottom_left / bottom_right / center；"
            "均分: left_right / top_bottom / vertical_3 / horizontal_3 / vertical_n / horizontal_n；"
            "网格: grid_2x2 / grid_2x3 / grid_3x2 / grid_3x3；"
            "主从: main_left / main_right / main_top / main_bottom；auto 根据 n 自动选。"
        ),
    )
    monitor_id: Optional[int] = Field(default=None, description="tile 的目标显示器 id")
    ratios: Optional[List[float]] = Field(
        default=None,
        description=(
            "tile 非对称比例。对均分 layout 长度 = hwnds；对 main_* 长度 = 2 (main, stack)。"
            "支持整数或小数，[4, 1] 与 [0.8, 0.2] 都表示 80/20。"
        ),
    )
    zones: Optional[List[Dict[str, float]]] = Field(
        default=None,
        description=(
            "tile 完全自定义矩形（优先级高于 layout/ratios）。每项 "
            "{x, y, width, height}，值都是 0~1 的比例（相对于所选显示器的工作区）。"
            "长度应等于 hwnds；顺序决定放置。"
        ),
    )

    # close 专用
    force: bool = Field(default=False, description="close=true 时强杀进程")

    # capture 专用
    scope: Optional[str] = Field(
        default=None,
        description=(
            'capture 专用：截图范围。"window"=单窗口（默认；不抢焦点）；'
            '"monitor"=整个显示器（含桌面其它窗口，适合跨软件协作）；'
            '"all_screens"=多屏虚拟桌面。'
        ),
    )
    prefer_printwindow: Optional[bool] = Field(
        default=None,
        description='capture scope=window 可选：true 时优先 PrintWindow（可截被遮挡/最小化的窗口），默认 false',
    )
    compress: Optional[bool] = Field(
        default=None,
        description="capture 可选：是否压缩（默认 true，约 300KB）",
    )


@router.post("/system/window-control")
async def window_control(request: WindowControlRequest) -> Dict[str, Any]:
    """
    窗口操作统一入口 —— 一个端点覆盖所有窗口 CRUD + 布局操作。

    示例:
        {"action": "list", "process_name": "POWERPNT.EXE"}
        {"action": "minimize", "hwnd": 3081918}
        {"action": "set_topmost", "hwnd": 3081918, "on": true}
        {"action": "move_resize", "hwnd": 3081918, "x": 0, "y": 0, "width": 960, "height": 1080}
        {"action": "tile", "hwnds": [3081918, 1180012], "layout": "left_right"}
        {"action": "close", "hwnd": 3081918, "force": false}
    """
    a = (request.action or "").strip().lower()
    W = SystemWindowHandler

    # --- 查询类 ---
    if a == "list":
        result = W.list_windows(
            process_name=request.process_name,
            title_contains=request.title_contains,
            include_minimized=request.include_minimized,
        )
    elif a == "get_foreground":
        result = W.get_foreground_window()
    elif a == "list_monitors":
        result = W.list_monitors()

    # --- 需要定位的单窗口操作 ---
    elif a == "activate":
        result = W.activate_window(
            hwnd=request.hwnd,
            process_name=request.process_name,
            title_contains=request.title_contains,
        )
    elif a == "minimize":
        result = W.minimize(
            hwnd=request.hwnd,
            process_name=request.process_name,
            title_contains=request.title_contains,
        )
    elif a == "maximize":
        result = W.maximize(
            hwnd=request.hwnd,
            process_name=request.process_name,
            title_contains=request.title_contains,
        )
    elif a == "restore":
        result = W.restore(
            hwnd=request.hwnd,
            process_name=request.process_name,
            title_contains=request.title_contains,
        )
    elif a == "close":
        result = W.close(
            hwnd=request.hwnd,
            process_name=request.process_name,
            title_contains=request.title_contains,
            force=request.force,
        )
    elif a == "set_topmost":
        if request.on is None:
            result = {"success": False, "error": "set_topmost requires `on: bool`"}
        else:
            result = W.set_topmost(
                on=bool(request.on),
                hwnd=request.hwnd,
                process_name=request.process_name,
                title_contains=request.title_contains,
            )
    elif a == "move_resize":
        if None in (request.x, request.y, request.width, request.height):
            result = {"success": False, "error": "move_resize requires x, y, width, height"}
        else:
            result = W.move_resize(
                x=int(request.x),
                y=int(request.y),
                width=int(request.width),
                height=int(request.height),
                hwnd=request.hwnd,
                process_name=request.process_name,
                title_contains=request.title_contains,
            )

    # --- 多窗口布局 ---
    elif a == "tile":
        if not request.hwnds:
            result = {"success": False, "error": "tile requires hwnds: [int, ...]"}
        else:
            result = W.tile(
                hwnds=list(request.hwnds),
                layout=request.layout or "auto",
                monitor_id=request.monitor_id,
                ratios=list(request.ratios) if request.ratios else None,
                zones=[dict(z) for z in request.zones] if request.zones else None,
            )

    # --- 截图（不抢焦点） ---
    elif a == "capture":
        capture_kwargs: Dict[str, Any] = {
            "scope": (request.scope or "window"),
            "hwnd": request.hwnd,
            "process_name": request.process_name,
            "title_contains": request.title_contains,
            "monitor_id": request.monitor_id,
        }
        if request.prefer_printwindow is not None:
            capture_kwargs["prefer_printwindow"] = bool(request.prefer_printwindow)
        if request.compress is not None:
            capture_kwargs["compress"] = bool(request.compress)
        result = W.capture(**capture_kwargs)

    else:
        result = {
            "success": False,
            "error": f"unknown action: {request.action!r}",
            "valid_actions": [
                "list", "get_foreground", "list_monitors",
                "activate", "minimize", "maximize", "restore", "close",
                "set_topmost", "move_resize", "tile", "capture",
            ],
        }

    return {"success": bool(result.get("success")), "data": result}


class ProcessControlRequest(BaseModel):
    """
    进程 / 软件操作统一入口。

    action 枚举:
      - "launch"           启动应用/打开文件（name / file / exe_path 任选）
      - "find_exe"         按名字查可启动 exe 候选（name 必填）
      - "list_installed"   列出已安装软件（可选 name 过滤）
      - "list_processes"   列出运行中进程（可选 name_contains / include_system / include_metrics）
      - "get_process"      按 pid 取进程详情（pid 必填）
    """
    action: str = Field(..., description="操作名，见类注释")

    # launch / find_exe / list_installed 用
    name: Optional[str] = Field(default=None, description="软件名")
    file: Optional[str] = Field(default=None, description="launch 时要打开的文件")
    exe_path: Optional[str] = Field(default=None, description="launch 时的精确 exe 路径")
    args: Optional[List[str]] = Field(default=None, description="launch 时的命令行参数")
    cwd: Optional[str] = Field(default=None, description="launch 时的工作目录")

    # list_processes 用
    name_contains: Optional[str] = Field(default=None, description="list_processes 按 exe 名过滤")
    include_system: bool = Field(default=False, description="list_processes 是否含系统噪音进程")
    include_metrics: bool = Field(default=False, description="list_processes 是否采 CPU/内存")

    # get_process 用
    pid: Optional[int] = Field(default=None, description="get_process 的目标 pid")


@router.post("/system/process-control")
async def process_control(request: ProcessControlRequest) -> Dict[str, Any]:
    """
    进程/软件操作统一入口。

    示例:
        {"action": "launch", "name": "PowerPoint"}
        {"action": "launch", "file": "C:/tmp/deck.pptx"}
        {"action": "find_exe", "name": "Cursor"}
        {"action": "list_installed", "name": "Office"}
        {"action": "list_processes", "name_contains": "POWERPNT"}
        {"action": "get_process", "pid": 22796}
    """
    a = (request.action or "").strip().lower()

    if a == "launch":
        if not (request.name or request.file or request.exe_path):
            result: Dict[str, Any] = {
                "success": False,
                "error": "launch requires one of: name, file, exe_path",
            }
        else:
            result = Launcher.launch_smart(
                name=request.name,
                file=request.file,
                exe_path=request.exe_path,
                args=request.args,
                cwd=request.cwd,
            )
    elif a == "find_exe":
        if not request.name:
            result = {"success": False, "error": "find_exe requires `name`"}
        else:
            result = SoftwareHandler.find_exe(name_contains=request.name)
    elif a == "list_installed":
        result = SoftwareHandler.list_installed(name_contains=request.name)
    elif a == "list_processes":
        result = ProcessHandler.list_processes(
            name_contains=request.name_contains,
            include_system=request.include_system,
            include_metrics=request.include_metrics,
        )
    elif a == "get_process":
        if request.pid is None:
            result = {"success": False, "error": "get_process requires `pid`"}
        else:
            result = ProcessHandler.get_process_info(int(request.pid))
    else:
        result = {
            "success": False,
            "error": f"unknown action: {request.action!r}",
            "valid_actions": ["launch", "find_exe", "list_installed", "list_processes", "get_process"],
        }

    return {"success": bool(result.get("success")), "data": result}
