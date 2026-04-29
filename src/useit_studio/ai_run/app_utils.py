import os
import time
from datetime import datetime, timedelta, timezone
from typing import Dict, Tuple, Optional, Any

# 旧的 gui 模块已移除，现在使用 gui_v2
from useit_studio.ai_run.node_handler.functional_nodes.computer_use.gui_v2 import (
    GUIAgent,
    Planner,
    Actor,
)
# 注意：GUIParser、TeachmodeActor、TeachModePlanner 等旧组件已移除
# 现在使用 gui_v2 中的 GUIAgent 统一处理

from useit_studio.ai_run.agent_loop.workflow.flow_processor import FlowProcessor
from useit_studio.ai_run.agent_loop.workflow.graph_manager import GraphManager

from useit_studio.ai_run.utils.logger_utils import LoggerUtils
from useit_studio.ai_run.utils.run_logger import RunLogger, StreamMessagePersister

# State Store for elastic scaling
from useit_studio.ai_run.runtime.state_store import StateStoreFactory, StateStore

# Agent Loop
from useit_studio.ai_run.agent_loop import AgentLoop

app_logger = LoggerUtils(component_name="app_utils")

UTC_PLUS_8 = timezone(timedelta(hours=8))

# --- Per-task workflow graph (inline JSON); no remote workflow DB ---
_STANDALONE_TASK_GRAPHS: Dict[str, Dict[str, Any]] = {}


def resolve_graph_definition_for_task(
    task_id: str,
    request_data: Dict[str, Any],
) -> Dict[str, Any]:
    """
    解析本次请求可用的图定义。
    优先级：请求中的 ``workflow_definition`` / ``graph`` > 内存缓存 > 默认 start→agent→end。
    """
    explicit = request_data.get("workflow_definition") or request_data.get("graph")
    if isinstance(explicit, dict) and explicit.get("nodes"):
        _STANDALONE_TASK_GRAPHS[task_id] = explicit
        return explicit
    cached = _STANDALONE_TASK_GRAPHS.get(task_id)
    if cached is not None:
        return cached
    from useit_studio.ai_run.config.default_standalone_workflow import get_default_minimal_workflow

    default_g = get_default_minimal_workflow()
    _STANDALONE_TASK_GRAPHS[task_id] = default_g
    return default_g

# --- AGENT COMPONENTS INITIALIZATION ---

def initialize_agent_components(
    cache_folder: str,
    api_keys: Dict[str, str],
    provider: Optional[str] = None,
    actor_model: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Initialize and return all global agent components.

    Args:
        cache_folder: Cache directory path
        api_keys: Dictionary of API keys
        provider: Actor provider ("openai" or "gemini"), defaults to env var ACTOR_PROVIDER or "openai"
        actor_model: Actor model name, defaults to env var ACTOR_MODEL or provider default
    """
    # 根据环境变量或参数选择 provider
    provider = provider or os.getenv("ACTOR_PROVIDER", "openai")
    provider = provider.lower()

    # 根据 provider 选择默认模型
    if actor_model is None:
        if provider == "openai":
            actor_model = os.getenv("ACTOR_MODEL", "computer-use-preview")
        elif provider == "gemini":
            actor_model = os.getenv("ACTOR_MODEL", "gemini-2.5-computer-use-preview-10-2025")
        else:
            actor_model = os.getenv("ACTOR_MODEL", "computer-use-preview")

    app_logger.logger.info(f"Initializing global agent components with provider={provider}, actor_model={actor_model}")

    # 旧组件已移除，现在使用 gui_v2 的 GUIAgent
    # GUIAgent 在 flow_processor.step() 中按需创建
    return {
        # gui_v2 架构：GUIAgent 统一处理 planner 和 actor
        # 不再需要单独的 gui_parser、teachmode_actor 等组件
        # 这些组件的功能已整合到 GUIAgent 中
    }


# --- DIRECTORY SETUP ---
# 使用环境变量配置，支持生产环境部署
RUN_LOG_DIR = os.getenv("RUN_LOG_DIR", "logs/useit_ai_run_logs")

def setup_directories():
    """Ensure all necessary logging directories exist."""
    os.makedirs(RUN_LOG_DIR, exist_ok=True)


def setup_timezone_for_flask():
    # Ensure process localtime is UTC+8 for all localtime-based logs (e.g., Werkzeug access logs)
    os.environ.setdefault("TZ", "Asia/Shanghai")
    try:
        time.tzset()
    except AttributeError:
        # time.tzset() not available on some platforms (e.g., Windows). Safe to ignore.
        pass

# --- HELPER FUNCTIONS ---

def validate_request_generate_action(data: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
    """Validate incoming request data."""

    for field in ['task_id', 'workflow_id', 'query', 'screenshot']:
        if field not in data:
            error_msg = f'Missing required field: {field}'
            return False, error_msg

    return True, None


def validate_request_generate_action_from_checkpoint(data: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
    """Validate incoming request data for checkpoint mode."""
    for field in ['task_id', 'workflow_id', 'node_id', 'query', 'screenshot']:
        if field not in data:
            error_msg = f'Missing required field: {field}'
            return False, error_msg

    return True, None


def setup_logging_directory(task_id: str, run_log_dir: str, endpoint_prefix: str = "gen_act") -> Tuple[str, str, bool]:
    """
    Set up logging directory for the current request.
    If a directory containing the task_id already exists, it is reused.
    Otherwise, a new directory is created with the format 'timestamp_tid_uuid'.
    
    注意：此函数保留用于向后兼容。推荐使用 create_run_logger() 获取 RunLogger 实例。
    """
    task_parent_folder = None
    is_casual_run = False

    # Check for an existing directory for this task_id
    if os.path.exists(run_log_dir):
        for dirname in os.listdir(run_log_dir):
            if task_id in dirname and os.path.isdir(os.path.join(run_log_dir, dirname)):
                task_parent_folder = os.path.join(run_log_dir, dirname)
                is_casual_run = True
                app_logger.logger.info(f"Found existing task directory for task_id: {task_id} at {task_parent_folder}")
                break

    # If no existing directory is found, create a new one
    if task_parent_folder is None:
        timestamp_for_folder = datetime.now(UTC_PLUS_8).strftime("%y%m%d-%H%M%S")
        folder_name = f"{timestamp_for_folder}_{endpoint_prefix}_tid_{task_id}"
        task_parent_folder = os.path.join(run_log_dir, folder_name)
        os.makedirs(task_parent_folder, exist_ok=True)
        app_logger.logger.info(f"Created new task directory for task_id: {task_id} -> {task_parent_folder}")
        is_casual_run = False # This is a new run
    
    # Create a new sub-directory for the current request's logs with timestamp + step numbering
    step_number = 1
    timestamp_for_log = datetime.now(UTC_PLUS_8).strftime("%m%d-%H-%M-%S")

    # Find the highest existing step number regardless of naming pattern
    if os.path.exists(task_parent_folder):
        for dirname in os.listdir(task_parent_folder):
            # Matches: stepX
            if dirname.startswith("step") and dirname[4:].isdigit():
                existing_step = int(dirname[4:])
                step_number = max(step_number, existing_step + 1)
            # Matches: <timestamp>_stepX
            elif "_step" in dirname:
                step_part = dirname.split("_step")[-1]
                if step_part.isdigit():
                    existing_step = int(step_part)
                    step_number = max(step_number, existing_step + 1)

    log_folder_name = f"{timestamp_for_log}_step{step_number}"
    log_folder = os.path.join(task_parent_folder, log_folder_name)
    os.makedirs(log_folder, exist_ok=False)
    return log_folder, task_parent_folder, is_casual_run


def create_run_logger(
    task_id: str,
    workflow_id: str,
    run_log_dir: str,
    endpoint_prefix: str = "gen_act",
    project_id: Optional[str] = None,
    chat_id: Optional[str] = None,
    enable_s3_upload: bool = False,
    node_type_folder: str = ".cua",
) -> RunLogger:
    """
    创建运行日志管理器
    
    使用新的 workflow/node/step 层级结构管理日志。
    支持 S3 云端落盘用于 RAG。
    
    Args:
        task_id: 任务 ID (即 workflow_run_id)
        workflow_id: 工作流 ID
        run_log_dir: 运行日志根目录
        endpoint_prefix: 端点前缀
        project_id: 项目 ID (用于 S3 上传)
        chat_id: 聊天 ID (用于 S3 上传)
        enable_s3_upload: 是否启用 S3 上传
        node_type_folder: S3 路径中的节点类型文件夹 (.cua 或 .tool_call)
        
    Returns:
        RunLogger 实例
    """
    run_logger = RunLogger(
        task_id=task_id,
        workflow_id=workflow_id,
        run_log_dir=run_log_dir,
        endpoint_prefix=endpoint_prefix,
        project_id=project_id,
        chat_id=chat_id,
        enable_s3_upload=enable_s3_upload,
        node_type_folder=node_type_folder,
    )
    
    s3_info = ""
    if enable_s3_upload and project_id and chat_id:
        s3_info = f", S3 upload enabled (project={project_id}, chat={chat_id})"
    
    app_logger.logger.info(f"Created RunLogger for task_id: {task_id}, workflow_dir: {run_logger.workflow_dir}{s3_info}")
    return run_logger


def get_or_create_flow_processor(
    task_id_to_flow_processor: Dict[str, FlowProcessor],
    task_id: str,
    workflow_id: str,
    state_store: Optional[StateStore] = None,
    graph_definition: Optional[Dict[str, Any]] = None,
) -> FlowProcessor:
    """
    Gets a FlowProcessor from cache, StateStore, or creates a new one.
    
    Lookup order:
    1. Local memory cache (task_id_to_flow_processor)
    2. StateStore (Redis/Memory) - for elastic scaling recovery
    3. Create new FlowProcessor
    
    Args:
        task_id_to_flow_processor: Local memory cache dict
        task_id: Unique task identifier
        workflow_id: Workflow definition ID
        state_store: Optional StateStore instance (uses singleton if not provided)
        graph_definition: Inline workflow graph (``nodes`` / ``edges``); merged with per-task cache.
    
    Returns:
        FlowProcessor instance
    """
    if graph_definition is not None:
        _STANDALONE_TASK_GRAPHS[task_id] = graph_definition
    effective_g = graph_definition or _STANDALONE_TASK_GRAPHS.get(task_id)
    if effective_g is None:
        from useit_studio.ai_run.config.default_standalone_workflow import get_default_minimal_workflow

        effective_g = get_default_minimal_workflow()
        _STANDALONE_TASK_GRAPHS[task_id] = effective_g
    graph_definition = effective_g

    # Get state store (use singleton if not provided)
    if state_store is None:
        state_store = StateStoreFactory.get_store()
    
    # 1. Check local memory cache first (fastest)
    if task_id in task_id_to_flow_processor:
        flow_processor = task_id_to_flow_processor[task_id]
        app_logger.logger.info(f"Retrieved FlowProcessor from memory cache for task {task_id}")
        
        # Update heartbeat
        state_store.heartbeat(task_id)
        return flow_processor
    
    # 2. Try to restore from StateStore (for elastic scaling)
    stored_state = state_store.load_runtime_state(task_id)
    if stored_state:
        app_logger.logger.info(f"Found stored state for task {task_id}, restoring FlowProcessor...")
        
        try:
            # Restore FlowProcessor from stored state
            graph_manager = GraphManager(
                workflow_id=workflow_id,
                task_id=task_id,
                graph_definition=graph_definition,
            )
            flow_processor = FlowProcessor(
                graph_manager=graph_manager,
                workflow_id=workflow_id,
            )
            
            # Restore runtime state
            flow_processor.restore_runtime_state(stored_state)
            
            # Cache in memory
            task_id_to_flow_processor[task_id] = flow_processor
            
            # Update heartbeat
            state_store.heartbeat(task_id)
            
            app_logger.logger.info(
                f"Restored FlowProcessor for task {task_id} from StateStore "
                f"(workflow_id: {workflow_id})"
            )
            return flow_processor
            
        except Exception as e:
            app_logger.logger.warning(
                f"Failed to restore FlowProcessor from StateStore for task {task_id}: {e}. "
                "Creating new FlowProcessor instead."
            )
            # Fall through to create new
    
    # 3. Create new FlowProcessor
    graph_manager = GraphManager(
        workflow_id=workflow_id,
        task_id=task_id,
        graph_definition=graph_definition,
    )
    flow_processor = FlowProcessor(
        graph_manager=graph_manager,
        workflow_id=workflow_id,
    )
    
    # Cache in memory
    task_id_to_flow_processor[task_id] = flow_processor
    
    # Save initial state to StateStore
    try:
        state_data = flow_processor.runtime_state.to_dict()
        state_store.save_runtime_state(task_id, state_data)
        state_store.heartbeat(task_id)
        app_logger.logger.info(
            f"Created new FlowProcessor for task {task_id} with workflow_id: {workflow_id} "
            "(saved to StateStore)"
        )
    except Exception as e:
        app_logger.logger.warning(f"Failed to save initial state to StateStore: {e}")
    
    return flow_processor


def get_or_create_orchestrator(
    task_id_to_orchestrator: Dict[str, AgentLoop],
    task_id: str,
    planner_model: str = "gemini-3-flash-preview",
    log_root: str = "",
) -> AgentLoop:
    """
    Get an AgentLoop from cache or create a new one.

    Same caching pattern as ``get_or_create_flow_processor`` but for the
    agent loop layer.  The loop instance is keyed by ``task_id`` and
    persists across HTTP round-trips.
    """
    if task_id in task_id_to_orchestrator:
        app_logger.logger.info(f"Retrieved AgentLoop from cache for task {task_id}")
        return task_id_to_orchestrator[task_id]

    orchestrator = AgentLoop(
        task_id=task_id,
        planner_model=planner_model,
        log_root=log_root,
    )
    task_id_to_orchestrator[task_id] = orchestrator
    app_logger.logger.info(f"Created new AgentLoop for task {task_id}")
    return orchestrator


def save_flow_processor_state(
    task_id: str,
    flow_processor: FlowProcessor,
    session_progress: Optional[Dict[str, Any]] = None,
    state_store: Optional[StateStore] = None,
) -> bool:
    """
    Save FlowProcessor state to StateStore.
    
    Call this after each step to persist state for elastic scaling.
    
    Args:
        task_id: Unique task identifier
        flow_processor: FlowProcessor instance to save
        session_progress: Optional session progress dict to save
        state_store: Optional StateStore instance (uses singleton if not provided)
    
    Returns:
        True if save successful
    """
    if state_store is None:
        state_store = StateStoreFactory.get_store()
    
    success = True
    
    # Save runtime state
    try:
        state_data = flow_processor.runtime_state.to_dict()
        if not state_store.save_runtime_state(task_id, state_data):
            success = False
            app_logger.logger.warning(f"Failed to save runtime state for task {task_id}")
    except Exception as e:
        success = False
        app_logger.logger.error(f"Error saving runtime state for task {task_id}: {e}")
    
    # Save session progress if provided
    if session_progress is not None:
        try:
            if not state_store.save_session_progress(task_id, session_progress):
                success = False
                app_logger.logger.warning(f"Failed to save session progress for task {task_id}")
        except Exception as e:
            success = False
            app_logger.logger.error(f"Error saving session progress for task {task_id}: {e}")
    
    # Update heartbeat
    state_store.heartbeat(task_id)
    
    return success


def format_server_response(task_session_progress: Dict[str, Any], loop_result: Dict[str, Any], task_id: str, log_folder: str) -> Dict[str, Any]:
    """Prepare the API response from the loop result."""
    current_node_id = loop_result.get("processed_node_id")
    is_node_completed = loop_result.get("is_node_completed", False)
    task_overall_complete_flag = loop_result.get("is_workflow_completed", False)
    milestone_md = loop_result.get("milestone_md")
    node_type = loop_result.get("processed_node_type")

    # Enrich response for Human-In-The-Loop nodes
    need_human_flag = loop_result.get("need_human_flag", False)

    # Get action history from session progress
    action_history = []
    session_data = task_session_progress.get(task_id, {})
    if current_node_id and session_data:
        # Try to get current node action history
        # For loop nodes, get from current iteration context
        current_iteration_context = session_data.get("current_iteration_context")
        if current_iteration_context and current_iteration_context.get("loop_id"):
            # Look for action history in current iteration context
            current_action_history = session_data.get("current_action_history", {}).get(current_node_id, [])
            action_history = current_action_history
        else:
            # For non-loop nodes, get from completed nodes if available
            completed_nodes = session_data.get("completed_nodes", {})
            if current_node_id in completed_nodes:
                node_data = completed_nodes[current_node_id]
                if "iterations" in node_data:
                    # Get latest iteration
                    latest_iteration = node_data.get("latest_iteration", 0)
                    iteration_data = node_data["iterations"].get(str(latest_iteration), {})
                    action_history = iteration_data.get("action_history", [])
                else:
                    action_history = node_data.get("action_history", [])

    response = {
        "status": "success",
        "generated_plan": loop_result.get("plan_details"),
        "generated_action": loop_result.get("action"),
        "action_history": action_history,
        "milestone_md": milestone_md,
        "current_milestone_id": current_node_id,
        "milestone_complete_flag": is_node_completed,
        "complete_flag": task_overall_complete_flag,
        "need_human_flag": need_human_flag,
        "node_type": node_type,
    }

    if need_human_flag:
        human_task = loop_result.get("human_task", "")
        response["human_task"] = human_task


    app_logger.log_json(response, "api_response.json", log_folder)
    return response


# --- PERFORMANCE AND MONITORING FUNCTIONS ---

def get_system_performance_stats() -> Dict[str, Any]:
    """Local OSS build: CPU/memory oriented stats only (no cloud DB)."""
    return {
        "graph_cache": GraphManager.get_cache_stats(),
        "timestamp": time.time(),
    }

def clear_all_caches() -> Dict[str, str]:
    """Clear all system caches"""
    GraphManager.clear_cache()
    return {"status": "success", "message": "All caches cleared"}

def optimize_cache_settings(cache_ttl_seconds: float = 1800) -> Dict[str, Any]:
    """Optimize cache settings"""
    GraphManager.set_cache_ttl(cache_ttl_seconds)
    return {
        "status": "success", 
        "message": f"Cache TTL set to {cache_ttl_seconds} seconds",
        "new_cache_stats": GraphManager.get_cache_stats()
    }