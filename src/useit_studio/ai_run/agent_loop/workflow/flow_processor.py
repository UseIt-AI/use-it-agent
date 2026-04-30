"""
FlowProcessor - 工作流执行控制器

职责：
1. 路由决策 - 根据节点类型和执行结果决定下一个节点
2. 图结构访问 - 通过 GraphManager 访问工作流定义
3. 状态管理 - 委托给内部的 RuntimeStateManager
4. 单步执行 - 通过 step() 方法执行当前节点

架构说明：
- FlowProcessor 是工作流执行的核心控制器
- RuntimeStateManager 是内部的状态管理器，提供更丰富的状态管理功能
- 通过 step() 方法可以执行当前节点并自动推进流程
- 通过 runtime_state 属性可以访问 RuntimeStateManager 的高级功能
"""

import os
import re
import uuid
from typing import Dict, List, Optional, Tuple, Any, AsyncGenerator

from useit_studio.ai_run.utils.logger_utils import LoggerUtils
from useit_studio.ai_run.agent_loop.workflow.graph_manager import GraphManager
from useit_studio.ai_run.runtime.state_manager import RuntimeStateManager
from useit_studio.ai_run.runtime.protocols import NodeOutputProtocol

logger = LoggerUtils(component_name="flow_processor")


class FlowProcessor:
    """
    工作流执行控制器
    
    对外接口保持不变，内部使用 RuntimeStateManager 管理状态。
    
    Usage:
        # 基本用法（向后兼容）
        fp = FlowProcessor(graph_manager, workflow_id)
        fp.start_procedure()
        node_id, node_dict, node_state = fp.get_active_node_details()
        
        # 高级用法（访问 RuntimeStateManager）
        fp.runtime_state.record_node_action(node_id, observation="...", action_type="click")
        fp.runtime_state.save_to_file("/path/to/state.json")
    """
    
    def __init__(
        self,
        graph_manager: GraphManager,
        workflow_id: str,
        task_id: Optional[str] = None,
    ):
        """
        初始化 FlowProcessor
        
        Args:
            graph_manager: 图管理器，提供工作流定义访问
            workflow_id: 工作流定义 ID
            task_id: 任务/运行 ID（可选，默认自动生成）
        """
        self.logger = logger
        self.graph_manager = graph_manager
        self.workflow_id = workflow_id
        self.task_id = task_id or str(uuid.uuid4())
        
        # 内部状态管理器
        self._runtime_state = RuntimeStateManager(
            workflow_id=workflow_id,
            run_id=self.task_id,
        )

        # Cross-node clarifications accumulated inside this workflow run.
        # Fed from two sources:
        #   1. Orchestrator level — passed in via ``step(clarifications=...)``
        #      every round.  These are re-derived from the orchestrator's
        #      conversation each step, so stale entries never linger.
        #   2. Agent node level — when a node's own ``ask_user`` answer
        #      lands, the node handler calls :meth:`add_node_clarification`
        #      so *subsequent* nodes in the same workflow see the answer
        #      (the current node's same-loop planner already sees it via
        #      ``last_execution_output``).
        # We merge the two sources when building :class:`NodeContext`, with
        # orchestrator-source entries first (they're almost always the
        # broadest, most-task-defining answers).
        self._node_clarifications: List[Any] = []

        # ===== 向后兼容：保留原有属性的访问方式 =====
        # 这些属性现在是 RuntimeStateManager 的代理
        
    @property
    def active_node_id(self) -> Optional[str]:
        """当前活动节点 ID（向后兼容）"""
        return self._runtime_state.state.current_node_id
    
    @active_node_id.setter
    def active_node_id(self, value: Optional[str]):
        """设置当前活动节点 ID（向后兼容）"""
        self._runtime_state.state.current_node_id = value
    
    @property
    def node_states(self) -> Dict[str, Dict]:
        """
        节点状态字典（向后兼容）
        
        注意：这是一个兼容性代理，返回的是 RuntimeStateManager 中的状态视图。
        对于新代码，建议使用 runtime_state.get_node_state() 等方法。
        """
        return _NodeStatesProxy(self._runtime_state)
    
    @property
    def execution_history(self) -> List[Dict]:
        """
        执行历史（向后兼容）
        
        返回简化的执行历史列表，格式与原来兼容。
        """
        history = []
        for node in self._runtime_state.state.get_all_nodes():
            if node.status.value in ("success", "failed"):
                history.append({
                    "node_id": node.node_def_id,
                    "node_type": node.original_node_type,
                    "handler_result_summary": {
                        "history_summary": node.history_summary,
                        "status": node.status.value,
                    },
                    "timestamp": node.end_time,
                })
        return history
    
    def add_node_clarification(self, clarification: Any) -> None:
        """Append a clarification produced by a node's own ``ask_user``.

        Called by ``agent_node/handler.py`` when it sees an ``ask_user``
        ``execution_result`` land in ``ctx.execution_result``.  Stored
        on the processor so every *subsequent* node invocation in this
        workflow run starts with the answer visible in its
        ``NodeContext.clarifications``.

        Idempotency: the handler only calls this once per round-trip
        (right after it detects the ``user_response`` payload), so no
        dedup is attempted here — if we ever need it, dedup on
        ``(question, answer, source_node_id)``.
        """
        self._node_clarifications.append(clarification)

    @property
    def node_clarifications(self) -> List[Any]:
        """Read-only view of clarifications accumulated from node-level
        ``ask_user`` calls.  Mainly for debugging / tests."""
        return list(self._node_clarifications)

    @property
    def runtime_state(self) -> RuntimeStateManager:
        """
        访问内部的 RuntimeStateManager
        
        提供更丰富的状态管理功能：
        - record_node_action(): 记录 Action 级别的操作
        - get_node_action_history(): 获取节点的 Action 历史
        - save_to_file() / load_from_file(): 状态持久化
        - get_variables() / set_variable(): 全局变量管理
        """
        return self._runtime_state

    # ==================== 辅助方法 ====================
    
    def _to_graph_node_id(self, runtime_or_graph_id: str) -> str:
        """
        将 runtime id (例如 "xxx_iter_0") 转换为 graph node id (例如 "xxx")。
        
        由于 active_node_id 是 property，读取的是 _runtime_state.state.current_node_id，
        而 start_node() 会将 current_node_id 设为带 _iter_N 后缀的 runtime id。
        graph_manager 只认 graph id，所以需要转换。
        """
        if not runtime_or_graph_id:
            return runtime_or_graph_id
        # Fast path: if it's already a valid graph id
        if self.graph_manager.get_milestone_by_id(runtime_or_graph_id):
            return runtime_or_graph_id
        # Try looking up the ExecutionNode and getting its node_def_id
        exec_node = self._runtime_state.state.get_node(runtime_or_graph_id)
        if exec_node and hasattr(exec_node, 'node_def_id') and exec_node.node_def_id:
            return exec_node.node_def_id
        # Fallback: strip _iter_N suffix via regex
        stripped = re.sub(r'_iter_\d+$', '', runtime_or_graph_id)
        if stripped != runtime_or_graph_id and self.graph_manager.get_milestone_by_id(stripped):
            return stripped
        # Give up, return as is
        return runtime_or_graph_id
    
    # ==================== 核心执行方法 ====================

    async def step(
        self,
        screenshot_path: str = "",
        uia_data: Dict[str, Any] = None,
        action_history: Dict[str, List[str]] = None,
        query: str = "",
        history_md: Optional[str] = None,
        log_folder: str = "./logs",
        planner_model: str = "gpt-4o-mini",
        planner_api_keys: Optional[Dict[str, str]] = None,
        actor_model: str = "oai-operator",
        gui_parser: Optional[Any] = None,
        actor: Optional[Any] = None,
        execution_result: Optional[Dict[str, Any]] = None,  # 新增：tool_call 执行结果
        project_id: Optional[str] = None,  # 用于 S3 输出上传、RAG 范围等
        chat_id: Optional[str] = None,
        project_path: Optional[str] = None,  # 用户机器上项目根目录的绝对路径，用于解析 attached_files[].path
        attached_files: Optional[List[Dict[str, Any]]] = None,  # 用户附加的文件列表
        attached_images: Optional[List[Dict[str, Any]]] = None,  # 用户附加的图片列表（base64）
        additional_context: Optional[str] = None,  # 项目目录结构等额外上下文
        run_logger: Optional[Any] = None,  # RunLogger 实例，用于日志落盘和 S3 上传
        clarifications: Optional[List[Any]] = None,  # 由 AgentLoop 从 orchestrator 对话抽取的 ask_user Q&A
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        执行当前节点的一步
        
        这是工作流执行的核心方法，整合了：
        1. 获取当前节点
        2. 构建执行上下文
        3. 分发到对应 Handler
        4. 处理执行结果
        5. 推进流程状态
        
        Args:
            screenshot_path: 截图路径（某些节点类型如 start, end, loop-start 不需要）
            uia_data: UIA 数据
            action_history: 动作历史
            query: 用户查询/任务描述
            history_md: 历史 Markdown
            log_folder: 日志目录
            planner_model: Planner 模型
            planner_api_keys: API 密钥
            actor_model: Actor 模型
            gui_parser: GUI 解析器（可选）
            actor: Actor 实例（可选）
            execution_result: tool_call 执行结果（用于 Word/Excel 等需要回调的节点）
            
        Yields:
            事件流（handler 事件 + 流程推进事件）
        """
        from useit_studio.ai_run.node_handler.base_v2 import NodeContext, WorkflowProgressEvent, ErrorEvent, SCREENSHOT_NOT_REQUIRED_TYPES
        from useit_studio.ai_run.node_handler.registry import NodeHandlerRegistry
        
        # 默认值处理
        uia_data = uia_data or {}
        action_history = action_history or {}
        
        # Step 1: 获取当前活动节点
        node_id, node_dict, node_state = self.get_active_node_details()
        
        # 如果没有活动节点，尝试启动流程
        if not node_id:
            self.logger.logger.info("No active node, attempting to start procedure")
            node_id, node_dict = self.start_procedure()
            if node_id and node_dict:
                _, _, node_state = self.get_active_node_details()
            else:
                self.logger.logger.error("Could not start procedure or no valid start node found")
                yield ErrorEvent(message="Could not start procedure", node_id="").to_dict()
                return
        
        # 如果有 node_id 但 node_dict 为 None，说明节点在图中不存在
        if not node_dict:
            error_msg = f"Node '{node_id}' not found in graph. The workflow may have completed or the node ID is invalid."
            self.logger.logger.error(f"[step] {error_msg}")
            yield ErrorEvent(message=error_msg, node_id=node_id or "").to_dict()
            return
        
        # 获取节点类型（使用 normalize_computer_use_node_type 处理 action_type 映射）
        from useit_studio.ai_run.agent_loop.workflow.node_types import normalize_computer_use_node_type
        raw_type = node_dict.get("data", {}).get("type", node_dict.get("type", "unknown"))
        node_type = normalize_computer_use_node_type(node_dict) if raw_type in ("computer-use", "computer_use") else raw_type
        
        self.logger.logger.info(f"[step] 开始执行 - Node: {node_id}, Type: {node_type}")
        
        # 检查是否需要截图（某些节点类型不需要）
        requires_screenshot = node_type not in SCREENSHOT_NOT_REQUIRED_TYPES
        if requires_screenshot and not screenshot_path:
            error_msg = f"Node type '{node_type}' requires screenshot_path but none provided"
            self.logger.logger.error(f"[step] {error_msg}")
            yield ErrorEvent(message=error_msg, node_id=node_id).to_dict()
            return
        
        # 如果有执行结果，存到 node_state 里（用于 Word/Excel 等需要回调的节点）
        if execution_result:
            self.logger.logger.info(f"[step] 收到执行结果，存入 node_state: keys={list(execution_result.keys())}")
            if node_state is None:
                node_state = {}
            node_state["execution_result"] = execution_result
            # 更新到 RuntimeStateManager
            self._update_node_state_dict(node_id, node_state)
        
        # ===== 加载 Skills =====
        from useit_studio.ai_run.skills.skill_loader import SkillCache
        from useit_studio.ai_run.skills.skill_downloader import (
            SkillDownloader, get_skill_downloader,
        )

        node_data = node_dict.get("data", {})

        skill_names = node_data.get("skills") or []
        skill_contents = None

        self.logger.logger.info(
            f"[step] Skills config from node data: {skill_names}"
        )

        if skill_names:
            cache = SkillCache()
            loaded_skills = {}
            s3_downloader = get_skill_downloader()

            for skill_name_raw in skill_names:
                skill = None
                skill_name = SkillDownloader.parse_skill_name(skill_name_raw)

                # S3 路径 (含 "/")：从 S3 下载到本地缓存后加载
                if SkillDownloader.is_s3_path(skill_name_raw):
                    self.logger.logger.info(
                        f"[step] S3 skill detected: '{skill_name_raw}' -> name='{skill_name}'"
                    )
                    try:
                        s3_folder, _ = s3_downloader.download_skill(skill_name_raw)
                        if s3_folder:
                            self.logger.logger.info(
                                f"[step] S3 skill ready, skill_folder={s3_folder}"
                            )
                            skill = cache.get_skill(
                                skill_name,
                                skill_folder=s3_folder,
                            )
                    except Exception as e:
                        self.logger.logger.error(
                            f"[step] S3 download failed for '{skill_name_raw}': {e}"
                        )
                else:
                    # 纯名称（无 "/"）：仅作为本地开发环境兼容
                    ai_run_root = os.path.dirname(
                        os.path.dirname(os.path.dirname(__file__))
                    )
                    local_skill_folder = os.path.join(ai_run_root, "SKILLS")
                    self.logger.logger.info(
                        f"[step] Local skill: {skill_name} "
                        f"(folder={local_skill_folder})"
                    )
                    skill = cache.get_skill(
                        skill_name,
                        skill_folder=local_skill_folder,
                    )

                if skill:
                    loaded_skills[skill_name] = skill
                    self.logger.logger.info(
                        f"[step] ✓ Skill loaded: {skill_name}\n"
                        f"  Base directory: {skill.base_dir}"
                    )
                else:
                    self.logger.logger.warning(f"[step] ✗ Skill not found: {skill_name}")

            if loaded_skills:
                skill_contents = loaded_skills
        else:
            self.logger.logger.info("[step] No skills configured for this node")

        # Merge clarifications: orchestrator-supplied (this round) + any
        # accumulated from earlier node-level ask_user answers in the
        # same workflow run.  Orchestrator entries come first because
        # they reflect the user's highest-level disambiguation (e.g.
        # "use tmp40liu0sx.pptx, not USEIT-BP-天使轮_v4.pptx") which
        # every subsequent node should anchor on before reading any
        # node-local detail.
        merged_clarifications: List[Any] = []
        if clarifications:
            merged_clarifications.extend(clarifications)
        if self._node_clarifications:
            merged_clarifications.extend(self._node_clarifications)

        # Step 2: 构建节点执行上下文
        ctx = NodeContext(
            flow_processor=self,
            node_id=node_id,
            node_dict=node_dict,
            node_state=node_state or {},
            node_type=node_type,
            screenshot_path=screenshot_path or "",  # 不需要截图的节点传空字符串
            uia_data=uia_data,
            action_history=action_history,
            history_md=history_md,
            task_id=self.task_id,
            query=query,
            log_folder=log_folder,
            planner_model=planner_model,
            planner_api_keys=planner_api_keys,
            actor_model=actor_model,
            gui_parser=gui_parser,
            actor=actor,
            execution_result=execution_result,
            project_id=project_id,
            chat_id=chat_id,
            project_path=project_path,
            attached_files=attached_files,
            attached_images=attached_images,
            additional_context=additional_context,
            run_logger=run_logger,
            skills=list(skill_contents.keys()) if skill_contents else [],
            skill_contents=skill_contents,
            clarifications=merged_clarifications,
        )
        
        # Step 3: 获取 handler
        registry = NodeHandlerRegistry.get_instance()
        handler = registry.get_handler(node_type)
        
        if not handler:
            error_msg = f"Unknown node type: {node_type}. Supported types: {registry.get_supported_types()}"
            self.logger.logger.error(f"[step] {error_msg}")
            yield ErrorEvent(message=error_msg, node_id=node_id).to_dict()
            return
        
        # Step 4: 执行 handler，透传事件
        # 注意：流程推进必须在 yield 之前完成，因为 SSE 流可能在任何时候被中断
        
        try:
            self.logger.logger.info(f"[step] 开始执行 handler: {handler.__class__.__name__}")
            async for event in handler.execute(ctx):
                event_type = event.get("type", "")
                # 跳过 cua_delta 的日志，太频繁了
                if event_type != "cua_delta":
                    self.logger.logger.info(f"[step] 收到事件: type={event_type}")
                
                # 如果是 node_complete 事件，先处理流程推进，再 yield
                if event_type == "node_complete":
                    self.logger.logger.info(f"[step] 捕获到 node_complete 事件，开始处理流程推进")
                    
                    content = event.get("content", {})
                    is_node_completed = content.get("is_node_completed", False)
                    self.logger.logger.info(f"[step] is_node_completed={is_node_completed}")
                    
                    if is_node_completed:
                        # 从 handler_result 中提取流程控制信息
                        handler_result = content.get("vlm_plan", {})
                        
                        # 确保 node_completion_summary 在 handler_result 中
                        # （NodeCompleteEvent 把它放在 content 顶层，需要合并进 handler_result）
                        if content.get("node_completion_summary") and not handler_result.get("node_completion_summary"):
                            handler_result["node_completion_summary"] = content.get("node_completion_summary")
                        if content.get("action_summary") and not handler_result.get("action_summary"):
                            handler_result["action_summary"] = content.get("action_summary")
                        
                        self.logger.logger.info(f"[step] 节点完成，准备推进流程")
                        
                        # 调用内部方法推进流程（在 yield 之前！）
                        next_node_id, _, _ = self.process_node_result_and_advance(
                            handler_result=handler_result,
                        )
                        
                        self.logger.logger.info(f"[step] 流程推进完成. next_node_id={next_node_id}, active_node_id={self.active_node_id}")
                        
                        is_workflow_completed = next_node_id is None
                        
                        # 先 yield 原始的 node_complete 事件
                        yield event
                        
                        # 再 yield 流程推进事件
                        yield WorkflowProgressEvent(
                            next_node_id=next_node_id,
                            is_workflow_completed=is_workflow_completed,
                        ).to_dict()
                        
                        # 如果工作流完成，发送完成事件
                        # 注意：前端期望 "workflow_complete"（没有 d）
                        if is_workflow_completed:
                            yield {
                                "type": "workflow_complete",
                                "content": {
                                    "is_workflow_completed": True,
                                    "message": "Workflow completed successfully"
                                }
                            }
                            self.logger.logger.info("[step] 工作流完成")
                    else:
                        # 节点未完成，保存 handler_result 到 node_state
                        # （用于 pending_completion 等跨步骤状态传递）
                        content = event.get("content", {})
                        vlm_plan = content.get("vlm_plan", {})
                        if vlm_plan:
                            self._update_node_state_dict(node_id, {"handler_result": vlm_plan})
                        yield event
                else:
                    # 其他事件直接透传
                    yield event
            
            self.logger.logger.info(f"[step] handler 执行完成")
        
        except Exception as e:
            error_msg = f"step() failed: {str(e)}"
            self.logger.logger.error(error_msg, exc_info=True)
            yield ErrorEvent(message=error_msg, node_id=node_id).to_dict()

    # ==================== 原有接口（保持不变） ====================

    def get_active_node_details(self) -> Tuple[Optional[str], Optional[Dict], Optional[Dict]]:
        """
        获取当前活动节点详情
        
        Returns:
            Tuple of (node_id, node_dict, node_state)
            - node_id: graph node id (without _iter_N suffix)
            - node_dict: 节点配置（从 graph_manager 获取）
            - node_state: 节点执行状态
        """
        if not self.active_node_id:
            return None, None, None
        
        # active_node_id property 读取的是 current_node_id，可能是 runtime id
        # 转换为 graph id 以便在 graph_manager 中查找
        graph_node_id = self._to_graph_node_id(self.active_node_id)
        
        active_node_dict = self.graph_manager.get_milestone_by_id(graph_node_id)
        if not active_node_dict:
            return graph_node_id, None, None
        
        # 从 RuntimeStateManager 获取节点状态
        current_node_state = self._get_node_state_dict(graph_node_id)
        return graph_node_id, active_node_dict, current_node_state

    def start_procedure(self, start_node_id: Optional[str] = None) -> Tuple[Optional[str], Optional[Dict]]:
        """
        启动工作流执行
        
        Args:
            start_node_id: 可选的起始节点 ID，默认从 start 节点开始
            
        Returns:
            Tuple of (node_id, node_dict)
        """
        if start_node_id:
            active_node_id = start_node_id
        else:
            # Find the start node
            ordered_nodes = self.graph_manager.get_ordered_nodes()
            if not ordered_nodes:
                if self.logger:
                    self.logger.logger.error(f"Cannot start procedure '{self.workflow_id}': No nodes found")
                return None, None
            
            start_node = next((node for node in ordered_nodes if node.get("type") == "start"), None)
            active_node_id = start_node["id"] if start_node else ordered_nodes[0]["id"]

        # 更新 RuntimeStateManager
        self.active_node_id = active_node_id
        
        if active_node_id:
            active_node_dict = self.graph_manager.get_milestone_by_id(active_node_id)
            if active_node_dict:
                # 在 RuntimeStateManager 中启动节点
                node_name = active_node_dict.get("data", {}).get("name", active_node_id)
                node_type = active_node_dict.get("type", "unknown")
                self._runtime_state.start_node(
                    node_def_id=active_node_id,
                    name=node_name,
                    original_node_type=node_type,
                    parent_id=active_node_dict.get("parentId") or active_node_dict.get("parentNode"),
                )
                return active_node_id, active_node_dict
        
        return None, None

    def process_node_result_and_advance(
        self,
        handler_result: dict,
        ordered_nodes_list: list = None,  # 保留参数但不使用，向后兼容
    ) -> Tuple[Optional[str], Optional[Dict], Optional[Dict]]:
        """
        处理节点执行结果并推进到下一个节点
        
        Args:
            handler_result: 节点处理器返回的结果
            ordered_nodes_list: 已废弃，保留仅为向后兼容
            
        Returns:
            Tuple of (next_node_id, next_node_dict, next_node_state)
        """
        # active_node_id 可能是 runtime id (带 _iter_N 后缀)，需要转为 graph id
        raw_active_id = self.active_node_id
        if not raw_active_id:
            if self.logger:
                self.logger.logger.error(f"No active node for procedure '{self.workflow_id}'")
            return None, None, None
        current_active_node_id = self._to_graph_node_id(raw_active_id)

        current_node_dict = self.graph_manager.get_milestone_by_id(current_active_node_id)
        if not current_node_dict:
            if self.logger:
                self.logger.logger.error(f"Could not find current node dict for ID {current_active_node_id} (raw: {raw_active_id})")
            return None, None, None

        current_node_type = current_node_dict.get("type")
        current_node_name = current_node_dict.get("data", {}).get("name", current_active_node_id)

        if self.logger:
            self.logger.logger.info(f"Processing node '{current_node_name}' (ID: {current_active_node_id}, Type: {current_node_type})")

        # 在 RuntimeStateManager 中完成当前节点
        self._complete_current_node(current_active_node_id, handler_result)

        # Update node state (兼容旧的 current_state 字段)
        if "current_state" in handler_result:
            self._update_node_state_dict(current_active_node_id, handler_result["current_state"])

        # Determine next node
        next_node_id = self._resolve_next_node_id(
            current_active_node_id, current_node_type, handler_result
        )

        # Log the transition
        if self.logger:
            if next_node_id:
                next_node_dict = self.graph_manager.get_milestone_by_id(next_node_id)
                next_node_name = next_node_dict.get("data", {}).get("name", next_node_id) if next_node_dict else next_node_id
                next_node_type = next_node_dict.get("type") if next_node_dict else "unknown"
                self.logger.logger.info(f"Advancing from '{current_node_name}' (ID: {current_active_node_id}) to '{next_node_name}' (ID: {next_node_id}, Type: {next_node_type})")
            else:
                self.logger.logger.info(f"Workflow completed or no next node found after '{current_node_name}' (ID: {current_active_node_id})")

        # Update active node
        self.active_node_id = next_node_id
        
        if next_node_id:
            next_node_dict = self.graph_manager.get_milestone_by_id(next_node_id)
            if next_node_dict:
                # 在 RuntimeStateManager 中启动下一个节点
                next_node_name = next_node_dict.get("data", {}).get("name", next_node_id)
                next_node_type = next_node_dict.get("type", "unknown")
                self._runtime_state.start_node(
                    node_def_id=next_node_id,
                    name=next_node_name,
                    original_node_type=next_node_type,
                    parent_id=next_node_dict.get("parentId") or next_node_dict.get("parentNode"),
                )
                next_node_state = self._get_node_state_dict(next_node_id)
                return next_node_id, next_node_dict, next_node_state
        else:
            # 工作流完成
            self._runtime_state.complete_workflow()
            self.logger.logger.info(f"Workflow completed or no next node found after '{current_node_name}' (ID: {current_active_node_id})")
            return None, None, None

    # ==================== 路由逻辑（保持不变） ====================

    def _resolve_next_node_id(
        self,
        current_node_id: str,
        current_node_type: str,
        handler_result: dict,
    ) -> Optional[str]:
        """解析下一个节点 ID"""
        current_node_dict = self.graph_manager.get_milestone_by_id(current_node_id)
        if not current_node_dict:
            self.logger.logger.error(f"Could not find current node dict for ID {current_node_id}")
            return None

        # If handler_result has explicit next_node_id, use it (but validate it exists)
        if "next_node_id" in handler_result:
            explicit_next_id = handler_result["next_node_id"]
            if explicit_next_id:
                # 验证节点是否存在
                next_node_dict = self.graph_manager.get_milestone_by_id(explicit_next_id)
                if next_node_dict:
                    return explicit_next_id
                else:
                    self.logger.logger.warning(
                        f"Explicit next_node_id '{explicit_next_id}' not found in graph, "
                        f"falling back to sequential lookup"
                    )
            else:
                return None  # 显式返回 None 表示工作流结束
        
        # Special handling for if-else nodes
        if current_node_type == "if-else":
            chosen_branch_id = handler_result.get("chosen_branch_id")
            if chosen_branch_id:
                return self._determine_next_node_for_if_else(current_node_id, chosen_branch_id)
            else:
                self.logger.logger.error(f"No chosen branch ID found for if-else node {current_node_id}")
                return None
            
        # Special handling for loop nodes (when loop exits due to max iterations)
        if current_node_type == "loop":
            if handler_result.get("break_loop"):
                return self._determine_next_node_sequentially(current_node_id)
            else:
                return current_node_dict.get('data', {}).get('start_node_id')
        
        if current_node_type == "loop-start":
            return self._determine_next_node_sequentially(current_node_id)
        
        # Special handling for loop-end nodes
        if current_node_type == "loop-end":
            return self._handle_loop_end(current_node_id, current_node_dict, handler_result)

        # Default sequential next node lookup
        return self._determine_next_node_sequentially(current_node_id)

    def _determine_next_node_sequentially(self, current_node_id: str) -> Optional[str]:
        """顺序查找下一个节点"""
        outgoing_edges = self.graph_manager.adjacency_list.get(current_node_id, [])
        if len(outgoing_edges) == 1:
            return outgoing_edges[0].get('target')
        elif len(outgoing_edges) > 1:
            self.logger.logger.warning(f"Node {current_node_id} has multiple outgoing edges but no specific logic handled the transition.")
            return None
        return None

    def _determine_next_node_for_if_else(self, if_else_node_id: str, chosen_branch_id: str) -> Optional[str]:
        """if-else 节点的分支选择"""
        for edge in self.graph_manager.adjacency_list.get(if_else_node_id, []):
            if edge.get("sourceHandle") == chosen_branch_id:
                return edge["target"]
        return None

    def _handle_loop_end(
        self,
        loop_end_node_id: str,
        loop_end_node_dict: dict,
        handler_result: dict,
    ) -> Optional[str]:
        """处理 loop-end 节点"""
        loop_id = (
            loop_end_node_dict.get('parentId') or 
            loop_end_node_dict.get('parentNode') or 
            loop_end_node_dict.get('data', {}).get('loop_id')
        )
        if not loop_id:
            self.logger.logger.error(f"Loop-end node {loop_end_node_id} is missing parentId and loop_id.")
            return None

        break_loop = handler_result.get("break_loop", False)
        
        if break_loop:
            # Exit loop
            self.logger.logger.info(f"Break condition met for loop {loop_id}. Exiting.")
            # 更新 RuntimeStateManager 中的循环状态
            self._runtime_state.set_variable(f"_loop_{loop_id}_break", True)
            return self._determine_next_node_sequentially(loop_id)
        
        else:
            # Continue loop
            self.logger.logger.info(f"Continuing loop {loop_id}.")
            loop_node_dict = self.graph_manager.get_milestone_by_id(loop_id)
            if not loop_node_dict:
                self.logger.logger.error(f"Could not find loop container node with id {loop_id}")
                return None
            
            # 完成当前迭代
            self._runtime_state.complete_loop_iteration(loop_id)
            
            # Check max iterations BEFORE starting new iteration
            # _iteration_counters 记录的是已启动的迭代总数，
            # 在 complete 之后不变，等于已完成的迭代数。
            max_iterations = loop_node_dict.get('data', {}).get('max_iterations', 2)
            started_count = self._runtime_state._iteration_counters.get(loop_id, 0)
            
            if started_count >= max_iterations:
                self.logger.logger.info(
                    f"Loop {loop_id} has reached max iterations "
                    f"({started_count}/{max_iterations}). Exiting."
                )
                # 清理 loop stack，避免后续节点被错误地标记为 loop 内部节点
                self._runtime_state.finish_loop(loop_id)
                return self._determine_next_node_sequentially(loop_id)
            
            # 开始新迭代（只有在未超限时才创建）
            self._runtime_state.start_loop_iteration(loop_id)

            # 查找 loop-start 节点
            start_node_id = loop_node_dict.get('data', {}).get('start_node_id')
            if not start_node_id:
                # 从图中查找 parentId 或 parentNode 为当前 loop 的 loop-start 节点
                for nid, ndata in self.graph_manager.nodes.items():
                    parent_id = ndata.get("parentId") or ndata.get("parentNode")
                    node_type = ndata.get("data", {}).get("type") or ndata.get("type")
                    if parent_id == loop_id and node_type == "loop-start":
                        start_node_id = nid
                        break
            
            if not start_node_id:
                self.logger.logger.error(f"Could not find loop-start node for loop {loop_id}")
                return None
            
            return start_node_id

    # ==================== RuntimeStateManager 集成辅助方法 ====================

    def _get_node_state_dict(self, node_id: str) -> Dict[str, Any]:
        """
        获取节点状态字典（兼容旧格式）
        
        将 RuntimeStateManager 的结构化状态转换为简单的 Dict
        """
        exec_node = self._runtime_state.get_node_resolved(node_id)
        if not exec_node:
            return {}
        
        # 合并 internal_state 和一些常用字段
        state = exec_node.internal_state.copy()
        state["_step_count"] = exec_node.step_count
        state["_status"] = exec_node.status.value
        
        # 如果是循环节点，添加迭代信息
        if exec_node.original_node_type == "loop":
            state["iteration"] = self._runtime_state.get_current_iteration(node_id)
        
        return state

    def _update_node_state_dict(self, node_id: str, state_dict: Dict[str, Any]):
        """
        更新节点状态字典（兼容旧格式）
        
        将简单的 Dict 更新到 RuntimeStateManager
        注意：不修改传入的 state_dict，避免影响调用方（如 NodeContext）
        """
        exec_node = self._runtime_state.get_node_resolved(node_id)
        if not exec_node:
            return
        
        # 提取特殊字段（用 get 而非 pop，避免修改调用者的 dict）
        step_count = state_dict.get("_step_count")
        if step_count is not None:
            exec_node.step_count = step_count
        
        # 其余更新到 internal_state（过滤掉特殊字段）
        SPECIAL_KEYS = {"_step_count", "_status"}
        for k, v in state_dict.items():
            if k not in SPECIAL_KEYS:
                exec_node.internal_state[k] = v

    def _complete_current_node(self, node_id: str, handler_result: dict):
        """
        在 RuntimeStateManager 中完成当前节点
        """
        exec_node = self._runtime_state.get_node_resolved(node_id)
        if not exec_node:
            return
        
        # 构建 NodeOutputProtocol
        output = NodeOutputProtocol(
            node_id=node_id,
            status="success" if not handler_result.get("error_message") else "failed",
            output_data=handler_result,
            history_summary=handler_result.get("node_completion_summary") or handler_result.get("action_summary", ""),
            chosen_branch_id=handler_result.get("chosen_branch_id"),
            break_loop=handler_result.get("break_loop"),
            token_usage=handler_result.get("token_usage", {}),
        )
        
        self._runtime_state.complete_node(node_id, output)

    # ==================== 新增便捷方法 ====================

    def record_action(
        self,
        observation: Optional[str] = None,
        reasoning: Optional[str] = None,
        action_type: Optional[str] = None,
        action_params: Optional[Dict[str, Any]] = None,
        action_target: Optional[str] = None,
        token_usage: Optional[Dict[str, Any]] = None,
    ):
        """
        记录当前节点的一个 Action
        
        这是 runtime_state.record_node_action() 的便捷封装。
        
        Args:
            observation: Agent 观察到的内容
            reasoning: Agent 的推理过程
            action_type: 动作类型 (click, type, scroll 等)
            action_params: 动作参数
            action_target: 动作目标描述
            token_usage: Token 使用量
        """
        if not self.active_node_id:
            return None
        
        return self._runtime_state.record_node_action(
            node_id=self.active_node_id,
            observation=observation,
            reasoning=reasoning,
            action_type=action_type,
            action_params=action_params,
            action_target=action_target,
            token_usage=token_usage,
        )

    def complete_action(
        self,
        status: str = "success",
        result_observation: Optional[str] = None,
        error: Optional[str] = None,
    ):
        """
        完成当前节点的最近一个 Action
        
        Args:
            status: 状态 (success/failed)
            result_observation: 执行后的观察
            error: 错误信息（如果失败）
        """
        if not self.active_node_id:
            return None
        
        return self._runtime_state.complete_node_action(
            node_id=self.active_node_id,
            status=status,
            result_observation=result_observation,
            error=error,
        )

    def get_action_history(self) -> List[Dict]:
        """
        获取当前节点的 Action 历史
        
        Returns:
            Action 记录列表
        """
        if not self.active_node_id:
            return []
        
        actions = self._runtime_state.get_node_action_history(self.active_node_id)
        return [action.to_dict() for action in actions]

    def save_state(self, file_path: str) -> bool:
        """
        保存当前状态到文件
        
        Args:
            file_path: 文件路径
            
        Returns:
            是否成功
        """
        return self._runtime_state.save_to_file(file_path)

    def restore_runtime_state(self, state_data: Dict[str, Any]) -> bool:
        """
        从字典恢复运行时状态
        
        用于从 StateStore (Redis/Memory) 恢复状态，支持弹性扩展。
        
        Args:
            state_data: RuntimeStateManager.to_dict() 的输出
            
        Returns:
            是否成功恢复
        """
        try:
            restored_manager = RuntimeStateManager.from_dict(state_data)
            
            # 验证 workflow_id 和 run_id 匹配
            if restored_manager.state.workflow_id != self.workflow_id:
                self.logger.logger.warning(
                    f"Workflow ID mismatch: expected {self.workflow_id}, "
                    f"got {restored_manager.state.workflow_id}"
                )
            
            if restored_manager.state.run_id != self.task_id:
                self.logger.logger.warning(
                    f"Task ID mismatch: expected {self.task_id}, "
                    f"got {restored_manager.state.run_id}"
                )
            
            # 替换内部状态管理器
            self._runtime_state = restored_manager
            
            self.logger.logger.info(
                f"Restored runtime state for task {self.task_id}: "
                f"status={restored_manager.state.status}, "
                f"current_node={restored_manager.state.current_node_id}, "
                f"nodes={len(restored_manager.state.get_all_nodes())}"
            )
            
            return True
            
        except Exception as e:
            self.logger.logger.error(f"Failed to restore runtime state: {e}")
            return False

    @classmethod
    def load_state(cls, file_path: str, graph_manager: GraphManager) -> Optional["FlowProcessor"]:
        """
        从文件加载状态
        
        Args:
            file_path: 文件路径
            graph_manager: 图管理器
            
        Returns:
            FlowProcessor 实例，失败返回 None
        """
        runtime_state = RuntimeStateManager.load_from_file(file_path)
        if not runtime_state:
            return None
        
        fp = cls(
            graph_manager=graph_manager,
            workflow_id=runtime_state.state.workflow_id,
            task_id=runtime_state.state.run_id,
        )
        fp._runtime_state = runtime_state
        return fp


class _NodeStatesProxy(dict):
    """
    node_states 属性的代理类
    
    提供向后兼容的 Dict 接口，内部委托给 RuntimeStateManager。
    """
    
    def __init__(self, runtime_state: RuntimeStateManager):
        super().__init__()
        self._runtime_state = runtime_state
    
    def __getitem__(self, node_id: str) -> Dict:
        exec_node = self._runtime_state.get_node_resolved(node_id)
        if not exec_node:
            # 自动创建空状态
            return {}
        
        state = exec_node.internal_state.copy()
        state["_step_count"] = exec_node.step_count
        
        # 循环迭代信息
        if exec_node.original_node_type == "loop":
            state["iteration"] = self._runtime_state.get_current_iteration(exec_node.id)
        
        return state
    
    def __setitem__(self, node_id: str, value: Dict):
        exec_node = self._runtime_state.get_node_resolved(node_id)
        if exec_node:
            # 特殊处理 _step_count：写入到 step_count 属性
            if "_step_count" in value:
                exec_node.step_count = value["_step_count"]
                value = {k: v for k, v in value.items() if k != "_step_count"}
            if value:
                exec_node.internal_state.update(value)
    
    def __contains__(self, node_id: str) -> bool:
        return self._runtime_state.get_node_resolved(node_id) is not None
    
    def get(self, node_id: str, default: Dict = None) -> Dict:
        if node_id in self:
            return self[node_id]
        return default if default is not None else {}
    
    def setdefault(self, node_id: str, default: Dict = None) -> Dict:
        if node_id not in self:
            # 节点不存在时，不能自动创建（需要通过 start_node）
            return default if default is not None else {}
        return self[node_id]
    
    def keys(self):
        return [node.node_def_id for node in self._runtime_state.state.get_all_nodes()]
    
    def values(self):
        return [self[node_id] for node_id in self.keys()]
    
    def items(self):
        return [(node_id, self[node_id]) for node_id in self.keys()]
