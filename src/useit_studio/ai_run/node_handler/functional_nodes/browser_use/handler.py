"""
Browser Node Handler - 浏览器节点处理器

流程：
1. 首次调用：发送 connect 请求启动浏览器
2. 连接成功后：发送 page_state 或 go_to_url 获取页面状态
3. 后续调用：从 execution_result 获取页面状态，调用 Agent 规划
4. 输出 tool_call 事件给前端执行
5. 前端执行后返回新的页面状态，继续下一轮

与 GUI 的区别：
- GUI: 使用屏幕坐标，Actor 解析自然语言为坐标
- Browser: 使用 DOM 元素索引，Planner 直接输出索引

前端 API 流程：
connect → 操作 (go_to_url, click_element, ...) → disconnect
"""

from __future__ import annotations

import os
import re
import uuid
from datetime import datetime
from typing import Dict, Any, List, AsyncGenerator, Optional

from useit_studio.ai_run.node_handler.base_v2 import (
    BaseNodeHandlerV2,
    NodeContext,
    NodeCompleteEvent,
    ErrorEvent,
)
from useit_studio.ai_run.runtime.models import ActionStatus
from useit_studio.ai_run.utils.logger_utils import LoggerUtils

from .agent import BrowserAgent
from .models import (
    BrowserContext,
    BrowserAgentStep,
    BrowserPlannerOutput,
    BrowserAction,
    BrowserActionType,
    PageState,
)


logger = LoggerUtils(component_name="BrowserNodeHandler")


class BrowserNodeHandler(BaseNodeHandlerV2):
    """
    Browser 节点处理器
    
    支持的节点类型：
    - browser-use
    - computer-use-browser
    """
    
    @classmethod
    def supported_types(cls) -> List[str]:
        return ["browser-use", "computer-use-browser"]
    
    async def execute(self, ctx: NodeContext) -> AsyncGenerator[Dict[str, Any], None]:
        """
        执行 Browser 节点
        """
        logger.logger.info(f"[BrowserNodeHandler] 开始执行节点: {ctx.node_id}")
        logger.logger.info(f"[BrowserNodeHandler] execution_result: {ctx.execution_result is not None}")
        logger.logger.info(f"[BrowserNodeHandler] node_state keys: {list(ctx.node_state.keys())}")
        
        cua_id = f"cua_{uuid.uuid4().hex[:8]}_{ctx.node_id}"
        
        try:
            # Step 0: 检查节点是否已完成，防止无限循环
            prev_handler_result = ctx.node_state.get("handler_result", {})
            if prev_handler_result.get("is_node_completed", False) and ctx.execution_result is None:
                logger.logger.info(
                    "[BrowserNodeHandler] 节点已完成 (is_node_completed=True)，跳过重复执行"
                )
                # 重新发出完成事件
                completion_summary = prev_handler_result.get("node_completion_summary", "Browser operation completed")
                yield NodeCompleteEvent(
                    node_id=ctx.node_id,
                    node_type=ctx.node_type,
                    is_node_completed=True,
                    handler_result=prev_handler_result,
                    action_summary="Already completed",
                    node_completion_summary=completion_summary,
                ).to_dict()
                return
            
            # Step 1: 发送节点开始事件（首次调用）
            if self._is_first_call(ctx):
                yield {
                    "type": "node_start",
                    "nodeId": ctx.node_id,
                    "title": ctx.get_node_title(),
                    "nodeType": ctx.node_type,
                    "instruction": ctx.get_node_instruction(),
                }
            
            # Step 2: 提取页面状态
            page_state = self._extract_page_state(ctx)
            execution_result = ctx.execution_result or ctx.node_state.get("execution_result")
            handler_result = ctx.node_state.get("handler_result", {})
            waiting_for_execution = handler_result.get("waiting_for_execution", False)
            
            logger.logger.info(
                f"[BrowserNodeHandler] page_state: {page_state is not None}, "
                f"execution_result: {execution_result is not None}, "
                f"waiting_for_execution: {waiting_for_execution}"
            )
            
            # Step 3: 判断流程分支
            # 检查浏览器连接状态
            is_connected = handler_result.get("browser_connected", False)
            
            # 3.1 如果有 execution_result，这是执行结果回调
            if execution_result is not None:
                # 检查是否是 connect 的回调
                last_action = handler_result.get("last_action")
                if last_action == "connect":
                    # connect 成功后，发送 page_state 或 go_to_url 请求
                    logger.logger.info("[BrowserNodeHandler] 浏览器已连接，获取页面状态")
                    async for event in self._emit_get_page_state_request(ctx, cua_id, is_connected=True):
                        yield event
                    return
                
                # 其他执行结果回调
                async for event in self._handle_execution_callback(
                    ctx, cua_id, execution_result
                ):
                    yield event
                return
            
            # 3.1.5 检查 pending_completion：上一步已标记完成，前端可能未传 execution_result
            # 这是对 _handle_execution_callback 中 pending_completion 检查的补充，
            # 用于处理前端执行完 close_tab 等动作后回调不携带 execution_result 的情况
            if handler_result.get("pending_completion") and execution_result is None:
                logger.logger.info(
                    "[BrowserNodeHandler] 检测到 pending_completion（主流程），"
                    "前端未传 execution_result，直接完成节点"
                )
                pending_data = handler_result.get("pending_completion_data", {})
                completion_summary = pending_data.get("completion_summary", "Browser operation completed")
                pending_handler_result = pending_data.get("handler_result", {})
                action_title = pending_data.get("action_title", "Sub-Task Completed")
                output_filename = pending_data.get("output_filename")
                result_markdown = pending_data.get("result_markdown")
                step_cua_id = f"cua_{cua_id}_pending_complete"
                
                yield {
                    "type": "cua_start",
                    "cuaId": step_cua_id,
                }
                
                yield {
                    "type": "cua_end",
                    "cuaId": step_cua_id,
                    "status": "completed",
                    "title": action_title,
                    "action": pending_handler_result.get("action", {}),
                }
                
                yield NodeCompleteEvent(
                    node_id=ctx.node_id,
                    node_type=ctx.node_type,
                    is_node_completed=True,
                    handler_result=pending_handler_result,
                    action_summary=action_title,
                    node_completion_summary=completion_summary,
                    output_filename=output_filename,
                    result_markdown=result_markdown,
                ).to_dict()
                return
            
            # 3.2 首次调用，检查是否需要先 connect
            if not is_connected and not page_state:
                logger.logger.info("[BrowserNodeHandler] 首步，发送 connect 请求")
                async for event in self._emit_connect_request(ctx, cua_id):
                    yield event
                return
            
            # 3.3 已连接但没有页面状态，发送获取页面状态的请求
            if not page_state:
                logger.logger.info("[BrowserNodeHandler] 已连接但无页面状态，发送获取状态请求")
                async for event in self._emit_get_page_state_request(ctx, cua_id, is_connected=True):
                    yield event
                return
            
            # 3.4 有页面状态，执行正常的 Agent 流程
            async for event in self._run_agent_step(ctx, cua_id, page_state):
                yield event
        
        except Exception as e:
            error_msg = f"Browser 节点执行失败: {str(e)}"
            logger.logger.error(error_msg, exc_info=True)
            
            yield {
                "type": "cua_end",
                "cuaId": cua_id,
                "status": "error",
                "error": error_msg,
            }
            yield ErrorEvent(message=error_msg, node_id=ctx.node_id).to_dict()
    
    async def _emit_connect_request(
        self,
        ctx: NodeContext,
        cua_id: str,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        发送连接浏览器的请求
        
        必须先 connect 才能执行其他操作。
        """
        step_cua_id = f"{cua_id}_step0_connect"
        
        # 获取配置
        data = ctx.node_dict.get("data", {})
        headless = data.get("headless", False)
        initial_url = data.get("initial_url") or data.get("url")
        browser_type = data.get("browser_type", "edge")  # 默认使用 Edge
        
        # 发送 CUA 开始
        yield {
            "type": "cua_start",
            "cuaId": step_cua_id,
            "step": 0,
            "title": "Connecting to browser",
            "nodeId": ctx.node_id,
        }
        
        # 发送 reasoning delta
        yield {
            "type": "cua_delta",
            "cuaId": step_cua_id,
            "reasoning": f"Starting {browser_type} browser connection...",
            "kind": "planner",
        }
        
        # 构建 connect action
        action_args: Dict[str, Any] = {
            "headless": headless,
            "browser_type": browser_type,
        }
        if initial_url:
            action_args["initial_url"] = initial_url
        
        action_dict = {
            "type": "connect",
            **action_args,
        }
        
        # 发送 cua_update
        yield {
            "type": "cua_update",
            "cuaId": step_cua_id,
            "content": action_dict,
            "kind": "planner",
        }
        
        # 发送 tool_call
        yield {
            "type": "tool_call",
            "id": f"call_browser_{ctx.node_id}_connect",
            "target": "browser",
            "name": "connect",
            "args": action_args,
        }
        
        # 发送 cua_end
        yield {
            "type": "cua_end",
            "cuaId": step_cua_id,
            "status": "completed",
            "title": "Connect to browser",
            "action": action_dict,
        }
        
        # 发送 node_complete，等待连接结果
        logger.logger.info("[BrowserNodeHandler] 等待浏览器连接")
        
        yield NodeCompleteEvent(
            node_id=ctx.node_id,
            node_type=ctx.node_type,
            is_node_completed=False,
            handler_result={
                "is_node_completed": False,
                "waiting_for_execution": True,
                "last_action": "connect",
                "browser_connected": False,
                "step": 0,
                "cua_id": cua_id,
            },
            action_summary="Connect to browser",
        ).to_dict()

    async def _emit_get_page_state_request(
        self, 
        ctx: NodeContext, 
        cua_id: str,
        is_connected: bool = False,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        发送获取页面状态的请求
        
        浏览器已连接后，发送 page_state 或 go_to_url 请求获取页面状态。
        """
        step_cua_id = f"{cua_id}_step1_get_state"
        
        # 获取初始 URL
        data = ctx.node_dict.get("data", {})
        initial_url = data.get("initial_url") or data.get("url") or "about:blank"
        
        # 发送 CUA 开始
        yield {
            "type": "cua_start",
            "cuaId": step_cua_id,
            "step": 1,
            "title": "Getting page state",
            "nodeId": ctx.node_id,
        }
        
        # 发送 reasoning delta
        reasoning = f"Navigating to {initial_url}..." if initial_url != "about:blank" else "Getting current page state..."
        yield {
            "type": "cua_delta",
            "cuaId": step_cua_id,
            "reasoning": reasoning,
            "kind": "planner",
        }
        
        # 构建 action
        # 如果有初始 URL，先导航到该 URL
        if initial_url and initial_url != "about:blank":
            action_dict = {
                "type": "go_to_url",
                "url": initial_url,
            }
            action_name = "go_to_url"
            action_args = {"url": initial_url}
        else:
            # 只获取当前页面状态
            action_dict = {
                "type": "page_state",
            }
            action_name = "page_state"
            action_args = {}
        
        # 发送 cua_update
        yield {
            "type": "cua_update",
            "cuaId": step_cua_id,
            "content": action_dict,
            "kind": "planner",
        }
        
        # 发送 tool_call
        yield {
            "type": "tool_call",
            "id": f"call_browser_{ctx.node_id}_init",
            "target": "browser",
            "name": action_name,
            "args": action_args,
        }
        
        # 发送 cua_end
        yield {
            "type": "cua_end",
            "cuaId": step_cua_id,
            "status": "completed",
            "title": f"Navigate to {initial_url}" if action_name == "go_to_url" else "Get page state",
            "action": action_dict,
        }
        
        # 发送 node_complete (is_node_completed=false)，等待执行结果
        logger.logger.info("[BrowserNodeHandler] 等待页面状态返回")
        
        yield NodeCompleteEvent(
            node_id=ctx.node_id,
            node_type=ctx.node_type,
            is_node_completed=False,
            handler_result={
                "is_node_completed": False,
                "waiting_for_execution": True,
                "waiting_for_page_state": True,
                "browser_connected": True,
                "last_action": action_name,
                "step": 1,
                "cua_id": cua_id,
            },
            action_summary=f"Navigate to {initial_url}" if action_name == "go_to_url" else "Get page state",
        ).to_dict()
    
    async def _handle_execution_callback(
        self,
        ctx: NodeContext,
        cua_id: str,
        execution_result: Dict[str, Any],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        处理执行结果回调
        
        前端执行完动作后，带着结果和新页面状态再次调用。
        """
        logger.logger.info(f"[BrowserNodeHandler] 收到执行结果回调")
        logger.logger.info(f"[BrowserNodeHandler] execution_result keys: {list(execution_result.keys())}")
        
        # 清除 node_state 中的 stale execution_result，防止后续步骤误取到旧数据
        # （flow_processor 会把 execution_result 持久化到 internal_state，
        #   如果下次请求不带 execution_result，handler 会从 node_state 捡到旧的）
        try:
            exec_node = ctx.flow_processor.runtime_state.get_node_resolved(ctx.node_id)
            if exec_node and "execution_result" in exec_node.internal_state:
                del exec_node.internal_state["execution_result"]
                logger.logger.info("[BrowserNodeHandler] 已清除 node_state 中的 stale execution_result")
        except Exception as e:
            logger.logger.warning(f"[BrowserNodeHandler] 清除 stale execution_result 失败: {e}")
        
        # 从 execution_result 提取页面状态
        page_state = self._extract_page_state_from_result(execution_result)
        
        if not page_state:
            # 检查是否还有 page_state 的字段但为空（前端可能还在处理）
            error_msg = "No page state in execution result. Ensure browser is connected and page is loaded."
            logger.logger.error(f"[BrowserNodeHandler] {error_msg}")
            yield {
                "type": "cua_end",
                "cuaId": cua_id,
                "status": "error",
                "error": error_msg,
            }
            yield ErrorEvent(message=error_msg, node_id=ctx.node_id).to_dict()
            return
        
        # 获取之前的状态
        prev_state = ctx.node_state.get("handler_result", {})
        prev_cua_id = prev_state.get("cua_id", cua_id)
        
        # 检查是否是 pending_completion（上一步 MilestoneCompleted=true 但有待执行的动作）
        # 动作已由前端执行完毕，直接完成节点，无需再调用 Agent
        if prev_state.get("pending_completion"):
            logger.logger.info("[BrowserNodeHandler] pending_completion 检测到，动作已执行，直接完成节点")
            
            pending_data = prev_state.get("pending_completion_data", {})
            completion_summary = pending_data.get("completion_summary", "Browser operation completed")
            handler_result = pending_data.get("handler_result", {})
            action_title = pending_data.get("action_title", "Sub-Task Completed")
            output_filename = pending_data.get("output_filename")
            result_markdown = pending_data.get("result_markdown")
            step_cua_id = f"cua_{cua_id}_pending_complete"
            
            yield {
                "type": "cua_start",
                "cuaId": step_cua_id,
            }
            
            yield {
                "type": "cua_end",
                "cuaId": step_cua_id,
                "status": "completed",
                "title": action_title,
                "action": handler_result.get("action", {}),
            }
            
            yield NodeCompleteEvent(
                node_id=ctx.node_id,
                node_type=ctx.node_type,
                is_node_completed=True,
                handler_result=handler_result,
                action_summary=action_title,
                node_completion_summary=completion_summary,
                output_filename=output_filename,
                result_markdown=result_markdown,
            ).to_dict()
            return
        
        # 从 execution_result 中提取 extract_content 的文本（如果有）
        extracted_content = self._extract_content_from_result(execution_result)
        # 也检查之前步骤中保存的 extracted_content
        if not extracted_content:
            extracted_content = prev_state.get("extracted_content")
        
        if extracted_content:
            logger.logger.info(
                f"[BrowserNodeHandler] 获取到 extracted_content, 长度={len(extracted_content)}"
            )
        
        # 继续执行 Agent 流程
        async for event in self._run_agent_step(ctx, prev_cua_id, page_state, extracted_content=extracted_content):
            yield event
    
    async def _run_agent_step(
        self,
        ctx: NodeContext,
        cua_id: str,
        page_state: PageState,
        extracted_content: Optional[str] = None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        执行 Agent 单步
        
        Args:
            ctx: 节点上下文
            cua_id: CUA ID
            page_state: 当前页面状态
            extracted_content: extract_content 返回的页面文本（可选）
        """
        # 计算步数
        step_count = self._increment_step_count(ctx)
        step_cua_id = f"{cua_id}_step{step_count}"
        
        # 检查是否超过最大步数限制
        max_steps = 60  # Browser Use 节点的最大步数
        if step_count > max_steps:
            logger.logger.warning(
                f"[BrowserNodeHandler] 达到最大步数限制 ({max_steps})，自动完成节点"
            )
            yield {
                "type": "cua_start",
                "cuaId": step_cua_id,
                "step": step_count,
                "title": ctx.get_node_title(),
                "nodeId": ctx.node_id,
            }
            yield {
                "type": "cua_end",
                "cuaId": step_cua_id,
                "status": "completed",
                "title": f"Reached max steps ({max_steps})",
                "action": {"type": "stop"},
            }
            yield NodeCompleteEvent(
                node_id=ctx.node_id,
                node_type=ctx.node_type,
                is_node_completed=True,
                handler_result={
                    "is_node_completed": True,
                    "Observation": f"Reached maximum steps ({max_steps})",
                    "browser_connected": True,
                },
                action_summary=f"Reached max steps ({max_steps})",
                node_completion_summary=f"Browser operation reached maximum steps limit ({max_steps})",
            ).to_dict()
            return
        
        # 发送 CUA 开始事件
        yield {
            "type": "cua_start",
            "cuaId": step_cua_id,
            "step": step_count,
            "title": ctx.get_node_title(),
            "nodeId": ctx.node_id,
        }
        
        # 创建 BrowserAgent
        agent = BrowserAgent(
            planner_model=ctx.planner_model,
            api_keys=ctx.planner_api_keys,
            node_id=ctx.node_id,
        )
        
        # 转换为 BrowserContext
        browser_context = self._convert_to_browser_context(ctx, page_state, extracted_content=extracted_content)
        
        # 执行 Agent（流式）
        agent_step: Optional[BrowserAgentStep] = None
        planner_output_dict: Dict[str, Any] = {}
        
        async for event in agent.step_streaming(
            context=browser_context,
            log_dir=ctx.log_folder,
        ):
            event_type = event.get("type", "")
            
            # 转发推理事件
            if event_type == "reasoning_delta":
                yield {
                    "type": "cua_delta",
                    "cuaId": step_cua_id,
                    "reasoning": event.get("content", ""),
                    "kind": event.get("source", "planner"),
                }
            
            # 转发规划完成事件
            elif event_type == "plan_complete":
                planner_output_dict = event.get("content", {})
                yield {
                    "type": "planner_complete",
                    "content": {"vlm_plan": planner_output_dict},
                }
                
                # 记录 action 到 RuntimeStateManager
                # 注意：record_node_action 内部会 exec_node.step_count += 1，
                # 但 _increment_step_count 已经递增过了，所以先回退一步
                if ctx.flow_processor and planner_output_dict:
                    try:
                        # 先将上一步的 action 标记为 SUCCESS（否则会一直显示 [-->]）
                        exec_node = ctx.flow_processor.runtime_state.get_node_resolved(ctx.node_id)
                        if exec_node and exec_node.action_history:
                            last_action = exec_node.action_history[-1]
                            if last_action.status == ActionStatus.RUNNING:
                                last_action.status = ActionStatus.SUCCESS
                        
                        action_desc = planner_output_dict.get("Action", "")
                        if exec_node:
                            exec_node.step_count = step_count - 1  # 回退，让 record_node_action 递增回 step_count
                        ctx.flow_processor.runtime_state.record_node_action(
                            node_id=ctx.node_id,
                            observation=planner_output_dict.get("Observation", ""),
                            reasoning=planner_output_dict.get("Reasoning", ""),
                            action_type="browser_action",
                            action_params={},
                            action_target=action_desc,
                        )
                    except Exception as e:
                        logger.logger.warning(f"[BrowserNodeHandler] 记录 action 失败: {e}")
                
                # 中途保存 node_completion_summary（覆盖式，不累加）
                # AI 可以在任意步骤写 node_completion_summary 来存储关键数据
                mid_task_summary = planner_output_dict.get("node_completion_summary")
                if mid_task_summary and not planner_output_dict.get("MilestoneCompleted", False):
                    try:
                        exec_node = ctx.flow_processor.runtime_state.get_node_resolved(ctx.node_id)
                        if exec_node:
                            # 只在数据发生变化时才写入 ActionRecord（避免每个 step 都重复显示）
                            old_summary = exec_node.history_summary
                            exec_node.history_summary = mid_task_summary
                            if exec_node.action_history and mid_task_summary != old_summary:
                                exec_node.action_history[-1].result_observation = mid_task_summary
                            logger.logger.info(
                                f"[BrowserNodeHandler] 中途保存 node_completion_summary: {mid_task_summary[:100]}..."
                            )
                    except Exception as e:
                        logger.logger.warning(f"[BrowserNodeHandler] 保存中途 summary 失败: {e}")
                
            
            # 转发动作事件 -> 输出 tool_call
            elif event_type == "action":
                action = event.get("action", {})
                yield {
                    "type": "cua_update",
                    "cuaId": step_cua_id,
                    "content": action,
                    "kind": "planner",
                }
                
                # 如果是 stop 动作，不发送 tool_call
                if action.get("type") != "stop":
                    tool_call_event = {
                        "type": "tool_call",
                        "id": f"call_{step_cua_id}",
                        "target": "browser",
                        "name": action.get("type", "unknown"),
                        "args": {k: v for k, v in action.items() if k != "type"},
                    }
                    logger.logger.info(f"[BrowserNodeHandler] 发送 tool_call: {tool_call_event}")
                    yield tool_call_event
            
            # 捕获最终结果
            elif event_type == "step_complete":
                content = event.get("content", {})
                agent_step = self._parse_step_complete(content)
            
            # 转发状态事件
            elif event_type == "status":
                yield {
                    "type": "status",
                    "content": event.get("content", ""),
                }
            
            # 转发错误
            elif event_type == "error":
                yield {
                    "type": "cua_end",
                    "cuaId": step_cua_id,
                    "status": "error",
                    "error": event.get("content", "Unknown error"),
                }
                yield ErrorEvent(
                    message=event.get("content", "Unknown error"),
                    node_id=ctx.node_id,
                ).to_dict()
                return
        
        # 处理最终结果
        if agent_step:
            is_completed = agent_step.is_completed
            action_dict = agent_step.browser_action.to_dict() if agent_step.browser_action else {}
            action_title = self._generate_action_title(action_dict)
            
            # 如果任务完成
            if is_completed:
                # 如果 AI 主动提供了 result_markdown，保存为文件到 outputs
                files_to_transfer: List[str] = []
                result_markdown = agent_step.planner_output.result_markdown
                saved_filename = None
                if result_markdown:
                    saved_filename = agent_step.planner_output.output_filename or "browser_result.md"
                    s3_key = await self._save_and_upload_result_markdown(
                        ctx=ctx,
                        markdown_content=result_markdown,
                        filename=saved_filename,
                    )
                    if s3_key:
                        files_to_transfer.append(s3_key)
                    logger.logger.info(
                        f"[BrowserNodeHandler] result_markdown 已保存到 outputs, "
                        f"filename={saved_filename}, 长度={len(result_markdown)}, s3_key={s3_key}"
                    )
                
                # 构建完成摘要（不再手动拼接文件名，由 NodeCompleteEvent 统一构建 XML）
                completion_summary = agent_step.planner_output.completion_summary or "Browser operation completed"
                if saved_filename:
                    result_observation = f"Task completed. File saved: {saved_filename}"
                else:
                    result_observation = "Task completed"
                
                # 标记 action 完成
                if ctx.flow_processor:
                    try:
                        ctx.flow_processor.runtime_state.complete_node_action(
                            node_id=ctx.node_id,
                            status="success",
                            result_observation=result_observation,
                        )
                    except Exception as e:
                        logger.logger.warning(f"[BrowserNodeHandler] 标记 action 完成失败: {e}")
                
                handler_result = agent_step.planner_output.to_dict() if agent_step.planner_output else {}
                handler_result["is_node_completed"] = True
                handler_result["action"] = action_dict
                handler_result["browser_connected"] = True  # 保持连接状态，让后续流程可以继续使用
                
                # 如果有文件需要传输，发送文件传输事件
                if files_to_transfer:
                    handler_result["files_transferred"] = files_to_transfer
                    yield {
                        "type": "file_transfer",
                        "files": files_to_transfer,
                        "target": "local",
                        "status": "pending",
                    }
                    logger.logger.info(f"[BrowserNodeHandler] Files to transfer: {files_to_transfer}")
                
                # 检查是否有需要在完成前执行的实际动作（如 switch_tab, close_tab 等）
                # 当 Planner 说 "Switch to tab1" + MilestoneCompleted=true 时，
                # 动作的 tool_call 已经在上面的 "action" 事件处理中发出了，
                # 但我们不能立即发 node_complete(is_completed=true)，
                # 因为前端需要先执行这个 tool_call，再回调结果。
                # 所以：标记 pending_completion，让下一步回调时直接完成。
                action_type_str = action_dict.get("type", "stop")
                if action_type_str != "stop":
                    logger.logger.info(
                        f"[BrowserNodeHandler] MilestoneCompleted=true 但有待执行动作: {action_type_str}，"
                        f"标记 pending_completion，等待前端执行后再完成"
                    )
                    
                    yield {
                        "type": "cua_end",
                        "cuaId": step_cua_id,
                        "status": "completed",
                        "title": action_title,
                        "action": action_dict,
                    }
                    
                    # 保存完成信息到 handler_result，下一步直接使用
                    pending_handler_result = {
                        "is_node_completed": False,
                        "waiting_for_execution": True,
                        "browser_connected": True,
                        "pending_completion": True,
                        "pending_completion_data": {
                            "completion_summary": completion_summary,
                            "handler_result": handler_result,
                            "action_title": action_title,
                            "files_to_transfer": files_to_transfer,
                            "output_filename": saved_filename,
                            "result_markdown": result_markdown,
                        },
                        "last_action": action_type_str,
                        "step": step_count,
                        "cua_id": cua_id,
                    }
                    
                    yield NodeCompleteEvent(
                        node_id=ctx.node_id,
                        node_type=ctx.node_type,
                        is_node_completed=False,
                        handler_result=pending_handler_result,
                        action_summary=action_title,
                    ).to_dict()
                else:
                    # 无待执行动作，直接完成
                    # cua_end 必须在 node_complete 之前发送！
                    # 前端收到 node_complete (is_node_completed=true) 后会关闭 SSE 连接，
                    # 之后的事件不会被消费。
                    yield {
                        "type": "cua_end",
                        "cuaId": step_cua_id,
                        "status": "completed",
                        "title": action_title,
                        "action": action_dict,
                    }
                    
                    yield NodeCompleteEvent(
                        node_id=ctx.node_id,
                        node_type=ctx.node_type,
                        is_node_completed=True,
                        handler_result=handler_result,
                        action_summary=action_title,
                        node_completion_summary=completion_summary,
                        output_filename=saved_filename,
                        result_markdown=result_markdown,
                    ).to_dict()
            else:
                # 任务未完成，等待执行结果
                yield {
                    "type": "cua_end",
                    "cuaId": step_cua_id,
                    "status": "completed",
                    "title": action_title,
                    "action": action_dict,
                }
                
                # 构建 handler_result，保存 extracted_content 跨步骤传递
                step_handler_result = {
                    "is_node_completed": False,
                    "waiting_for_execution": True,
                    "browser_connected": True,  # 保持连接状态
                    "last_action": action_dict.get("type", "unknown"),
                    "step": step_count,
                    "cua_id": cua_id,
                    "planner_content": planner_output_dict,
                }
                if extracted_content:
                    step_handler_result["extracted_content"] = extracted_content
                
                yield NodeCompleteEvent(
                    node_id=ctx.node_id,
                    node_type=ctx.node_type,
                    is_node_completed=False,
                    handler_result=step_handler_result,
                    action_summary=action_title,
                ).to_dict()
        else:
            yield {
                "type": "cua_end",
                "cuaId": step_cua_id,
                "status": "error",
                "error": "Agent did not return a valid result",
            }
            yield ErrorEvent(
                message="Agent did not return a valid result",
                node_id=ctx.node_id,
            ).to_dict()
    
    async def _save_and_upload_result_markdown(
        self,
        ctx: NodeContext,
        markdown_content: str,
        filename: str,
    ) -> Optional[str]:
        """
        保存 markdown 结果到本地日志目录并上传到 S3
        
        与 Tool Use 节点一致的路径模式：
        - 本地: {step_dir}/{safe_filename}.md (日志留存)
        - S3:   projects/{project_id}/outputs/{safe_filename}.md (云端持久化)
        - 前端通过 file_transfer 事件从 S3 下载到项目 outputs 目录
        
        Args:
            ctx: 节点上下文
            markdown_content: markdown 内容
            filename: 文件名 (如 "browser_extract_result.md")
            
        Returns:
            S3 key，上传失败或未配置则返回 None
        """
        try:
            # 1. 确定本地保存路径（与 Tool Use 一致）
            if ctx.run_logger:
                step_dir = ctx.run_logger.get_step_dir()
                if not step_dir:
                    step_dir = ctx.log_folder
            else:
                step_dir = ctx.log_folder or os.path.join("logs", "browser_use", ctx.node_id)
            
            os.makedirs(step_dir, exist_ok=True)
            
            # 清理文件名
            base_filename = filename.replace('.md', '') if filename.endswith('.md') else filename
            safe_base = "".join(c for c in base_filename if c.isalnum() or c in ('_', '-')).strip()
            if not safe_base:
                safe_base = "browser_result"
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            safe_filename = f"{safe_base}_{timestamp}.md"
            local_path = os.path.join(step_dir, safe_filename)
            
            # 2. 保存到本地日志目录
            with open(local_path, "w", encoding="utf-8") as f:
                f.write(markdown_content)
            
            logger.logger.info(f"[BrowserNodeHandler] Saved result markdown to: {local_path}")
            
            # 3. 上传到 S3 (如果配置了 project_id)
            project_id = getattr(ctx, "project_id", None)
            if not project_id:
                logger.logger.info("[BrowserNodeHandler] project_id not provided, skip S3 upload")
                return None
            
            try:
                from useit_studio.ai_run.utils.s3_uploader import get_s3_uploader, _get_s3_client
                
                if _get_s3_client() is None:
                    logger.logger.info("[BrowserNodeHandler] S3 client not available, skip upload")
                    return None
                
                uploader = get_s3_uploader()
                s3_key = f"projects/{project_id}/outputs/{safe_filename}"
                
                success = await uploader.upload_file_async(
                    local_path=local_path,
                    s3_key=s3_key,
                    content_type="text/markdown"
                )
                
                if success:
                    logger.logger.info(f"[BrowserNodeHandler] Uploaded result markdown to S3: {s3_key}")
                    return s3_key
                else:
                    logger.logger.warning("[BrowserNodeHandler] Failed to upload result markdown to S3")
                    return None
                    
            except Exception as e:
                logger.logger.warning(f"[BrowserNodeHandler] S3 upload error: {e}")
                return None
                
        except Exception as e:
            logger.logger.error(f"[BrowserNodeHandler] Failed to save result markdown: {e}")
            return None
    
    def _extract_content_from_result(self, execution_result: Dict[str, Any]) -> Optional[str]:
        """
        从 execution_result 中提取 extract_content 的文本内容
        
        Local Engine 返回格式：
        {
            "result": {
                "action_results": [
                    {"success": true, "action": "extract_content", "content": "...text..."}
                ],
                "page_state": {...}
            }
        }
        或直接：
        {
            "action_results": [
                {"success": true, "action": "extract_content", "content": "...text..."}
            ],
            "page_state": {...}
        }
        """
        # 格式1: result.action_results
        result = execution_result.get("result", {})
        if isinstance(result, dict):
            action_results = result.get("action_results", [])
            for ar in action_results:
                if isinstance(ar, dict) and ar.get("action") == "extract_content" and ar.get("content"):
                    return ar["content"]
        
        # 格式2: 直接 action_results
        action_results = execution_result.get("action_results", [])
        for ar in action_results:
            if isinstance(ar, dict) and ar.get("action") == "extract_content" and ar.get("content"):
                return ar["content"]
        
        return None
    
    def _extract_page_state(self, ctx: NodeContext) -> Optional[PageState]:
        """
        从请求中提取页面状态
        """
        # 检查 execution_result
        if ctx.execution_result:
            return self._extract_page_state_from_result(ctx.execution_result)
        
        # 检查 node_state 中的 execution_result
        execution_result = ctx.node_state.get("execution_result")
        if execution_result:
            return self._extract_page_state_from_result(execution_result)
        
        # 检查 node_state 中是否有缓存的页面状态
        cached_state = ctx.node_state.get("page_state") or ctx.node_state.get("_page_state")
        if cached_state:
            return PageState.from_dict(cached_state)
        
        return None
    
    def _extract_page_state_from_result(self, execution_result: Dict[str, Any]) -> Optional[PageState]:
        """
        从 execution_result 中提取页面状态
        
        前端返回格式：
        {
            "status": "success",
            "result": {
                "page_state": { "url": "...", "title": "...", "elements": [...] },
                "screenshot": "<base64>"
            }
        }
        或者：
        {
            "page_state": { ... },
            "screenshot": "..."
        }
        """
        # 格式1: result.page_state
        result = execution_result.get("result", {})
        page_state_data = result.get("page_state")
        if page_state_data:
            screenshot = result.get("screenshot") or page_state_data.get("screenshot")
            page_state_data["screenshot"] = screenshot
            return PageState.from_dict(page_state_data)
        
        # 格式2: 直接 page_state
        page_state_data = execution_result.get("page_state")
        if page_state_data:
            screenshot = execution_result.get("screenshot") or page_state_data.get("screenshot")
            page_state_data["screenshot"] = screenshot
            return PageState.from_dict(page_state_data)
        
        return None
    
    def _convert_to_browser_context(
        self,
        ctx: NodeContext,
        page_state: PageState,
        extracted_content: Optional[str] = None,
    ) -> BrowserContext:
        """将 NodeContext 转换为 BrowserContext"""
        history_md = ""
        if ctx.history_md:
            history_md = ctx.history_md
        elif hasattr(ctx, 'get_history_md'):
            try:
                history_md = ctx.get_history_md()
            except Exception:
                pass
        
        # 从 exec_node 读取中途收集的数据（不改变 plan tree 格式）
        collected_data = None
        try:
            exec_node = ctx.flow_processor.runtime_state.get_node_resolved(ctx.node_id)
            if exec_node and exec_node.history_summary:
                collected_data = exec_node.history_summary
        except Exception:
            pass
        
        return BrowserContext(
            node_id=ctx.node_id,
            task_description=ctx.query,
            milestone_objective=ctx.get_node_instruction(),
            page_state=page_state,
            guidance_steps=self._get_guidance_steps(ctx.node_dict),
            history_md=history_md,
            loop_context=ctx.get_loop_context(),
            extracted_content=extracted_content,
            collected_data=collected_data,
        )
    
    def _get_guidance_steps(self, node_dict: Dict[str, Any]) -> List[str]:
        """从节点配置中提取指导步骤"""
        data = node_dict.get("data", {})
        if data.get("milestone_steps"):
            return data["milestone_steps"]
        if node_dict.get("milestone_steps"):
            return node_dict["milestone_steps"]
        return []
    
    def _parse_step_complete(self, content: Dict[str, Any]) -> BrowserAgentStep:
        """解析 step_complete 事件内容"""
        planner_dict = content.get("planner", {})
        planner_output = BrowserPlannerOutput(
            observation=planner_dict.get("Observation", ""),
            reasoning=planner_dict.get("Reasoning", ""),
            next_action=planner_dict.get("Action", ""),
            target_element=planner_dict.get("TargetElement"),
            is_milestone_completed=planner_dict.get("MilestoneCompleted", False),
            completion_summary=planner_dict.get("node_completion_summary"),
            output_filename=planner_dict.get("output_filename"),
            result_markdown=planner_dict.get("result_markdown"),
        )
        
        action_dict = content.get("action")
        browser_action = None
        if action_dict:
            action_type_str = action_dict.get("type", "stop")
            try:
                action_type = BrowserActionType(action_type_str)
            except ValueError:
                action_type = BrowserActionType.STOP
            browser_action = BrowserAction(
                action_type=action_type,
                args={k: v for k, v in action_dict.items() if k != "type"},
            )
        
        return BrowserAgentStep(
            planner_output=planner_output,
            browser_action=browser_action,
            reasoning_text=content.get("reasoning", ""),
            token_usage=content.get("token_usage", {}),
            error=content.get("error"),
        )
    
    def _generate_action_title(self, action: Optional[Dict[str, Any]]) -> str:
        """生成用户友好的动作标题"""
        if not action:
            return "Completed"
        
        action_type = action.get("type", "").lower()
        
        # 连接管理
        if action_type == "connect":
            return "Connect to browser"
        elif action_type == "attach":
            return "Attach to browser"
        elif action_type == "disconnect":
            return "Disconnect from browser"
        elif action_type == "status":
            return "Check browser status"
        # 元素交互
        elif action_type == "click_element":
            return f"Click element [{action.get('index', '?')}]"
        elif action_type == "input_text":
            text = action.get("text", "")[:15]
            return f"Type: {text}..." if len(action.get("text", "")) > 15 else f"Type: {text}"
        # 导航
        elif action_type == "go_to_url":
            url = action.get("url", "")[:30]
            return f"Navigate: {url}..."
        elif action_type == "scroll_down":
            return "Scroll down"
        elif action_type == "scroll_up":
            return "Scroll up"
        elif action_type == "press_key":
            return f"Press: {action.get('key', '')}"
        elif action_type == "go_back":
            return "Go back"
        elif action_type == "go_forward":
            return "Go forward"
        elif action_type == "refresh":
            return "Refresh page"
        elif action_type == "wait":
            return f"Wait {action.get('seconds', 2)}s"
        elif action_type == "extract_content":
            selector = action.get("selector", "body")
            return f"Extract content ({selector})"
        elif action_type == "page_state":
            return "Get page state"
        elif action_type == "stop":
            return "Sub-Task Completed"
        else:
            return f"Action: {action_type}"
