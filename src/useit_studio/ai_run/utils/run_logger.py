"""
运行日志管理器

提供按 workflow/node/step 层级结构组织的日志落盘功能。

目录结构:
    logs/useit_ai_run_logs/
    └── {timestamp}_{endpoint}_tid_{task_id}/                   # workflow 级别
        ├── workflow_info.json                                  # workflow 元信息
        ├── stream_messages.jsonl                               # 所有流式消息 (append)
        ├── node_{node_type}_{node_id}/                         # node 级别 (包含类型)
        │   ├── node_info.json                                  # node 元信息
        │   ├── stream_messages.jsonl                           # 该 node 的流式消息 (append)
        │   ├── step_{global_step_number}/                      # step 级别 (全局递增)
        │   │   ├── step_info.json                              # step 元信息
        │   │   ├── screenshot.png                              # 截图
        │   │   ├── planner_request.json                        # planner 请求
        │   │   ├── planner_response.json                       # planner 响应
        │   │   ├── actor_request.json                          # actor 请求
        │   │   ├── actor_response.json                         # actor 响应
        │   │   └── stream_messages.jsonl                       # 该 step 的流式消息 (append)
        │   └── step_{global_step_number+1}/
        │       └── ...
        └── node_{node_type_2}_{node_id_2}/
            └── ...

S3 云端落盘结构 (用于 RAG):
    useit.user.demo.storage/
    └── projects/
        └── {project_id}/
            └── .cua/
                └── {chat_id}/
                    └── {workflow_run_id}/
                        └── step_{NNN}/
                            ├── runtime_memory.json
                            ├── metadata.json
                            └── image_{timestamp}.png

使用示例:
    from useit_studio.ai_run.utils.run_logger import RunLogger
    
    # 初始化 (带 S3 上传支持)
    run_logger = RunLogger(
        task_id="task_123",
        workflow_id="wf_456",
        run_log_dir="logs/useit_ai_run_logs",
        project_id="proj_789",      # 可选，用于 S3 上传
        chat_id="chat_abc",         # 可选，用于 S3 上传
        enable_s3_upload=True,      # 启用 S3 上传
    )
    
    # 开始一个 node
    run_logger.start_node("node_1", node_type="computer-use", node_name="执行操作")
    
    # 开始一个 step (step 编号全局递增)
    step_dir = run_logger.start_step()
    
    # 记录流式消息 (自动 append 到对应的 stream_messages.jsonl)
    run_logger.append_stream_message(event_dict)
    
    # 保存运行时内存并上传到 S3
    run_logger.save_runtime_memory(
        runtime_memory={"Observation": "...", "Action": "..."},
        screenshot_path="/path/to/screenshot.png"
    )
    
    # 结束 step
    run_logger.end_step()
    
    # 结束 node
    run_logger.end_node()
"""

import os
import json
import time
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, Optional, List, TYPE_CHECKING
from threading import Lock

if TYPE_CHECKING:
    from .s3_uploader import S3Uploader

UTC_PLUS_8 = timezone(timedelta(hours=8))

# 写入 execution_result.json 时，screenshot 超过此长度则替换为缩略信息
_SCREENSHOT_TRUNCATE_THRESHOLD = 200
_SCREENSHOT_PREVIEW_LEN = 80


def _truncate_screenshot_in_obj(obj: Any) -> Any:
    """
    递归遍历 obj，将名为 "screenshot" 且值为较长 base64 字符串的字段
    替换为缩略形式（_screenshot_info + 占位文案），避免日志体积过大。
    """
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if k == "screenshot" and isinstance(v, str) and len(v) > _SCREENSHOT_TRUNCATE_THRESHOLD:
                preview = v[:_SCREENSHOT_PREVIEW_LEN] + "..." if len(v) > _SCREENSHOT_PREVIEW_LEN else v
                out["_screenshot_info"] = {
                    "has_screenshot": True,
                    "base64_length": len(v),
                    "base64_preview": preview,
                }
                out["screenshot"] = f"[TRUNCATED base64, len={len(v)}]"
            else:
                out[k] = _truncate_screenshot_in_obj(v)
        return out
    if isinstance(obj, list):
        return [_truncate_screenshot_in_obj(item) for item in obj]
    return obj


class RunLogger:
    """
    运行日志管理器
    
    管理 workflow/node/step 三级日志目录结构，支持流式消息的 append 落盘。
    支持 S3 云端落盘，用于后续 RAG 检索。
    
    关键特性:
    - node 目录名包含 node_type: node_{node_type}_{node_id}
    - step 编号全局递增，跨请求保持连续
    - step 必须在 node 内创建
    - 支持异步 S3 上传 (fire-and-forget)
    """
    
    def __init__(
        self,
        task_id: str,
        workflow_id: str,
        run_log_dir: str = "logs/useit_ai_run_logs",
        endpoint_prefix: str = "gen_act",
        project_id: Optional[str] = None,
        chat_id: Optional[str] = None,
        enable_s3_upload: bool = False,
        node_type_folder: str = ".cua",
    ):
        """
        初始化运行日志管理器
        
        Args:
            task_id: 任务 ID (即 workflow_run_id)
            workflow_id: 工作流 ID
            run_log_dir: 运行日志根目录
            endpoint_prefix: 端点前缀，用于目录命名
            project_id: 项目 ID (用于 S3 上传路径)
            chat_id: 聊天 ID (用于 S3 上传路径)
            enable_s3_upload: 是否启用 S3 上传
            node_type_folder: S3 路径中的节点类型文件夹 (.cua 或 .tool_call)
        """
        self.task_id = task_id
        self.workflow_id = workflow_id
        self.run_log_dir = run_log_dir
        self.endpoint_prefix = endpoint_prefix
        
        # S3 上传相关
        self.project_id = project_id
        self.chat_id = chat_id
        self.enable_s3_upload = enable_s3_upload
        self.node_type_folder = node_type_folder
        self._s3_uploader: Optional["S3Uploader"] = None
        
        # 当前状态
        self._workflow_dir: Optional[str] = None
        self._current_node_id: Optional[str] = None
        self._current_node_type: Optional[str] = None
        self._current_node_dir: Optional[str] = None
        self._current_step_dir: Optional[str] = None
        
        # 当前 step 的截图路径 (用于 S3 上传)
        self._current_screenshot_path: Optional[str] = None
        
        # 全局 step 计数 (跨 node 保持递增)
        self._global_step_number: int = 0
        
        # 线程安全锁
        self._lock = Lock()
        
        # 初始化 workflow 目录
        self._init_workflow_dir()
        
        # 初始化 S3 上传器
        if self.enable_s3_upload and self.project_id and self.chat_id:
            self._init_s3_uploader()
    
    def _init_s3_uploader(self):
        """初始化 S3 上传器（在后台线程预初始化 S3 客户端）"""
        try:
            from .s3_uploader import S3Uploader
            # lazy_init=False 会在后台线程预初始化 S3 客户端，避免第一次上传时阻塞
            self._s3_uploader = S3Uploader(node_type_folder=self.node_type_folder, lazy_init=False)
            print(f"[RunLogger] S3 uploader initialized for project={self.project_id}, chat={self.chat_id}")
        except Exception as e:
            print(f"[RunLogger] Failed to initialize S3 uploader: {e}")
            self._s3_uploader = None
    
    def cleanup_s3_cua_data(self):
        """
        清理 S3 上 .cua/{chat_id}/ 下的所有运行时数据
        
        工作流完成后调用。这些数据仅在运行时用于 RAG，运行结束后不再需要。
        """
        if not self._s3_uploader or not self.project_id or not self.chat_id:
            return
        
        print(f"[RunLogger] Triggering S3 .cua cleanup for project={self.project_id}, chat={self.chat_id}")
        self._s3_uploader.cleanup_chat_data_fire_and_forget(
            project_id=self.project_id,
            chat_id=self.chat_id,
        )
    
    def set_s3_config(
        self,
        project_id: str,
        chat_id: str,
        enable_s3_upload: bool = True,
        node_type_folder: str = ".cua",
    ):
        """
        动态设置 S3 配置
        
        允许在 RunLogger 创建后设置 S3 相关参数。
        
        Args:
            project_id: 项目 ID
            chat_id: 聊天 ID
            enable_s3_upload: 是否启用 S3 上传
            node_type_folder: S3 路径中的节点类型文件夹
        """
        self.project_id = project_id
        self.chat_id = chat_id
        self.enable_s3_upload = enable_s3_upload
        self.node_type_folder = node_type_folder
        
        if enable_s3_upload and project_id and chat_id:
            self._init_s3_uploader()
        else:
            self._s3_uploader = None
    
    def _init_workflow_dir(self):
        """初始化或复用 workflow 目录"""
        # 检查是否存在该 task_id 的目录
        if os.path.exists(self.run_log_dir):
            for dirname in os.listdir(self.run_log_dir):
                if self.task_id in dirname and os.path.isdir(os.path.join(self.run_log_dir, dirname)):
                    self._workflow_dir = os.path.join(self.run_log_dir, dirname)
                    # 恢复全局 step 计数
                    self._global_step_number = self._get_max_global_step_number()
                    break
        
        # 如果不存在，创建新目录
        if self._workflow_dir is None:
            timestamp = datetime.now(UTC_PLUS_8).strftime("%y%m%d-%H%M%S")
            folder_name = f"{timestamp}_{self.endpoint_prefix}_tid_{self.task_id}"
            self._workflow_dir = os.path.join(self.run_log_dir, folder_name)
            os.makedirs(self._workflow_dir, exist_ok=True)
            
            # 写入 workflow 元信息
            workflow_info = {
                "task_id": self.task_id,
                "workflow_id": self.workflow_id,
                "created_at": datetime.now(UTC_PLUS_8).isoformat(),
                "endpoint_prefix": self.endpoint_prefix,
            }
            self._write_json(os.path.join(self._workflow_dir, "workflow_info.json"), workflow_info)
    
    def _get_max_global_step_number(self) -> int:
        """获取 workflow 目录下所有 node 中最大的 step 编号"""
        max_step = 0
        if not self._workflow_dir or not os.path.exists(self._workflow_dir):
            return 0
        
        for node_dirname in os.listdir(self._workflow_dir):
            node_path = os.path.join(self._workflow_dir, node_dirname)
            if os.path.isdir(node_path) and node_dirname.startswith("node_"):
                for step_dirname in os.listdir(node_path):
                    if step_dirname.startswith("step_"):
                        try:
                            # 解析 step_XXX 格式
                            parts = step_dirname.split("_")
                            if len(parts) >= 2:
                                step_num = int(parts[1])
                                max_step = max(max_step, step_num)
                        except (ValueError, IndexError):
                            pass
        return max_step
    
    @property
    def workflow_dir(self) -> str:
        """获取 workflow 目录路径"""
        return self._workflow_dir
    
    @property
    def current_node_dir(self) -> Optional[str]:
        """获取当前 node 目录路径"""
        return self._current_node_dir
    
    @property
    def current_step_dir(self) -> Optional[str]:
        """获取当前 step 目录路径"""
        return self._current_step_dir
    
    @property
    def current_node_id(self) -> Optional[str]:
        """获取当前 node ID"""
        return self._current_node_id
    
    @property
    def global_step_number(self) -> int:
        """获取当前全局 step 编号"""
        return self._global_step_number
    
    def start_node(
        self,
        node_id: str,
        node_type: str = "unknown",
        node_name: str = "",
        extra_info: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        开始一个新的 node
        
        目录名格式: node_{node_type}_{node_id}
        
        Args:
            node_id: 节点 ID
            node_type: 节点类型 (如 computer-use, if-else, loop 等)
            node_name: 节点名称 (用于显示)
            extra_info: 额外信息
            
        Returns:
            node 目录路径
        """
        with self._lock:
            self._current_node_id = node_id
            self._current_node_type = node_type
            
            # 创建 node 目录: node_{node_type}_{node_id}
            safe_node_type = self._safe_filename(node_type)
            safe_node_id = self._safe_filename(node_id)
            node_dir_name = f"node_{safe_node_type}_{safe_node_id}"
            self._current_node_dir = os.path.join(self._workflow_dir, node_dir_name)
            os.makedirs(self._current_node_dir, exist_ok=True)
            
            # 重置 step 目录
            self._current_step_dir = None
            
            # 写入 node 元信息
            node_info = {
                "node_id": node_id,
                "node_type": node_type,
                "node_name": node_name,
                "started_at": datetime.now(UTC_PLUS_8).isoformat(),
                **(extra_info or {}),
            }
            self._write_json(os.path.join(self._current_node_dir, "node_info.json"), node_info)
            
            return self._current_node_dir
    
    def end_node(
        self,
        status: str = "completed",
        summary: str = "",
        extra_info: Optional[Dict[str, Any]] = None,
    ):
        """
        结束当前 node
        
        Args:
            status: 节点状态 (completed/failed/error)
            summary: 节点执行摘要
            extra_info: 额外信息
        """
        with self._lock:
            if not self._current_node_dir:
                return
            
            # 更新 node 元信息
            node_info_path = os.path.join(self._current_node_dir, "node_info.json")
            if os.path.exists(node_info_path):
                node_info = self._read_json(node_info_path)
                node_info.update({
                    "ended_at": datetime.now(UTC_PLUS_8).isoformat(),
                    "status": status,
                    "summary": summary,
                    **(extra_info or {}),
                })
                self._write_json(node_info_path, node_info)
            
            # 重置状态 (但保留 global_step_number)
            self._current_node_id = None
            self._current_node_type = None
            self._current_node_dir = None
            self._current_step_dir = None
    
    def start_step(
        self,
        extra_info: Optional[Dict[str, Any]] = None,
    ) -> Optional[str]:
        """
        开始一个新的 step
        
        注意: step 必须在 node 内创建。如果没有当前 node，返回 None。
        step 编号全局递增，跨 node 保持连续。
        
        目录名格式: step_{global_step_number:03d}
        
        Args:
            extra_info: 额外信息
            
        Returns:
            step 目录路径，如果没有当前 node 则返回 None
        """
        with self._lock:
            # step 必须在 node 内创建
            if not self._current_node_dir:
                return None
            
            # 全局递增 step 计数
            self._global_step_number += 1
            
            # 创建 step 目录: step_{global_step_number:03d}
            self._current_step_dir = os.path.join(
                self._current_node_dir, 
                f"step_{self._global_step_number:03d}"
            )
            os.makedirs(self._current_step_dir, exist_ok=True)
            
            # 写入 step 元信息
            step_info = {
                "step_number": self._global_step_number,
                "node_id": self._current_node_id,
                "node_type": self._current_node_type,
                "started_at": datetime.now(UTC_PLUS_8).isoformat(),
                **(extra_info or {}),
            }
            self._write_json(os.path.join(self._current_step_dir, "step_info.json"), step_info)
            
            return self._current_step_dir
    
    def end_step(
        self,
        status: str = "completed",
        action_summary: str = "",
        extra_info: Optional[Dict[str, Any]] = None,
        runtime_memory: Optional[Dict[str, Any]] = None,
        screenshot_path: Optional[str] = None,
    ):
        """
        结束当前 step
        
        如果提供了 runtime_memory，会同时保存到本地和上传到 S3。
        
        Args:
            status: step 状态
            action_summary: 动作摘要
            extra_info: 额外信息
            runtime_memory: 运行时内存数据 (可选，用于 S3 上传)
            screenshot_path: 截图路径 (可选，用于 S3 上传)
        """
        # 先在锁内获取需要的信息，然后在锁外执行 S3 上传（避免死锁）
        should_upload = False
        actual_screenshot_path = None
        step_number = 0
        current_step_dir = None
        
        with self._lock:
            if not self._current_step_dir:
                return
            
            current_step_dir = self._current_step_dir
            step_number = self._global_step_number
            
            # 更新 step 元信息
            step_info_path = os.path.join(self._current_step_dir, "step_info.json")
            if os.path.exists(step_info_path):
                step_info = self._read_json(step_info_path)
                step_info.update({
                    "ended_at": datetime.now(UTC_PLUS_8).isoformat(),
                    "status": status,
                    "action_summary": action_summary,
                    **(extra_info or {}),
                })
                self._write_json(step_info_path, step_info)
            
            # 准备 S3 上传（但不在锁内执行）
            if runtime_memory:
                should_upload = True
                actual_screenshot_path = screenshot_path or self._current_screenshot_path
            
            # 重置 step_dir 和截图路径 (但保留 node_dir 和 global_step_number)
            self._current_step_dir = None
            self._current_screenshot_path = None
        
        # 在锁外执行 S3 上传（避免死锁）
        if should_upload and runtime_memory:
            print(f"[RunLogger.end_step] Triggering S3 upload outside lock for step {step_number}")
            self._save_and_upload_step_data_no_lock(
                runtime_memory=runtime_memory,
                screenshot_path=actual_screenshot_path,
                step_number=step_number,
                step_dir=current_step_dir,
            )
    
    def append_stream_message(
        self,
        message: Dict[str, Any],
        level: str = "all",
    ):
        """
        追加流式消息到日志文件
        
        消息会根据 level 参数写入到不同层级的 stream_messages.jsonl 文件：
        - "all": 写入所有层级 (workflow, node, step)
        - "workflow": 只写入 workflow 级别
        - "node": 写入 workflow 和 node 级别
        - "step": 写入所有层级
        
        Args:
            message: 消息字典
            level: 写入层级
        """
        with self._lock:
            # 添加时间戳
            message_with_ts = {
                "timestamp": datetime.now(UTC_PLUS_8).isoformat(),
                **message,
            }
            
            # 序列化为 JSON 行
            json_line = json.dumps(message_with_ts, ensure_ascii=False) + "\n"
            
            # 根据 level 决定写入哪些文件
            targets: List[str] = []
            
            if level in ("all", "workflow", "node", "step"):
                # 总是写入 workflow 级别
                targets.append(os.path.join(self._workflow_dir, "stream_messages.jsonl"))
            
            if level in ("all", "node", "step") and self._current_node_dir:
                # 写入 node 级别
                targets.append(os.path.join(self._current_node_dir, "stream_messages.jsonl"))
            
            if level in ("all", "step") and self._current_step_dir:
                # 写入 step 级别
                targets.append(os.path.join(self._current_step_dir, "stream_messages.jsonl"))
            
            # 写入所有目标文件
            for target_path in targets:
                self._append_line(target_path, json_line)
    
    def log_json(
        self,
        data: Dict[str, Any],
        filename: str,
        level: str = "step",
    ) -> Optional[str]:
        """
        记录 JSON 数据到指定层级
        
        Args:
            data: JSON 数据
            filename: 文件名
            level: 层级 (workflow/node/step)
            
        Returns:
            文件路径
        """
        with self._lock:
            target_dir = self._get_target_dir(level)
            if not target_dir:
                return None
            
            file_path = os.path.join(target_dir, filename)
            self._write_json(file_path, data)
            return file_path
    
    def log_text(
        self,
        text: str,
        filename: str,
        level: str = "step",
    ) -> Optional[str]:
        """
        记录文本数据到指定层级
        
        Args:
            text: 文本内容
            filename: 文件名
            level: 层级 (workflow/node/step)
            
        Returns:
            文件路径
        """
        with self._lock:
            target_dir = self._get_target_dir(level)
            if not target_dir:
                return None
            
            file_path = os.path.join(target_dir, filename)
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(text)
            return file_path
    
    def get_step_dir(self) -> Optional[str]:
        """
        获取当前 step 目录，如果不存在且有当前 node 则创建
        
        Returns:
            step 目录路径，如果没有当前 node 则返回 None
        """
        if not self._current_step_dir and self._current_node_dir:
            return self.start_step()
        return self._current_step_dir
    
    def set_screenshot_path(self, screenshot_path: str):
        """
        设置当前 step 的截图路径
        
        Args:
            screenshot_path: 截图文件路径
        """
        self._current_screenshot_path = screenshot_path
    
    def save_runtime_memory(
        self,
        runtime_memory: Dict[str, Any],
        screenshot_path: Optional[str] = None,
        upload_to_s3: bool = True,
    ) -> Optional[str]:
        """
        保存运行时内存数据到本地，并可选上传到 S3
        
        runtime_memory 格式:
        {
            "Observation": "屏幕截图已获取，分辨率 3840x2160",
            "Reasoning": "Clicking on layer manager section",
            "Action": "click @ (92, 1965)",
            "is_node_completed": false,
            "current_state": {
                "iteration": 1,
                "action": {"type": "click", "button": "left", "x": 92, "y": 1965}
            },
            "node_completion_summary": "执行了 click @ (92, 1965)",
            "status": "success",
            "error_message": null,
            "processed_node_id": "step_1",
            "processed_node_type": "action"
        }
        
        Args:
            runtime_memory: 运行时内存数据
            screenshot_path: 截图路径 (可选)
            upload_to_s3: 是否上传到 S3
            
        Returns:
            本地文件路径
        """
        # 保存到本地
        local_path = self.log_json(runtime_memory, "runtime_memory.json", level="step")
        
        # 更新截图路径
        if screenshot_path:
            self._current_screenshot_path = screenshot_path
        
        # 上传到 S3
        if upload_to_s3:
            actual_screenshot_path = screenshot_path or self._current_screenshot_path
            self._save_and_upload_step_data(
                runtime_memory=runtime_memory,
                screenshot_path=actual_screenshot_path,
            )
        
        return local_path
    
    def _save_and_upload_step_data(
        self,
        runtime_memory: Dict[str, Any],
        screenshot_path: Optional[str] = None,
    ):
        """
        保存并上传 step 数据到 S3（旧方法，保留兼容性）
        注意：此方法会获取锁，不要在已持有锁的上下文中调用
        """
        self._save_and_upload_step_data_no_lock(
            runtime_memory=runtime_memory,
            screenshot_path=screenshot_path,
            step_number=self._global_step_number,
            step_dir=self._current_step_dir,
        )
    
    def _save_and_upload_step_data_no_lock(
        self,
        runtime_memory: Dict[str, Any],
        screenshot_path: Optional[str] = None,
        step_number: Optional[int] = None,
        step_dir: Optional[str] = None,
    ):
        """
        保存并上传 step 数据到 S3（不获取锁的版本）
        
        Args:
            runtime_memory: 运行时内存数据
            screenshot_path: 截图路径
            step_number: 步骤编号
            step_dir: 步骤目录
        """
        step_num = step_number or self._global_step_number
        print(f"[RunLogger._save_and_upload_step_data_no_lock] Starting for step {step_num}")
        
        # 检查是否可以上传
        if not self._s3_uploader:
            print(f"[RunLogger._save_and_upload_step_data_no_lock] No S3 uploader, skipping")
            return
        if not self.project_id or not self.chat_id:
            print(f"[RunLogger._save_and_upload_step_data_no_lock] Missing project_id or chat_id, skipping")
            return
        
        # 构建 metadata
        metadata = {
            "workflow_id": self.workflow_id,
            "workflow_run_id": self.task_id,
            "node_id": self._current_node_id,
            "node_type": self._current_node_type,
            "step": step_num,
            "ask_step": 0,  # 可以后续扩展
            "data_source": "",
            "time": datetime.now(UTC_PLUS_8).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
        
        # 保存 metadata 到本地（直接写文件，不通过 log_json 避免锁）
        if step_dir:
            print(f"[RunLogger._save_and_upload_step_data_no_lock] Saving metadata.json locally to {step_dir}")
            try:
                metadata_path = os.path.join(step_dir, "metadata.json")
                self._write_json(metadata_path, metadata)
                
                # 同时保存 runtime_memory.json
                runtime_memory_path = os.path.join(step_dir, "runtime_memory.json")
                self._write_json(runtime_memory_path, runtime_memory)
                print(f"[RunLogger._save_and_upload_step_data_no_lock] Local files saved")
            except Exception as e:
                print(f"[RunLogger._save_and_upload_step_data_no_lock] Error saving local files: {e}")
        
        # 异步上传到 S3 (fire-and-forget)
        print(f"[RunLogger._save_and_upload_step_data_no_lock] Triggering S3 fire-and-forget upload")
        try:
            self._s3_uploader.upload_step_data_fire_and_forget(
                project_id=self.project_id,
                chat_id=self.chat_id,
                workflow_run_id=self.task_id,
                step_number=step_num,
                runtime_memory=runtime_memory,
                metadata=metadata,
                screenshot_path=screenshot_path,
            )
            print(f"[RunLogger._save_and_upload_step_data_no_lock] S3 upload triggered successfully for step {step_num}")
        except Exception as e:
            print(f"[RunLogger._save_and_upload_step_data_no_lock] Failed to trigger S3 upload: {e}")
        
        print(f"[RunLogger._save_and_upload_step_data_no_lock] Completed for step {step_num}")
    
    def ensure_node(
        self,
        node_id: str,
        node_type: str = "unknown",
        node_name: str = "",
    ) -> str:
        """
        确保指定的 node 目录存在
        
        如果当前已经在该 node 中，直接返回目录路径。
        如果不在，则开始新的 node。
        
        Args:
            node_id: 节点 ID
            node_type: 节点类型
            node_name: 节点名称
            
        Returns:
            node 目录路径
        """
        with self._lock:
            if self._current_node_id == node_id and self._current_node_dir:
                return self._current_node_dir
        
        # 需要在锁外调用 start_node，因为它也会获取锁
        return self.start_node(node_id, node_type, node_name)
    
    # ==================== 辅助方法 ====================
    
    def _get_target_dir(self, level: str) -> Optional[str]:
        """根据层级获取目标目录"""
        if level == "workflow":
            return self._workflow_dir
        elif level == "node":
            return self._current_node_dir or self._workflow_dir
        elif level == "step":
            # step 级别：优先 step_dir，其次 node_dir，最后 workflow_dir
            return self._current_step_dir or self._current_node_dir or self._workflow_dir
        return None
    
    @staticmethod
    def _safe_filename(name: str) -> str:
        """将字符串转换为安全的文件名"""
        # 替换不安全字符
        unsafe_chars = ['/', '\\', ':', '*', '?', '"', '<', '>', '|', ' ']
        result = name
        for char in unsafe_chars:
            result = result.replace(char, '_')
        # 限制长度
        if len(result) > 50:
            result = result[:50]
        return result
    
    @staticmethod
    def _write_json(file_path: str, data: Dict[str, Any]):
        """写入 JSON 文件"""
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    
    @staticmethod
    def _read_json(file_path: str) -> Dict[str, Any]:
        """读取 JSON 文件"""
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)
    
    @staticmethod
    def _append_line(file_path: str, line: str):
        """追加一行到文件"""
        with open(file_path, "a", encoding="utf-8") as f:
            f.write(line)
    
    # ==================== 请求/响应落盘方法 ====================
    
    def log_incoming_request(
        self,
        request_data: Dict[str, Any],
        screenshot_base64: Optional[str] = None,
        execution_result: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Optional[str]]:
        """
        落盘完整的 API 请求数据
        
        会分别保存:
        1. incoming_request.json - 完整请求（screenshot 只保存元信息）
        2. execution_result.json - 执行结果（如有）
        
        Args:
            request_data: 请求数据（不包含已 pop 的字段）
            screenshot_base64: 截图 base64 数据（用于记录元信息）
            execution_result: 执行结果数据
            
        Returns:
            Dict 包含各文件路径:
            {
                "request_path": "...",
                "execution_result_path": "...",  # 可能为 None
            }
        """
        result_paths = {
            "request_path": None,
            "execution_result_path": None,
        }
        
        # 构建请求记录
        request_record = {
            "timestamp": datetime.now(UTC_PLUS_8).isoformat(),
            **request_data,
        }
        
        # 记录 screenshot 元信息（不保存完整 base64）
        if screenshot_base64:
            request_record["_screenshot_info"] = {
                "has_screenshot": True,
                "base64_length": len(screenshot_base64),
                "base64_preview": screenshot_base64[:100] + "..." if len(screenshot_base64) > 100 else screenshot_base64,
            }
        else:
            request_record["_screenshot_info"] = {
                "has_screenshot": False,
            }
        
        # 记录 execution_result 引用
        if execution_result:
            request_record["_has_execution_result"] = True
        
        # 保存请求到当前 step 目录
        result_paths["request_path"] = self.log_json(
            request_record, 
            "incoming_request.json", 
            level="step"
        )
        
        # 单独保存 execution_result（如果有）
        if execution_result:
            # 递归缩略所有名为 screenshot 的 base64 字段，避免 execution_result.json 体积过大
            truncated = _truncate_screenshot_in_obj(execution_result)
            execution_record = {
                "timestamp": datetime.now(UTC_PLUS_8).isoformat(),
                **(truncated if isinstance(truncated, dict) else {"data": truncated}),
            }
            result_paths["execution_result_path"] = self.log_json(
                execution_record,
                "execution_result.json",
                level="step"
            )
        
        return result_paths
    
    def log_callback_response(
        self,
        request_id: str,
        callback_data: Dict[str, Any],
        is_error: bool = False,
    ) -> Optional[str]:
        """
        落盘回调端点收到的响应数据
        
        保存到 workflow 级别的 callback_responses/ 目录
        
        Args:
            request_id: 请求 ID
            callback_data: 回调数据
            is_error: 是否为错误响应
            
        Returns:
            文件路径
        """
        # 创建 callback_responses 目录
        callback_dir = os.path.join(self._workflow_dir, "callback_responses")
        os.makedirs(callback_dir, exist_ok=True)
        
        # 构建回调记录
        timestamp = datetime.now(UTC_PLUS_8)
        callback_record = {
            "timestamp": timestamp.isoformat(),
            "request_id": request_id,
            "is_error": is_error,
            "data": callback_data,
        }
        
        # 生成文件名: callback_{request_id}_{timestamp}.json
        timestamp_str = timestamp.strftime("%H%M%S_%f")
        # 截断 request_id 避免文件名过长
        safe_request_id = self._safe_filename(request_id)[:30]
        filename = f"callback_{safe_request_id}_{timestamp_str}.json"
        
        file_path = os.path.join(callback_dir, filename)
        self._write_json(file_path, callback_record)
        
        return file_path


class StreamMessagePersister:
    """
    流式消息落盘器
    
    专门用于将流式事件持久化到文件，支持多层级落盘。
    
    使用示例:
        persister = StreamMessagePersister(run_logger)
        
        async for event in event_stream:
            # 落盘
            persister.persist(event)
            # 继续处理
            yield event
    """
    
    def __init__(self, run_logger: RunLogger):
        """
        初始化流式消息落盘器
        
        Args:
            run_logger: 运行日志管理器
        """
        self.run_logger = run_logger
        self._message_count = 0
    
    def persist(
        self,
        event: Dict[str, Any],
        level: str = "all",
    ):
        """
        持久化一个事件
        
        Args:
            event: 事件字典
            level: 落盘层级
        """
        self._message_count += 1
        
        # 添加序号
        event_with_seq = {
            "seq": self._message_count,
            **event,
        }
        
        self.run_logger.append_stream_message(event_with_seq, level=level)
    
    def persist_batch(
        self,
        events: List[Dict[str, Any]],
        level: str = "all",
    ):
        """
        批量持久化事件
        
        Args:
            events: 事件列表
            level: 落盘层级
        """
        for event in events:
            self.persist(event, level=level)
    
    @property
    def message_count(self) -> int:
        """获取已持久化的消息数量"""
        return self._message_count
