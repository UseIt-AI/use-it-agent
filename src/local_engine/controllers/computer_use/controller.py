"""
Computer Use 本地执行控制器
直接调用 win_executor 的 handlers，不依赖外部服务
"""
import asyncio
import base64
import io
import logging
from typing import Any, Dict, List, Literal, TypedDict, Union

from PIL import Image

logger = logging.getLogger(__name__)

# 直接导入本地 handlers
from .win_executor.handlers import (
    MouseHandler,
    KeyboardHandler,
    ScreenHandler,
    ClipboardHandler,
    FilesystemHandler,
    WindowHandler,
)

# 截图压缩配置（已移至 image_utils.py）
# 全屏截图目标尺寸：16:9 → 1366x768，按宽度缩放保持比例
from .win_executor.handlers.image_utils import (
    compress_fullscreen_screenshot,
    FULLSCREEN_TARGET_WIDTH,
    FULLSCREEN_TARGET_HEIGHT,
)

# 兼容旧代码的别名
SCREENSHOT_TARGET_WIDTH = FULLSCREEN_TARGET_WIDTH
SCREENSHOT_TARGET_HEIGHT = FULLSCREEN_TARGET_HEIGHT


# -------------------------
# OpenAI Computer Actions
# -------------------------

class ClickAction(TypedDict):
    type: Literal["click"]
    button: Literal["left", "right", "wheel", "back", "forward"]
    x: int
    y: int


class DoubleClickAction(TypedDict, total=False):
    type: Literal["double_click"]
    button: Literal["left", "right", "wheel", "back", "forward"]
    x: int
    y: int


class DragAction(TypedDict, total=False):
    type: Literal["drag"]
    button: Literal["left", "right", "wheel", "back", "forward"]
    path: List[tuple[int, int]]  # [(x1, y1), (x2, y2), ...]


class KeyPressAction(TypedDict):
    type: Literal["keypress"]
    keys: List[str]  # e.g., ["ctrl", "a"]


class MoveAction(TypedDict):
    type: Literal["move"]
    x: int
    y: int


class ScreenshotAction(TypedDict, total=False):
    type: Literal["screenshot"]
    resize: bool  # 是否缩放截图，默认 True


class ScreenInfoAction(TypedDict):
    type: Literal["screen_info", "get_screen_info", "get_screen_size"]


class ScrollAction(TypedDict):
    type: Literal["scroll"]
    scroll_x: int
    scroll_y: int
    x: int
    y: int


class TypeAction(TypedDict):
    type: Literal["type"]
    text: str


class WaitAction(TypedDict):
    type: Literal["wait"]
    seconds: int | float | None


class CodeAction(TypedDict, total=False):
    """
    非 GUI 动作：用于执行代码类任务（例如 Excel PowerShell/Python 自动化）。

    上游（AI Run）常见格式：
    {
      "type": "code",
      "metadata": {
        "tool_name": "excel",
        "config": {"language": "powershell", "sheet_name": "Sheet1"},
        "execution": {"code": "...", "timeout": 120}
      }
    }
    """

    type: Literal["code"]
    metadata: Dict[str, Any]


ComputerAction = Union[
    ClickAction,
    DoubleClickAction,
    DragAction,
    KeyPressAction,
    MoveAction,
    ScreenshotAction,
    ScreenInfoAction,
    ScrollAction,
    TypeAction,
    WaitAction,
    CodeAction,
]


class ComputerUseController:
    """
    本地 Computer Use 执行控制器
    直接调用 win_executor handlers，无需外部服务
    """

    def __init__(self) -> None:
        pass

    async def _execute_action(self, action: ComputerAction) -> Dict[str, Any]:
        """
        执行单个动作，直接调用本地 handlers
        
        支持两种格式：
        1. Local Engine 原生格式: {"type": "click", "x": 100, "y": 200}
        2. AI_Run 格式: {"action": "CLICK", "position": [100, 200], "value": ""}
        """
        # ========== 格式兼容：AI_Run 格式 -> Local Engine 格式 ==========
        if isinstance(action, dict):
            # AI_Run 使用 "action" 字段，Local Engine 使用 "type" 字段
            if "action" in action and "type" not in action:
                action["type"] = action["action"]
            
            # 将 AI_Run 的 position 转为 x/y
            pos = action.get("position")
            if isinstance(pos, (list, tuple)) and len(pos) >= 2:
                action.setdefault("x", pos[0])
                action.setdefault("y", pos[1])
            
            # 将 coordinate 也兼容为 x/y
            coord = action.get("coordinate")
            if isinstance(coord, (list, tuple)) and len(coord) >= 2:
                action.setdefault("x", coord[0])
                action.setdefault("y", coord[1])
            
            # 处理 coordinate_system: 千分位坐标转换为实际屏幕坐标
            coord_system = action.get("coordinate_system")
            if coord_system == "normalized_1000":
                # 获取逻辑分辨率（与 pynput 坐标系一致）
                import win32api
                import win32con
                logical_w = win32api.GetSystemMetrics(win32con.SM_CXSCREEN)
                logical_h = win32api.GetSystemMetrics(win32con.SM_CYSCREEN)
                
                orig_x = action.get("x")
                orig_y = action.get("y")
                
                # 千分位 -> 逻辑屏幕坐标
                if "x" in action and action["x"] is not None:
                    action["x"] = int(action["x"] * logical_w / 1000)
                if "y" in action and action["y"] is not None:
                    action["y"] = int(action["y"] * logical_h / 1000)
                
                logger.info(f"[normalized_1000] ({orig_x}, {orig_y}) -> ({action.get('x')}, {action.get('y')}) | logical: {logical_w}x{logical_h}")
                
                # 转换 path 中的坐标（用于 drag 操作）
                if "path" in action and isinstance(action["path"], list):
                    orig_path = list(action["path"])
                    action["path"] = [
                        (int(p[0] * logical_w / 1000), int(p[1] * logical_h / 1000))
                        for p in action["path"] if isinstance(p, (list, tuple)) and len(p) >= 2
                    ]
                    logger.info(f"[normalized_1000] drag path: {orig_path} -> {action['path']} (logical {logical_w}x{logical_h})")
            
            # AI_Run 的 value 字段兼容
            value = action.get("value")
            if value is not None and value != "":
                # INPUT/TYPE: value -> text
                if action.get("type", "").upper() in ("INPUT", "TYPE") and "text" not in action:
                    action["text"] = value
                # KEY/KEYPRESS: value -> keys
                elif action.get("type", "").upper() in ("KEY", "KEYPRESS") and "keys" not in action:
                    if isinstance(value, list):
                        action["keys"] = value
                    elif isinstance(value, str):
                        # 单个按键或组合键字符串
                        action["keys"] = [value] if "+" not in value else value.split("+")
                # SCROLL: value -> scroll_x/scroll_y
                elif action.get("type", "").upper() == "SCROLL" and isinstance(value, list) and len(value) >= 2:
                    action.setdefault("scroll_x", value[0])
                    action.setdefault("scroll_y", value[1])
                # WAIT: value (ms) -> seconds
                elif action.get("type", "").upper() == "WAIT" and "seconds" not in action:
                    if isinstance(value, (int, float)):
                        action["seconds"] = value / 1000.0  # ms -> seconds
        
        # 获取 action type 并标准化
        raw_type = action.get("type")  # type: ignore[attr-defined]
        action_type = str(raw_type or "").strip().lower()
        
        # 常见别名映射（包括 AI_Run 的大写格式）
        alias_map = {
            # AI_Run 格式
            "input": "type",
            "key": "keypress",
            # 其他别名
            "doubleclick": "double_click",
            "double-click": "double_click",
            "rightclick": "click",
            "right-click": "click",
            "mouse_move": "move",
            "mousemove": "move",
            "key_press": "keypress",
            "key-press": "keypress",
        }
        action_type = alias_map.get(action_type, action_type)

        # "右键点击"兼容
        if action_type in ("right_click", "rightclick", "right-click"):
            action_type = "click"
            if isinstance(action, dict):
                action.setdefault("button", "right")

        # ========== 鼠标操作 ==========
        # 注意：所有坐标均为逻辑坐标（logical pixel），与 pynput 坐标系一致
        # 逻辑分辨率 = win32api.GetSystemMetrics(SM_CXSCREEN/SM_CYSCREEN)
        # 例如：2560x1440 物理分辨率 + 125% 缩放 = 2048x1152 逻辑分辨率
        
        if action_type == "click":
            a = action  # type: ClickAction
            button = a.get("button", "left")
            x = a.get("x")
            y = a.get("y")
            
            # 调试日志：打印坐标信息
            logger.info(f"[click] action={a}, x={x} (type={type(x).__name__}), y={y} (type={type(y).__name__})")
            
            # 确保坐标是整数
            if x is None or y is None:
                raise Exception(f"Click requires x and y coordinates, got x={x}, y={y}")
            
            x = int(x)
            y = int(y)
            
            result = MouseHandler.click(x, y, button)
            if not result.get("success"):
                raise Exception(result.get("error", "Click failed"))
            
            return {"type": action_type, "button": button, "x": x, "y": y}

        if action_type == "double_click":
            a = action  # type: DoubleClickAction
            button = a.get("button", "left")
            x, y = a.get("x", 0), a.get("y", 0)  # 逻辑坐标 (logical pixel)
            
            result = MouseHandler.double_click(x, y, button)
            if not result.get("success"):
                raise Exception(result.get("error", "Double click failed"))
            
            return {"type": action_type, "button": button, "x": x, "y": y}

        if action_type == "drag":
            a = action  # type: DragAction
            button = a.get("button", "left")
            path = a.get("path") or []  # 路径点均为逻辑坐标 (logical pixel)
            speed = a.get("speed")  # 可选：自定义速度（像素/秒）
            
            if not path or len(path) < 2:
                return {"type": action_type, "status": "skipped", "reason": "empty_path"}

            # 使用 MouseHandler.drag 处理拖拽（支持折线、固定速度、起点终点减速）
            result = MouseHandler.drag(
                path=path,
                button=button,
                speed=speed,
            )
            
            if not result.get("success"):
                raise Exception(result.get("error", "Drag failed"))

            return {
                "type": action_type,
                "button": button,
                "path_points": result.get("path_points"),
                "total_length": result.get("total_length"),
                "duration": result.get("duration"),
            }

        if action_type == "move":
            a = action  # type: MoveAction
            x, y = a["x"], a["y"]  # 逻辑坐标 (logical pixel)
            
            result = MouseHandler.move(x, y)
            if not result.get("success"):
                raise Exception(result.get("error", "Move failed"))
            
            return {"type": action_type, "x": x, "y": y}

        if action_type == "scroll":
            a = action  # type: ScrollAction
            scroll_x = a.get("scroll_x", 0)
            scroll_y = a.get("scroll_y", 0)
            x = a.get("x")  # 滚动位置，逻辑坐标 (logical pixel)
            y = a.get("y")  # 滚动位置，逻辑坐标 (logical pixel)
            
            logger.info(f"[scroll] 收到滚动请求: action={a}, scroll_x={scroll_x}, scroll_y={scroll_y}, x={x}, y={y}")
            
            # OpenAI/AI_Run 的 scroll 方向与 pynput 相反：
            # - OpenAI: scroll_y > 0 表示向下滚动（页面内容向上移动）
            # - pynput: dy > 0 表示向上滚动（页面内容向下移动）
            # 所以需要取反
            pynput_dx = scroll_x  # TODO：水平方向暂不取反（待确认）
            pynput_dy = -scroll_y  # 垂直方向取反
            
            logger.info(f"[scroll] 转换后: pynput_dx={pynput_dx}, pynput_dy={pynput_dy}")
            
            result = MouseHandler.scroll(pynput_dx, pynput_dy, x, y)
            if not result.get("success"):
                raise Exception(result.get("error", "Scroll failed"))
            
            logger.info(f"[scroll] 执行结果: {result}")
            
            return {
                "type": action_type,
                "scroll_x": scroll_x,
                "scroll_y": scroll_y,
            }

        # ========== 键盘操作 ==========
        if action_type == "keypress":
            a = action  # type: KeyPressAction
            # 兼容 'key' (单个字符串) 和 'keys' (列表) 两种格式
            keys = a.get("keys") or ([a["key"]] if "key" in a else None)
            if not keys:
                raise Exception(f"Keypress requires 'keys' or 'key' field, got: {a}")
            
            # 如果 keys 是单元素列表且包含 '+' (如 ['CTRL+A'])，拆分为组合键
            if len(keys) == 1 and "+" in keys[0]:
                keys = [k.strip() for k in keys[0].split("+")]
            
            # 如果是组合键（多个键），使用 hotkey
            if len(keys) > 1:
                # 将列表转为字符串，如 ["ctrl", "a"] -> "ctrl+a"
                keys_str = "+".join(keys)
                result = KeyboardHandler.hotkey(keys_str)
            else:
                # 单个按键
                result = KeyboardHandler.press_key(keys[0])
            
            if not result.get("success"):
                raise Exception(result.get("error", "Keypress failed"))
            
            return {"type": action_type, "keys": keys}

        if action_type == "type":
            a = action  # type: TypeAction
            text = a.get("text")
            
            # 调试日志
            logger.info(f"[type] action={a}, text={text}")
            
            if text is None:
                raise Exception(f"Type requires text, got None")
            
            result = KeyboardHandler.type_text(str(text))
            if not result.get("success"):
                raise Exception(result.get("error", "Type failed"))
            
            return {"type": action_type, "text": text}

        # ========== 屏幕操作 ==========
        if action_type == "screenshot":
            # 是否压缩截图（默认 True，缩放 + JPEG 压缩到 ~300KB）
            should_compress = action.get("resize", True) if isinstance(action, dict) else True
            
            # ScreenHandler.screenshot 已内置压缩逻辑
            result = ScreenHandler.screenshot(compress=should_compress)
            
            if not result.get("success"):
                raise Exception(result.get("error", "Screenshot failed"))
            
            # 获取 base64 图像数据（已压缩）
            img_base64 = result.get("image_data", "")
            
            return {
                "type": action_type,
                "image_base64": img_base64,
                "resized": should_compress,  # 兼容旧字段名
                "compressed": should_compress,
            }

        # ========== 等待 ==========
        if action_type == "wait":
            a = action  # type: WaitAction
            seconds = a.get("seconds") or 1.0
            await asyncio.sleep(float(seconds))
            return {"type": action_type, "seconds": seconds}

        # ========== 屏幕信息 ==========
        if action_type in ("screen_info", "get_screen_info", "get_screen_size"):
            result = ScreenHandler.get_screen_info()
            
            if not result.get("success"):
                raise Exception(result.get("error", "Get screen info failed"))
            
            # 提取逻辑尺寸（用于坐标计算）
            logical_size = result.get("logical_size", {})
            width = logical_size.get("width", 1920)
            height = logical_size.get("height", 1080)
            
            return {
                "type": "screen_info",
                "width": width,
                "height": height,
                "scale": result.get("scale", 1.0),
                "dpi": result.get("dpi", 96),
                "logical_size": logical_size,
                "physical_size": result.get("physical_size", {}),
            }

        if action_type == "code":
            # 注意：这类动作不依赖 computer server，直接在 Local Engine 内路由到对应 Controller 执行。
            if not isinstance(action, dict):
                raise ValueError("Invalid code action payload (expected dict)")

            # 兼容多种上游形态：
            # A) {"type":"code","metadata":{...}}  （AI_Run cua_update.content）
            # B) {"type":"code","content":{"type":"code","metadata":{...}}} （某些层会包一层 content）
            # C) {"type":"code","value":"..."} （部分 agent 会把代码放到 value/text 字段）
            content = action.get("content")
            if isinstance(content, dict) and isinstance(content.get("metadata"), dict):
                metadata = content.get("metadata") or {}
            else:
                metadata = action.get("metadata") or {}

            if not isinstance(metadata, dict):
                metadata = {}

            tool_name = str(
                metadata.get("tool_name")
                or (content.get("tool_name") if isinstance(content, dict) else None)
                or action.get("tool_name")
                or ""
            ).strip().lower()
            config = metadata.get("config") or {}
            execution = metadata.get("execution") or {}
            if not isinstance(config, dict):
                config = {}
            if not isinstance(execution, dict):
                execution = {}

            # code 兼容：execution.code / execution.generated_code / action.value / action.text / action.code
            code = (
                execution.get("code")
                or execution.get("generated_code")
                or (content.get("value") if isinstance(content, dict) else None)
                or (content.get("text") if isinstance(content, dict) else None)
                or action.get("value")
                or action.get("text")
                or action.get("code")
            )
            if not isinstance(code, str) or not code.strip():
                # 不要直接 raise，避免整个 action pipeline 因为“空 code 占位”而失败
                return {
                    "type": action_type,
                    "status": "skipped",
                    "reason": "missing_or_empty_code",
                    "tool_name": tool_name or None,
                }

            timeout = execution.get("timeout", 120)
            try:
                timeout_int = int(timeout)
            except Exception:
                timeout_int = 120

            # 默认行为：如果上游没提供文件路径，就使用 ACTIVE_WORKBOOK
            file_path = (
                config.get("file_path")
                or metadata.get("file_path")
                or action.get("file_path")
                or "ACTIVE_WORKBOOK"
            )

            # 兼容 sheet_name / specific_sheet 两种字段
            sheet_name = (
                config.get("sheet_name")
                or config.get("specific_sheet")
                or metadata.get("sheet_name")
                or metadata.get("specific_sheet")
                or "Sheet1"
            )

            language = config.get("language") or metadata.get("language") or "PowerShell"

            # 目前只支持 excel（最小实现，先跑通）
            if tool_name in ("", "unknown", "none"):
                # 上游未携带 tool_name 时，默认按 excel 处理（与当前 Excel CUA 集成期保持一致）
                tool_name = "excel"
            if tool_name not in ("excel",):
                return {
                    "type": action_type,
                    "status": "skipped",
                    "reason": f"unsupported_tool_name:{tool_name}",
                    "tool_name": tool_name,
                }

            # 使用共享映射路由到 ExcelController.execute_code
            from core.router import route_and_execute_cua_request

            result = await route_and_execute_cua_request(
                request_type="excel_execute_code",
                params={
                    "code": code,
                    "file_path": file_path,
                    "specific_sheet": sheet_name,
                    "language": language,
                    "timeout": timeout_int,
                },
            )

            return {
                "type": action_type,
                "tool_name": tool_name,
                "success": bool(result.get("success")),
                "output": (result.get("data") or {}).get("output") if isinstance(result.get("data"), dict) else result.get("data"),
                "error": result.get("error"),
            }

        # 理论上不会走到这里（因为类型已经限制），加一层兜底
        raise ValueError(f"Unsupported action type: {action_type}")

    async def run_actions(self, actions: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        执行一组 JSON 动作（来自云端）
        """
        import traceback as tb
        print(f"[ComputerUseController] Executing {len(actions)} actions")
        
        if not actions:
            return {"status": "ok", "results": [], "message": "no actions"}

        results: List[Dict[str, Any]] = []
        
        for idx, raw in enumerate(actions):
            action_type = raw.get("type", "unknown")
            print(f"[ComputerUseController] Action[{idx}]: {action_type}")
            
            try:
                result = await self._execute_action(raw)  # type: ignore[arg-type]
                print(f"[ComputerUseController] Action[{idx}] SUCCESS")
                
                if result.get("type") == "screenshot":
                    img_len = len(result.get("image_base64", ""))
                    print(f"[ComputerUseController] Screenshot size: {img_len} chars")
                
                results.append({
                    "index": idx,
                    "ok": True,
                    "result": result,
                })
            except Exception as e:
                print(f"[ComputerUseController] Action[{idx}] FAILED: {e}")
                tb.print_exc()
                results.append({
                    "index": idx,
                    "ok": False,
                    "error": str(e),
                })
        print(f"[DEBUG] ComputerUseController.run_actions: creating Computer connection...")


        # Incoming change: The computer server is not used anymore. TODO: CHheck if need to remove this block of code.
        # 只有在确实需要 GUI 动作时才建立 Computer 连接；否则（如纯 code）无需依赖 computer server。
        # def _needs_computer(action_dict: Dict[str, Any]) -> bool:
        #     t = str(action_dict.get("type") or "").strip().lower()
        #     return t not in ("code",)

        # try:
        #     if any(_needs_computer(a) for a in actions):
        #         async with Computer(
        #             use_host_computer_server=True,
        #             host=self.host,
        #             port=self.port,
        #         ) as computer:
        #             print(f"[DEBUG] ComputerUseController.run_actions: Computer connected successfully")

        #             for idx, raw in enumerate(actions):
        #                 action_type = raw.get("type", "unknown")
        #                 print(f"[DEBUG] ComputerUseController.run_actions: executing action[{idx}] type={action_type}")
        #                 try:
        #                     result = await self._execute_action(computer, raw)  # type: ignore[arg-type]
        #                     print(f"[DEBUG] ComputerUseController.run_actions: action[{idx}] SUCCESS, result_type={result.get('type')}")
        #                     if result.get("type") == "screenshot":
        #                         img_len = len(result.get("image_base64", ""))
        #                         print(f"[DEBUG] ComputerUseController.run_actions: screenshot image_base64 length={img_len}")
        #                     results.append({"index": idx, "ok": True, "result": result})
        #                 except Exception as e:
        #                     print(f"[DEBUG] ComputerUseController.run_actions: action[{idx}] FAILED: {e}")
        #                     tb.print_exc()
        #                     results.append({"index": idx, "ok": False, "error": str(e)})
        #     else:
        #         print("[DEBUG] ComputerUseController.run_actions: no GUI actions detected, skipping Computer connection")
        #         for idx, raw in enumerate(actions):
        #             action_type = raw.get("type", "unknown")
        #             print(f"[DEBUG] ComputerUseController.run_actions: executing action[{idx}] type={action_type}")
        #             try:
        #                 # code 动作不需要 computer；这里创建一个 None 占位不会被使用
        #                 result = await self._execute_action(None, raw)  # type: ignore[arg-type]
        #                 results.append({"index": idx, "ok": True, "result": result})
        #             except Exception as e:
        #                 print(f"[DEBUG] ComputerUseController.run_actions: action[{idx}] FAILED: {e}")
        #                 tb.print_exc()
        #                 results.append({"index": idx, "ok": False, "error": str(e)})
        # except Exception as e:
        #     print(f"[DEBUG] ComputerUseController.run_actions: Computer connection FAILED: {e}")
        #     tb.print_exc()
        #     return {"status": "error", "results": [], "message": str(e)}

        print(f"[ComputerUseController] Completed {len(results)} actions")
        return {"status": "ok", "results": results}
