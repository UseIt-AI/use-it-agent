"""
Excel Node Handler V2 - 纯桥接层

职责：
1. 实现 BaseNodeHandlerV2 接口
2. 从请求中提取初始快照
3. 运行 ExcelAgent 决策循环
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
from useit_studio.ai_run.skills import SkillFileReader

from .core import create_agent
from .models import (
    SheetSnapshot,
    sheet_snapshot_from_dict,
    AgentContext,
    AgentStep,
)


logger = LoggerUtils(component_name="ExcelNodeHandlerV2")


class ExcelNodeHandlerV2(BaseNodeHandlerV2):
    """
    Excel 节点处理器 V2 - 纯桥接层
    
    支持的节点类型：
    - computer-use-excel
    """
    
    @classmethod
    def supported_types(cls) -> List[str]:
        return ["computer-use-excel"]
    
    async def execute(self, ctx: V2NodeContext) -> AsyncGenerator[Dict[str, Any], None]:
        """
        执行 Excel 节点
        """
        logger.logger.info(f"[ExcelNodeHandlerV2] 开始执行节点: {ctx.node_id}")
        
        cua_id = f"excel_{uuid.uuid4().hex[:8]}_{ctx.node_id}"
        
        try:
            # 解析节点配置
            node_data = ctx.node_dict.get("data", {})
            user_goal = ctx.query
            node_instruction = node_data.get("instruction", "") or node_data.get("description", "")
            query = node_instruction or user_goal
            
            logger.logger.info(f"[ExcelNodeHandlerV2] Query: {query[:100] if query else 'Empty'}...")
            
            # 提取初始快照
            initial_snapshot = self._extract_snapshot(ctx)
            
            # 检查是否是执行结果回调
            execution_result = ctx.execution_result or ctx.node_state.get("execution_result")
            handler_result = ctx.node_state.get("handler_result", {})
            waiting_for_execution = handler_result.get("waiting_for_execution", False)
            
            logger.logger.info(f"[ExcelNodeHandlerV2] execution_result: {execution_result is not None}, waiting_for_execution: {waiting_for_execution}")
            
            # 如果有 execution_result，从中提取 snapshot
            if execution_result and not initial_snapshot:
                snapshot_data = execution_result.get("snapshot")
                if snapshot_data:
                    try:
                        initial_snapshot = sheet_snapshot_from_dict(snapshot_data)
                        logger.logger.info(f"[ExcelNodeHandlerV2] snapshot 提取成功")
                    except Exception as e:
                        logger.logger.warning(f"[ExcelNodeHandlerV2] 解析 snapshot 失败: {e}")
            
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
                logger.logger.info("[ExcelNodeHandlerV2] 首步无 snapshot，发送获取状态的代码")
                async for event in self._emit_get_snapshot_request(ctx, cua_id):
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
                    logger.logger.warning(f"[ExcelNodeHandlerV2] 生成 history_md 失败: {e}")
            
            # 获取附件文件内容（异步，包含智能路由判断）
            attached_files_content = ""
            if hasattr(ctx, 'get_attached_files_content'):
                attached_files_content = await ctx.get_attached_files_content()

            # ===== SkillFileReader：恢复已读文件状态 =====
            skill_contents = getattr(ctx, 'skill_contents', None) or {}
            reader = SkillFileReader.from_state(ctx.node_state, skill_contents)

            # ===== 获取完整的 Skills Prompt（SKILL.md + 已读文件）=====
            skills_prompt = ""
            if hasattr(ctx, 'get_skills_prompt'):
                skills_prompt_base = ctx.get_skills_prompt()

                if skills_prompt_base:
                    # 有外部 skills - 使用外部 skills（默认参考按需加载）
                    if reader.accumulated_content:
                        skills_prompt = skills_prompt_base + reader.accumulated_content_header + reader.accumulated_content
                        skill_names = ", ".join(ctx.skills) if ctx.skills else "unknown"
                        logger.logger.info(
                            f"[ExcelNodeHandlerV2] ✓ Skills prompt assembled:\n"
                            f"  - Skills: {skill_names}\n"
                            f"  - SKILL.md: {len(skills_prompt_base)} chars\n"
                            f"  - Previously read: {len(reader.accumulated_content)} chars ({len(reader.read_files_list)} files)\n"
                            f"  - Default reference: available via read_default_reference action"
                        )
                    else:
                        skills_prompt = skills_prompt_base
                        skill_names = ", ".join(ctx.skills) if ctx.skills else "unknown"
                        logger.logger.info(
                            f"[ExcelNodeHandlerV2] ✓ Skills loaded: {skill_names}\n"
                            f"  (SKILL.md content will be added to prompt)\n"
                            f"  (Default reference available via read_default_reference action)"
                        )
                else:
                    # 没有外部 skills - 自动注入默认参考
                    from .prompts import DEFALUT_SKILL_REFERENCE_PROMPT

                    skills_prompt = DEFALUT_SKILL_REFERENCE_PROMPT
                    if reader.accumulated_content:
                        skills_prompt += reader.accumulated_content_header + reader.accumulated_content

                    logger.logger.info(
                        f"[ExcelNodeHandlerV2] ✓ Auto-injected default Excel COM reference\n"
                        f"  - No external skills configured\n"
                        f"  - Default reference: {len(DEFALUT_SKILL_REFERENCE_PROMPT)} chars\n"
                        f"  - Previously read: {len(reader.accumulated_content)} chars ({len(reader.read_files_list)} files)"
                    )
            else:
                logger.logger.info("[ExcelNodeHandlerV2] Skills feature not available")

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
                skills_prompt=skills_prompt,
            )
            
            async for event in agent_gen:
                event_type = event.get("type", "")
                
                if event_type == "step_start":
                    step_count = event.get("step", step_count + 1)
                    yield {
                        "type": "cua_start",
                        "cuaId": f"{cua_id}_step{step_count}",
                        "step": step_count,
                        "title": f"Excel 操作 - 步骤 {step_count}",
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
                            logger.logger.warning(f"[ExcelNodeHandlerV2] Failed to record action: {e}")
                
                elif event_type == "action":
                    yield {
                        "type": "cua_update",
                        "cuaId": f"{cua_id}_step{step_count}",
                        "content": event.get("action", {}),
                        "kind": "actor",
                    }
                
                elif event_type == "tool_call":
                    action_type = event.get("name", "execute_code")
                    action_args = event.get("args", {})

                    # ===== 处理 read_default_reference action =====
                    if action_type == "read_default_reference":
                        async for read_event in self._handle_read_default_reference(
                            ctx, cua_id, reader
                        ):
                            yield read_event
                        return  # 暂停，等待下次调用

                    # ===== 处理 read_file action =====
                    elif action_type == "read_file":
                        async for read_event in self._handle_read_file(
                            ctx, action_args, cua_id, reader
                        ):
                            yield read_event
                        return  # 暂停，等待下次调用

                    # ===== 处理 execute_script action =====
                    elif action_type == "execute_script":
                        async for script_event in self._handle_execute_script(
                            ctx, action_args, cua_id, current_planner_content, step_count, reader
                        ):
                            yield script_event
                        # execute_script 需要等待执行结果，继续往下走

                    # ===== 原有的 execute_code 处理 =====
                    action_dict = {"type": action_type, **action_args}
                    action_title = current_planner_content.get("Title") or current_planner_content.get("Action", "Execute code")

                    # 只有 execute_code 才需要 yield tool_call（其他 action 已经在各自的 handler 中处理）
                    if action_type == "execute_code":
                        yield event

                        yield {
                            "type": "cua_end",
                            "cuaId": f"{cua_id}_step{step_count}",
                            "status": "completed",
                            "title": action_title,
                            "action": action_dict,
                        }
                
                elif event_type == "wait_for_execution":
                    logger.logger.info("[ExcelNodeHandlerV2] Waiting for execution result")
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
                            **reader.get_state(),  # 携带已读文件状态
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
                            logger.logger.warning(f"[ExcelNodeHandlerV2] Failed to complete action: {e}")
                    
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
                        node_completion_summary=event.get("summary", "Excel operation completed"),
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
                        node_completion_summary="Excel 操作达到最大步数限制",
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
            error_msg = f"Excel 节点执行失败: {str(e)}"
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
        new_snapshot: Optional[SheetSnapshot],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """处理执行结果回调"""
        logger.logger.info(f"[ExcelNodeHandlerV2] 收到执行结果回调")
        
        # 解析执行结果
        execution_data = execution_result.get("execution", {})
        if execution_data:
            success = execution_data.get("success", False)
            output = execution_data.get("output", "") or ""
            error = execution_data.get("error", "") or ""
        else:
            success = execution_result.get("success", False)
            output = execution_result.get("output", "") or ""
            error = execution_result.get("error", "") or ""

        logger.logger.info(f"[ExcelNodeHandlerV2] execution output length: {len(output)}, success: {success}")
        
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
            "title": f"Excel Step {step_count}",
            "nodeId": ctx.node_id,
        }
        
        # 完成上一个 action 的状态更新
        # Include actual output in result_observation for history_md
        if success:
            observation = f"Code executed successfully. Output: {output[:500]}" if output else "Code executed successfully"
        else:
            observation = f"Code execution failed: {error}"

        if ctx.flow_processor:
            try:
                ctx.flow_processor.runtime_state.complete_node_action(
                    node_id=ctx.node_id,
                    status="success" if success else "failed",
                    result_observation=observation,
                    error=error if not success else None,
                )
            except Exception as e:
                logger.logger.warning(f"[ExcelNodeHandlerV2] Failed to update action status: {e}")
        
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
                logger.logger.warning(f"[ExcelNodeHandlerV2] 生成 history_md 失败: {e}")
        
        # 获取附件文件内容（异步，包含智能路由判断）
        attached_files_content = ""
        if hasattr(ctx, 'get_attached_files_content'):
            attached_files_content = await ctx.get_attached_files_content()

        # ===== SkillFileReader：恢复已读文件状态 =====
        skill_contents = getattr(ctx, 'skill_contents', None) or {}
        reader = SkillFileReader.from_state(ctx.node_state, skill_contents)

        # ===== 获取完整的 Skills Prompt（SKILL.md + 已读文件）=====
        skills_prompt = ""
        if hasattr(ctx, 'get_skills_prompt'):
            skills_prompt_base = ctx.get_skills_prompt()

            if skills_prompt_base:
                # 有外部 skills
                if reader.accumulated_content:
                    skills_prompt = skills_prompt_base + reader.accumulated_content_header + reader.accumulated_content
                else:
                    skills_prompt = skills_prompt_base
            else:
                # 没有外部 skills - 自动注入默认参考
                from .prompts import DEFALUT_SKILL_REFERENCE_PROMPT

                skills_prompt = DEFALUT_SKILL_REFERENCE_PROMPT
                if reader.accumulated_content:
                    skills_prompt += reader.accumulated_content_header + reader.accumulated_content

        # 继续决策循环（单步）
        context = AgentContext(
            user_goal=user_goal,
            node_instruction=node_instruction,
            current_snapshot=new_snapshot,
            history_md=history_md,
            attached_files_content=attached_files_content,
            attached_images=self._extract_attached_images(ctx),
            additional_context=ctx.additional_context or "",
            skills_prompt=skills_prompt,
            last_execution_output=output,
        )
        
        step: Optional[AgentStep] = None
        planner_content: Dict[str, Any] = {}
        
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
                        logger.logger.warning(f"[ExcelNodeHandlerV2] Failed to record action: {e}")
            
            elif event_type == "action":
                yield {
                    "type": "cua_update",
                    "cuaId": step_cua_id,
                    "content": event.get("action", {}),
                    "kind": "actor",
                }
            
            elif event_type == "tool_call":
                # step_streaming 现在也会为 skill-based actions 生成 tool_call
                tc_name = event.get("name", "")
                tc_args = event.get("args", {})
                
                if tc_name == "execute_script":
                    async for script_event in self._handle_execute_script(
                        ctx, tc_args, prev_cua_id, planner_content, step_count, reader
                    ):
                        yield script_event
                elif tc_name == "read_file":
                    async for read_event in self._handle_read_file(
                        ctx, tc_args, prev_cua_id, reader
                    ):
                        yield read_event
                    return
                elif tc_name == "read_default_reference":
                    async for read_event in self._handle_read_default_reference(
                        ctx, prev_cua_id, reader
                    ):
                        yield read_event
                    return
            
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
                    logger.logger.warning(f"[ExcelNodeHandlerV2] Failed to complete action: {e}")
            
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
                node_completion_summary=step.planner_output.completion_summary or "Excel operation completed",
            ).to_dict()
            return
        
        # 需要继续执行
        planner_action = planner_content.get("Action", "")
        
        # Skill-based action（execute_script）已在 tool_call 事件中通过 _handle_execute_script 处理
        # 这里只需发送 wait 事件
        if planner_action == "execute_script":
            action_title = planner_content.get("Title") or f"Execute {planner_content.get('ScriptPath', 'script')}"
            
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
                    **reader.get_state(),
                },
                action_summary=action_title,
            ).to_dict()
        elif step.action and step.action.code:
            action_dict = step.action.to_dict()
            action_title = planner_content.get("Title") or planner_content.get("Action", "Execute code")
            
            yield {
                "type": "tool_call",
                "id": f"call_excel_{step_cua_id}",
                "target": "excel",
                "name": action_dict.get("type", "execute_code"),
                "args": {k: v for k, v in action_dict.items() if k != "type"},
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
                    **reader.get_state(),  # 携带已读文件状态
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
        cua_id: str
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """发送获取 Excel 工作表快照的请求"""
        step_cua_id = f"{cua_id}_step0_get_snapshot"
        
        yield {
            "type": "cua_start",
            "cuaId": step_cua_id,
            "step": 0,
            "title": "Reading Excel state",
            "nodeId": ctx.node_id,
        }
        
        yield {
            "type": "cua_delta",
            "cuaId": step_cua_id,
            "reasoning": "Reading current Excel workbook state...",
            "kind": "planner",
        }
        
        # 记录 action 到 RuntimeStateManager（用于 milestone_history.md 生成）
        if ctx.flow_processor:
            try:
                ctx.flow_processor.runtime_state.record_node_action(
                    node_id=ctx.node_id,
                    thinking="Need to read current Excel workbook state before making any changes.",
                    title="Read Excel state",
                    observation="No Excel workbook snapshot available yet",
                    action_type="execute_code",
                    action_params={},
                    action_target="Read Excel workbook state",
                )
            except Exception as e:
                from useit_studio.ai_run.utils.logger_utils import LoggerUtils
                logger = LoggerUtils(component_name="ExcelNodeHandlerV2")
                logger.logger.warning(f"[ExcelNodeHandlerV2] Failed to record get_snapshot action: {e}")
        
        get_snapshot_code = '''try {
    # Try to get existing Excel instance
    try {
        $excel = [System.Runtime.InteropServices.Marshal]::GetActiveObject("Excel.Application")
        Write-Host "Connected to existing Excel instance."
    } catch {
        Write-Host "Excel is not running. No workbook to inspect."
        exit 0
    }
    
    # Check if there's an active workbook
    if ($excel.Workbooks.Count -eq 0) {
        Write-Host "No workbook is currently open in Excel."
        exit 0
    }
    
    $workbook = $excel.ActiveWorkbook
    $sheet = $excel.ActiveSheet
    
    Write-Host "Active workbook: $($workbook.Name)"
    Write-Host "Workbook path: $($workbook.FullName)"
    Write-Host "Active sheet: $($sheet.Name)"
    Write-Host "Sheet count: $($workbook.Worksheets.Count)"
    
    # Get used range info
    $usedRange = $sheet.UsedRange
    Write-Host "Used range: $($usedRange.Address)"
    Write-Host "Rows: $($usedRange.Rows.Count)"
    Write-Host "Columns: $($usedRange.Columns.Count)"
    
    # Get first few cells for context
    $maxRows = [Math]::Min(5, $usedRange.Rows.Count)
    $maxCols = [Math]::Min(5, $usedRange.Columns.Count)
    
    for ($r = 1; $r -le $maxRows; $r++) {
        $rowData = @()
        for ($c = 1; $c -le $maxCols; $c++) {
            $cell = $sheet.Cells($r, $c)
            $value = $cell.Value2
            if ($null -ne $value) {
                $rowData += "$value"
            } else {
                $rowData += ""
            }
        }
        Write-Host "Row $r : $($rowData -join ' | ')"
    }
    
    Write-Host "Excel snapshot retrieved successfully."
    
} catch {
    Write-Host "Error getting Excel state: $_"
}'''
        
        action_dict = {"type": "execute_code", "code": get_snapshot_code, "language": "PowerShell"}
        
        yield {
            "type": "cua_update",
            "cuaId": step_cua_id,
            "content": action_dict,
            "kind": "actor",
        }
        
        yield {
            "type": "tool_call",
            "id": f"call_excel_{ctx.node_id}_get_snapshot",
            "target": "excel",
            "name": "execute_code",
            "args": {"code": get_snapshot_code, "language": "PowerShell"},
        }
        
        yield {
            "type": "cua_end",
            "cuaId": step_cua_id,
            "status": "completed",
            "title": "Reading Excel state",
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
                    "Observation": "No Excel snapshot available yet",
                    "Action": "Read Excel workbook state",
                },
            },
            action_summary="Read Excel workbook state",
        ).to_dict()
    
    def _extract_snapshot(self, ctx: V2NodeContext) -> Optional[SheetSnapshot]:
        """
        从请求中提取工作表快照
        
        前端请求时可能在以下位置附带快照:
        1. node_state.snapshot (直接是 SheetSnapshot 结构，包含 workbook_info)
        2. node_state.snapshot.excel_data (嵌套结构)
        3. node_state.excel_data (直接结构)
        """
        # 尝试从 snapshot 字段提取
        snapshot_data = ctx.node_state.get("snapshot", {})
        
        if snapshot_data:
            # 情况 1: snapshot 直接是 SheetSnapshot 结构 (包含 workbook_info)
            if "workbook_info" in snapshot_data:
                try:
                    return sheet_snapshot_from_dict(snapshot_data)
                except Exception as e:
                    logger.logger.warning(f"解析 snapshot (直接结构) 失败: {e}")
            
            # 情况 2: snapshot.excel_data 嵌套结构
            excel_data = snapshot_data.get("excel_data")
            if excel_data:
                try:
                    return sheet_snapshot_from_dict(excel_data)
                except Exception as e:
                    logger.logger.warning(f"解析 snapshot.excel_data 失败: {e}")
        
        # 情况 3: 直接从 excel_data 提取
        excel_data = ctx.node_state.get("excel_data")
        if excel_data:
            try:
                return sheet_snapshot_from_dict(excel_data)
            except Exception as e:
                logger.logger.warning(f"解析 excel_data 失败: {e}")
        
        logger.logger.info("[ExcelNodeHandlerV2] 没有找到工作表快照，Excel 可能未打开")
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

    async def _handle_read_default_reference(
        self,
        ctx: V2NodeContext,
        cua_id: str,
        reader: SkillFileReader,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        处理 read_default_reference action

        使用 SkillFileReader 加载默认参考文档。
        参考内容由 prompts.py 的 DEFALUT_SKILL_REFERENCE_PROMPT 提供（Excel 特有）。
        """
        logger.logger.info("[ExcelNodeHandlerV2] read_default_reference: Loading default Excel COM reference")

        step_cua_id = f"{cua_id}_read_default_ref"

        yield {
            "type": "cua_start",
            "cuaId": step_cua_id,
            "title": "Load Excel COM reference",
            "nodeId": ctx.node_id,
        }

        try:
            from .prompts import DEFALUT_SKILL_REFERENCE_PROMPT

            result = reader.read_default_reference(
                DEFALUT_SKILL_REFERENCE_PROMPT,
                label="Excel COM API Reference",
            )

            title = "Load Excel COM reference" + (" (cached)" if result.is_cached else "")

            yield {
                "type": "cua_end",
                "cuaId": step_cua_id,
                "status": "completed",
                "title": title,
                "action": {"type": "read_default_reference"},
            }

            yield NodeCompleteEvent(
                node_id=ctx.node_id,
                node_type=ctx.node_type,
                is_node_completed=False,
                handler_result={
                    "is_node_completed": False,
                    "waiting_for_execution": False,
                    **reader.get_state(),
                },
                action_summary=title,
            ).to_dict()

        except Exception as e:
            error_msg = f"Failed to load default reference: {e}"
            logger.logger.error(error_msg, exc_info=True)

            yield {
                "type": "cua_end",
                "cuaId": step_cua_id,
                "status": "error",
                "error": error_msg,
            }

            yield ErrorEvent(
                message=error_msg,
                node_id=ctx.node_id,
            ).to_dict()

    async def _handle_read_file(
        self,
        ctx: V2NodeContext,
        action_args: Dict[str, Any],
        cua_id: str,
        reader: SkillFileReader,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        处理 read_file action

        使用 SkillFileReader 读取文件（自动去重、截断、格式化）。
        """
        file_path = action_args.get("FilePath", "")
        skill_name = action_args.get("skill_name")

        logger.logger.info(f"[ExcelNodeHandlerV2] read_file: {file_path}")

        step_cua_id = f"{cua_id}_read_file"

        yield {
            "type": "cua_start",
            "cuaId": step_cua_id,
            "title": f"Read {file_path}",
            "nodeId": ctx.node_id,
        }

        result = reader.read_file(file_path, skill_name)

        if not result.success:
            logger.logger.error(f"[ExcelNodeHandlerV2] read_file failed: {result.error}")
            yield {
                "type": "cua_end",
                "cuaId": step_cua_id,
                "status": "error",
                "error": result.error,
            }
            yield ErrorEvent(message=result.error, node_id=ctx.node_id).to_dict()
            return

        title = f"Read {file_path}" + (" (cached)" if result.is_cached else "")

        yield {
            "type": "cua_end",
            "cuaId": step_cua_id,
            "status": "completed",
            "title": title,
            "action": {"type": "read_file", "FilePath": file_path},
        }

        yield NodeCompleteEvent(
            node_id=ctx.node_id,
            node_type=ctx.node_type,
            is_node_completed=False,
            handler_result={
                "is_node_completed": False,
                "waiting_for_execution": False,
                **reader.get_state(),
            },
            action_summary=title,
        ).to_dict()

    async def _handle_execute_script(
        self,
        ctx: V2NodeContext,
        action_args: Dict[str, Any],
        cua_id: str,
        planner_content: Dict[str, Any],
        step_count: int,
        reader: SkillFileReader,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        处理 execute_script action (Mode 2: Script-based execution)

        简化流程（共享目录，无需读取脚本内容）：
        1. 确定 skill_id（通过 SkillFileReader）
        2. 发送 execute_script tool_call（skill_id + script_path + parameters）
        3. 等待执行结果（由 wait_for_execution 处理）
        """
        # 优先从 action_args 获取，fallback 到 planner_content（兼容不同来源）
        script_path = action_args.get("ScriptPath") or planner_content.get("ScriptPath", "")
        parameters = action_args.get("Parameters") or planner_content.get("Parameters", {})
        skill_id = action_args.get("skill_id")  # AI 可能直接提供

        logger.logger.info(f"[ExcelNodeHandlerV2] execute_script: {script_path} with params: {parameters}")

        # 确定 skill_id（通过 SkillFileReader 查找）
        if not skill_id:
            skill_id = reader.find_skill_id(script_path)

            if not skill_id:
                skill_id = "66666666"
                logger.logger.warning(f"[ExcelNodeHandlerV2] Cannot determine skill_id, using default: {skill_id}")

        logger.logger.info(f"[ExcelNodeHandlerV2] Using skill_id: {skill_id}")

        # 2. 发送 execute_script tool_call
        action_title = planner_content.get("Title") or f"Execute {script_path}"

        # Detect language from file extension
        ext = script_path.rsplit(".", 1)[-1].lower() if "." in script_path else "ps1"
        lang = "Python" if ext == "py" else "PowerShell"

        tool_call_args = {
            "skill_id": skill_id,
            "script_path": script_path,
            "parameters": parameters,
            "language": lang,
        }

        yield {
            "type": "tool_call",
            "id": f"call_excel_{cua_id}_step{step_count}",
            "target": "excel",
            "name": "execute_script",
            "args": tool_call_args,
        }

        yield {
            "type": "cua_end",
            "cuaId": f"{cua_id}_step{step_count}",
            "status": "completed",
            "title": action_title,
            "action": {
                "type": "execute_script",
                "skill_id": skill_id,
                "script_path": script_path,
                "parameters": parameters,
            },
        }
