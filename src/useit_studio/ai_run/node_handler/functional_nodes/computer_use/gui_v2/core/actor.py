"""
GUI Agent V2 - Actor 核心逻辑

Actor 负责"执行"：
1. 接收 Planner 的自然语言指令（如 "点击搜索框"）
2. 观察截图，定位具体位置
3. 生成精确的设备动作（如 click(x=100, y=200)）

输出：DeviceAction（包含 action_type, x, y, text 等）
"""

import json
import os
from typing import Dict, Any, Optional, AsyncGenerator, List

from ..models import DeviceAction, ActionType, CoordinateSystem, ReasoningDeltaEvent, ActionEvent

from ..utils.llm_client import VLMClient, LLMConfig
from ..utils.image_utils import resize_screenshot, draw_action_visualization
from useit_studio.ai_run.utils.logger_utils import LoggerUtils


# ==================== Prompt 模板 ====================

ACTOR_SYSTEM_PROMPT = """You are a helpful assistant for computer-use tasks to navigate the {os_name} desktop screen.

You have access to a set of functions that allow you to interact with a computer environment following the user's instruction.
You can only interact with the desktop GUI via the mouse and keyboard.

The available action space is:
{action_space}

Generate the action in JSON format. **Do not output any other text or ask for clarification**."""


ACTOR_ACTION_SPACE = """- click(x, y): Click at the specified coordinates
- double_click(x, y): Double click at the specified coordinates
- drag(path): Drag from first point to last along path. path is a list of [x,y] points, at least 2 (e.g. [[x1,y1],[x2,y2]]).
- type(text): Type the specified text
- key(key_name): Press a key (e.g., "Enter", "Tab", "Ctrl+C", "Escape")
- scroll(x, y, scroll_x, scroll_y): Scroll at position (x,y) by (scroll_x, scroll_y). Positive scroll_y = scroll down.
- move(x, y): Move mouse to coordinates
- wait(ms): Wait for specified milliseconds
- stop(): Indicate that the task is complete"""


ACTOR_USER_PROMPT = """The user instruction is:
{instruction}

Look at the screenshot and generate the appropriate action to accomplish this instruction.

Output Format (JSON only):
{{
    "reasoning": str,  # Brief explanation of why you chose this action
    "action": {{
        "type": str,  # One of: click, double_click, drag, type, key, scroll, move, wait, stop
        "x": int | null,  # X coordinate (for click, double_click, scroll, move)
        "y": int | null,  # Y coordinate (for click, double_click, scroll, move)
        "path": list | null,  # For drag: list of [x,y] points, at least 2, e.g. [[x1,y1],[x2,y2]]
        "button": str | null,  # For drag: "left" (default) or "right"
        "text": str | null,  # Text to type (for type action)
        "key": str | null,  # Key name (for key action)
        "scroll_x": int | null,  # Horizontal scroll amount
        "scroll_y": int | null,  # Vertical scroll amount (positive = down)
        "ms": int | null  # Milliseconds to wait (for wait action)
    }}
}}

Now generate the action:"""


class Actor:
    """
    GUI Agent Actor
    
    负责将自然语言指令转换为具体的设备动作。
    """
    
    def __init__(
        self,
        model: str = "gemini-3-flash-preview",
        api_keys: Optional[Dict[str, str]] = None,
        max_tokens: int = 4096,  # 增加默认值到 4096，避免 Gemini MAX_TOKENS 截断问题
        temperature: float = 0.0,
        screen_max_side: int = 1024,
        os_name: str = "Windows",
        node_id: str = "",  # 用于日志标识
    ):
        self.model = model
        self.os_name = os_name
        self.screen_max_side = screen_max_side
        self.node_id = node_id
        self.logger = LoggerUtils(component_name="Actor")
        
        # 判断是否是 Gemini 模型（输出千分位坐标）
        self.is_gemini_model = "gemini" in model.lower()
        
        # 初始化 VLM 客户端（带角色标识）
        config = LLMConfig(
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            role="actor",  # 标识这是 Actor
            node_id=node_id,
        )
        self.vlm = VLMClient(config=config, api_keys=api_keys, logger=self.logger)
    
    def set_node_id(self, node_id: str):
        """更新节点 ID（用于日志）"""
        self.node_id = node_id
        self.vlm.config.node_id = node_id
    
    async def act(
        self,
        instruction: str,
        screenshot_path: str,
        log_dir: Optional[str] = None,
        visualize: bool = True,
        attached_images_base64: Optional[List[str]] = None,
    ) -> tuple[DeviceAction, str, Dict[str, int]]:
        """
        非流式执行
        
        Args:
            instruction: Planner 给出的自然语言指令
            screenshot_path: 当前截图路径
            log_dir: 日志目录
            visualize: 是否生成可视化图片（十字准星标记点击位置）
            
        Returns:
            (DeviceAction, reasoning_text, token_usage)
        """
        # 准备截图
        resized_path = self._prepare_screenshot(screenshot_path, log_dir)
        
        # 构建提示
        system_prompt = ACTOR_SYSTEM_PROMPT.format(
            os_name=self.os_name,
            action_space=ACTOR_ACTION_SPACE,
        )
        user_prompt = ACTOR_USER_PROMPT.format(instruction=instruction)
        
        # 调用 VLM
        response = await self.vlm.call(
            prompt=user_prompt,
            system_prompt=system_prompt,
            screenshot_path=resized_path,
            attached_images_base64=attached_images_base64,
            log_dir=log_dir,
        )
        
        # 解析响应
        action, reasoning, parse_error = self._parse_response(response["content"])
        
        # 如果解析失败，抛出异常
        if parse_error:
            raise ValueError(f"Actor 解析失败: {parse_error}")
        
        # 生成可视化图片
        if visualize and log_dir:
            self._visualize_action(screenshot_path, action, log_dir)
        
        return action, reasoning, response.get("token_usage", {})
    
    async def act_streaming(
        self,
        instruction: str,
        screenshot_path: str,
        log_dir: Optional[str] = None,
        visualize: bool = True,
        attached_images_base64: Optional[List[str]] = None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        流式执行
        
        Args:
            instruction: Planner 给出的自然语言指令
            screenshot_path: 当前截图路径
            log_dir: 日志目录
            visualize: 是否生成可视化图片（十字准星标记点击位置）
        
        Yields:
            ReasoningDeltaEvent - 推理过程增量
            ActionEvent - 生成的动作
        """
        # 准备截图
        resized_path = self._prepare_screenshot(screenshot_path, log_dir)
        
        # 构建提示
        system_prompt = ACTOR_SYSTEM_PROMPT.format(
            os_name=self.os_name,
            action_space=ACTOR_ACTION_SPACE,
        )
        user_prompt = ACTOR_USER_PROMPT.format(instruction=instruction)
        
        full_content = ""
        
        # 流式调用 VLM
        async for chunk in self.vlm.stream(
            prompt=user_prompt,
            system_prompt=system_prompt,
            screenshot_path=resized_path,
            attached_images_base64=attached_images_base64,
            log_dir=log_dir,
        ):
            if chunk["type"] == "delta":
                raw_content = chunk["content"]
                # 详细日志：记录原始 content 的类型
                self.logger.logger.debug(
                    f"[Actor.stream] chunk content type={type(raw_content).__name__}, "
                    f"preview={str(raw_content)[:100] if raw_content else 'None'}"
                )
                content = raw_content
                # 确保 content 是字符串
                if isinstance(content, list):
                    self.logger.logger.debug(f"[Actor.stream] Converting list with {len(content)} items to str")
                    content = "".join(str(c) for c in content)
                elif not isinstance(content, str):
                    self.logger.logger.debug(f"[Actor.stream] Converting {type(content).__name__} to str")
                    content = str(content)
                full_content += content
                yield ReasoningDeltaEvent(content=content, source="actor").to_dict()
                
            elif chunk["type"] == "complete":
                # 解析完整响应
                action, reasoning, parse_error = self._parse_response(full_content)
                
                # 如果解析失败，返回错误事件而不是 stop 动作
                if parse_error:
                    self.logger.logger.error(f"[Actor] 解析响应失败: {parse_error}, 原始内容: {full_content[:500]}")
                    yield {"type": "error", "content": f"Actor 解析失败: {parse_error}"}
                    return
                
                # 生成可视化图片
                visualization_path = None
                if visualize and log_dir:
                    visualization_path = self._visualize_action(screenshot_path, action, log_dir)
                
                yield ActionEvent(action=action).to_dict()
                yield {
                    "type": "actor_complete",
                    "action": action.to_dict(),
                    "reasoning": reasoning,
                    "token_usage": chunk.get("token_usage", {}),
                    "visualization_path": visualization_path,
                }
                
            elif chunk["type"] == "error":
                yield {"type": "error", "content": chunk["content"]}
    
    def _prepare_screenshot(self, screenshot_path: str, log_dir: Optional[str]) -> str:
        """准备截图（调整大小）"""
        if not screenshot_path or not os.path.exists(screenshot_path):
            raise ValueError(f"截图文件不存在: {screenshot_path}")
        
        if log_dir:
            output_path = os.path.join(log_dir, "actor_screenshot.png")
        else:
            output_path = screenshot_path.replace(".png", "_actor_resized.png")
        
        return resize_screenshot(screenshot_path, output_path, self.screen_max_side)
    
    def _visualize_action(
        self,
        screenshot_path: str,
        action: DeviceAction,
        log_dir: str,
    ) -> Optional[str]:
        """
        生成动作可视化图片（在原始截图上绘制十字准星）
        
        Args:
            screenshot_path: 原始截图路径
            action: 解析后的动作
            log_dir: 日志目录
            
        Returns:
            可视化图片路径，如果不需要可视化则返回 None
        """
        try:
            # 只对有坐标的动作进行可视化
            if action.x is None or action.y is None:
                return None
            
            output_path = os.path.join(log_dir, "action_visualization.png")
            
            visualization_path = draw_action_visualization(
                image_path=screenshot_path,
                action_dict=action.to_dict(),
                output_path=output_path,
            )
            
            self.logger.logger.info(
                f"[Actor] 生成可视化图片: {visualization_path}, "
                f"坐标: ({action.x}, {action.y}), "
                f"坐标系: {action.coordinate_system.value}"
            )
            
            return visualization_path
            
        except Exception as e:
            self.logger.logger.warning(f"[Actor] 生成可视化图片失败: {e}")
            return None
    
    def _parse_response(self, response: str) -> tuple[DeviceAction, str, Optional[str]]:
        """
        解析 LLM 响应为 DeviceAction
        
        Returns:
            (DeviceAction, reasoning, error_message)
            - 如果解析成功，error_message 为 None
            - 如果解析失败，返回 stop 动作和错误信息
        """
        try:
            parsed = self._extract_json(response)
            
            reasoning = parsed.get("reasoning", "")
            action_dict = parsed.get("action", {})
            
            # 检查 action_dict 是否有效
            if not action_dict:
                return DeviceAction.stop(), reasoning, f"响应中缺少 action 字段: {response[:200]}"
            
            # 解析动作类型
            action_type_str = action_dict.get("type", "").lower()
            
            if not action_type_str:
                return DeviceAction.stop(), reasoning, f"action 中缺少 type 字段: {response[:200]}"
            
            try:
                action_type = ActionType(action_type_str)
            except ValueError:
                self.logger.logger.warning(f"未知动作类型: {action_type_str}")
                return DeviceAction.stop(), reasoning, f"未知动作类型: {action_type_str}"
            
            # 确定坐标系：Gemini 模型输出千分位坐标，其他模型输出屏幕坐标
            coordinate_system = (
                CoordinateSystem.NORMALIZED_1000 
                if self.is_gemini_model 
                else CoordinateSystem.SCREEN_PIXEL
            )
            
            # 拖拽 path 规范化：至少 2 个点，每点为 [x,y]
            path = None
            if action_type == ActionType.DRAG:
                raw_path = action_dict.get("path")
                if isinstance(raw_path, list) and len(raw_path) >= 2:
                    path = []
                    for p in raw_path:
                        if isinstance(p, (list, tuple)) and len(p) >= 2:
                            path.append([int(p[0]), int(p[1])])
                    if len(path) < 2:
                        path = None
                if path is None:
                    return DeviceAction.stop(), reasoning, "drag 动作需要 path 且至少 2 个点"

            # 构建 DeviceAction
            action = DeviceAction(
                action_type=action_type,
                x=action_dict.get("x"),
                y=action_dict.get("y"),
                text=action_dict.get("text"),
                key=action_dict.get("key"),
                scroll_x=action_dict.get("scroll_x", 0) or 0,
                scroll_y=action_dict.get("scroll_y", 0) or 0,
                duration_ms=action_dict.get("ms", 0) or 0,
                coordinate_system=coordinate_system,
                path=path,
                button=action_dict.get("button") or (None if action_type != ActionType.DRAG else "left"),
            )
            
            return action, reasoning, None  # 成功，无错误
            
        except Exception as e:
            self.logger.logger.error(f"解析 Actor 响应失败: {e}, 原始响应: {response[:300]}")
            return DeviceAction.stop(), f"Parse error: {e}", str(e)
    
    def _extract_json(self, text: str) -> Dict[str, Any]:
        """从文本中提取 JSON"""
        text = text.strip()
        
        # 直接尝试解析
        if text.startswith("{"):
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                pass
        
        # 尝试从 ```json 块中提取
        import re
        json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', text, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError:
                pass
        
        # 尝试提取第一个 { 到最后一个 }
        start = text.find("{")
        end = text.rfind("}") + 1
        if start != -1 and end > start:
            try:
                return json.loads(text[start:end])
            except json.JSONDecodeError:
                pass
        
        raise ValueError(f"无法从响应中提取 JSON: {text[:200]}...")
