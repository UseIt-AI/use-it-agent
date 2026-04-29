"""
PowerPoint Node Handler V2 - 纯桥接层

职责：
1. 实现 BaseNodeHandlerV2 接口
2. 从请求中提取初始快照
3. 运行 PPTAgent 决策循环
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
    SlideSnapshot,
    slide_snapshot_from_dict,
    AgentContext,
    AgentStep,
)


logger = LoggerUtils(component_name="PPTNodeHandlerV2")


class PPTNodeHandlerV2(BaseNodeHandlerV2):
    """
    PowerPoint 节点处理器 V2 - 纯桥接层
    
    支持的节点类型：
    - computer-use-ppt
    - computer-use-powerpoint
    """
    
    @classmethod
    def supported_types(cls) -> List[str]:
        return ["computer-use-ppt", "computer-use-powerpoint"]
    
    async def execute(self, ctx: V2NodeContext) -> AsyncGenerator[Dict[str, Any], None]:
        """
        执行 PowerPoint 节点
        """
        logger.logger.info(f"[PPTNodeHandlerV2] 开始执行节点: {ctx.node_id}")
        
        cua_id = f"ppt_{uuid.uuid4().hex[:8]}_{ctx.node_id}"
        
        try:
            # 解析节点配置
            node_data = ctx.node_dict.get("data", {})
            user_goal = ctx.query
            node_instruction = node_data.get("instruction", "") or node_data.get("description", "")
            query = node_instruction or user_goal
            
            logger.logger.info(f"[PPTNodeHandlerV2] Query: {query[:100] if query else 'Empty'}...")
            
            # 检查是否是执行结果回调
            execution_result = ctx.execution_result or ctx.node_state.get("execution_result")
            handler_result = ctx.node_state.get("handler_result", {})
            waiting_for_execution = handler_result.get("waiting_for_execution", False)
            
            logger.logger.info(f"[PPTNodeHandlerV2] execution_result: {execution_result is not None}, waiting_for_execution: {waiting_for_execution}")
            
            # 提取快照：优先从 execution_result 中提取
            initial_snapshot = None
            if execution_result and isinstance(execution_result, dict):
                initial_snapshot = self._extract_snapshot_from_execution_result(execution_result)
                if initial_snapshot:
                    logger.logger.info("[PPTNodeHandlerV2] 从 execution_result 提取 snapshot 成功")
            
            # 如果 execution_result 中没有 snapshot，从 node_state 中提取
            if not initial_snapshot:
                initial_snapshot = self._extract_snapshot(ctx)
                if initial_snapshot:
                    logger.logger.info("[PPTNodeHandlerV2] 从 node_state 提取 snapshot 成功")
            
            # 执行结果回调
            if execution_result is not None:
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
            
            # 如果没有 snapshot，先发送获取 snapshot 的代码
            if not initial_snapshot:
                logger.logger.info("[PPTNodeHandlerV2] 首步无 snapshot，发送获取状态的代码")
                async for event in self._emit_get_snapshot_request(ctx, cua_id):
                    yield event
                return
            
            # 创建并运行 Agent
            node_model = self._get_node_model(ctx.node_dict)
            planner_model = node_model or ctx.planner_model
            logger.logger.info(
                f"[PPTNodeHandlerV2] 使用模型: {planner_model} "
                f"(node_model={node_model}, ctx.planner_model={ctx.planner_model})"
            )
            agent = create_agent(
                planner_model=planner_model,
                api_keys=ctx.planner_api_keys,
                node_id=ctx.node_id,
            )
            
            step_count = 0
            current_planner_content: Dict[str, Any] = {}
            step_history: List[Dict[str, Any]] = []
            
            # 获取 history_md
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
                    logger.logger.warning(f"[PPTNodeHandlerV2] 生成 history_md 失败: {e}")
            
            # 获取附件文件内容（异步，包含智能路由判断）
            attached_files_content = ""
            if hasattr(ctx, 'get_attached_files_content'):
                attached_files_content = await ctx.get_attached_files_content()
            
            # 合并 project_files 到 additional_context
            additional_context = ctx.additional_context or ""
            if initial_snapshot and initial_snapshot.project_files:
                pf = initial_snapshot.project_files
                if pf not in additional_context:
                    additional_context = (additional_context + "\n" + pf).strip()

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
                additional_context=additional_context,
            )
            
            async for event in agent_gen:
                event_type = event.get("type", "")
                
                if event_type == "step_start":
                    step_count = event.get("step", step_count + 1)
                    yield {
                        "type": "cua_start",
                        "cuaId": f"{cua_id}_step{step_count}",
                        "step": step_count,
                        "title": f"PowerPoint 操作 - 步骤 {step_count}",
                        "nodeId": ctx.node_id,
                    }
                
                elif event_type == "reasoning_delta":
                    yield {
                        "type": "cua_delta",
                        "cuaId": f"{cua_id}_step{step_count}",
                        "reasoning": event.get("content", ""),
                        "kind": event.get("source", "planner"),
                    }
                
                elif event_type == "plan_complete":
                    planner_content = event.get("content", {})
                    current_planner_content = planner_content
                    yield {
                        "type": "planner_complete",
                        "content": {"vlm_plan": planner_content},
                    }
                    
                    # 记录 action 到 RuntimeStateManager
                    if ctx.flow_processor and planner_content:
                        try:
                            action_desc = planner_content.get("Action", "")
                            action_title = planner_content.get("Title", "")
                            ctx.flow_processor.runtime_state.record_node_action(
                                node_id=ctx.node_id,
                                thinking=planner_content.get("Thinking", ""),
                                title=action_title,
                                observation=planner_content.get("Observation", ""),
                                reasoning=planner_content.get("Reasoning", ""),
                                action_type="execute_code",
                                action_params={},
                                action_target=action_desc,
                            )
                        except Exception as e:
                            logger.logger.warning(f"[PPTNodeHandlerV2] Failed to record action: {e}")
                
                elif event_type == "action":
                    yield {
                        "type": "cua_update",
                        "cuaId": f"{cua_id}_step{step_count}",
                        "content": event.get("action", {}),
                        "kind": "actor",
                    }
                
                elif event_type == "tool_call":
                    action_type = event.get("name", "step")
                    action_args = event.get("args", {})
                    action_dict = {"type": action_type, **action_args}
                    action_title = current_planner_content.get("Title") or current_planner_content.get("Action", "Execute step")

                    yield event

                    yield {
                        "type": "cua_end",
                        "cuaId": f"{cua_id}_step{step_count}",
                        "status": "completed",
                        "title": action_title,
                        "action": action_dict,
                    }
                
                elif event_type == "wait_for_execution":
                    logger.logger.info("[PPTNodeHandlerV2] Waiting for execution result")
                    action_title = current_planner_content.get("Title") or current_planner_content.get("Action", "Waiting")
                    
                    actions = current_planner_content.get("Actions") or []
                    action_types = [
                        a.get("action")
                        for a in actions
                        if isinstance(a, dict) and a.get("action")
                    ]
                    step_history.append({
                        "step": step_count,
                        "title": action_title,
                        "execution_status": "pending",
                        "action_types": action_types,
                    })
                    
                    yield NodeCompleteEvent(
                        node_id=ctx.node_id,
                        node_type=ctx.node_type,
                        is_node_completed=False,
                        handler_result={
                            "is_node_completed": False,
                            "waiting_for_execution": True,
                            "step": step_count,
                            "cua_id": cua_id,
                            "planner_content": current_planner_content,
                            "step_history": step_history,
                        },
                        action_summary=action_title,
                    ).to_dict()
                    return
                
                elif event_type == "task_completed":
                    completion_summary = event.get("summary", "")
                    action_title = current_planner_content.get("Title") or completion_summary or "Task completed"
                    
                    if ctx.flow_processor:
                        try:
                            ctx.flow_processor.runtime_state.complete_node_action(
                                node_id=ctx.node_id,
                                status="success",
                                result_observation=completion_summary or "Task completed successfully",
                            )
                        except Exception as e:
                            logger.logger.warning(f"[PPTNodeHandlerV2] Failed to complete action: {e}")
                    
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
                        },
                        action_summary=action_title,
                        node_completion_summary=event.get("summary", "PowerPoint operation completed"),
                    ).to_dict()
                    return
                
                elif event_type == "max_steps_reached":
                    yield NodeCompleteEvent(
                        node_id=ctx.node_id,
                        node_type=ctx.node_type,
                        is_node_completed=True,
                        handler_result={
                            "is_node_completed": True,
                            "Observation": f"Reached maximum steps ({event.get('steps', 10)})",
                        },
                        action_summary="达到最大步数",
                        node_completion_summary="PowerPoint 操作达到最大步数限制",
                    ).to_dict()
                    return
                
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
            error_msg = f"PowerPoint 节点执行失败: {str(e)}"
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
        new_snapshot: Optional[SlideSnapshot],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """处理执行结果回调"""
        logger.logger.info(f"[PPTNodeHandlerV2] 收到执行结果回调")
        
        # 解析执行结果
        # 支持两种层级：
        #   1. execution_result 本身就是 {execution: {...}, snapshot: {...}}（来自 /step）
        #   2. 简化格式：{success, error}，或 snapshot 回调 {status, screenshot, presentation_info, ...}
        execution_data = execution_result.get("execution", {})
        if execution_data:
            success = execution_data.get("success", False)
            # 新 API 的 results 是数组，聚合失败条目
            results = execution_data.get("results", [])
            failed = [r for r in results if not r.get("success", True)]
            error = execution_data.get("error") or ""
            if not error and failed:
                error = "; ".join(
                    r.get("error", "action failed") for r in failed if r.get("error")
                )
            error = error or ""
        else:
            explicit_success = execution_result.get("success")
            if explicit_success is not None:
                success = bool(explicit_success)
            else:
                status_val = str(execution_result.get("status", "")).lower()
                success = (
                    status_val in ("success", "ok")
                    or "screenshot" in execution_result
                    or "presentation_info" in execution_result
                )
            error = execution_result.get("error", "") or ""
        
        # 获取之前的状态
        prev_state = ctx.node_state.get("handler_result", {})
        step_count = prev_state.get("step", 1)
        prev_cua_id = prev_state.get("cua_id", cua_id)
        prev_planner_content = prev_state.get("planner_content", {})
        step_history: List[Dict[str, Any]] = prev_state.get("step_history", [])
        
        # 更新上一步的执行状态
        if step_history:
            step_history[-1]["execution_status"] = "success" if success else "failed"
            if error:
                step_history[-1]["execution_error"] = error[:200]
        
        # 开始新的 CUA
        step_count += 1
        step_cua_id = f"{prev_cua_id}_step{step_count}"
        
        yield {
            "type": "cua_start",
            "cuaId": step_cua_id,
            "step": step_count,
            "title": f"PowerPoint Step {step_count}",
            "nodeId": ctx.node_id,
        }
        
        # 完成上一个 action 的状态更新
        if ctx.flow_processor:
            try:
                ctx.flow_processor.runtime_state.complete_node_action(
                    node_id=ctx.node_id,
                    status="success" if success else "failed",
                    result_observation="Code executed successfully" if success else f"Code execution failed: {error}",
                    error=error if not success else None,
                )
            except Exception as e:
                logger.logger.warning(f"[PPTNodeHandlerV2] Failed to update action status: {e}")
        
        # 重新创建 Agent 继续决策
        node_data = ctx.node_dict.get("data", {})
        user_goal = ctx.query
        node_instruction = node_data.get("instruction", "") or node_data.get("description", "")
        node_model = self._get_node_model(ctx.node_dict)
        planner_model = node_model or ctx.planner_model
        logger.logger.info(
            f"[PPTNodeHandlerV2] 回调继续执行使用模型: {planner_model} "
            f"(node_model={node_model}, ctx.planner_model={ctx.planner_model})"
        )
        
        agent = create_agent(
            planner_model=planner_model,
            api_keys=ctx.planner_api_keys,
            node_id=ctx.node_id,
        )
        
        # 获取 history_md
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
                logger.logger.warning(f"[PPTNodeHandlerV2] 生成 history_md 失败: {e}")
        
        # 获取附件文件内容（异步，包含智能路由判断）
        attached_files_content = ""
        if hasattr(ctx, 'get_attached_files_content'):
            attached_files_content = await ctx.get_attached_files_content()
        
        # 构建上一步执行结果摘要，让 planner 知道发生了什么
        last_exec_output = self._summarize_execution_result(execution_result, success, error)

        # 合并 project_files 到 additional_context
        additional_context = ctx.additional_context or ""
        if new_snapshot and hasattr(new_snapshot, 'project_files') and new_snapshot.project_files:
            pf = new_snapshot.project_files
            if pf not in additional_context:
                additional_context = (additional_context + "\n" + pf).strip()

        # 注入本节点已执行步骤，避免恢复决策时重复同一批动作（例如两次 add_shape_animation）
        agent_history = self._step_history_to_agent_history(
            step_history, prev_planner_content
        )

        context = AgentContext(
            user_goal=user_goal,
            node_instruction=node_instruction,
            current_snapshot=new_snapshot,
            history_md=history_md,
            history=agent_history,
            attached_files_content=attached_files_content,
            attached_images=self._extract_attached_images(ctx),
            additional_context=additional_context,
            last_execution_output=last_exec_output,
        )
        
        step: Optional[AgentStep] = None
        planner_content: Dict[str, Any] = {}
        tool_call_event: Optional[Dict[str, Any]] = None
        
        async for event in agent.step_streaming(context, ctx.log_folder):
            event_type = event.get("type", "")
            
            if event_type == "reasoning_delta":
                yield {
                    "type": "cua_delta",
                    "cuaId": step_cua_id,
                    "reasoning": event.get("content", ""),
                    "kind": event.get("source", "planner"),
                }
            
            elif event_type == "plan_complete":
                planner_content = event.get("content", {})
                yield {
                    "type": "planner_complete",
                    "content": {"vlm_plan": planner_content},
                }
                
                if ctx.flow_processor and planner_content:
                    try:
                        action_desc = planner_content.get("Action", "")
                        action_title = planner_content.get("Title", "")
                        ctx.flow_processor.runtime_state.record_node_action(
                            node_id=ctx.node_id,
                            thinking=planner_content.get("Thinking", ""),
                            title=action_title,
                            observation=planner_content.get("Observation", ""),
                            reasoning=planner_content.get("Reasoning", ""),
                            action_type="execute_code",
                            action_params={},
                            action_target=action_desc,
                        )
                    except Exception as e:
                        logger.logger.warning(f"[PPTNodeHandlerV2] Failed to record action: {e}")
            
            elif event_type == "action":
                yield {
                    "type": "cua_update",
                    "cuaId": step_cua_id,
                    "content": event.get("action", {}),
                    "kind": "actor",
                }
            
            elif event_type == "tool_call":
                tool_call_event = event
                yield event
            
            elif event_type == "step_complete":
                step = event.get("step")
            
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
        
        if not planner_content:
            planner_content = step.planner_output.to_dict()
        
        # 检查是否完成
        if step.is_completed:
            action_title = planner_content.get("Title") or step.planner_output.completion_summary or "Task completed"
            
            if ctx.flow_processor:
                try:
                    ctx.flow_processor.runtime_state.complete_node_action(
                        node_id=ctx.node_id,
                        status="success",
                        result_observation=step.planner_output.completion_summary or "Task completed successfully",
                    )
                except Exception as e:
                    logger.logger.warning(f"[PPTNodeHandlerV2] Failed to complete action: {e}")
            
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
                },
                action_summary=action_title,
                node_completion_summary=step.planner_output.completion_summary or "PowerPoint operation completed",
            ).to_dict()
            return
        
        # tool_call was already emitted by step_streaming (via ToolRegistry or legacy path)
        if tool_call_event:
            action_title = planner_content.get("Title") or planner_content.get("Action", "Execute step")

            yield {
                "type": "cua_end",
                "cuaId": step_cua_id,
                "status": "completed",
                "title": action_title,
                "action": {"type": tool_call_event.get("name", "step"), **tool_call_event.get("args", {})},
            }
            
            actions = planner_content.get("Actions") or []
            action_types = [
                a.get("action")
                for a in actions
                if isinstance(a, dict) and a.get("action")
            ]
            step_history.append({
                "step": step_count,
                "title": action_title,
                "execution_status": "pending",
                "action_types": action_types,
            })
            
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
        cua_id: str,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        通过 local engine 的 /snapshot 接口获取演示文稿快照。

        向前端发送 tool_call {name: "snapshot"}，前端调 POST /api/v1/ppt/snapshot。
        不再通过 PowerShell 脚本获取——直接使用结构化 API，更快更准确。
        """
        step_cua_id = f"{cua_id}_step0_get_snapshot"

        yield {
            "type": "cua_start",
            "cuaId": step_cua_id,
            "step": 0,
            "title": "Reading PowerPoint state",
            "nodeId": ctx.node_id,
        }

        yield {
            "type": "cua_delta",
            "cuaId": step_cua_id,
            "reasoning": "Reading current PowerPoint presentation state via snapshot API...",
            "kind": "planner",
        }

        if ctx.flow_processor:
            try:
                ctx.flow_processor.runtime_state.record_node_action(
                    node_id=ctx.node_id,
                    thinking="Need to read current PowerPoint presentation state before making any changes.",
                    title="Read PowerPoint state",
                    observation="No PowerPoint snapshot available yet",
                    action_type="snapshot",
                    action_params={},
                    action_target="Read PowerPoint presentation state",
                )
            except Exception as e:
                logger.logger.warning(f"[PPTNodeHandlerV2] Failed to record get_snapshot action: {e}")

        snapshot_args = {
            "include_content": True,
            "include_screenshot": True,
            "current_slide_only": True,
        }
        action_dict = {"type": "snapshot", **snapshot_args}

        yield {
            "type": "cua_update",
            "cuaId": step_cua_id,
            "content": action_dict,
            "kind": "actor",
        }

        yield {
            "type": "tool_call",
            "id": f"call_ppt_{ctx.node_id}_get_snapshot",
            "target": "ppt",
            "name": "snapshot",
            "args": snapshot_args,
        }

        yield {
            "type": "cua_end",
            "cuaId": step_cua_id,
            "status": "completed",
            "title": "Reading PowerPoint state",
            "action": action_dict,
        }

        yield NodeCompleteEvent(
            node_id=ctx.node_id,
            node_type=ctx.node_type,
            is_node_completed=False,
            handler_result={
                "is_node_completed": False,
                "waiting_for_execution": True,
                "waiting_for_snapshot": True,
                "step": 0,
                "cua_id": cua_id,
                "planner_content": {
                    "Observation": "No PowerPoint snapshot available yet",
                    "Action": "Read PowerPoint presentation state",
                },
            },
            action_summary="Read PowerPoint presentation state",
        ).to_dict()

    def _get_node_model(self, node_dict: Dict[str, Any]) -> Optional[str]:
        """
        从节点配置中获取模型。

        Args:
            node_dict: 节点字典，包含 data.model 字段

        Returns:
            模型名称，如果未配置则返回 None
        """
        data = node_dict.get("data", {})
        model = data.get("model")

        if not model:
            return None

        # 模型名称映射（统一到实际使用的模型名称）
        model_mapping = {
            # Gemini 系列
            "gemini-3-flash-preview": "gemini-3-flash-preview",
            "gemini-3-pro-preview": "gemini-3-pro-preview",
            "gemini-3.1-pro-preview": "gemini-3.1-pro-preview",
            "gemini-3.1-flash-lite-preview": "gemini-3.1-flash-lite-preview",
            "gemini-2.0-flash": "gemini-2.0-flash",
            "gemini-2.5-flash-preview-04-17": "gemini-2.5-flash-preview-04-17",
            # OpenAI 系列
            "gpt-5.2": "gpt-5.2",
            "openai-computer-use-preview": "gpt-5.2",  # 别名映射
            "gpt-4o": "gpt-4o",
            "gpt-4o-mini": "gpt-4o-mini",
            # Anthropic（与前端 modelConfig 一致，透传官方 model id）
            "claude-opus-4-7": "claude-opus-4-7",
            "claude-opus-4-6": "claude-opus-4-6",
            "claude-sonnet-4-6": "claude-sonnet-4-6",
        }

        mapped_model = model_mapping.get(model, model)
        logger.logger.info(f"[PPTNodeHandlerV2] 节点模型配置: {model} -> {mapped_model}")
        return mapped_model
    
    def _extract_snapshot(self, ctx: V2NodeContext) -> Optional[SlideSnapshot]:
        """
        从请求中提取演示文稿快照
        
        前端请求时可能在以下位置附带快照:
        1. node_state.snapshot (直接是 SlideSnapshot 结构，包含 presentation_info)
        2. node_state.snapshot.ppt_data (嵌套结构)
        3. node_state.ppt_data (直接结构)
        """
        # 尝试从 snapshot 字段提取
        snapshot_data = ctx.node_state.get("snapshot", {})
        
        if snapshot_data:
            # 情况 1: snapshot 直接是 SlideSnapshot 结构 (包含 presentation_info)
            if "presentation_info" in snapshot_data:
                try:
                    return slide_snapshot_from_dict(snapshot_data)
                except Exception as e:
                    logger.logger.warning(f"解析 snapshot (直接结构) 失败: {e}")
            
            # 情况 2: snapshot.ppt_data 嵌套结构
            ppt_data = snapshot_data.get("ppt_data")
            if ppt_data:
                try:
                    return slide_snapshot_from_dict(ppt_data)
                except Exception as e:
                    logger.logger.warning(f"解析 snapshot.ppt_data 失败: {e}")
        
        # 情况 3: 直接从 ppt_data 提取
        ppt_data = ctx.node_state.get("ppt_data")
        if ppt_data:
            try:
                return slide_snapshot_from_dict(ppt_data)
            except Exception as e:
                logger.logger.warning(f"解析 ppt_data 失败: {e}")
        
        logger.logger.info("[PPTNodeHandlerV2] 没有找到演示文稿快照，PowerPoint 可能未打开")
        return None

    @staticmethod
    def _extract_snapshot_from_execution_result(execution_result: Dict[str, Any]) -> Optional[SlideSnapshot]:
        """
        从 execution_result 中提取 snapshot，处理多种嵌套格式。

        前端可能传回以下任一格式：
          A: {"success": true, "data": {"execution": {...}, "snapshot": {...}}}
          B: {"execution": {...}, "snapshot": {...}}
          C: {"snapshot": {...}}
          D: 直接就是 snapshot 结构 {"presentation_info": {...}, ...}
        """
        # 尝试逐层探测
        candidates = []

        # Path A: full API response → data.snapshot
        data_inner = execution_result.get("data")
        if isinstance(data_inner, dict):
            snap = data_inner.get("snapshot")
            if isinstance(snap, dict):
                candidates.append(("data.snapshot", snap))

        # Path B/C: execution_result.snapshot
        snap = execution_result.get("snapshot")
        if isinstance(snap, dict):
            candidates.append(("snapshot", snap))

        # Path D: execution_result itself contains presentation_info
        if "presentation_info" in execution_result:
            candidates.append(("direct", execution_result))

        for label, snap_data in candidates:
            try:
                result = slide_snapshot_from_dict(snap_data)
                if result and result.has_data:
                    logger.logger.info(f"[PPTNodeHandlerV2] snapshot extracted via path: {label}")
                    return result
            except Exception as e:
                logger.logger.warning(f"[PPTNodeHandlerV2] snapshot extraction failed (path={label}): {e}")

        logger.logger.warning(
            f"[PPTNodeHandlerV2] 无法从 execution_result 提取 snapshot, "
            f"keys={list(execution_result.keys())[:10]}"
        )
        return None

    @staticmethod
    def _step_history_to_agent_history(
        step_history: List[Dict[str, Any]],
        last_planner_content: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """
        将 handler 侧 step_history 转为 AgentContext.history，供 Planner 在 prompt 中可见。
        解决：执行回调路径会新建 AgentContext，若不注入历史，模型会重复执行已成功的一批动作。
        """
        rows: List[Dict[str, Any]] = []
        n = len(step_history)
        for idx, sh in enumerate(step_history):
            st = sh.get("execution_status", "")
            if st == "pending":
                continue
            title = sh.get("title", "step")
            types = list(sh.get("action_types") or [])
            if not types and idx == n - 1:
                acts = (last_planner_content or {}).get("Actions") or []
                types = [
                    a.get("action")
                    for a in acts
                    if isinstance(a, dict) and a.get("action")
                ]
            summary = f"{title} ({', '.join(types)})" if types else title
            if st == "success":
                result = "success"
            elif st == "failed":
                err = sh.get("execution_error", "")
                result = f"failed: {err}" if err else "failed"
            else:
                result = str(st)
            rows.append({"action": title, "summary": summary, "result": result})
        return rows

    @staticmethod
    def _summarize_execution_result(
        execution_result: Dict[str, Any],
        success: bool,
        error: str,
    ) -> str:
        """
        将执行结果摘要为文本，供 planner 的 last_execution_output 使用。
        """
        parts = []
        parts.append(f"Execution status: {'SUCCESS' if success else 'FAILED'}")
        if error:
            parts.append(f"Error: {error}")

        # 提取 actions 级别的 results
        exec_data = execution_result.get("execution", {})
        if not exec_data:
            data_inner = execution_result.get("data", {})
            if isinstance(data_inner, dict):
                exec_data = data_inner.get("execution", {})

        results = exec_data.get("results", []) if isinstance(exec_data, dict) else []
        if results:
            parts.append(f"Actions executed: {len(results)}")
            for i, r in enumerate(results[:10]):
                status = "OK" if r.get("success", True) else "FAILED"
                action_name = r.get("action", f"action_{i}")
                detail = f"  [{i+1}] {action_name}: {status}"
                if r.get("error"):
                    detail += f" — {r['error'][:100]}"
                parts.append(detail)
            if success:
                parts.append(
                    "If the node instruction is already satisfied by these successful actions, "
                    "respond with Action=\"stop\" and MilestoneCompleted=true. "
                    "Do NOT emit the same Mode A action list again (e.g. duplicate add_shape_animation)."
                )

        return "\n".join(parts)

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
