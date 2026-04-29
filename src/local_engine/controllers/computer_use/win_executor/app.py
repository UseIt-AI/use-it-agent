#!/usr/bin/env python
"""
Windows Executor - Windows 桌面自动化执行器

注意：不要设置 DPI 感知！
保持 Windows 默认的 DPI 虚拟化，这样：
- pynput 使用逻辑坐标
- 屏幕 API 返回逻辑分辨率
- 截图自动缩放到逻辑分辨率
三者天然对齐，无需坐标转换。

提供 Windows 平台的桌面自动化能力：
- 鼠标/键盘控制（pynput）
- 屏幕截图（pillow）
- 剪贴板操作（win32clipboard）
- 文件系统操作
- 窗口管理（win32gui）

使用方式：
- 作为 Local Engine 的一部分嵌入运行
- 或独立运行: python -m controllers.computer_use.win_executor
"""
import json
import logging
import os
import sys

# 支持直接运行 app.py
if __name__ == "__main__" and __package__ is None:
    # 将父目录添加到 sys.path (local_engine 根目录)
    import pathlib
    root_dir = pathlib.Path(__file__).parent.parent.parent.parent
    if str(root_dir) not in sys.path:
        sys.path.insert(0, str(root_dir))
    __package__ = "controllers.computer_use.win_executor"

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from .core.models import CmdRequest
from .core.dependencies import PIL_AVAILABLE, PYNPUT_AVAILABLE, WINDOWS_API_AVAILABLE
from .handlers import (
    MouseHandler,
    KeyboardHandler,
    ScreenHandler,
    ClipboardHandler,
    FilesystemHandler,
    WindowHandler,
)

# ============================================================
# 日志配置
# ============================================================
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)-8s %(name)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# ============================================================
# FastAPI 应用
# ============================================================
app = FastAPI(
    title="Windows Executor",
    description="Windows 桌面自动化执行器",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================================
# 命令路由表
# ============================================================
COMMAND_HANDLERS = {
    # 版本信息
    "version": lambda p: {
        "success": True,
        "protocol_version": "1.0.0",
        "package_version": "1.0.0",
        "server": "win_executor"
    },
    
    # 鼠标操作
    "left_click": lambda p: MouseHandler.click(p.get("x"), p.get("y"), "left"),
    "right_click": lambda p: MouseHandler.click(p.get("x"), p.get("y"), "right"),
    "middle_click": lambda p: MouseHandler.click(p.get("x"), p.get("y"), "middle"),
    "double_click": lambda p: MouseHandler.double_click(p.get("x"), p.get("y"), p.get("button", "left")),
    "mouse_move": lambda p: MouseHandler.move(int(p["x"]), int(p["y"])) if p.get("x") and p.get("y") else {"success": False, "error": "x and y required"},
    "move_cursor": lambda p: MouseHandler.move(int(p["x"]), int(p["y"])) if p.get("x") and p.get("y") else {"success": False, "error": "x and y required"},
    "mouse_down": lambda p: MouseHandler.mouse_down(p.get("button", "left"), p.get("x"), p.get("y")),
    "mouse_up": lambda p: MouseHandler.mouse_up(p.get("button", "left"), p.get("x"), p.get("y")),
    "drag": lambda p: MouseHandler.drag(
        start_x=p.get("start_x") or p.get("x"),
        start_y=p.get("start_y") or p.get("y"),
        end_x=p.get("end_x"),
        end_y=p.get("end_y"),
        dx=p.get("dx", p.get("offset_x", 0)),
        dy=p.get("dy", p.get("offset_y", 0)),
        path=p.get("path"),
        button=p.get("button", "left"),
        speed=p.get("speed"),
    ),
    "drag_to": lambda p: MouseHandler.drag_to(int(p["x"]), int(p["y"])) if p.get("x") and p.get("y") else {"success": False, "error": "x and y required"},
    "scroll": lambda p: MouseHandler.scroll(
        int(p.get("dx", p.get("scroll_x", 0))),
        int(p.get("dy", p.get("scroll_y", 0))),
        p.get("x"),
        p.get("y")
    ),
    "scroll_down": lambda p: MouseHandler.scroll_down(int(p.get("clicks", 3))),
    "scroll_up": lambda p: MouseHandler.scroll_up(int(p.get("clicks", 3))),
    "get_cursor_position": lambda p: MouseHandler.get_position(),
    
    # 键盘操作
    "type": lambda p: KeyboardHandler.type_text(p.get("text", "")),
    "type_text": lambda p: KeyboardHandler.type_text(p.get("text", "")),
    "key": lambda p: KeyboardHandler.press_key(p.get("key", "")),
    "press_key": lambda p: KeyboardHandler.press_key(p.get("key", "")),
    "key_down": lambda p: KeyboardHandler.key_down(p.get("key", "")),
    "key_up": lambda p: KeyboardHandler.key_up(p.get("key", "")),
    "hotkey": lambda p: KeyboardHandler.hotkey(p.get("keys", p.get("combination", ""))),
    "key_combination": lambda p: KeyboardHandler.hotkey(p.get("keys", p.get("combination", ""))),
    
    # 屏幕操作
    "screenshot": lambda p: ScreenHandler.screenshot(),
    "get_screen_size": lambda p: ScreenHandler.get_screen_size(),
    "get_screen_info": lambda p: ScreenHandler.get_screen_info(),
    
    # 剪贴板操作
    "get_clipboard": lambda p: ClipboardHandler.get_clipboard(),
    "copy_to_clipboard": lambda p: ClipboardHandler.get_clipboard(),
    "set_clipboard": lambda p: ClipboardHandler.set_clipboard(p.get("text", "")),
    
    # 文件系统操作
    "file_exists": lambda p: FilesystemHandler.file_exists(p.get("path", "")),
    "directory_exists": lambda p: FilesystemHandler.directory_exists(p.get("path", "")),
    "list_dir": lambda p: FilesystemHandler.list_dir(p.get("path", ".")),
    "read_text": lambda p: FilesystemHandler.read_text(p.get("path", ""), p.get("encoding", "utf-8")),
    "write_text": lambda p: FilesystemHandler.write_text(p.get("path", ""), p.get("content", ""), p.get("encoding", "utf-8")),
    "read_bytes": lambda p: FilesystemHandler.read_bytes(p.get("path", "")),
    "write_bytes": lambda p: FilesystemHandler.write_bytes(p.get("path", ""), p.get("content", "")),
    "get_file_size": lambda p: FilesystemHandler.get_file_size(p.get("path", "")),
    "delete_file": lambda p: FilesystemHandler.delete_file(p.get("path", "")),
    "create_dir": lambda p: FilesystemHandler.create_dir(p.get("path", "")),
    "delete_dir": lambda p: FilesystemHandler.delete_dir(p.get("path", "")),
    "run_command": lambda p: FilesystemHandler.run_command(p.get("command", ""), p.get("timeout", 30)),
    
    # 窗口操作
    "get_accessibility_tree": lambda p: WindowHandler.get_accessibility_tree(),
    "find_element": lambda p: WindowHandler.find_element(p.get("title", "")),
}


def execute_command(command: str, params: dict) -> dict:
    """执行命令"""
    command = command.lower()
    
    handler = COMMAND_HANDLERS.get(command)
    if handler:
        try:
            return handler(params)
        except Exception as e:
            logger.exception(f"Command '{command}' failed")
            return {"success": False, "error": str(e)}
    else:
        return {"success": False, "error": f"Unknown command: {command}"}


# ============================================================
# API 路由
# ============================================================

@app.get("/")
async def root():
    """健康检查"""
    return {
        "status": "ok",
        "service": "Windows Executor",
        "version": "1.0.0",
        "capabilities": {
            "pynput": PYNPUT_AVAILABLE,
            "pillow": PIL_AVAILABLE,
            "windows_api": WINDOWS_API_AVAILABLE,
        }
    }


@app.get("/health")
async def health():
    """健康检查"""
    return {"status": "healthy"}

# deprecated
# @app.post("/action", response_model=ActionResponse)
# async def execute_action(req: ActionRequest):
#     """执行动作（简化接口）"""
#     action = req.action.lower()
    
#     # 构建参数
#     params = {
#         "x": req.x,
#         "y": req.y,
#         "button": req.button,
#         "text": req.text,
#         "key": req.key,
#         "keys": req.keys,
#         "clicks": req.clicks,
#         "scroll_x": req.scroll_x,
#         "scroll_y": req.scroll_y,
#     }
    
#     # 映射 action 到 command
#     action_map = {
#         "click": "left_click",
#         "double_click": "double_click",
#         "move": "mouse_move",
#         "mouse_down": "mouse_down",
#         "mouse_up": "mouse_up",
#         "drag": "drag",
#         "scroll": "scroll",
#         "scroll_down": "scroll_down",
#         "scroll_up": "scroll_up",
#         "type": "type",
#         "key": "key",
#         "hotkey": "hotkey",
#         "screenshot": "screenshot",
#         "get_screen_size": "get_screen_size",
#         "get_cursor_position": "get_cursor_position",
#         "get_clipboard": "get_clipboard",
#         "set_clipboard": "set_clipboard",
#     }
    
#     command = action_map.get(action, action)
#     result = execute_command(command, params)
    
#     return ActionResponse(
#         success=result.get("success", False),
#         error=result.get("error"),
#         data={k: v for k, v in result.items() if k not in ("success", "error")} or None
#     )


@app.post("/cmd")
async def execute_cmd(req: CmdRequest):
    """兼容 cua-computer-server 的 /cmd 接口"""
    return execute_command(req.command, req.params or {})


# ============================================================
# WebSocket 端点
# ============================================================

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket 端点 - 兼容 cua-computer SDK"""
    await websocket.accept()
    logger.info("WebSocket client connected")
    
    try:
        while True:
            data = await websocket.receive_text()
            logger.debug(f"WS received: {data[:200]}...")
            
            try:
                message = json.loads(data)
                command = message.get("command", "")
                params = message.get("params", {})
                
                result = execute_command(command, params)
                await websocket.send_text(json.dumps(result))
                
            except json.JSONDecodeError as e:
                await websocket.send_text(json.dumps({"success": False, "error": f"Invalid JSON: {e}"}))
            except Exception as e:
                await websocket.send_text(json.dumps({"success": False, "error": str(e)}))
                
    except WebSocketDisconnect:
        logger.info("WebSocket client disconnected")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")


# ============================================================
# 启动入口
# ============================================================

def main():
    """启动服务"""
    import uvicorn
    
    host = os.environ.get('CUA_SERVER_HOST', '0.0.0.0')
    port = int(os.environ.get('CUA_SERVER_PORT', '8080'))
    
    logger.info("=" * 60)
    logger.info("  Windows Executor Starting...")
    logger.info("=" * 60)
    logger.info(f"  PID: {os.getpid()}")
    logger.info(f"  Python: {sys.version}")
    logger.info(f"  Host: {host}")
    logger.info(f"  Port: {port}")
    logger.info(f"  pynput: {PYNPUT_AVAILABLE}")
    logger.info(f"  PIL: {PIL_AVAILABLE}")
    logger.info(f"  Windows API: {WINDOWS_API_AVAILABLE}")
    logger.info("=" * 60)
    
    uvicorn.run(app, host=host, port=port, log_level='info')


if __name__ == '__main__':
    main()
