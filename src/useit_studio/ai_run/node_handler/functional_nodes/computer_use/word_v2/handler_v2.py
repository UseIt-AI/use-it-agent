"""
Word Node Handler V2 - 纯桥接层

职责：
1. 实现 BaseNodeHandlerV2 接口
2. 从请求中提取初始快照
3. 运行 WordAgent 决策循环
4. 转发事件，处理暂停/恢复

Handler 不做任何决策，所有决策都在 Agent 中完成。
"""

from __future__ import annotations

import uuid
from typing import Dict, Any, List, AsyncGenerator, Optional

from useit_studio.ai_run.node_handler.base_v2 import (
    BaseNodeHandlerV2,
    NodeContext as V2NodeContext,
    NodeCompleteEvent,
    ErrorEvent,
)
from useit_studio.ai_run.utils.logger_utils import LoggerUtils

from .core import create_agent
from .models import (
    DocumentSnapshot,
    document_snapshot_from_dict,
)

# 默认使用 planner_only 模式
DEFAULT_AGENT_MODE = "planner_only"


logger = LoggerUtils(component_name="WordNodeHandlerV2")


class WordNodeHandlerV2(BaseNodeHandlerV2):
    """
    Word 节点处理器 V2 - 纯桥接层
    
    支持的节点类型：
    - computer-use-word
    """
    
    @classmethod
    def supported_types(cls) -> List[str]:
        return ["computer-use-word"]
    
    async def execute(self, ctx: V2NodeContext) -> AsyncGenerator[Dict[str, Any], None]:
        """
        执行 Word 节点
        
        流程：
        1. 提取初始快照（从请求中）
        2. 检查是否是执行结果回调
        3. 运行 Agent 决策循环
        4. 转发事件
        """
        logger.logger.info(f"[WordNodeHandlerV2] 开始执行节点: {ctx.node_id}")
        logger.logger.info(f"[WordNodeHandlerV2] node_state keys: {list(ctx.node_state.keys())}")
        
        cua_id = f"word_{uuid.uuid4().hex[:8]}_{ctx.node_id}"
        
        try:
            # 解析节点配置
            # 重要：区分宏观目标和节点指令
            # - user_goal: 用户在前端输入的宏观目标（ctx.query）
            # - node_instruction: 当前节点的具体指令（来自 workflow 定义）
            node_data = ctx.node_dict.get("data", {})
            user_goal = ctx.query  # 用户输入的宏观目标
            node_instruction = node_data.get("instruction", "") or node_data.get("description", "")
            
            # 向后兼容：如果没有节点指令，使用用户目标
            query = node_instruction or user_goal
            
            logger.logger.info(f"[WordNodeHandlerV2] Query: {query[:100] if query else 'Empty'}...")
            
            # 提取初始快照（前端请求时附带）
            initial_snapshot = self._extract_snapshot(ctx)
            
            # 检查是否是执行结果回调（第二次及后续调用）
            # 优先使用 ctx.execution_result（从请求中传递的），其次检查 node_state
            execution_result = ctx.execution_result or ctx.node_state.get("execution_result")
            handler_result = ctx.node_state.get("handler_result", {})
            waiting_for_execution = handler_result.get("waiting_for_execution", False)
            
            logger.logger.info(f"[WordNodeHandlerV2] execution_result: {execution_result is not None}, waiting_for_execution: {waiting_for_execution}")
            
            # 如果有 execution_result，从中提取 snapshot
            if execution_result and not initial_snapshot:
                snapshot_data = execution_result.get("snapshot")
                if snapshot_data:
                    logger.logger.info(f"[WordNodeHandlerV2] 从 execution_result 中提取 snapshot")
                    try:
                        initial_snapshot = document_snapshot_from_dict(snapshot_data)
                        logger.logger.info(f"[WordNodeHandlerV2] snapshot 提取成功: {initial_snapshot.document_info.name if initial_snapshot and initial_snapshot.document_info else 'N/A'}")
                    except Exception as e:
                        logger.logger.warning(f"[WordNodeHandlerV2] 解析 execution_result.snapshot 失败: {e}")
            
            # 判断是否是执行结果回调：必须有 execution_result
            # waiting_for_execution 只是标记上次请求在等待执行，但如果没有 execution_result，说明还没收到结果
            if execution_result is not None:
                # 这是执行完成后的回调
                async for event in self._handle_execution_callback(
                    ctx, cua_id, execution_result, initial_snapshot
                ):
                    yield event
                return
            
            # 首次调用：发送节点开始事件
            yield {
                "type": "node_start",
                "nodeId": ctx.node_id,
                "title": ctx.get_node_title(),
                "nodeType": ctx.node_type,
                "instruction": ctx.get_node_instruction(),
            }
            
            # ===== 问题1修复：Node 首步如果没有 snapshot，先发送获取 snapshot 的代码 =====
            if not initial_snapshot:
                logger.logger.info("[WordNodeHandlerV2] 首步无 snapshot，发送获取状态的代码")
                async for event in self._emit_get_snapshot_request(ctx, cua_id):
                    yield event
                return
            
            # 创建并运行 Agent（使用工厂函数，支持模式切换）
            agent = create_agent(
                mode=DEFAULT_AGENT_MODE,
                planner_model=ctx.planner_model,
                actor_model=ctx.actor_model,
                api_keys=ctx.planner_api_keys,
                node_id=ctx.node_id,
            )
            
            step_count = 0
            current_planner_content: Dict[str, Any] = {}  # 保存当前 planner 输出，用于 cua_end 的 title
            step_history: List[Dict[str, Any]] = []  # 保存所有步骤的历史
            
            # 获取 history_md（从 RuntimeStateManager 生成）
            history_md = ""
            if ctx.flow_processor:
                try:
                    from useit_studio.ai_run.runtime.transformers import AIMarkdownTransformer
                    history_md = AIMarkdownTransformer(
                        ctx.flow_processor.runtime_state.state,
                        graph_nodes=ctx.flow_processor.graph_manager.nodes,
                        graph_edges=ctx.flow_processor.graph_manager.edges,
                    ).transform()
                except Exception as e:
                    logger.logger.warning(f"[WordNodeHandlerV2] 生成 history_md 失败: {e}")
            
            # 获取附件文件内容（异步，包含智能路由判断）
            attached_files_content = ""
            if hasattr(ctx, 'get_attached_files_content'):
                attached_files_content = await ctx.get_attached_files_content()
            
            # 运行 Agent 决策循环
            agent_gen = agent.run(
                user_goal=user_goal,
                node_instruction=node_instruction,
                initial_snapshot=initial_snapshot,
                max_steps=60,
                log_dir=ctx.log_folder,
                history_md=history_md,
                attached_files_content=attached_files_content,
                attached_images=ctx.attached_images or [],
                additional_context=ctx.additional_context or "",
            )
            
            async for event in agent_gen:
                event_type = event.get("type", "")
                
                # Step 开始
                if event_type == "step_start":
                    step_count = event.get("step", step_count + 1)
                    yield {
                        "type": "cua_start",
                        "cuaId": f"{cua_id}_step{step_count}",
                        "step": step_count,
                        "title": f"Word 操作 - 步骤 {step_count}",
                        "nodeId": ctx.node_id,
                    }
                
                # 推理过程
                elif event_type == "reasoning_delta":
                    yield {
                        "type": "cua_delta",
                        "cuaId": f"{cua_id}_step{step_count}",
                        "reasoning": event.get("content", ""),
                        "kind": event.get("source", "planner"),
                    }
                
                # 规划完成
                elif event_type == "plan_complete":
                    planner_content = event.get("content", {})
                    current_planner_content = planner_content  # 保存用于 cua_end
                    yield {
                        "type": "planner_complete",
                        "content": {"vlm_plan": planner_content},
                    }
                    
                    # 记录 action 到 RuntimeStateManager（用于生成 milestone_history.md）
                    if ctx.flow_processor and planner_content:
                        try:
                            action_desc = planner_content.get("Action", "")
                            action_title = planner_content.get("Title", "")
                            thinking = planner_content.get("Thinking", "")
                            ctx.flow_processor.runtime_state.record_node_action(
                                node_id=ctx.node_id,
                                thinking=thinking,
                                title=action_title,
                                observation=planner_content.get("Observation", ""),
                                reasoning=planner_content.get("Reasoning", ""),
                                action_type="execute_code",
                                action_params={},
                                action_target=action_desc,
                            )
                            logger.logger.info(f"[WordNodeHandlerV2] Recorded action to RuntimeStateManager: {action_title or action_desc[:50]}")
                        except Exception as e:
                            logger.logger.warning(f"[WordNodeHandlerV2] Failed to record action: {e}")
                
                # 动作生成
                elif event_type == "action":
                    yield {
                        "type": "cua_update",
                        "cuaId": f"{cua_id}_step{step_count}",
                        "content": event.get("action", {}),
                        "kind": "actor",
                    }
                
                # 需要执行代码
                elif event_type == "tool_call":
                    # 从 tool_call 事件中提取 action 信息
                    action_type = event.get("name", "execute_code")
                    action_args = event.get("args", {})
                    action_dict = {"type": action_type, **action_args}
                    
                    # title 优先使用 planner 的 Title，其次使用 Action
                    action_title = current_planner_content.get("Title") or current_planner_content.get("Action", "Execute code")
                    
                    # 转发 tool_call
                    yield event
                    
                    # 发送 cua_end（这一步的 CUA 结束）
                    yield {
                        "type": "cua_end",
                        "cuaId": f"{cua_id}_step{step_count}",
                        "status": "completed",
                        "title": action_title,
                        "action": action_dict,
                    }
                
                # 等待执行结果
                elif event_type == "wait_for_execution":
                    # Agent 需要等待执行结果
                    # 发送 node_complete (is_node_completed=false) 表示节点未完成
                    logger.logger.info("[WordNodeHandlerV2] Waiting for execution result, pausing")
                    
                    # action_summary 使用 Title
                    action_title = current_planner_content.get("Title") or current_planner_content.get("Action", "Waiting for execution")
                    
                    # 记录当前步骤到历史
                    step_history.append({
                        "step": step_count,
                        "thinking": current_planner_content.get("Thinking", ""),
                        "action": current_planner_content.get("Action", ""),
                        "title": action_title,
                        "execution_status": "pending",  # 等待执行结果
                    })
                    
                    yield NodeCompleteEvent(
                        node_id=ctx.node_id,
                        node_type=ctx.node_type,
                        is_node_completed=False,
                        handler_result={
                            "is_node_completed": False,
                            "waiting_for_execution": True,
                            "step": step_count,
                            "cua_id": cua_id,  # 保存 cua_id 用于回调时继续使用
                            "planner_content": current_planner_content,  # 保存 planner 输出
                            "step_history": step_history,  # 保存步骤历史
                        },
                        action_summary=action_title,
                    ).to_dict()
                    return
                
                # 任务完成
                elif event_type == "task_completed":
                    # title 优先使用 planner 的 Title，其次使用 completion_summary
                    completion_summary = event.get("summary", "")
                    action_title = current_planner_content.get("Title") or completion_summary or "Task completed"
                    
                    # 完成最后一个 action 的状态更新（标记为成功）
                    if ctx.flow_processor:
                        try:
                            ctx.flow_processor.runtime_state.complete_node_action(
                                node_id=ctx.node_id,
                                status="success",
                                result_observation=completion_summary or "Task completed successfully",
                            )
                            logger.logger.info(f"[WordNodeHandlerV2] Completed final action with success status")
                        except Exception as e:
                            logger.logger.warning(f"[WordNodeHandlerV2] Failed to complete final action: {e}")
                    
                    yield {
                        "type": "cua_end",
                        "cuaId": f"{cua_id}_step{step_count}",
                        "status": "completed",
                        "title": action_title,
                        "action": {"type": "stop"},
                    }
                    
                    yield NodeCompleteEvent(
                        node_id=ctx.node_id,
                        node_type=ctx.node_type,
                        is_node_completed=True,
                        handler_result={
                            "is_node_completed": True,
                            "Observation": "Task completed successfully",
                            "Reasoning": "All requested operations have been performed",
                        },
                        action_summary=action_title,
                        node_completion_summary=event.get("summary", "Word operation completed"),
                    ).to_dict()
                    return
                
                # 达到最大步数
                elif event_type == "max_steps_reached":
                    yield NodeCompleteEvent(
                        node_id=ctx.node_id,
                        node_type=ctx.node_type,
                        is_node_completed=True,
                        handler_result={
                            "is_node_completed": True,
                            "Observation": f"Reached maximum steps ({event.get('steps', 10)})",
                            "Reasoning": "Task may be incomplete",
                        },
                        action_summary="达到最大步数",
                        node_completion_summary="Word 操作达到最大步数限制",
                    ).to_dict()
                    return
                
                # 错误
                elif event_type == "error":
                    yield {
                        "type": "cua_end",
                        "cuaId": f"{cua_id}_step{step_count}",
                        "status": "error",
                        "error": event.get("content", "Unknown error"),
                    }
                    yield ErrorEvent(
                        message=event.get("content", "Unknown error"),
                        node_id=ctx.node_id,
                    ).to_dict()
                    return
        
        except Exception as e:
            error_msg = f"Word 节点执行失败: {str(e)}"
            logger.logger.error(error_msg, exc_info=True)
            
            yield {
                "type": "cua_end",
                "cuaId": cua_id,
                "status": "error",
                "error": error_msg,
            }
            yield ErrorEvent(message=error_msg, node_id=ctx.node_id).to_dict()
    
    async def _handle_execution_callback(
        self,
        ctx: V2NodeContext,
        cua_id: str,
        execution_result: Dict[str, Any],
        new_snapshot: Optional[DocumentSnapshot],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        处理执行结果回调
        
        当前端执行完代码后，会带着结果和新快照再次调用。
        这里需要让 Agent 继续决策循环。
        
        execution_result 格式（来自 Backend）：
        {
            "execution": { "success": true, "output": "...", "error": null, "return_code": 0 },
            "snapshot": { "document_info": {...}, "content": {...}, "screenshot": "base64..." },
            "status": "success"
        }
        """
        logger.logger.info(f"[WordNodeHandlerV2] 收到执行结果回调")
        logger.logger.info(f"[WordNodeHandlerV2] execution_result keys: {list(execution_result.keys()) if execution_result else 'None'}")
        
        # 兼容两种格式：
        # 1. 新格式（Backend）: execution_result.execution.success
        # 2. 旧格式: execution_result.success
        execution_data = execution_result.get("execution", {})
        if execution_data:
            success = execution_data.get("success", False)
            error = execution_data.get("error", "") or ""
            output = execution_data.get("output", "")
        else:
            # 旧格式兼容
            success = execution_result.get("success", False)
            error = execution_result.get("error", "") or ""
            output = execution_result.get("output", "")
        
        logger.logger.info(f"[WordNodeHandlerV2] 执行结果: success={success}, error={error[:100] if error else 'None'}")
        
        # 获取之前的状态（包括 cua_id 和 planner_content）
        prev_state = ctx.node_state.get("handler_result", {})
        step_count = prev_state.get("step", 1)
        prev_cua_id = prev_state.get("cua_id", cua_id)  # 使用之前保存的 cua_id
        prev_planner_content = prev_state.get("planner_content", {})
        step_history: List[Dict[str, Any]] = prev_state.get("step_history", [])
        
        # 更新上一步的执行状态
        if step_history:
            step_history[-1]["execution_status"] = "success" if success else "failed"
            if error:
                step_history[-1]["execution_error"] = error[:200]
        
        # 开始新的 CUA（上一个 CUA 已在 tool_call 时结束）
        step_count += 1
        step_cua_id = f"{prev_cua_id}_step{step_count}"
        
        yield {
            "type": "cua_start",
            "cuaId": step_cua_id,
            "step": step_count,
            "title": f"Word Step {step_count}",
            "nodeId": ctx.node_id,
        }
        
        # 注意：不再发送硬编码的 cua_delta
        # AI 的真实 thinking 会通过 Agent 的 reasoning_delta 事件转换为 cua_delta 发送到前端
        
        # 完成上一个 action 的状态更新
        if ctx.flow_processor:
            try:
                ctx.flow_processor.runtime_state.complete_node_action(
                    node_id=ctx.node_id,
                    status="success" if success else "failed",
                    result_observation="Code executed successfully" if success else f"Code execution failed: {error}",
                    error=error if not success else None,
                )
                logger.logger.info(f"[WordNodeHandlerV2] Updated previous action status: {'success' if success else 'failed'}")
            except Exception as e:
                logger.logger.warning(f"[WordNodeHandlerV2] Failed to update action status: {e}")
        
        # 重新创建 Agent 继续决策
        # 注意：这里需要恢复历史记录
        # 重要：区分宏观目标和节点指令
        node_data = ctx.node_dict.get("data", {})
        user_goal = ctx.query  # 用户输入的宏观目标
        node_instruction = node_data.get("instruction", "") or node_data.get("description", "")
        
        agent = create_agent(
            mode=DEFAULT_AGENT_MODE,
            planner_model=ctx.planner_model,
            actor_model=ctx.actor_model,
            api_keys=ctx.planner_api_keys,
            node_id=ctx.node_id,
        )
        
        # 获取 history_md（从 RuntimeStateManager 生成）
        history_md = ""
        if ctx.flow_processor:
            try:
                from useit_studio.ai_run.runtime.transformers import AIMarkdownTransformer
                history_md = AIMarkdownTransformer(
                    ctx.flow_processor.runtime_state.state,
                    graph_nodes=ctx.flow_processor.graph_manager.nodes,
                    graph_edges=ctx.flow_processor.graph_manager.edges,
                ).transform()
            except Exception as e:
                logger.logger.warning(f"[WordNodeHandlerV2] 生成 history_md 失败: {e}")
        
        # 获取附件文件内容（异步，包含智能路由判断）
        attached_files_content = ""
        if hasattr(ctx, 'get_attached_files_content'):
            attached_files_content = await ctx.get_attached_files_content()
        
        # 继续决策循环（流式）
        from .models import AgentContext, AgentStep
        
        context = AgentContext(
            user_goal=user_goal,
            node_instruction=node_instruction,
            current_snapshot=new_snapshot,
            history_md=history_md,
            attached_files_content=attached_files_content,
            attached_images=self._extract_attached_images(ctx),
            additional_context=ctx.additional_context or "",
        )
        
        # 执行单步决策（流式）
        step: Optional[AgentStep] = None
        planner_content: Dict[str, Any] = {}
        
        async for event in agent.step_streaming(context, ctx.log_folder):
            event_type = event.get("type", "")
            
            # 转发推理事件到前端
            if event_type == "reasoning_delta":
                yield {
                    "type": "cua_delta",
                    "cuaId": step_cua_id,
                    "reasoning": event.get("content", ""),
                    "kind": event.get("source", "planner"),
                }
            
            # 规划完成
            elif event_type == "plan_complete":
                planner_content = event.get("content", {})
                yield {
                    "type": "planner_complete",
                    "content": {"vlm_plan": planner_content},
                }
                
                # 记录 action 到 RuntimeStateManager
                if ctx.flow_processor and planner_content:
                    try:
                        action_desc = planner_content.get("Action", "")
                        action_title = planner_content.get("Title", "")
                        thinking = planner_content.get("Thinking", "")
                        ctx.flow_processor.runtime_state.record_node_action(
                            node_id=ctx.node_id,
                            thinking=thinking,
                            title=action_title,
                            observation=planner_content.get("Observation", ""),
                            reasoning=planner_content.get("Reasoning", ""),
                            action_type="execute_code",
                            action_params={},
                            action_target=action_desc,
                        )
                        logger.logger.info(f"[WordNodeHandlerV2] Recorded action: {action_title or action_desc[:50]}")
                    except Exception as e:
                        logger.logger.warning(f"[WordNodeHandlerV2] Failed to record action: {e}")
            
            # Actor 生成动作
            elif event_type == "action":
                yield {
                    "type": "cua_update",
                    "cuaId": step_cua_id,
                    "content": event.get("action", {}),
                    "kind": "actor",
                }
            
            # 单步完成
            elif event_type == "step_complete":
                step = event.get("step")
            
            # 错误
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
        
        if not step:
            yield {
                "type": "cua_end",
                "cuaId": step_cua_id,
                "status": "error",
                "error": "No step result",
            }
            yield ErrorEvent(message="No step result", node_id=ctx.node_id).to_dict()
            return
        
        # 更新 planner_content（如果没有在事件中获取到）
        if not planner_content:
            planner_content = step.planner_output.to_dict()
        
        # 检查是否完成
        if step.is_completed:
            action_title = planner_content.get("Title") or step.planner_output.completion_summary or "Task completed"
            
            # 完成最后一个 action 的状态更新（标记为成功）
            if ctx.flow_processor:
                try:
                    ctx.flow_processor.runtime_state.complete_node_action(
                        node_id=ctx.node_id,
                        status="success",
                        result_observation=step.planner_output.completion_summary or "Task completed successfully",
                    )
                    logger.logger.info(f"[WordNodeHandlerV2] Completed final action with success status")
                except Exception as e:
                    logger.logger.warning(f"[WordNodeHandlerV2] Failed to complete final action: {e}")
            
            yield {
                "type": "cua_end",
                "cuaId": step_cua_id,
                "status": "completed",
                "title": action_title,
                "action": {"type": "stop"},
            }
            
            yield NodeCompleteEvent(
                node_id=ctx.node_id,
                node_type=ctx.node_type,
                is_node_completed=True,
                handler_result={
                    "is_node_completed": True,
                    "Observation": step.planner_output.observation,
                    "Reasoning": step.planner_output.reasoning,
                },
                action_summary=action_title,
                node_completion_summary=step.planner_output.completion_summary or "Word operation completed",
            ).to_dict()
            return
        
        # 需要继续执行：发送 tool_call，然后结束 CUA
        if step.action and step.action.code:
            action_dict = step.action.to_dict()
            action_title = planner_content.get("Title") or planner_content.get("Action", "Execute code")
            
            # 标准 tool_call 格式
            yield {
                "type": "tool_call",
                "id": f"call_word_{step_cua_id}",
                "target": "word",
                "name": action_dict.get("type", "execute_code"),
                "args": {k: v for k, v in action_dict.items() if k != "type"},
            }
            
            # 结束当前 CUA
            yield {
                "type": "cua_end",
                "cuaId": step_cua_id,
                "status": "completed",
                "title": action_title,
                "action": action_dict,
            }
            
            # 记录当前步骤到历史
            step_history.append({
                "step": step_count,
                "thinking": planner_content.get("Thinking", ""),
                "action": planner_content.get("Action", ""),
                "title": action_title,
                "execution_status": "pending",
            })
            
            # 保存状态，等待下次回调
            yield NodeCompleteEvent(
                node_id=ctx.node_id,
                node_type=ctx.node_type,
                is_node_completed=False,
                handler_result={
                    "is_node_completed": False,
                    "waiting_for_execution": True,
                    "step": step_count,
                    "cua_id": prev_cua_id,
                    "planner_content": planner_content,
                    "step_history": step_history,
                },
                action_summary=action_title,
            ).to_dict()
        else:
            # 没有动作，可能是错误
            yield {
                "type": "cua_end",
                "cuaId": step_cua_id,
                "status": "error",
                "error": step.error or "No action generated",
            }
            
            yield ErrorEvent(
                message=step.error or "No action generated",
                node_id=ctx.node_id,
            ).to_dict()
    
    async def _emit_get_snapshot_request(
        self, 
        ctx: V2NodeContext, 
        cua_id: str
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        发送获取 Word 文档快照的请求
        
        当 Node 首步没有 snapshot 时，需要先发送一段"获取状态"的代码，
        让前端执行后返回当前 Word 文档的快照。
        
        这个代码不做任何修改操作，只是获取文档信息。
        """
        step_cua_id = f"{cua_id}_step0_get_snapshot"
        
        # 发送 CUA 开始
        yield {
            "type": "cua_start",
            "cuaId": step_cua_id,
            "step": 0,
            "title": "Reading document state",
            "nodeId": ctx.node_id,
        }
        
        # 发送 reasoning delta
        yield {
            "type": "cua_delta",
            "cuaId": step_cua_id,
            "reasoning": "Reading current Word document state...",
            "kind": "planner",
        }
        
        # 记录 action 到 RuntimeStateManager（用于 milestone_history.md 生成）
        if ctx.flow_processor:
            try:
                ctx.flow_processor.runtime_state.record_node_action(
                    node_id=ctx.node_id,
                    thinking="Need to read current Word document state before making any changes.",
                    title="Read document state",
                    observation="No Word document snapshot available yet",
                    action_type="execute_code",
                    action_params={},
                    action_target="Read Word document state",
                )
            except Exception as e:
                logger.logger.warning(f"[WordNodeHandlerV2] Failed to record get_snapshot action: {e}")
        
        # 生成获取快照的 PowerShell 代码
        # 注意：这段代码只获取状态，不做任何修改
        get_snapshot_code = '''try {
    # Try to get existing Word instance
    try {
        $word = [System.Runtime.InteropServices.Marshal]::GetActiveObject("Word.Application")
        Write-Host "Connected to existing Word instance."
    } catch {
        Write-Host "Word is not running. No document to inspect."
        exit 0
    }
    
    # Check if there's an active document
    if ($word.Documents.Count -eq 0) {
        Write-Host "No document is currently open in Word."
        exit 0
    }
    
    $doc = $word.ActiveDocument
    Write-Host "Active document: $($doc.Name)"
    Write-Host "Document path: $($doc.FullName)"
    Write-Host "Page count: $($doc.ComputeStatistics(2))"  # wdStatisticPages = 2
    Write-Host "Word count: $($doc.ComputeStatistics(0))"  # wdStatisticWords = 0
    Write-Host "Paragraph count: $($doc.Paragraphs.Count)"
    
    # Get first few paragraphs for context
    $maxParas = [Math]::Min(5, $doc.Paragraphs.Count)
    for ($i = 1; $i -le $maxParas; $i++) {
        $para = $doc.Paragraphs($i)
        $text = $para.Range.Text.Trim()
        if ($text.Length -gt 100) {
            $text = $text.Substring(0, 100) + "..."
        }
        Write-Host "Paragraph $i : $text"
    }
    
    Write-Host "Document snapshot retrieved successfully."
    
} catch {
    Write-Host "Error getting document state: $_"
}'''
        
        action_dict = {"type": "execute_code", "code": get_snapshot_code, "language": "PowerShell"}
        
        # 发送 cua_update
        yield {
            "type": "cua_update",
            "cuaId": step_cua_id,
            "content": action_dict,
            "kind": "actor",
        }
        
        # 发送 tool_call
        yield {
            "type": "tool_call",
            "id": f"call_word_{ctx.node_id}_get_snapshot",
            "target": "word",
            "name": "execute_code",
            "args": {"code": get_snapshot_code, "language": "PowerShell"},
        }
        
        # 发送 cua_end
        yield {
            "type": "cua_end",
            "cuaId": step_cua_id,
            "status": "completed",
            "title": "Reading document state",
            "action": action_dict,
        }
        
        # 发送 node_complete (is_node_completed=false)，等待执行结果
        logger.logger.info("[WordNodeHandlerV2] Waiting for document snapshot execution result")
        
        yield NodeCompleteEvent(
            node_id=ctx.node_id,
            node_type=ctx.node_type,
            is_node_completed=False,
            handler_result={
                "is_node_completed": False,
                "waiting_for_execution": True,
                "waiting_for_snapshot": True,  # 标记这是获取 snapshot 的请求
                "step": 0,
                "cua_id": cua_id,
                "planner_content": {
                    "Observation": "No document snapshot available yet",
                    "Reasoning": "Need to read current Word document state before planning",
                    "Action": "Read Word document state",
                },
            },
            action_summary="Read Word document state",
        ).to_dict()
    
    def _extract_snapshot(self, ctx: V2NodeContext) -> Optional[DocumentSnapshot]:
        """
        从请求中提取文档快照
        
        前端请求时可能在以下位置附带快照:
        1. node_state.snapshot (直接是 DocumentSnapshot 结构)
        2. node_state.snapshot.word_data (嵌套结构)
        3. node_state.word_data (直接结构)
        """
        # 尝试从 snapshot 字段提取
        snapshot_data = ctx.node_state.get("snapshot", {})
        
        if snapshot_data:
            # 情况 1: snapshot 直接是 DocumentSnapshot 结构 (包含 document_info)
            if "document_info" in snapshot_data:
                try:
                    return document_snapshot_from_dict(snapshot_data)
                except Exception as e:
                    logger.logger.warning(f"解析 snapshot (直接结构) 失败: {e}")
            
            # 情况 2: snapshot.word_data 嵌套结构
            word_data = snapshot_data.get("word_data")
            if word_data:
                try:
                    return document_snapshot_from_dict(word_data)
                except Exception as e:
                    logger.logger.warning(f"解析 snapshot.word_data 失败: {e}")
        
        # 情况 3: 直接从 word_data 提取
        word_data = ctx.node_state.get("word_data")
        if word_data:
            try:
                return document_snapshot_from_dict(word_data)
            except Exception as e:
                logger.logger.warning(f"解析 word_data 失败: {e}")
        
        # 没有快照数据
        logger.logger.info("[WordNodeHandlerV2] 没有找到文档快照，Word 可能未打开")
        return None

    @staticmethod
    def _extract_attached_images(ctx: V2NodeContext) -> List[str]:
        """提取并标准化附件图片 base64（去掉 data URI 前缀）"""
        images: List[str] = []
        for item in (ctx.attached_images or []):
            if not isinstance(item, dict):
                continue
            raw = item.get("base64")
            if not isinstance(raw, str):
                continue
            value = raw.strip()
            if not value:
                continue
            if value.startswith("data:") and "," in value:
                value = value.split(",", 1)[1]
            images.append(value)
        return images
