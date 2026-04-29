"""
AI_Run Workflow Executor - 核心调度器

架构说明：
- Backend 通过 SSE 发送 client_request 事件给 Frontend
- Frontend 转发请求给 Local Engine（客户端本地）
- Local Engine 执行后，Frontend 通过 /workflow/callback 回传结果
- Backend 通过 WorkflowInteractionManager 等待并获取结果

设计原则:
- 单次调用，单次返回: AI_Run 每次调用处理一个节点
- 节点类型分发: 根据节点类型采用不同的处理策略
- 自动化循环: 根据节点结果决定是否自动继续或等待前端操作
"""
import asyncio
import datetime
import json
import logging
import time
from typing import Any, AsyncGenerator, Dict, Optional

from useit_studio.gateway.settings import get_ai_run_url, use_in_process_ai_run

from .ai_run_client import AIRunClient, CUAEventConverter
from .interaction_manager import WorkflowInteractionManager
from .exceptions import ScreenshotAcquisitionError, AIRunServiceError, InfiniteLoopError

from .constants import (
    MAX_ITERATIONS,
    MAX_SCREENSHOT_ATTEMPTS,
    SCREENSHOT_RETRY_DELAY,
    TOOL_CALL_TIMEOUT,
    WORKFLOW_DEBUG,
)

from .handlers import ScreenshotHandler, ToolCallHandler, ActionExecutor, CUARequestHandler
from .utils import LoopDetector, log_message, normalize_action_for_local_engine
from .utils.message_logger import sanitize_message

logger = logging.getLogger(__name__)


def _log_sse_token_usage_debug(step_usage: Dict[str, Any], workflow_run_id: Optional[str] = None) -> None:
    """WORKFLOW_DEBUG 时打印本 step 的 token_usage 摘要（已 sanitize）。"""
    if not WORKFLOW_DEBUG:
        return
    try:
        safe = sanitize_message(step_usage) if isinstance(step_usage, dict) else step_usage
        line = json.dumps(safe, ensure_ascii=False, default=str)
        if len(line) > 8000:
            line = line[:8000] + "…(truncated)"
        print(f"[TOKEN][debug] run={workflow_run_id} token_usage={line}")
    except Exception as e:
        logger.warning("_log_sse_token_usage_debug 失败: %s", e)


class AIRunWorkflowExecutor:
    """
    AI_Run 工作流执行器 - 支持自动化循环
    
    节点处理策略:
    - GUI节点: 返回Action → 通过SSE请求前端执行 → 等待回调 → 自动继续
    - 其他节点: 返回结果 → 立即自动继续
    
    架构:
    - Backend (Server) <--SSE--> Frontend (Browser) <--HTTP--> Local Engine (Client PC)
    """
    
    def __init__(self) -> None:
        self.ai_run_url = get_ai_run_url().rstrip("/")
        _ip = use_in_process_ai_run()
        self.ai_run_client = AIRunClient(
            base_url=self.ai_run_url, use_in_process=_ip
        )
        self.event_converter = CUAEventConverter()

        # Handlers
        self.screenshot_handler = ScreenshotHandler()
        self.tool_call_handler = ToolCallHandler(self.screenshot_handler)
        self.action_executor = ActionExecutor(self.screenshot_handler)
        self.cua_handler = CUARequestHandler(
            self.ai_run_url, use_in_process=_ip
        )
        
        # 工作流标识
        self.workflow_id = None  # 不使用 DEFAULT_WORKFLOW_ID，允许为 None
        self.workflow_run_id = None
        
        # 工作流循环控制
        self.max_iterations = MAX_ITERATIONS
        self.current_iteration = 0
        self.workflow_completed = False
        self.current_screenshot_base64 = None
        
        # 屏幕信息缓存
        self._screen_width: Optional[int] = None
        self._screen_height: Optional[int] = None
        
        # 项目文件列表缓存（用于 AI 上下文）
        self._current_project_files: Optional[str] = None
        
        # 无限循环检测器
        self.loop_detector = LoopDetector()

        # 交互管理器引用
        self._interaction_manager: Optional[WorkflowInteractionManager] = None

        # 待传递给 AI_Run 的执行结果
        self._pending_execution_result: Optional[Dict[str, Any]] = None

        # Token usage 累计数据（每次收到的都是总量）
        self._last_token_usage: Optional[Dict[str, Any]] = None

    async def execute(
        self,
        workflow_id: str,
        user_input: str,
        workflow_run_id: Optional[str] = None,
        user_id: Optional[str] = None,
        interaction_manager: Optional[WorkflowInteractionManager] = None,
        chat_id: Optional[str] = None,
        project_id: Optional[str] = None,
        attached_files: Optional[list] = None,
        **kwargs,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        执行工作流 - 主入口
        
        Args:
            workflow_id: 工作流ID
            user_input: 用户输入
            workflow_run_id: 工作流执行实例ID
            user_id: 用户 ID
            interaction_manager: 交互管理器（SSE 模式必需）
            chat_id: 聊天会话ID
            project_id: 项目ID
            attached_files: 附加的文件/文件夹列表
            
        Yields:
            执行过程中的事件
        """
        # 保存上下文
        # 注意：workflow_id 可以为 None，不使用 DEFAULT_WORKFLOW_ID 作为默认值
        self.workflow_id = workflow_id  # 允许为 None
        self.workflow_run_id = workflow_run_id
        self._interaction_manager = interaction_manager
        self._attached_files = attached_files  # 保存附加文件
        self._attached_images = kwargs.get("attached_images")  # 保存附加图片（base64）
        self._user_api_keys = kwargs.get('user_api_keys') or {}
        
        context = {
            "workflow_id": self.workflow_id,  # 可以为 None
            "workflow_run_id": workflow_run_id,
            "user_id": user_id,
            "chat_id": chat_id,
            "project_id": project_id,
        }
        
        # 性能监测
        perf_start = time.time()
        logger.info(f"[Executor] ===== Execute 开始 ===== workflow_id={self.workflow_id or 'None'}")

        if not interaction_manager:
            logger.warning("[Executor] interaction_manager 未提供，SSE 回调模式可能无法正常工作")

        try:
            # 1. 重置状态
            self._reset_state()

            # 2. 发送开始事件
            yield self._create_start_event(context)
            
            # 3. 获取初始截图
            async for event in self._acquire_initial_screenshot(interaction_manager):
                yield event
            
            # 4. 检查 AI_Run 服务健康状态
            if not await self._check_ai_run_health():
                raise AIRunServiceError("AI_Run服务不可用")
            
            # 5. 主循环
            async for event in self._main_loop(user_input, interaction_manager, context):
                yield event
            
            # 6. 完成处理
            async for event in self._finalize():
                yield event

        except ScreenshotAcquisitionError as e:
            yield self._create_error_event(e, context)
        except InfiniteLoopError as e:
            yield self._create_error_event(e, context)
        except AIRunServiceError as e:
            yield self._create_error_event(e, context)
        except Exception as e:
            logger.error(f"[Executor] 工作流执行失败: {e}", exc_info=True)
            yield {
                "type": "error",
                "content": f"AI_Run 工作流执行失败: {str(e)}",
                "error_code": "UNKNOWN_ERROR",
                "recoverable": False,
                **context,
            }

    def _reset_state(self) -> None:
        """重置执行器状态"""
        self.current_iteration = 0
        self.workflow_completed = False
        self.current_screenshot_base64 = None
        self._screen_width = None
        self._screen_height = None
        self._current_project_files = None
        self._pending_execution_result = None
        self._last_token_usage = None
        self.loop_detector.reset()
        logger.info("[Executor] 状态已重置")

    def _create_start_event(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """创建开始事件"""
        return {
            "type": "workflow_start",
            "content": f"开始执行工作流: {self.workflow_id}",
            "workflow_name": self.workflow_id,
            **context,
        }

    def _create_error_event(self, error: Exception, context: Dict[str, Any]) -> Dict[str, Any]:
        """创建错误事件"""
        return {
            "type": "error",
            "content": str(error),
            "error_code": getattr(error, 'error_code', 'UNKNOWN_ERROR'),
            "recoverable": getattr(error, 'recoverable', False),
            "workflow_name": self.workflow_id,
            **context,
        }

    async def _acquire_initial_screenshot(
        self,
        interaction_manager: Optional[WorkflowInteractionManager],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        获取初始截图（带重试）
        """
        perf_start = time.time()
        logger.info("[Executor] 开始获取初始截图")
        
        screenshot_base64: Optional[str] = None
        screen_w: Optional[int] = None
        screen_h: Optional[int] = None
        
        for attempt in range(MAX_SCREENSHOT_ATTEMPTS):
            try:
                async for event in self.screenshot_handler.request_via_sse(interaction_manager):
                    if event.get("type") == "_internal_screenshot_result":
                        screen_w = event.get("screen_width")
                        screen_h = event.get("screen_height")
                        screenshot_base64 = event.get("screenshot_base64")
                        # 提取项目文件列表
                        project_files = event.get("project_files")
                        if project_files:
                            self._current_project_files = project_files
                            logger.info(f"[Executor] 📁 获取到项目文件列表，长度={len(project_files)}")
                    else:
                        yield event

                if self.screenshot_handler.validate(screenshot_base64):
                    self._screen_width = screen_w
                    self._screen_height = screen_h
                    self.current_screenshot_base64 = screenshot_base64
                    break

                logger.warning(f"[Executor] 截图验证失败，尝试 {attempt + 1}/{MAX_SCREENSHOT_ATTEMPTS}")
                
            except Exception as e:
                logger.error(f"[Executor] 截图获取异常 ({attempt + 1}/{MAX_SCREENSHOT_ATTEMPTS}): {e}")

            if attempt < MAX_SCREENSHOT_ATTEMPTS - 1:
                await asyncio.sleep(SCREENSHOT_RETRY_DELAY)

        # 检查是否获取到 screen_info（必需）
        if not (self._screen_width and self._screen_height):
            raise ScreenshotAcquisitionError(
                f"经过 {MAX_SCREENSHOT_ATTEMPTS} 次尝试，无法获取有效的 screen_info"
            )

        # 截图是可选的
        if not screenshot_base64:
            self.current_screenshot_base64 = None
            logger.info("[Executor] ℹ️ 初始截图为空，后续调用将不包含截图")
        
        perf_duration = time.time() - perf_start
        logger.info(f"[Executor] ✅ 初始截图获取完成 [耗时: {perf_duration:.3f}s]")
        
        if WORKFLOW_DEBUG and screen_w and screen_h:
            yield {"type": "token", "content": f"\n[debug] screen_info: {screen_w}x{screen_h}\n"}
        
        yield {"type": "screenshot_received", "content": "已获取并验证初始截图"}

    async def _main_loop(
        self,
        user_input: str,
        interaction_manager: Optional[WorkflowInteractionManager],
        context: Dict[str, Any],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        主执行循环
        """
        logger.info("[Executor] ===== 开始主循环 =====")
        
        while not self.workflow_completed and self.current_iteration < self.max_iterations:
            self.current_iteration += 1
            logger.info(f"[Executor] ----- 迭代 #{self.current_iteration} -----")

            # 确保有有效截图
            async for event in self._ensure_valid_screenshot(interaction_manager):
                yield event

            # 处理一次 AI_Run 调用
            async for event in self._process_one_iteration(
                user_input, interaction_manager, context
            ):
                yield event

    async def _ensure_valid_screenshot(
        self,
        interaction_manager: Optional[WorkflowInteractionManager],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """确保当前有有效截图"""
        if self.screenshot_handler.validate(self.current_screenshot_base64):
            return
        
        logger.info("[Executor] 需要获取截图（当前截图为空或无效）")
        
        for attempt in range(MAX_SCREENSHOT_ATTEMPTS):
            try:
                async for event in self.action_executor.execute_via_sse(
                    [{"type": "screenshot"}],
                    interaction_manager
                ):
                    if event.get("type") == "_internal_action_result":
                        new_screenshot = event.get("screenshot_base64")
                        if self.screenshot_handler.validate(new_screenshot):
                            self.current_screenshot_base64 = new_screenshot
                            logger.info("[Executor] ✅ 截图获取成功")
                            return
                    else:
                        yield event

                logger.warning(f"[Executor] 截图获取失败 ({attempt + 1}/{MAX_SCREENSHOT_ATTEMPTS})")
                
            except Exception as e:
                logger.error(f"[Executor] 截图获取异常 ({attempt + 1}/{MAX_SCREENSHOT_ATTEMPTS}): {e}")

            if attempt < MAX_SCREENSHOT_ATTEMPTS - 1:
                await asyncio.sleep(SCREENSHOT_RETRY_DELAY)

        raise ScreenshotAcquisitionError(
            f"经过 {MAX_SCREENSHOT_ATTEMPTS} 次尝试，无法获取有效截图"
        )

    async def _process_one_iteration(
        self,
        user_input: str,
        interaction_manager: Optional[WorkflowInteractionManager],
        context: Dict[str, Any],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        处理单次 AI_Run 调用迭代
        """
        perf_start = time.time()
        logger.info(f"[Executor] 🔹 开始第 {self.current_iteration} 次 AI_Run 调用")

        pending_action: Optional[Dict[str, Any]] = None
        perf_first_event_received = False

        # 构建 additional_context（包含项目文件列表等）
        additional_context = None
        if self._current_project_files:
            additional_context = f"## Project Files\n{self._current_project_files}"
            logger.info(f"[Executor] 📁 附带项目文件列表，长度={len(self._current_project_files)}")

        async with self.ai_run_client:
            async for ai_run_event in self.ai_run_client.stream_computer_use_action(
                instruction=user_input,
                screenshot_base64=self.current_screenshot_base64,
                additional_context=additional_context,
                uia_data={
                    "screen_width": self._screen_width,
                    "screen_height": self._screen_height,
                },
                task_id=context.get("workflow_run_id") or self.workflow_run_id,
                workflow_id=self.workflow_id,
                user_id=context.get("user_id"),
                project_id=context.get("project_id"),
                chat_id=context.get("chat_id"),
                execution_result=self._pending_execution_result,
                attached_files=self._attached_files,
                attached_images=self._attached_images,
                user_api_keys=self._user_api_keys if self._user_api_keys else None,
            ):
                # 性能监测：第一个事件
                if not perf_first_event_received:
                    perf_latency = time.time() - perf_start
                    logger.info(f"[Executor] ⚡ 首个事件 [延迟: {perf_latency:.3f}s]")
                    perf_first_event_received = True

                # 清空执行结果（已传递）
                if self._pending_execution_result:
                    self._pending_execution_result = None

                # 转换事件格式
                event = self.event_converter.convert_to_engineering_format(ai_run_event)
                event["workflow_name"] = self.workflow_id
                event["workflow_run_id"] = context.get("workflow_run_id")
                
                # 消息落盘
                log_message("RECV", event, context=f"iteration={self.current_iteration}")

                evt_type = event.get("type", "unknown")

                # 捕获内部 token usage 事件（不传给前端）
                if evt_type == "_internal_step_token_usage":
                    step_usage = ai_run_event.get("step_token_usage") or {}
                    self._last_token_usage = step_usage
                    _log_sse_token_usage_debug(step_usage, workflow_run_id=self.workflow_run_id)
                    continue

                # 处理 workflow_complete/workflow_completed
                if evt_type in ("workflow_complete", "workflow_completed"):
                    self.workflow_completed = True
                    logger.info(f"[Executor] ✅✅✅ 收到 {evt_type} 事件 ✅✅✅")
                    yield event
                    return

                # 处理 node_complete 中的完成标志
                if evt_type in ("node_complete", "node_end"):
                    if self._check_node_complete_for_workflow_end(event):
                        self.workflow_completed = True
                        yield event
                        continue
                    
                    # 如果有 pending tool_call，在 node_complete 时 break
                    if pending_action and pending_action.get("type") == "_tool_call":
                        logger.info("[Executor] node_complete 收到，有 pending tool_call，break")
                        yield event
                        break

                # 处理 cua_request（异步，不阻塞）
                if evt_type == "cua_request":
                    asyncio.create_task(
                        self.cua_handler.handle(event, interaction_manager)
                    )
                    yield event
                    continue

                yield event

                # 处理 tool_call
                if evt_type == "tool_call":
                    pending_action = self._handle_tool_call_event(event)
                    if pending_action and pending_action.get("type") == "_stop_and_refresh":
                        continue

                # 处理 cua_end
                if evt_type == "cua_end":
                    if pending_action:
                        logger.info(f"[Executor] cua_end，pending_action: {pending_action.get('type')}")
                        break
                    continue

                # 处理 cua_update 中的完成信号
                if evt_type == "cua_update":
                    result = self._check_cua_update_for_completion(event)
                    if result == "finish":
                        self.workflow_completed = True
                        continue
                    elif result == "stop":
                        pending_action = {"type": "_stop_and_refresh"}
                        continue

        # 处理 pending_action
        if pending_action:
            async for event in self._handle_pending_action(
                pending_action, interaction_manager
            ):
                yield event

    def _check_node_complete_for_workflow_end(self, event: Dict[str, Any]) -> bool:
        """检查 node_complete 事件中是否包含工作流完成标志"""
        content = event.get("content") or event.get("result", {})
        if content.get("is_workflow_completed"):
            logger.info("[Executor] 通过 node_complete.is_workflow_completed 检测到工作流完成")
            return True
        
        action_data = content.get("action", {})
        if isinstance(action_data, dict):
            action_type = action_data.get("type") or action_data.get("action")
            if isinstance(action_type, str) and action_type.lower() in ("finish_milestone", "stop"):
                logger.info(f"[Executor] 检测到 {action_type} action，标记完成")
                return True
        return False

    def _handle_tool_call_event(self, event: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """处理 tool_call 事件，返回 pending_action"""
        parsed = self.tool_call_handler.parse_tool_call(event)
        if not parsed:
            return None
        
        tool_call_id = parsed["tool_call_id"]
        target = parsed["target"]
        name = parsed["name"]
        
        logger.info(f"[Executor] 收到 tool_call: id={tool_call_id}, target={target}, name={name}")
        
        # stop 动作不需要执行
        if name == "stop":
            logger.info("[Executor] 收到 stop action")
            return {"type": "_stop_and_refresh"}
        
        return {
            "type": "_tool_call",
            "tool_call_id": tool_call_id,
            "target": target,
            "name": name,
        }

    def _check_cua_update_for_completion(self, event: Dict[str, Any]) -> Optional[str]:
        """检查 cua_update 中是否有完成信号"""
        content = event.get("content") or {}
        if isinstance(content, dict):
            act_name = content.get("type", "")
            if isinstance(act_name, str):
                if act_name.upper() == "FINISH_MILESTONE":
                    logger.info("[Executor] ✅✅✅ 收到 FINISH_MILESTONE ✅✅✅")
                    return "finish"
                if act_name.upper() == "STOP":
                    logger.info("[Executor] 收到 stop action")
                    return "stop"
        return None

    async def _handle_pending_action(
        self,
        pending_action: Dict[str, Any],
        interaction_manager: Optional[WorkflowInteractionManager],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """处理待执行的动作"""
        action_type = pending_action.get("type", "unknown")
        
        # stop 后只获取截图
        if action_type == "_stop_and_refresh":
            logger.info("[Executor] 节点完成（stop），获取新截图")
            async for event in self.action_executor.execute_via_sse(
                [{"type": "screenshot"}],
                interaction_manager
            ):
                if event.get("type") == "_internal_action_result":
                    new_screenshot = event.get("screenshot_base64")
                    if new_screenshot:
                        self.current_screenshot_base64 = new_screenshot
                        logger.info("[Executor] 📸 截图更新成功")
                else:
                    yield event
            return
        
        # tool_call：等待回调
        if action_type == "_tool_call":
            async for event in self._handle_tool_call(pending_action, interaction_manager):
                yield event
            return
        
        # 旧格式：通过 client_request 执行
        logger.info(f"[Executor] 执行动作（旧格式）: {action_type}")
        
        yield {
            "type": "action_pending",
            "content": {"action": pending_action, "message": f"请求执行: {action_type}"}
        }
        
        # 执行动作 + wait + screenshot
        new_screenshot: Optional[str] = None
        async for event in self.action_executor.execute_via_sse(
            [pending_action, {"type": "wait", "seconds": 0.8}, {"type": "screenshot"}],
            interaction_manager
        ):
            if event.get("type") == "_internal_action_result":
                new_screenshot = event.get("screenshot_base64")
            else:
                yield event

        if new_screenshot:
            self.current_screenshot_base64 = new_screenshot
            yield {
                "type": "action_completed",
                "content": {
                    "action": pending_action,
                    "message": f"Action执行完成: {action_type}",
                    "screenshot_updated": True,
                },
                # 如果有新截图，包含在事件中供 Web 端显示
                "screenshot": new_screenshot,
            }
        else:
            logger.warning("[Executor] ❌ 动作执行后未获取到截图")
            yield {
                "type": "action_failed",
                "content": {"action": pending_action, "message": "⚠️ 未获取到截图"},
            }

    async def _handle_tool_call(
        self,
        pending_action: Dict[str, Any],
        interaction_manager: Optional[WorkflowInteractionManager],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """处理 tool_call 动作"""
        tool_call_id = pending_action["tool_call_id"]
        target = pending_action["target"]
        name = pending_action["name"]
        
        logger.info(f"[Executor] 等待 tool_call 回调: id={tool_call_id}")
        
        if not interaction_manager:
            logger.warning("[Executor] interaction_manager 未提供，无法等待回调")
            return
        
        result = await self.tool_call_handler.wait_for_callback(
            tool_call_id, target, name, interaction_manager, timeout=TOOL_CALL_TIMEOUT
        )
        
        if result["success"]:
            # 保存执行结果，下次 AI_Run 调用时传递
            self._pending_execution_result = result["result"]
            logger.info(f"[Executor] 保存执行结果: keys={list(result['result'].keys()) if isinstance(result['result'], dict) else 'N/A'}")
            
            # 更新截图
            if result["screenshot"]:
                self.current_screenshot_base64 = result["screenshot"]
                logger.info("[Executor] 📸 tool_call 回调包含截图")
            
            # 更新项目文件列表
            if result.get("project_files"):
                self._current_project_files = result["project_files"]
                logger.info(f"[Executor] 📁 tool_call 回调包含项目文件列表，长度={len(result['project_files'])}")
            else:
                # 没有截图，主动请求
                async for event in self.action_executor.execute_via_sse(
                    [{"type": "screenshot"}],
                    interaction_manager
                ):
                    if event.get("type") == "_internal_action_result":
                        new_screenshot = event.get("screenshot_base64")
                        if new_screenshot:
                            self.current_screenshot_base64 = new_screenshot
                    else:
                        yield event
            
            yield {
                "type": "action_completed",
                "content": {
                    "tool_call_id": tool_call_id,
                    "target": target,
                    "name": name,
                    "message": "tool_call 执行完成",
                    "screenshot_updated": result["screenshot"] is not None,
                },
                # 如果有新截图，包含在事件中供 Web 端显示
                "screenshot": self.current_screenshot_base64,
            }
        else:
            error_msg = result["error"] or "未知错误"
            yield {
                "type": "action_failed",
                "content": {
                    "tool_call_id": tool_call_id,
                    "message": f"tool_call 执行失败: {error_msg}",
                },
            }

    async def _finalize(self) -> AsyncGenerator[Dict[str, Any], None]:
        """完成处理"""
        logger.info(f"[Executor] ===== 主循环结束 =====")
        logger.info(f"[Executor] completed={self.workflow_completed}, iterations={self.current_iteration}/{self.max_iterations}")

        if self.workflow_completed:
            logger.info(f"[Executor] ✅ 工作流完成，共执行 {self.current_iteration} 步")
            if WORKFLOW_DEBUG:
                yield {"type": "token", "content": f"\n[debug] ✅ 完成，共 {self.current_iteration} 步\n"}
        else:
            logger.warning(f"[Executor] ⚠️ 达到最大迭代次数限制")
            yield {"type": "warning", "content": f"达到最大迭代次数限制 ({self.current_iteration})"}

    async def _check_ai_run_health(self) -> bool:
        """检查 AI_Run 服务健康状态"""
        try:
            health_ok = await self.ai_run_client.health_check()
            if health_ok:
                logger.info("[Executor] AI_Run 服务健康检查通过")
            else:
                logger.warning("[Executor] AI_Run 服务健康检查失败")
            return health_ok
        except Exception as e:
            logger.error(f"[Executor] AI_Run 服务健康检查异常: {e}")
            return False

    async def close(self):
        """关闭执行器"""
        if hasattr(self, 'ai_run_client'):
            await self.ai_run_client.close()


# 兼容性封装
class WorkflowExecutor(AIRunWorkflowExecutor):
    """兼容性封装，继承 AI_Run 执行器"""

    def __init__(self) -> None:
        super().__init__()
        logger.info("[Workflow] 使用 AI_Run 执行器")

    async def execute(
        self,
        workflow_id: str,
        user_input: str,
        use_ai_run_cua: bool = True,  # 已忽略
        workflow_run_id: Optional[str] = None,
        user_id: Optional[str] = None,
        **kwargs,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """兼容原有接口"""
        if kwargs.pop("ai_run_url", None):
            logger.warning(
                "[Workflow] 已忽略过时的 ai_run_url 参数；AI_Run 仅使用本机 get_ai_run_url()"
            )
        async for event in super().execute(
            workflow_id=workflow_id,
            user_input=user_input,
            workflow_run_id=workflow_run_id,
            user_id=user_id,
            **kwargs
        ):
            yield event


class AgentExecutor:
    """
    调用 AI Run ``/agent``：与 ``WorkflowExecutor`` 相同的 tool_call / 回调循环；
    服务端固定最小工作流（start → agent → end），由 ``FlowProcessor`` 执行。

    在工作流需要视觉上下文时，通过 SSE 获取截图并传给 AI_Run。
    """

    def __init__(self) -> None:
        self.ai_run_url = get_ai_run_url().rstrip("/")
        _ip = use_in_process_ai_run()
        self.ai_run_client = AIRunClient(
            base_url=self.ai_run_url, use_in_process=_ip
        )
        self.screenshot_handler = ScreenshotHandler()
        self.tool_call_handler = ToolCallHandler(self.screenshot_handler)
        self.action_executor = ActionExecutor(self.screenshot_handler)
        self._pending_execution_result: Optional[Dict[str, Any]] = None
        self._interaction_manager: Optional[WorkflowInteractionManager] = None
        self.current_screenshot_base64: Optional[str] = None
        self._in_workflow_mode: bool = False
        self.max_iterations = MAX_ITERATIONS
        logger.info(f"[AgentExecutor] Initialized with AI_Run URL: {self.ai_run_url}")

    async def execute(
        self,
        query: str,
        task_id: str,
        *,
        user_id: Optional[str] = None,
        interaction_manager: Optional[WorkflowInteractionManager] = None,
        project_id: Optional[str] = None,
        chat_id: Optional[str] = None,
        app_capabilities: Optional[list] = None,
        workflow_capabilities: Optional[list] = None,
        attached_files: Optional[list] = None,
        attached_images: Optional[list] = None,
        user_api_keys: Optional[Dict[str, str]] = None,
        additional_context: Optional[str] = None,
        workflow_id: Optional[str] = None,
        uia_data: Optional[Dict[str, Any]] = None,
        workflow_run_id: Optional[str] = None,
        chat_history: Optional[list] = None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Agent 执行循环：反复调用 ``/agent``，在 tool_call 回调之间迭代，
        直到收到 ``done`` / ``task_completed`` / ``workflow_complete`` 或达到迭代上限。

        在需要时通过 SSE 获取截图并传给 AI_Run，供 ``FlowProcessor`` 节点使用。
        """
        ctx = {
            "user_id": user_id,
            "project_id": project_id,
            "chat_id": chat_id,
            "workflow_run_id": workflow_run_id,
        }

        self._interaction_manager = interaction_manager
        self._pending_execution_result = None
        self.current_screenshot_base64 = None
        # AgentLoop + agent_node no longer emit orchestrator step_complete with
        # action_type=workflow_action; rely on interaction_manager instead.
        self._in_workflow_mode = bool(interaction_manager)
        completed = False

        for iteration in range(self.max_iterations):
            logger.info(f"[AgentExecutor] Iteration {iteration + 1}, workflow_mode={self._in_workflow_mode}")

            # When in workflow mode, ensure a valid screenshot before calling AI Run
            if self._in_workflow_mode and interaction_manager:
                if not self.screenshot_handler.validate(self.current_screenshot_base64):
                    logger.info("[AgentExecutor] Acquiring screenshot for workflow mode")
                    async for evt in self._acquire_screenshot(interaction_manager):
                        yield evt

            pending_tool_call = None

            # Chat history seeds the orchestrator's conversation on its
            # FIRST round-trip of this HTTP request. On subsequent
            # iterations of the same HTTP request (tool_call callbacks
            # within the same user turn), we must NOT resend the history
            # — the orchestrator already has it in memory and resending
            # would duplicate turns.
            history_for_this_call = chat_history if iteration == 0 else None

            async with self.ai_run_client:
                async for event in self.ai_run_client.stream_agent_action(
                    query=query,
                    task_id=task_id,
                    execution_result=self._pending_execution_result,
                    screenshot_base64=self.current_screenshot_base64,
                    uia_data=uia_data,
                    project_id=project_id,
                    chat_id=chat_id,
                    user_id=user_id,
                    attached_files=attached_files,
                    attached_images=attached_images,
                    user_api_keys=user_api_keys,
                    app_capabilities=app_capabilities,
                    workflow_capabilities=workflow_capabilities,
                    additional_context=additional_context,
                    workflow_id=workflow_id,
                    workflow_run_id=workflow_run_id,
                    chat_history=history_for_this_call,
                ):
                    event_type = event.get("type", "")

                    if event_type == "_internal_step_token_usage":
                        step_usage = event.get("step_token_usage") or {}
                        _log_sse_token_usage_debug(step_usage, workflow_run_id=workflow_run_id or task_id)
                        continue

                    # Detect transition to workflow mode
                    if event_type == "step_complete":
                        content = event.get("content", {})
                        if isinstance(content, dict) and content.get("action_type") == "workflow_action":
                            self._in_workflow_mode = True
                            logger.info("[AgentExecutor] Entered workflow mode")

                    if event_type == "tool_call":
                        pending_tool_call = {
                            "tool_call_id": event.get("id", ""),
                            "target": event.get("target", ""),
                            "name": event.get("name", ""),
                            "args": event.get("args", {}),
                        }
                        yield event

                    elif event_type == "done":
                        completed = True
                        yield event

                    elif event_type == "orchestrator_complete":
                        completed = True
                        yield event

                    elif event_type == "workflow_complete":
                        completed = True
                        self._in_workflow_mode = False
                        yield event

                    elif event_type == "task_completed":
                        completed = True
                        yield event

                    else:
                        yield event

            self._pending_execution_result = None

            if completed:
                break

            if pending_tool_call and interaction_manager:
                result = await self.tool_call_handler.wait_for_callback(
                    pending_tool_call["tool_call_id"],
                    pending_tool_call["target"],
                    pending_tool_call["name"],
                    interaction_manager,
                    timeout=TOOL_CALL_TIMEOUT,
                )
                if result["success"]:
                    self._pending_execution_result = result["result"]
                    # Extract screenshot from the callback for the next iteration
                    cb_screenshot = result.get("screenshot")
                    if cb_screenshot:
                        self.current_screenshot_base64 = cb_screenshot
                        logger.info("[AgentExecutor] Updated screenshot from tool_call callback")
                else:
                    self._pending_execution_result = {
                        "status": "error",
                        "error": result.get("error", "Callback failed"),
                    }
            elif pending_tool_call:
                logger.warning("[AgentExecutor] No interaction_manager, cannot wait for callback")
                break
            elif self._in_workflow_mode:
                # In workflow mode with no pending tool_call — invalidate screenshot
                # so it gets re-acquired on the next iteration
                self.current_screenshot_base64 = None

        if not completed:
            yield {"type": "warning", "content": "Orchestrator reached max iterations"}

    async def _acquire_screenshot(
        self,
        interaction_manager: WorkflowInteractionManager,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Acquire a screenshot from the frontend via SSE/callback."""
        for attempt in range(MAX_SCREENSHOT_ATTEMPTS):
            try:
                async for event in self.action_executor.execute_via_sse(
                    [{"type": "screenshot"}],
                    interaction_manager,
                ):
                    if event.get("type") == "_internal_action_result":
                        new_screenshot = event.get("screenshot_base64")
                        if self.screenshot_handler.validate(new_screenshot):
                            self.current_screenshot_base64 = new_screenshot
                            logger.info("[AgentExecutor] Screenshot acquired successfully")
                            return
                    else:
                        yield event

                logger.warning(
                    f"[AgentExecutor] Screenshot acquisition failed ({attempt + 1}/{MAX_SCREENSHOT_ATTEMPTS})"
                )
            except Exception as e:
                logger.error(
                    f"[AgentExecutor] Screenshot error ({attempt + 1}/{MAX_SCREENSHOT_ATTEMPTS}): {e}"
                )

            if attempt < MAX_SCREENSHOT_ATTEMPTS - 1:
                await asyncio.sleep(SCREENSHOT_RETRY_DELAY)

        logger.warning("[AgentExecutor] Could not acquire screenshot after all retries, continuing without")

    async def close(self):
        await self.ai_run_client.close()
