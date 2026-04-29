"""
AutoCAD Node Handler - AutoCAD 专用操作节点处理器

处理 AutoCAD 专用操作，包括：
- CAD 图形绘制 (draw_from_json)
- Python COM 代码执行 (execute_python_com)
- 图纸管理 (open, close, new, activate)
- 标准件操作 (list_standard_parts, draw_standard_part)
- 状态和快照获取 (status, snapshot)

节点类型：computer-use-autocad

API 前缀: /api/v1/autocad/v2
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
from useit_studio.ai_run.skills import SkillFileReader

from .core import create_agent, AutoCADAgentContext, AutoCADAgentStep
from .models import (
    AutoCADSnapshot,
    autocad_snapshot_from_dict,
)


logger = LoggerUtils(component_name="AutoCADNodeHandler")


class AutoCADNodeHandlerV2(BaseNodeHandlerV2):
    """
    AutoCAD 节点处理器 V2
    
    支持的节点类型：
    - computer-use-autocad
    """
    
    @classmethod
    def supported_types(cls) -> List[str]:
        return ["computer-use-autocad"]
    
    async def execute(self, ctx: V2NodeContext) -> AsyncGenerator[Dict[str, Any], None]:
        """
        执行 AutoCAD 节点
        """
        logger.logger.info(f"[AutoCADNodeHandler] 开始执行节点: {ctx.node_id}")
        
        cua_id = f"autocad_{uuid.uuid4().hex[:8]}_{ctx.node_id}"
        
        try:
            # 解析节点配置
            node_data = ctx.node_dict.get("data", {})
            user_goal = ctx.query
            node_instruction = node_data.get("instruction", "") or node_data.get("description", "")
            query = node_instruction or user_goal
            
            logger.logger.info(f"[AutoCADNodeHandler] Query: {query[:100] if query else 'Empty'}...")
            
            # 提取初始快照
            initial_snapshot = self._extract_snapshot(ctx)
            
            # 检查是否是执行结果回调
            execution_result = ctx.execution_result or ctx.node_state.get("execution_result")
            handler_result = ctx.node_state.get("handler_result", {})
            waiting_for_execution = handler_result.get("waiting_for_execution", False)
            
            logger.logger.info(f"[AutoCADNodeHandler] execution_result: {execution_result is not None}, waiting_for_execution: {waiting_for_execution}")
            
            # 如果有 execution_result，从中提取 snapshot（优先于 initial_snapshot，因为它是最新的）
            if execution_result:
                extracted_snapshot = self._extract_snapshot_from_execution_result(execution_result)
                if extracted_snapshot:
                    initial_snapshot = extracted_snapshot
                    logger.logger.info(f"[AutoCADNodeHandler] 从执行结果提取 snapshot 成功, has_data={initial_snapshot.has_data}, running={initial_snapshot.status.running}")
            
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
            
            # 如果没有 snapshot，先发送获取状态的请求
            if not initial_snapshot:
                logger.logger.info("[AutoCADNodeHandler] 首步无 snapshot，发送获取状态的请求")
                async for event in self._emit_get_status_request(ctx, cua_id):
                    yield event
                return
            
            # 创建并运行 Agent
            agent = create_agent(
                planner_model=ctx.planner_model,
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
                    logger.logger.warning(f"[AutoCADNodeHandler] 生成 history_md 失败: {e}")
            
            # 获取附件文件内容
            attached_files_content = ""
            if hasattr(ctx, 'get_attached_files_content'):
                attached_files_content = await ctx.get_attached_files_content()
            
            # ===== Skills：加载 SKILL.md + 恢复已读文件 =====
            skills_prompt = self._build_skills_prompt(ctx)
            skill_contents = getattr(ctx, 'skill_contents', None) or {}
            skill_reader = SkillFileReader.from_state(ctx.node_state, skill_contents)
            
            # 运行 Agent 决策循环
            agent_gen = agent.run(
                user_goal=user_goal,
                node_instruction=node_instruction,
                initial_snapshot=initial_snapshot,
                max_steps=60,
                log_dir=ctx.log_folder,
                history_md=history_md,
                attached_files_content=attached_files_content,
                additional_context=ctx.additional_context or "",
                skills_prompt=skills_prompt,
                skill_reader=skill_reader,
            )
            
            async for event in agent_gen:
                event_type = event.get("type", "")
                
                if event_type == "step_start":
                    step_count = event.get("step", step_count + 1)
                    yield {
                        "type": "cua_start",
                        "cuaId": f"{cua_id}_step{step_count}",
                        "step": step_count,
                        "title": f"AutoCAD 操作 - 步骤 {step_count}",
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
                            action_name = planner_content.get("Action", "")
                            action_title = planner_content.get("Title", "")
                            ctx.flow_processor.runtime_state.record_node_action(
                                node_id=ctx.node_id,
                                thinking=planner_content.get("Thinking", ""),
                                title=action_title,
                                observation="",
                                reasoning="",
                                action_type=action_name,
                                action_params=planner_content.get("Args", {}),
                                action_target=action_name,
                            )
                        except Exception as e:
                            logger.logger.warning(f"[AutoCADNodeHandler] Failed to record action: {e}")
                
                elif event_type == "action":
                    yield {
                        "type": "cua_update",
                        "cuaId": f"{cua_id}_step{step_count}",
                        "content": event.get("action", {}),
                        "kind": "actor",
                    }
                
                elif event_type == "tool_call":
                    action_name = event.get("name", "")
                    action_args = event.get("args", {})
                    action_dict = {"type": action_name, **action_args}
                    action_title = current_planner_content.get("Title") or current_planner_content.get("Action", "Execute action")
                    
                    yield event
                    
                    yield {
                        "type": "cua_end",
                        "cuaId": f"{cua_id}_step{step_count}",
                        "status": "completed",
                        "title": action_title,
                        "action": action_dict,
                    }
                
                elif event_type == "wait_for_execution":
                    logger.logger.info("[AutoCADNodeHandler] Waiting for execution result")
                    action_title = current_planner_content.get("Title") or current_planner_content.get("Action", "Waiting")
                    
                    step_history.append({
                        "step": step_count,
                        "title": action_title,
                        "execution_status": "pending",
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
                            **skill_reader.get_state(),
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
                            logger.logger.warning(f"[AutoCADNodeHandler] Failed to complete action: {e}")
                    
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
                        node_completion_summary=event.get("summary", "AutoCAD operation completed"),
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
                        node_completion_summary="AutoCAD 操作达到最大步数限制",
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
            error_msg = f"AutoCAD 节点执行失败: {str(e)}"
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
        new_snapshot: Optional[AutoCADSnapshot],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """处理执行结果回调"""
        logger.logger.info(f"[AutoCADNodeHandler] 收到执行结果回调")
        
        # 解析执行结果中的错误信息
        execution_data = execution_result.get("execution", {})
        if execution_data:
            success = execution_data.get("success", False)
            error = execution_data.get("error", "") or ""
        else:
            success = execution_result.get("success", True)  # 默认成功，除非明确标记失败
            error = execution_result.get("error", "") or ""
        
        # 检查 status 字段
        if execution_result.get("status") == "error":
            success = False
            if not error:
                error = execution_result.get("error", "Unknown error")
        
        # 尝试从 execution_result 中提取 snapshot（仅在成功时）
        if success:
            extracted_snapshot = self._extract_snapshot_from_execution_result(execution_result)
            if extracted_snapshot:
                new_snapshot = extracted_snapshot
                logger.logger.info(f"[AutoCADNodeHandler] 从执行结果提取 snapshot: has_data={new_snapshot.has_data}")
        else:
            logger.logger.info(f"[AutoCADNodeHandler] 执行失败，错误信息: {error[:200] if error else 'Unknown'}")
        
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
            "title": f"AutoCAD Step {step_count}",
            "nodeId": ctx.node_id,
        }
        
        # 完成上一个 action 的状态更新
        if ctx.flow_processor:
            try:
                ctx.flow_processor.runtime_state.complete_node_action(
                    node_id=ctx.node_id,
                    status="success" if success else "failed",
                    result_observation="Action executed successfully" if success else f"Action failed: {error}",
                    error=error if not success else None,
                )
            except Exception as e:
                logger.logger.warning(f"[AutoCADNodeHandler] Failed to update action status: {e}")
        
        # 重新创建 Agent 继续决策
        node_data = ctx.node_dict.get("data", {})
        user_goal = ctx.query
        node_instruction = node_data.get("instruction", "") or node_data.get("description", "")
        
        agent = create_agent(
            planner_model=ctx.planner_model,
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
                logger.logger.warning(f"[AutoCADNodeHandler] 生成 history_md 失败: {e}")
        
        # 获取附件文件内容
        attached_files_content = ""
        if hasattr(ctx, 'get_attached_files_content'):
            attached_files_content = await ctx.get_attached_files_content()
        
        # ===== Skills：加载 SKILL.md + 恢复已读文件 =====
        skills_prompt = self._build_skills_prompt(ctx)
        skill_contents = getattr(ctx, 'skill_contents', None) or {}
        skill_reader = SkillFileReader.from_state(ctx.node_state, skill_contents)
        
        # 决策循环：单步执行，read_file 时自动继续下一步
        MAX_LOCAL_STEPS = 10
        current_execution_result = execution_result
        current_snapshot = new_snapshot

        for _local_iter in range(MAX_LOCAL_STEPS):
            context = AutoCADAgentContext(
                user_goal=user_goal,
                node_instruction=node_instruction,
                current_snapshot=current_snapshot,
                history_md=history_md,
                attached_files_content=attached_files_content,
                additional_context=ctx.additional_context or "",
                skills_prompt=skills_prompt,
                skill_reader=skill_reader,
                last_execution_result=current_execution_result,
            )

            step: Optional[AutoCADAgentStep] = None
            planner_content: Dict[str, Any] = {}
            local_action_result = None

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
                            ctx.flow_processor.runtime_state.record_node_action(
                                node_id=ctx.node_id,
                                thinking=planner_content.get("Thinking", ""),
                                title=planner_content.get("Title", ""),
                                observation="",
                                reasoning="",
                                action_type=planner_content.get("Action", ""),
                                action_params=planner_content.get("Args", {}),
                                action_target=planner_content.get("Action", ""),
                            )
                        except Exception as e:
                            logger.logger.warning(f"[AutoCADNodeHandler] Failed to record action: {e}")

                elif event_type == "action":
                    yield {
                        "type": "cua_update",
                        "cuaId": step_cua_id,
                        "content": event.get("action", {}),
                        "kind": "actor",
                    }

                elif event_type == "step_complete":
                    step = event.get("step")
                    local_action_result = event.get("local_action_result")

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

            # Local action (read_file / run_skill_script) → loop back
            if local_action_result is not None:
                action_name = planner_content.get("Action", "local_action")
                action_title = planner_content.get("Title") or action_name
                logger.logger.info(
                    f"[AutoCADNodeHandler] {action_name} handled locally, continuing loop "
                    f"(iter={_local_iter}, status={local_action_result.get('status')})"
                )
                yield {
                    "type": "cua_end",
                    "cuaId": step_cua_id,
                    "status": "completed",
                    "title": action_title,
                    "action": {"type": action_name},
                }
                if ctx.flow_processor:
                    try:
                        ctx.flow_processor.runtime_state.complete_node_action(
                            node_id=ctx.node_id,
                            status="success",
                            result_observation=f"{action_name}: {local_action_result.get('status')}",
                        )
                    except Exception:
                        pass
                current_execution_result = local_action_result
                step_count += 1
                step_cua_id = f"{prev_cua_id}_step{step_count}"
                yield {
                    "type": "cua_start",
                    "cuaId": step_cua_id,
                    "step": step_count,
                    "title": f"AutoCAD Step {step_count}",
                    "nodeId": ctx.node_id,
                }
                continue

            # Normal exit from loop
            break

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
                    logger.logger.warning(f"[AutoCADNodeHandler] Failed to complete action: {e}")
            
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
                    "Observation": "Task completed successfully",
                },
                action_summary=action_title,
                node_completion_summary=step.planner_output.completion_summary or "AutoCAD operation completed",
            ).to_dict()
            return
        
        # 需要继续执行
        if step.action:
            # Guard: local-only actions must never be sent to the external engine
            if step.action.name in ("read_file", "run_skill_script"):
                logger.logger.error(
                    f"[AutoCADNodeHandler] {step.action.name} leaked past local loop "
                    f"(MAX_LOCAL_STEPS={MAX_LOCAL_STEPS} exhausted). Returning error."
                )
                yield {
                    "type": "cua_end",
                    "cuaId": step_cua_id,
                    "status": "error",
                    "error": f"Too many consecutive local actions ({step.action.name})",
                }
                yield ErrorEvent(
                    message=f"Agent stuck in {step.action.name} loop. Check skill configuration.",
                    node_id=ctx.node_id,
                ).to_dict()
                return

            action_dict = step.action.to_dict()
            action_title = planner_content.get("Title") or planner_content.get("Action", "Execute action")
            
            yield {
                "type": "tool_call",
                "id": f"call_autocad_{step_cua_id}",
                "target": "autocad",
                "name": step.action.name,
                "args": step.action.args,
            }
            
            yield {
                "type": "cua_end",
                "cuaId": step_cua_id,
                "status": "completed",
                "title": action_title,
                "action": action_dict,
            }
            
            step_history.append({
                "step": step_count,
                "title": action_title,
                "execution_status": "pending",
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
                    **skill_reader.get_state(),
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
    
    def _build_skills_prompt(self, ctx: V2NodeContext) -> str:
        """
        构建 base skills prompt（仅 SKILL.md 内容）。
        
        已读文件的累积内容由 SkillFileReader 在 AutoCADAgentContext 中
        通过 _get_full_skills_prompt() 动态提供，不在此处拼接。
        """
        if not hasattr(ctx, 'get_skills_prompt'):
            logger.logger.info("[AutoCADNodeHandler] Skills feature not available")
            return ""

        skills_prompt_base = ctx.get_skills_prompt()
        if not skills_prompt_base:
            logger.logger.info("[AutoCADNodeHandler] No skills configured for this node")
            return ""

        skill_names = ", ".join(ctx.skills) if ctx.skills else "unknown"
        logger.logger.info(f"[AutoCADNodeHandler] Skills loaded: {skill_names} ({len(skills_prompt_base)} chars)")
        return skills_prompt_base

    async def _emit_get_status_request(
        self, 
        ctx: V2NodeContext, 
        cua_id: str
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """发送获取 AutoCAD 状态的请求"""
        step_cua_id = f"{cua_id}_step0_get_status"
        
        yield {
            "type": "cua_start",
            "cuaId": step_cua_id,
            "step": 0,
            "title": "Reading AutoCAD state",
            "nodeId": ctx.node_id,
        }
        
        yield {
            "type": "cua_delta",
            "cuaId": step_cua_id,
            "reasoning": "Reading current AutoCAD state and drawing content...",
            "kind": "planner",
        }
        
        # 记录 action 到 RuntimeStateManager
        if ctx.flow_processor:
            try:
                ctx.flow_processor.runtime_state.record_node_action(
                    node_id=ctx.node_id,
                    thinking="Need to read current AutoCAD state before making any changes.",
                    title="Read AutoCAD state",
                    observation="No AutoCAD snapshot available yet",
                    action_type="snapshot",
                    action_params={"include_content": True, "include_screenshot": True},
                    action_target="Read AutoCAD drawing state",
                )
            except Exception as e:
                logger.logger.warning(f"[AutoCADNodeHandler] Failed to record get_status action: {e}")
        
        # 发送 snapshot 请求获取当前状态
        action_dict = {
            "type": "snapshot",
            "include_content": True,
            "include_screenshot": True,
        }
        
        yield {
            "type": "cua_update",
            "cuaId": step_cua_id,
            "content": action_dict,
            "kind": "actor",
        }
        
        yield {
            "type": "tool_call",
            "id": f"call_autocad_{ctx.node_id}_get_snapshot",
            "target": "autocad",
            "name": "snapshot",
            "args": {
                "include_content": True,
                "include_screenshot": True,
            },
        }
        
        yield {
            "type": "cua_end",
            "cuaId": step_cua_id,
            "status": "completed",
            "title": "Reading AutoCAD state",
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
                    "Observation": "No AutoCAD snapshot available yet",
                    "Action": "Read AutoCAD drawing state",
                },
            },
            action_summary="Read AutoCAD drawing state",
        ).to_dict()
    
    def _extract_snapshot_from_execution_result(self, execution_result: Dict[str, Any]) -> Optional[AutoCADSnapshot]:
        """
        从执行结果中提取 AutoCADSnapshot
        
        支持两种数据格式：
        1. snapshot API 返回: {status, document_info, content, screenshot}
        2. status API 返回: {running, has_document, document_count, documents, document_info, status}
        
        注意: 如果执行结果包含错误，返回 None，错误信息由调用方单独处理
        """
        from .snapshot import AutoCADStatus, DocumentInfo, AutoCADSnapshot
        
        try:
            # 检查是否是错误响应，如果是则返回 None
            error_msg = execution_result.get("error") or ""
            if error_msg:
                logger.logger.info(f"[AutoCADNodeHandler] 执行结果包含错误，不解析 snapshot: {error_msg[:100]}")
                return None
            if execution_result.get("success") is False:
                logger.logger.info(f"[AutoCADNodeHandler] 执行结果 success=false，不解析 snapshot")
                return None
            if execution_result.get("status") == "error":
                logger.logger.info(f"[AutoCADNodeHandler] 执行结果 status=error，不解析 snapshot")
                return None
            
            # 尝试从 snapshot 字段提取（snapshot API 返回格式）
            snapshot_data = execution_result.get("snapshot") or execution_result.get("data")
            if snapshot_data:
                # 如果 snapshot_data 本身包含 status 字典，说明是 snapshot API 格式
                if isinstance(snapshot_data.get("status"), dict):
                    return autocad_snapshot_from_dict(snapshot_data)
            
            # 尝试从 status API 返回格式提取
            # status API 返回: {running, has_document, document_count, documents, document_info, status, error}
            if "running" in execution_result:
                running = execution_result.get("running", False)
                documents = execution_result.get("documents", [])
                
                # 构建 AutoCADStatus
                status = AutoCADStatus(
                    running=running,
                    version="",
                    documents=documents,
                )
                
                # 提取 document_info
                document_info = None
                doc_info_data = execution_result.get("document_info")
                if doc_info_data:
                    document_info = DocumentInfo.from_dict(doc_info_data)
                elif documents and len(documents) > 0:
                    # 从 documents 列表中提取当前文档信息
                    current_doc = documents[0]  # 取第一个文档
                    document_info = DocumentInfo(
                        name=current_doc.get("name", "Unknown"),
                        path=current_doc.get("path"),
                        bounds=None,
                    )
                
                snapshot = AutoCADSnapshot(
                    status=status,
                    document_info=document_info,
                    content=None,  # status API 不返回 content
                    _screenshot=execution_result.get("screenshot"),
                )
                
                logger.logger.info(
                    f"[AutoCADNodeHandler] 从 status 结果构建 snapshot: "
                    f"running={running}, has_document={execution_result.get('has_document')}, "
                    f"document_count={execution_result.get('document_count')}"
                )
                return snapshot
            
            # 尝试直接作为 snapshot 格式解析
            if execution_result:
                return autocad_snapshot_from_dict(execution_result)
                
        except Exception as e:
            logger.logger.warning(f"[AutoCADNodeHandler] 从执行结果提取 snapshot 失败: {e}")
        
        return None

    def _extract_snapshot(self, ctx: V2NodeContext) -> Optional[AutoCADSnapshot]:
        """
        从请求中提取图纸快照
        
        前端请求时可能在以下位置附带快照:
        1. node_state.snapshot (直接是 AutoCADSnapshot 结构)
        2. node_state.snapshot.autocad_data (嵌套结构)
        3. node_state.autocad_data (直接结构)
        4. node_state.snapshot.data (API 返回格式)
        """
        # 尝试从 snapshot 字段提取
        snapshot_data = ctx.node_state.get("snapshot", {})
        
        if snapshot_data:
            # 情况 1: snapshot 直接是 AutoCADSnapshot 结构 (包含 status)
            if "status" in snapshot_data or "document_info" in snapshot_data:
                try:
                    return autocad_snapshot_from_dict(snapshot_data)
                except Exception as e:
                    logger.logger.warning(f"解析 snapshot (直接结构) 失败: {e}")
            
            # 情况 2: snapshot.autocad_data 嵌套结构
            autocad_data = snapshot_data.get("autocad_data")
            if autocad_data:
                try:
                    return autocad_snapshot_from_dict(autocad_data)
                except Exception as e:
                    logger.logger.warning(f"解析 snapshot.autocad_data 失败: {e}")
            
            # 情况 4: snapshot.data (API 返回格式)
            data = snapshot_data.get("data")
            if data:
                try:
                    return autocad_snapshot_from_dict({"data": data})
                except Exception as e:
                    logger.logger.warning(f"解析 snapshot.data 失败: {e}")
        
        # 情况 3: 直接从 autocad_data 提取
        autocad_data = ctx.node_state.get("autocad_data")
        if autocad_data:
            try:
                return autocad_snapshot_from_dict(autocad_data)
            except Exception as e:
                logger.logger.warning(f"解析 autocad_data 失败: {e}")
        
        logger.logger.info("[AutoCADNodeHandler] 没有找到图纸快照，AutoCAD 可能未运行")
        return None


# ==================== 兼容旧接口 ====================

async def handle_node_streaming(**kwargs) -> AsyncGenerator[Dict[str, Any], None]:
    """
    AutoCAD 节点处理主函数 - 兼容旧接口
    
    这个函数提供向后兼容性，内部使用新的 V2 Handler。
    """
    logger.logger.info("[AutoCADHandler] Using V2 handler")
    
    # 发送状态提示
    yield {
        "type": "status",
        "content": "Using AutoCAD V2 handler"
    }
    
    # 尝试使用 V2 handler
    try:
        from useit_studio.ai_run.node_handler.base_v2 import NodeContext as V2NodeContext
        
        # 构造 V2NodeContext
        ctx = V2NodeContext(
            node_id=kwargs.get("node_id", ""),
            node_type=kwargs.get("node_type", "computer-use-autocad"),
            node_dict=kwargs.get("node_dict", {}),
            query=kwargs.get("query", ""),
            planner_model=kwargs.get("planner_model", "gpt-4o-mini"),
            planner_api_keys=kwargs.get("planner_api_keys", {}),
            node_state=kwargs.get("node_state", {}),
            execution_result=kwargs.get("execution_result"),
            flow_processor=kwargs.get("flow_processor"),
            log_folder=kwargs.get("log_folder", ""),
            additional_context=kwargs.get("additional_context", ""),
        )
        
        handler = AutoCADNodeHandlerV2()
        async for event in handler.execute(ctx):
            yield event
            
    except Exception as e:
        logger.logger.error(f"[AutoCADHandler] V2 handler failed: {e}", exc_info=True)
        yield {
            "type": "error",
            "content": f"AutoCAD handler error: {str(e)}"
        }
