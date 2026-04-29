"""
GUI Node Handler V2 - 符合新架构的 GUI 节点处理器

这是 gui_v2 模块与新 node_handler 架构的桥接层。

职责：
1. 实现 BaseNodeHandlerV2 接口
2. 将 NodeContext 转换为 gui_v2 的 NodeContext
3. 调用 GUIAgent 执行
4. 将事件转换为统一格式
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime
from typing import Dict, Any, List, AsyncGenerator, Optional

from useit_studio.ai_run.node_handler.base_v2 import (
    BaseNodeHandlerV2,
    NodeContext as V2NodeContext,
    NodeCompleteEvent,
    ErrorEvent,
)
from useit_studio.ai_run.utils.logger_utils import LoggerUtils

# gui_v2 模块
from .agent import GUIAgent
from .models import NodeContext as GUINodeContext, AgentStep


logger = LoggerUtils(component_name="GUINodeHandlerV2")


class GUINodeHandlerV2(BaseNodeHandlerV2):
    """
    GUI 节点处理器 V2
    
    实现 BaseNodeHandlerV2 接口，内部使用 gui_v2 的 GUIAgent。
    
    支持的节点类型：
    - computer-use-gui
    - computer-use (legacy, 默认 GUI)
    """
    
    @classmethod
    def supported_types(cls) -> List[str]:
        return ["computer-use-gui", "computer-use"]
    
    async def execute(self, ctx: V2NodeContext) -> AsyncGenerator[Dict[str, Any], None]:
        """
        执行 GUI 节点
        
        流程：
        1. 转换上下文
        2. 创建 GUIAgent
        3. 调用 agent.step_streaming()
        4. 转换事件格式
        """
        logger.logger.info(f"[GUINodeHandlerV2] 开始执行节点: {ctx.node_id}")
        
        # 生成唯一 ID
        cua_id = f"cua_{uuid.uuid4().hex[:8]}_{ctx.node_id}"
        
        try:
            # Step 1: 发送节点开始事件（如果是第一次调用）
            if self._is_first_call(ctx):
                yield {
                    "type": "node_start",
                    "nodeId": ctx.node_id,
                    "title": ctx.get_node_title(),
                    "nodeType": ctx.node_type,
                    "instruction": ctx.get_node_instruction(),
                }
            
            # Step 2: 计算步数
            step_count = self._increment_step_count(ctx)
            
            # Step 3: 发送 CUA 开始事件
            yield {
                "type": "cua_start",
                "cuaId": cua_id,
                "step": step_count,
                "title": ctx.get_node_title(),
                "nodeId": ctx.node_id,
            }
            
            # Step 4: 创建 GUIAgent（带节点 ID 用于日志）
            # 从 node 的 data.model 获取模型配置，支持 gemini-3-flash-preview 和 gpt-5.2
            node_model = self._get_node_model(ctx.node_dict)
            planner_model = node_model or ctx.planner_model
            
            logger.logger.info(f"[GUINodeHandlerV2] 使用模型: {planner_model} (node_model={node_model}, ctx.planner_model={ctx.planner_model})")
            
            agent = GUIAgent(
                planner_model=planner_model,
                actor_model=ctx.actor_model,  # Planner-Only 模式下不使用 actor_model
                api_keys=ctx.planner_api_keys,
                node_id=ctx.node_id,  # 传递节点 ID 用于日志标识
            )
            
            # Step 5: 转换为 gui_v2 的 NodeContext（异步，包含附件文件智能路由）
            gui_context = await self._convert_to_gui_context(ctx)
            
            # Step 6: 执行 Agent（流式）
            agent_step: Optional[AgentStep] = None
            planner_output_dict: Dict[str, Any] = {}  # 保存 planner 输出用于记录 action
            
            logger.logger.info(f"[GUINodeHandlerV2] 开始 Agent 流式执行, cua_id={cua_id}")
            
            async for event in agent.step_streaming(
                context=gui_context,
                screenshot_path=ctx.screenshot_path,
                log_dir=ctx.log_folder,
            ):
                event_type = event.get("type", "")
                
                # 转发推理事件
                if event_type == "reasoning_delta":
                    yield {
                        "type": "cua_delta",
                        "cuaId": cua_id,
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
                
                # 转发动作事件
                elif event_type == "action":
                    action = event.get("action", {})
                    yield {
                        "type": "cua_update",
                        "cuaId": cua_id,
                        "content": action,
                        "kind": "actor",
                    }
                    # 标准 tool_call 格式
                    tool_call_event = {
                        "type": "tool_call",
                        "id": f"call_{cua_id}_{step_count}",
                        "target": "gui",
                        "name": action.get("type", "unknown"),
                        "args": {k: v for k, v in action.items() if k != "type"},
                    }
                    print(f"[GUI_V2] 发送 tool_call: {tool_call_event}")
                    yield tool_call_event
                
                # 捕获最终结果
                elif event_type == "step_complete":
                    content = event.get("content", {})
                    agent_step = self._parse_step_complete(content)
                    logger.logger.info(f"[GUINodeHandlerV2] 收到 step_complete 事件, cua_id={cua_id}, is_completed={agent_step.is_completed if agent_step else 'None'}")
                    
                    # 记录 action 到 RuntimeStateManager（用于生成 milestone_history.md）
                    # 使用 Planner 输出的 Action 字段（自然语言描述）作为 action_target
                    if agent_step and ctx.flow_processor:
                        try:
                            action_dict = agent_step.device_action.to_dict() if agent_step.device_action else {}
                            action_type = action_dict.get("type", "unknown")
                            # 使用 Planner 的 Action 字段作为 action_target（自然语言描述）
                            planner_action = planner_output_dict.get("Action", "")
                            action_target = planner_action if planner_action else self._generate_action_title(action_dict)
                            # 获取 step_memory（AI 在这一步记录的关键信息/笔记）
                            step_memory = planner_output_dict.get("step_memory")
                            
                            ctx.flow_processor.runtime_state.record_node_action(
                                node_id=ctx.node_id,
                                observation=planner_output_dict.get("Observation", ""),
                                reasoning=planner_output_dict.get("Reasoning", ""),
                                action_type=action_type,
                                action_params=action_dict,
                                action_target=action_target,
                                step_memory=step_memory,
                            )
                            logger.logger.info(f"[GUINodeHandlerV2] 已记录 action 到 RuntimeStateManager: {action_target}")
                        except Exception as e:
                            logger.logger.warning(f"[GUINodeHandlerV2] 记录 action 失败: {e}")
                
                # 转发状态事件
                elif event_type == "status":
                    yield {
                        "type": "status",
                        "content": event.get("content", ""),
                    }
                
                # 转发错误
                elif event_type == "error":
                    # 错误时也要发送 cua_end 保证流程完整性
                    yield {
                        "type": "cua_end",
                        "cuaId": cua_id,
                        "status": "error",
                        "error": event.get("content", "Unknown error"),
                    }
                    yield ErrorEvent(
                        message=event.get("content", "Unknown error"),
                        node_id=ctx.node_id,
                    ).to_dict()
                    return
            
            # Step 7: 处理最终结果
            if agent_step:
                is_completed = agent_step.is_completed
                action_dict = agent_step.device_action.to_dict() if agent_step.device_action else {}
                
                # 生成动作标题
                action_title = self._generate_action_title(action_dict)
                
                # 如果任务完成且 AI 提供了 result_markdown，保存为文件到 outputs
                files_to_transfer: List[str] = []
                saved_filename = None
                if is_completed and agent_step.planner_output:
                    result_markdown = agent_step.planner_output.result_markdown
                    if result_markdown:
                        saved_filename = agent_step.planner_output.output_filename or "gui_result.md"
                        s3_key = await self._save_and_upload_result_markdown(
                            ctx=ctx,
                            markdown_content=result_markdown,
                            filename=saved_filename,
                        )
                        if s3_key:
                            files_to_transfer.append(s3_key)
                        logger.logger.info(
                            f"[GUINodeHandlerV2] result_markdown 已保存到 outputs, "
                            f"filename={saved_filename}, 长度={len(result_markdown)}, s3_key={s3_key}"
                        )
                
                # 标记 action 为成功（更新 RuntimeStateManager 中的 action 状态）
                # 注意：gui_v2 不再使用 result_observation，改用 working_memory 由 AI 主动记录关键信息
                if ctx.flow_processor:
                    try:
                        ctx.flow_processor.runtime_state.complete_node_action(
                            node_id=ctx.node_id,
                            status="success",
                        )
                    except Exception as e:
                        logger.logger.warning(f"[GUINodeHandlerV2] 标记 action 完成失败: {e}")
                
                # 发送 CUA 结束事件
                logger.logger.info(f"[GUINodeHandlerV2] 发送 cua_end 事件, cua_id={cua_id}, status=completed, action_type={action_dict.get('type', 'unknown')}")
                yield {
                    "type": "cua_end",
                    "cuaId": cua_id,
                    "status": "completed",
                    "title": action_title,
                    "action": action_dict,
                }
                
                # 构建 handler_result（兼容旧格式）
                handler_result = agent_step.planner_output.to_dict() if agent_step.planner_output else {}
                handler_result["is_node_completed"] = is_completed
                handler_result["action"] = action_dict
                
                # 获取 completion_summary 和 result_markdown
                completion_summary = handler_result.get("node_completion_summary", "")
                result_markdown = agent_step.planner_output.result_markdown if agent_step.planner_output else None
                
                # 如果有文件需要传输，发送文件传输事件
                if files_to_transfer:
                    handler_result["files_transferred"] = files_to_transfer
                    yield {
                        "type": "file_transfer",
                        "files": files_to_transfer,
                        "target": "local",
                        "status": "pending",
                    }
                    logger.logger.info(f"[GUINodeHandlerV2] Files to transfer: {files_to_transfer}")
                
                # 发送节点完成事件（XML 格式由 NodeCompleteEvent 统一构建）
                yield NodeCompleteEvent(
                    node_id=ctx.node_id,
                    node_type=ctx.node_type,
                    is_node_completed=is_completed,
                    handler_result=handler_result,
                    action_summary=action_title,
                    node_completion_summary=completion_summary,
                    output_filename=saved_filename,
                    result_markdown=result_markdown,
                ).to_dict()
            else:
                # 没有收到 step_complete 事件，返回错误
                # 也要发送 cua_end 保证流程完整性
                logger.logger.warning(f"[GUINodeHandlerV2] agent_step 为 None，发送 cua_end 错误事件, cua_id={cua_id}")
                yield {
                    "type": "cua_end",
                    "cuaId": cua_id,
                    "status": "error",
                    "error": "Agent did not return a valid result",
                }
                yield ErrorEvent(
                    message="Agent did not return a valid result",
                    node_id=ctx.node_id,
                ).to_dict()
        
        except Exception as e:
            error_msg = f"GUI 节点执行失败: {str(e)}"
            logger.logger.error(error_msg, exc_info=True)
            
            yield {
                "type": "cua_end",
                "cuaId": cua_id,
                "status": "error",
                "error": error_msg,
            }
            yield ErrorEvent(message=error_msg, node_id=ctx.node_id).to_dict()
    
    # ==================== 辅助方法 ====================
    
    def _get_node_model(self, node_dict: Dict[str, Any]) -> Optional[str]:
        """
        从节点配置中获取模型
        
        支持的模型:
        - gemini-3-flash-preview
        - gpt-5.2
        - openai-computer-use-preview (映射到 gpt-5.2)
        - claude-opus-4-7 / claude-opus-4-6 / claude-sonnet-4-6（Anthropic API id，透传）
        
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
        logger.logger.info(f"[GUINodeHandlerV2] 节点模型配置: {model} -> {mapped_model}")
        
        return mapped_model
    
    async def _convert_to_gui_context(self, ctx: V2NodeContext) -> GUINodeContext:
        """将 V2 NodeContext 转换为 gui_v2 的 NodeContext"""
        # 使用 RuntimeStateManager 生成 history_md（新方式）
        # 如果 ctx.history_md 已经有值（旧方式传入），则作为 fallback
        history_md = ctx.get_history_md() if hasattr(ctx, 'get_history_md') else (ctx.history_md or "")
        
        # 获取附件文件内容（异步，包含智能路由判断）
        attached_files_content = ""
        if hasattr(ctx, 'get_attached_files_content'):
            attached_files_content = await ctx.get_attached_files_content()
        attached_images = self._extract_attached_images(ctx)
        
        return GUINodeContext(
            node_id=ctx.node_id,
            task_description=ctx.query,
            milestone_objective=ctx.get_node_instruction(),
            guidance_steps=self._get_guidance_steps(ctx.node_dict),
            history_md=history_md,
            loop_context=ctx.get_loop_context(),
            attached_files_content=attached_files_content,
            attached_images=attached_images,
        )

    def _extract_attached_images(self, ctx: V2NodeContext) -> List[str]:
        """提取并标准化附件图片 base64（去掉 data URI 前缀）"""
        images: List[str] = []
        for item in (ctx.attached_images or []):
            if not isinstance(item, dict):
                continue
            raw = item.get("base64")
            if not isinstance(raw, str) or not raw.strip():
                continue
            value = raw.strip()
            if value.startswith("data:") and "," in value:
                value = value.split(",", 1)[1]
            images.append(value)
        return images
    
    def _get_guidance_steps(self, node_dict: Dict[str, Any]) -> List[str]:
        """从节点配置中提取指导步骤"""
        # 从 milestone_steps 获取
        if node_dict.get("milestone_steps"):
            return node_dict["milestone_steps"]
        
        # 从 trajectories 获取
        trajectories = node_dict.get("trajectories", [])
        steps = []
        for traj in trajectories:
            caption = traj.get("caption", {})
            action = caption.get("action", "")
            if action:
                steps.append(action)
        
        return steps
    
    def _parse_step_complete(self, content: Dict[str, Any]) -> AgentStep:
        """解析 step_complete 事件内容"""
        from .models import PlannerOutput, DeviceAction, ActionType
        
        # 解析 planner output
        planner_dict = content.get("planner", {})
        planner_output = PlannerOutput(
            observation=planner_dict.get("Observation", ""),
            reasoning=planner_dict.get("Reasoning", ""),
            next_action=planner_dict.get("Action", ""),
            current_step=planner_dict.get("Current Step", 1),
            step_explanation=planner_dict.get("Current Step Reason", ""),
            expectation=planner_dict.get("Expectation", ""),
            is_milestone_completed=planner_dict.get("MilestoneCompleted", False),
            completion_summary=planner_dict.get("node_completion_summary"),
            output_filename=planner_dict.get("output_filename"),
            result_markdown=planner_dict.get("result_markdown"),
        )
        
        # 解析 device action
        action_dict = content.get("action")
        device_action = None
        if action_dict:
            action_type_str = action_dict.get("type", "stop")
            try:
                action_type = ActionType(action_type_str)
            except ValueError:
                action_type = ActionType.STOP
            
            coord = action_dict.get("coordinate", [None, None])
            device_action = DeviceAction(
                action_type=action_type,
                x=coord[0] if len(coord) > 0 else None,
                y=coord[1] if len(coord) > 1 else None,
                text=action_dict.get("text"),
                key=action_dict.get("key"),
            )
        
        return AgentStep(
            planner_output=planner_output,
            device_action=device_action,
            reasoning_text=content.get("reasoning", ""),
            token_usage=content.get("token_usage", {}),
            error=content.get("error"),
        )
    
    def _generate_action_title(self, action: Optional[Dict[str, Any]]) -> str:
        """生成用户友好的动作标题"""
        if not action:
            return "Completed"
        
        action_type = action.get("type", "").lower()
        
        if action_type in ["click", "double_click"]:
            coord = action.get("coordinate", [0, 0])
            if isinstance(coord, list) and len(coord) >= 2:
                return f"Click ({coord[0]}, {coord[1]})"
            return "Click"
        elif action_type == "type":
            text = action.get("text", "")[:15]
            return f"Type: {text}..." if len(action.get("text", "")) > 15 else f"Type: {text}"
        elif action_type == "key":
            return f"Key: {action.get('key', '')}"
        elif action_type == "scroll":
            return "Scroll"
        elif action_type == "drag":
            path = action.get("path", [])
            n = len(path) if isinstance(path, list) else 0
            return f"Drag ({n} points)" if n >= 2 else "Drag"
        elif action_type == "stop":
            return "Sub-Task Completed"
        else:
            return f"Action: {action_type}"
    
    async def _save_and_upload_result_markdown(
        self,
        ctx: V2NodeContext,
        markdown_content: str,
        filename: str,
    ) -> Optional[str]:
        """
        保存 markdown 结果到本地日志目录并上传到 S3
        
        与 Browser Use 节点一致的路径模式：
        - 本地: {step_dir}/{safe_filename}.md (日志留存)
        - S3:   projects/{project_id}/outputs/{safe_filename}.md (云端持久化)
        - 前端通过 file_transfer 事件从 S3 下载到项目 outputs 目录
        
        Args:
            ctx: 节点上下文
            markdown_content: markdown 内容
            filename: 文件名 (如 "report.md")
            
        Returns:
            S3 key，上传失败或未配置则返回 None
        """
        try:
            # 1. 确定本地保存路径
            if ctx.run_logger:
                step_dir = ctx.run_logger.get_step_dir()
                if not step_dir:
                    step_dir = ctx.log_folder
            else:
                step_dir = ctx.log_folder or os.path.join("logs", "gui_v2", ctx.node_id)
            
            os.makedirs(step_dir, exist_ok=True)
            
            # 清理文件名
            base_filename = filename.replace('.md', '') if filename.endswith('.md') else filename
            safe_base = "".join(c for c in base_filename if c.isalnum() or c in ('_', '-')).strip()
            if not safe_base:
                safe_base = "gui_result"
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            safe_filename = f"{safe_base}_{timestamp}.md"
            local_path = os.path.join(step_dir, safe_filename)
            
            # 2. 保存到本地日志目录
            with open(local_path, "w", encoding="utf-8") as f:
                f.write(markdown_content)
            
            logger.logger.info(f"[GUINodeHandlerV2] Saved result markdown to: {local_path}")
            
            # 3. 上传到 S3 (如果配置了 project_id)
            project_id = getattr(ctx, "project_id", None)
            if not project_id:
                logger.logger.info("[GUINodeHandlerV2] project_id not provided, skip S3 upload")
                return None
            
            try:
                from useit_studio.ai_run.utils.s3_uploader import get_s3_uploader, _get_s3_client
                
                if _get_s3_client() is None:
                    logger.logger.info("[GUINodeHandlerV2] S3 client not available, skip upload")
                    return None
                
                uploader = get_s3_uploader()
                s3_key = f"projects/{project_id}/outputs/{safe_filename}"
                
                success = await uploader.upload_file_async(
                    local_path=local_path,
                    s3_key=s3_key,
                    content_type="text/markdown"
                )
                
                if success:
                    logger.logger.info(f"[GUINodeHandlerV2] Uploaded result markdown to S3: {s3_key}")
                    return s3_key
                else:
                    logger.logger.warning("[GUINodeHandlerV2] Failed to upload result markdown to S3")
                    return None
                    
            except Exception as e:
                logger.logger.warning(f"[GUINodeHandlerV2] S3 upload error: {e}")
                return None
                
        except Exception as e:
            logger.logger.error(f"[GUINodeHandlerV2] Failed to save result markdown: {e}")
            return None


# ==================== 便捷接口（兼容旧代码） ====================

async def handle_gui_node_v2(**kwargs) -> AsyncGenerator[Dict[str, Any], None]:
    """
    便捷函数：使用新架构处理 GUI 节点
    
    这个函数接受旧格式的参数，转换为 NodeContext 后调用新 handler。
    主要用于渐进式迁移。
    
    注意：history_md 参数已废弃，现在直接从 RuntimeStateManager 生成。
    """
    # 从 kwargs 构建 NodeContext
    flow_processor = kwargs.get("flow_processor")
    active_node_id = kwargs.get("active_node_id")
    current_node_dict = kwargs.get("current_node_dict", {})
    current_node_state = kwargs.get("current_node_state", {})
    
    ctx = V2NodeContext(
        flow_processor=flow_processor,
        node_id=active_node_id,
        node_dict=current_node_dict,
        node_state=current_node_state,
        node_type=current_node_dict.get("data", {}).get("type", "computer-use-gui"),
        screenshot_path=kwargs.get("screenshot_path", ""),
        uia_data=kwargs.get("uia_data"),
        action_history=kwargs.get("action_history", {}),
        history_md=None,  # 废弃：现在从 RuntimeStateManager 生成
        task_id=kwargs.get("task_id", ""),
        query=kwargs.get("query", ""),
        log_folder=kwargs.get("log_folder", "./logs"),
        planner_model=kwargs.get("planner_model", "gpt-4o-mini"),
        planner_api_keys=kwargs.get("planner_api_keys"),
        actor_model=kwargs.get("actor_model", "oai-operator"),
    )
    
    handler = GUINodeHandlerV2()
    async for event in handler.execute(ctx):
        yield event
