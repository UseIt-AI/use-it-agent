"""
Agent Loop

在 ``FlowProcessor`` 之上的一层薄封装：每个 HTTP round-trip 根据
``OrchestratorContext`` 状态把用户请求交给 **固定最小工作流**
（start → agent → end，见 ``default_standalone_workflow``），不再包含
编排器 LLM（无 app / workflow 能力表规划）。
"""

from __future__ import annotations

import logging
from typing import Any, AsyncGenerator, Dict, List, Optional

from useit_studio.ai_run.agent_loop.action_models import (
    ConversationTurn,
    OrchestratorContext,
    OrchestratorState,
    ErrorEvent,
    TaskCompletedEvent,
)
from useit_studio.ai_run.agent_loop.logger import AgentLoopLogger

logger = logging.getLogger(__name__)

_MAX_SEED_HISTORY_TURNS = 50


class AgentLoop:
    """
    有状态的任务循环，按 ``task_id`` 缓存在内存中、跨 HTTP 往返复用。

    * **ORCHESTRATING** — 将本轮用户消息写入上下文后，直接进入内置最小工作流。
    * **EXECUTING_WORKFLOW** — 委托 ``FlowProcessor.step()``；节点/工具回调仍经
      ``execution_result`` 在同一任务上继续。
    * **DONE** — 无后续工作；产出完成事件。
    """

    def __init__(
        self,
        task_id: str,
        planner_model: str = "gemini-3-flash-preview",
        log_root: str = "",
    ):
        self.task_id = task_id
        self.planner_model = planner_model
        self.ctx = OrchestratorContext(task_id=task_id)
        self._flow_processor = None
        self._workflow_run_logger = None
        self._log = AgentLoopLogger(task_id=task_id, log_root=log_root)
        self._session_logged = False
        self._total_token_usage: Dict[str, int] = {}

    async def step(
        self,
        query: str = "",
        execution_result: Optional[Dict[str, Any]] = None,
        screenshot_path: str = "",
        screenshot_base64: Optional[str] = None,
        uia_data: Optional[Dict[str, Any]] = None,
        action_history: Optional[Dict[str, List[str]]] = None,
        history_md: Optional[str] = None,
        log_folder: str = "./logs",
        planner_model: str = "gemini-3-flash-preview",
        planner_api_keys: Optional[Dict[str, str]] = None,
        actor_model: str = "gemini-3-flash-preview",
        project_id: Optional[str] = None,
        chat_id: Optional[str] = None,
        attached_files: Optional[List[Dict[str, Any]]] = None,
        attached_images: Optional[List[Dict[str, Any]]] = None,
        additional_context: Optional[str] = None,
        run_logger: Optional[Any] = None,
        app_capabilities: Optional[List[Dict[str, Any]]] = None,
        workflow_capabilities: Optional[List[Dict[str, Any]]] = None,
        selected_workflow_id: Optional[str] = None,
        chat_history: Optional[List[Dict[str, Any]]] = None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """单次 ``/agent`` 往返：仅驱动内置最小工作流。"""
        self.planner_model = planner_model

        if app_capabilities is not None:
            self.ctx.app_capabilities = app_capabilities
        if workflow_capabilities is not None:
            self.ctx.workflow_capabilities = workflow_capabilities
        if selected_workflow_id is not None:
            self.ctx.selected_workflow_id = selected_workflow_id

        self.ctx.screenshot_path = screenshot_path or ""
        self.ctx.uia_data = uia_data or {}
        self.ctx.attached_files = attached_files or []
        self.ctx.attached_images = attached_images or []
        self.ctx.action_history = action_history or {}
        self.ctx.history_md = history_md

        if chat_history and not self.ctx.conversation:
            self._seed_conversation_from_history(chat_history)

        if not self._session_logged:
            self._log.log_session_info(
                planner_model=planner_model,
                app_capability_count=len(self.ctx.app_capabilities),
                workflow_capability_count=len(self.ctx.workflow_capabilities),
                selected_workflow_id=self.ctx.selected_workflow_id or "",
            )
            self._session_logged = True

        state = self.ctx.state
        logger.info(
            "[AgentLoop] step() entry: state=%s task=%s query=%s",
            state.value,
            self.task_id,
            (query or "")[:80],
        )

        if state in (
            OrchestratorState.WAITING_APP_CALLBACK,
            OrchestratorState.WAITING_USER_RESPONSE,
        ):
            logger.warning(
                "[AgentLoop] clearing stale waiter state=%s (workflow-only loop)",
                state.value,
            )
            self.ctx.pending_app_action = None
            self.ctx.pending_ask_user = None
            self.ctx.state = OrchestratorState.ORCHESTRATING
            state = self.ctx.state

        if state == OrchestratorState.ORCHESTRATING:
            self.ctx.add_user_message(query)
            self.ctx.step_count += 1
            if self.ctx.step_count > self.ctx.max_steps:
                yield ErrorEvent(
                    message="Maximum orchestration steps reached."
                ).to_dict()
                yield TaskCompletedEvent(
                    summary="Stopped: max steps reached."
                ).to_dict()
                self.ctx.state = OrchestratorState.DONE
            else:
                wf_label = (self.ctx.selected_workflow_id or "").strip() or "__default_minimal__"
                logger.info(
                    "[AgentLoop] workflow-only: start minimal graph workflow_id=%s task=%s",
                    wf_label,
                    self.task_id,
                )
                self._start_workflow(wf_label)
                async for event in self._handle_workflow_step(
                    query=query,
                    execution_result=execution_result,
                    screenshot_path=screenshot_path,
                    screenshot_base64=screenshot_base64,
                    uia_data=uia_data or {},
                    action_history=action_history or {},
                    history_md=history_md,
                    log_folder=log_folder,
                    planner_model=planner_model,
                    planner_api_keys=planner_api_keys,
                    actor_model=actor_model,
                    project_id=project_id,
                    chat_id=chat_id,
                    attached_files=attached_files,
                    attached_images=attached_images,
                    additional_context=additional_context,
                    run_logger=run_logger,
                ):
                    self._log.append_event(event)
                    yield event

        elif state == OrchestratorState.EXECUTING_WORKFLOW:
            async for event in self._handle_workflow_step(
                query=query,
                execution_result=execution_result,
                screenshot_path=screenshot_path,
                screenshot_base64=screenshot_base64,
                uia_data=uia_data or {},
                action_history=action_history or {},
                history_md=history_md,
                log_folder=log_folder,
                planner_model=planner_model,
                planner_api_keys=planner_api_keys,
                actor_model=actor_model,
                project_id=project_id,
                chat_id=chat_id,
                attached_files=attached_files,
                attached_images=attached_images,
                additional_context=additional_context,
                run_logger=run_logger,
            ):
                self._log.append_event(event)
                yield event

        elif state == OrchestratorState.DONE:
            event = TaskCompletedEvent(summary="Task already completed.").to_dict()
            yield event
            return

        if self.ctx.state == OrchestratorState.DONE:
            self._log.log_summary(
                total_steps=self.ctx.step_count,
                final_state=self.ctx.state.value,
                total_token_usage=self._total_token_usage,
            )

    def _start_workflow(self, workflow_id: str) -> None:
        """进入工作流执行模式（内部，不单独产事件）。"""
        self.ctx.active_workflow_id = workflow_id
        self.ctx.state = OrchestratorState.EXECUTING_WORKFLOW

        self._log.start_step(self.ctx.step_count, suffix="workflow")
        self._log.log_workflow_decision(
            workflow_id,
            {"action": "workflow__run", "step": self.ctx.step_count},
        )

    async def _handle_workflow_step(
        self,
        query: str,
        execution_result: Optional[Dict[str, Any]],
        screenshot_path: str,
        screenshot_base64: Optional[str],
        uia_data: Dict[str, Any],
        action_history: Dict,
        history_md: Optional[str],
        log_folder: str,
        planner_model: str,
        planner_api_keys: Optional[Dict[str, str]],
        actor_model: str,
        project_id: Optional[str],
        chat_id: Optional[str],
        attached_files: Optional[List[Dict[str, Any]]],
        attached_images: Optional[List[Dict[str, Any]]],
        additional_context: Optional[str],
        run_logger: Optional[Any],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """委托 ``FlowProcessor.step()``。"""
        fp = self._get_or_create_flow_processor()
        if fp is None:
            yield ErrorEvent(message="Failed to create workflow executor.").to_dict()
            self.ctx.state = OrchestratorState.ORCHESTRATING
            return

        if run_logger is None:
            run_logger = self._get_or_create_workflow_run_logger(
                project_id=project_id,
                chat_id=chat_id,
            )

        wf_log_folder = log_folder
        wf_screenshot_path = screenshot_path
        if run_logger is not None:
            try:
                node_id, node_dict, _ = fp.get_active_node_details()
                if not node_id:
                    node_id, node_dict = fp.start_procedure()
                if node_id and node_dict:
                    node_type = node_dict.get("data", {}).get(
                        "type", node_dict.get("type", "unknown")
                    )
                    node_name = node_dict.get("data", {}).get(
                        "name", node_dict.get("data", {}).get("title", "")
                    )
                    run_logger.start_node(
                        node_id, node_type=node_type, node_name=node_name
                    )
                    step_dir = run_logger.start_step()
                    if step_dir:
                        wf_log_folder = step_dir
                        if screenshot_base64:
                            from useit_studio.ai_run.utils import save_base64_image

                            wf_screenshot_path = save_base64_image(
                                screenshot_base64, step_dir
                            )
                            run_logger.set_screenshot_path(wf_screenshot_path)
                        elif screenshot_path:
                            run_logger.set_screenshot_path(screenshot_path)
                    run_logger.log_incoming_request(
                        request_data={
                            "task_id": self.task_id,
                            "workflow_id": self.ctx.active_workflow_id,
                            "query": query,
                        },
                        screenshot_base64=screenshot_base64,
                        execution_result=execution_result,
                    )
            except Exception as exc:
                logger.warning("[AgentLoop] RunLogger node/step setup failed: %s", exc)

        workflow_completed = False

        try:
            orch_clarifications = self.ctx.extract_clarifications()
        except Exception as exc:  # noqa: BLE001
            logger.warning("[AgentLoop] extract_clarifications failed: %s", exc)
            orch_clarifications = []

        if orch_clarifications:
            logger.info(
                "[AgentLoop] forwarding %d clarification(s) to workflow",
                len(orch_clarifications),
            )

        async for event in fp.step(
            screenshot_path=wf_screenshot_path,
            uia_data=uia_data,
            action_history=action_history,
            query=query,
            history_md=history_md,
            log_folder=wf_log_folder,
            planner_model=planner_model,
            planner_api_keys=planner_api_keys,
            actor_model=actor_model,
            execution_result=execution_result,
            project_id=project_id,
            chat_id=chat_id,
            attached_files=attached_files,
            attached_images=attached_images,
            additional_context=additional_context,
            run_logger=run_logger,
            clarifications=orch_clarifications,
        ):
            yield event

            event_type = event.get("type", "")
            if event_type == "workflow_complete":
                workflow_completed = True
            elif event_type == "workflow_progress":
                if event.get("is_workflow_completed"):
                    workflow_completed = True
            elif event_type == "node_complete":
                content = event.get("content", {})
                if isinstance(content, dict):
                    if content.get("is_workflow_completed"):
                        workflow_completed = True

        if workflow_completed:
            wf_id = self.ctx.active_workflow_id or ""
            self.ctx.active_workflow_id = None
            self._flow_processor = None
            self._workflow_run_logger = None

            self.ctx.add_tool_result(
                f"wf_{wf_id[:8]}",
                "workflow__run",
                f"Workflow {wf_id} completed successfully.",
            )

            self.ctx.state = OrchestratorState.ORCHESTRATING

    def _seed_conversation_from_history(
        self,
        history: List[Dict[str, Any]],
    ) -> None:
        """从持久化聊天记录填充 ``self.ctx.conversation``（每个 AgentLoop 实例仅一次）。"""
        if not isinstance(history, list):
            return

        seeded = 0
        for turn in history[-_MAX_SEED_HISTORY_TURNS:]:
            if not isinstance(turn, dict):
                continue
            role = (turn.get("role") or "").lower()
            content = turn.get("content") or ""
            if not isinstance(content, str) or not content.strip():
                continue

            if role == "user":
                self.ctx.conversation.append(
                    ConversationTurn(role="user", content=content)
                )
                seeded += 1
            elif role == "assistant":
                self.ctx.conversation.append(
                    ConversationTurn(role="assistant", content=content)
                )
                seeded += 1

        if seeded:
            logger.info(
                "[AgentLoop] Seeded %d historical turn(s) into conversation (task=%s)",
                seeded,
                self.task_id,
            )

    def _get_or_create_flow_processor(self):
        """懒创建 ``FlowProcessor``（固定最小图）。"""
        if self._flow_processor is not None:
            return self._flow_processor

        workflow_id = self.ctx.active_workflow_id
        if not workflow_id:
            logger.error("No active_workflow_id set")
            return None

        try:
            from useit_studio.ai_run.agent_loop.workflow.graph_manager import GraphManager
            from useit_studio.ai_run.agent_loop.workflow.flow_processor import FlowProcessor
            from useit_studio.ai_run.config.default_standalone_workflow import (
                get_default_minimal_workflow,
            )

            graph_manager = GraphManager(
                workflow_id=workflow_id,
                task_id=self.task_id,
                graph_definition=get_default_minimal_workflow(),
            )
            self._flow_processor = FlowProcessor(
                graph_manager=graph_manager,
                workflow_id=workflow_id,
            )
            return self._flow_processor
        except Exception as exc:
            logger.error("Failed to create FlowProcessor: %s", exc, exc_info=True)
            return None

    def _get_or_create_workflow_run_logger(
        self,
        project_id: Optional[str] = None,
        chat_id: Optional[str] = None,
    ) -> Any:
        """创建与 ``AgentLoopLogger`` 任务目录复用的 ``RunLogger``。"""
        if self._workflow_run_logger is not None:
            return self._workflow_run_logger

        try:
            from useit_studio.ai_run.utils.run_logger import RunLogger

            _ = self._log.task_dir

            wf_id = self.ctx.active_workflow_id or "unknown"
            rl = RunLogger(
                task_id=self.task_id,
                workflow_id=wf_id,
                run_log_dir=self._log._log_root,
                endpoint_prefix="agent",
                project_id=project_id,
                chat_id=chat_id,
            )
            self._workflow_run_logger = rl
            logger.info("[AgentLoop] Created RunLogger, workflow_dir=%s", rl.workflow_dir)
            return rl
        except Exception as exc:
            logger.warning("[AgentLoop] Failed to create RunLogger: %s", exc)
            return None
