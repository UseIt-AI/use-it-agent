"""
S3 异步上传工具

用于将运行时数据上传到 S3，支持 RAG 后续检索。

S3 路径结构:
    useit.user.demo.storage/
    └── projects/
        └── {project_id}/
            └── .cua/  (或 .tool_call)
                └── {chat_id}/
                    └── {workflow_run_id}/
                        └── step_{NNN}/
                            ├── runtime_memory.json
                            ├── metadata.json
                            └── image_{timestamp}.png

使用示例:
    from useit_studio.ai_run.utils.s3_uploader import S3Uploader
    
    uploader = S3Uploader()
    
    # 异步上传文件
    await uploader.upload_file_async(
        local_path="/path/to/file.json",
        s3_key="projects/xxx/.cua/yyy/zzz/step_001/runtime_memory.json"
    )
    
    # 或使用便捷方法
    await uploader.upload_step_data_async(
        project_id="xxx",
        chat_id="yyy",
        workflow_run_id="zzz",
        step_number=1,
        runtime_memory={"Observation": "...", "Action": "..."},
        metadata={"workflow_id": "...", "step": 1},
        screenshot_path="/path/to/screenshot.png"
    )
"""

import os
import json
import asyncio
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, Optional
from concurrent.futures import ThreadPoolExecutor
import threading

# boto3 懒加载，避免未安装时报错
_boto3 = None
_s3_client = None
_executor = None
_lock = threading.Lock()

UTC_PLUS_8 = timezone(timedelta(hours=8))


def _get_boto3():
    """懒加载 boto3"""
    global _boto3
    if _boto3 is None:
        try:
            import boto3
            _boto3 = boto3
        except ImportError:
            raise ImportError("boto3 is required for S3 upload. Install with: pip install boto3")
    return _boto3


def _get_s3_client():
    """获取或创建 S3 客户端（单例）"""
    global _s3_client
    if _s3_client is None:
        with _lock:
            if _s3_client is None:
                # 检查是否配置了 AWS 凭证
                access_key = os.getenv('AWS_ACCESS_KEY_ID')
                secret_key = os.getenv('AWS_SECRET_ACCESS_KEY')
                
                if not access_key or not secret_key:
                    print("[S3Uploader] AWS credentials not configured, S3 upload disabled")
                    return None
                
                try:
                    boto3 = _get_boto3()
                    from botocore.config import Config
                    
                    # 配置超时和重试
                    config = Config(
                        connect_timeout=5,
                        read_timeout=10,
                        retries={'max_attempts': 2}
                    )
                    
                    _s3_client = boto3.client(
                        's3',
                        aws_access_key_id=access_key,
                        aws_secret_access_key=secret_key,
                        region_name=os.getenv('AWS_REGION', 'us-west-2'),
                        config=config
                    )
                    print("[S3Uploader] S3 client initialized successfully")
                except Exception as e:
                    print(f"[S3Uploader] Failed to initialize S3 client: {e}")
                    return None
    return _s3_client


def _get_executor():
    """获取线程池执行器（用于异步上传）"""
    global _executor
    if _executor is None:
        with _lock:
            if _executor is None:
                _executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="s3_upload_")
    return _executor


class S3Uploader:
    """
    S3 异步上传器
    
    特性:
    - 异步上传，不阻塞主流程
    - 自动构建 S3 路径
    - 支持 JSON 和图片文件
    - 线程安全
    - 预初始化 S3 客户端（在后台线程）
    """
    
    def __init__(
        self,
        bucket_name: Optional[str] = None,
        base_prefix: str = "projects",
        node_type_folder: str = ".cua",  # .cua 或 .tool_call
        lazy_init: bool = True,  # 是否延迟初始化 S3 客户端
    ):
        """
        初始化 S3 上传器
        
        Args:
            bucket_name: S3 bucket 名称，默认从环境变量 S3_BUCKET_NAME 读取
            base_prefix: S3 路径前缀，默认 "projects"
            node_type_folder: 节点类型文件夹，默认 ".cua"
            lazy_init: 是否延迟初始化 S3 客户端，默认 True
        """
        self.bucket_name = bucket_name or os.getenv('S3_BUCKET_NAME', 'useit.user.demo.storage')
        # 移除可能的引号
        self.bucket_name = self.bucket_name.strip('"\'')
        self.base_prefix = base_prefix
        self.node_type_folder = node_type_folder
        
        # 上传统计
        self._upload_count = 0
        self._error_count = 0
        self._lock = threading.Lock()
        
        # 在后台线程预初始化 S3 客户端（避免阻塞主线程）
        if not lazy_init:
            executor = _get_executor()
            executor.submit(_get_s3_client)
    
    def _build_s3_key(
        self,
        project_id: str,
        chat_id: str,
        workflow_run_id: str,
        step_number: int,
        filename: str,
    ) -> str:
        """
        构建 S3 对象键
        
        路径格式: projects/{project_id}/.cua/{chat_id}/{workflow_run_id}/step_{NNN}/{filename}
        """
        step_folder = f"step_{step_number:03d}"
        return f"{self.base_prefix}/{project_id}/{self.node_type_folder}/{chat_id}/{workflow_run_id}/{step_folder}/{filename}"
    
    def _build_tagging_str(self) -> str:
        """构建 S3 Object Tagging 字符串（用于 Lifecycle 自动过期）"""
        if self.node_type_folder in (".cua", ".tool_call"):
            return "lifecycle=auto-expire"
        return ""
    
    def _upload_file_sync(
        self,
        local_path: str,
        s3_key: str,
        content_type: Optional[str] = None,
    ) -> bool:
        """
        同步上传文件到 S3
        
        Args:
            local_path: 本地文件路径
            s3_key: S3 对象键
            content_type: 内容类型
            
        Returns:
            是否成功
        """
        try:
            client = _get_s3_client()
            if client is None:
                return False
            
            extra_args = {}
            if content_type:
                extra_args['ContentType'] = content_type
            elif local_path.endswith('.json'):
                extra_args['ContentType'] = 'application/json'
            elif local_path.endswith('.png'):
                extra_args['ContentType'] = 'image/png'
            elif local_path.endswith('.jpg') or local_path.endswith('.jpeg'):
                extra_args['ContentType'] = 'image/jpeg'
            
            tagging = self._build_tagging_str()
            if tagging:
                extra_args['Tagging'] = tagging
            
            client.upload_file(
                local_path,
                self.bucket_name,
                s3_key,
                ExtraArgs=extra_args if extra_args else None
            )
            
            with self._lock:
                self._upload_count += 1
            
            print(f"[S3Uploader] Uploaded {local_path} -> s3://{self.bucket_name}/{s3_key}")
            return True
            
        except Exception as e:
            with self._lock:
                self._error_count += 1
            print(f"[S3Uploader] Error uploading {local_path} to s3://{self.bucket_name}/{s3_key}: {e}")
            return False
    
    def _upload_json_sync(
        self,
        data: Dict[str, Any],
        s3_key: str,
    ) -> bool:
        """
        同步上传 JSON 数据到 S3
        
        Args:
            data: JSON 数据
            s3_key: S3 对象键
            
        Returns:
            是否成功
        """
        try:
            client = _get_s3_client()
            if client is None:
                return False
            
            json_bytes = json.dumps(data, ensure_ascii=False, indent=2).encode('utf-8')
            
            put_kwargs = {
                'Bucket': self.bucket_name,
                'Key': s3_key,
                'Body': json_bytes,
                'ContentType': 'application/json',
            }
            tagging = self._build_tagging_str()
            if tagging:
                put_kwargs['Tagging'] = tagging
            
            client.put_object(**put_kwargs)
            
            with self._lock:
                self._upload_count += 1
            
            print(f"[S3Uploader] Uploaded JSON -> s3://{self.bucket_name}/{s3_key}")
            return True
            
        except Exception as e:
            with self._lock:
                self._error_count += 1
            print(f"[S3Uploader] Error uploading JSON to s3://{self.bucket_name}/{s3_key}: {e}")
            return False
    
    async def upload_file_async(
        self,
        local_path: str,
        s3_key: str,
        content_type: Optional[str] = None,
    ) -> bool:
        """
        异步上传文件到 S3
        
        Args:
            local_path: 本地文件路径
            s3_key: S3 对象键
            content_type: 内容类型
            
        Returns:
            是否成功
        """
        loop = asyncio.get_event_loop()
        executor = _get_executor()
        return await loop.run_in_executor(
            executor,
            self._upload_file_sync,
            local_path,
            s3_key,
            content_type
        )
    
    async def upload_json_async(
        self,
        data: Dict[str, Any],
        s3_key: str,
    ) -> bool:
        """
        异步上传 JSON 数据到 S3
        
        Args:
            data: JSON 数据
            s3_key: S3 对象键
            
        Returns:
            是否成功
        """
        loop = asyncio.get_event_loop()
        executor = _get_executor()
        return await loop.run_in_executor(
            executor,
            self._upload_json_sync,
            data,
            s3_key
        )
    
    async def upload_step_data_async(
        self,
        project_id: str,
        chat_id: str,
        workflow_run_id: str,
        step_number: int,
        runtime_memory: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        screenshot_path: Optional[str] = None,
    ) -> Dict[str, bool]:
        """
        异步上传一个 step 的所有数据
        
        Args:
            project_id: 项目 ID
            chat_id: 聊天 ID
            workflow_run_id: 工作流运行 ID
            step_number: 步骤编号
            runtime_memory: 运行时内存数据
            metadata: 元数据
            screenshot_path: 截图本地路径
            
        Returns:
            各文件上传结果 {"runtime_memory.json": True, "metadata.json": True, "image_xxx.png": True}
        """
        results = {}
        tasks = []
        
        # 上传 runtime_memory.json
        if runtime_memory:
            s3_key = self._build_s3_key(
                project_id, chat_id, workflow_run_id, step_number, "runtime_memory.json"
            )
            tasks.append(("runtime_memory.json", self.upload_json_async(runtime_memory, s3_key)))
        
        # 上传 metadata.json
        if metadata:
            s3_key = self._build_s3_key(
                project_id, chat_id, workflow_run_id, step_number, "metadata.json"
            )
            tasks.append(("metadata.json", self.upload_json_async(metadata, s3_key)))
        
        # 上传截图
        if screenshot_path and os.path.exists(screenshot_path):
            timestamp = datetime.now(UTC_PLUS_8).strftime("%Y%m%d_%H%M%S")
            filename = f"image_{timestamp}.png"
            s3_key = self._build_s3_key(
                project_id, chat_id, workflow_run_id, step_number, filename
            )
            tasks.append((filename, self.upload_file_async(screenshot_path, s3_key)))
        
        # 并发执行所有上传任务
        if tasks:
            task_names = [t[0] for t in tasks]
            task_coros = [t[1] for t in tasks]
            upload_results = await asyncio.gather(*task_coros, return_exceptions=True)
            
            for name, result in zip(task_names, upload_results):
                if isinstance(result, Exception):
                    results[name] = False
                    print(f"[S3Uploader] Exception uploading {name}: {result}")
                else:
                    results[name] = result
        
        return results
    
    def upload_step_data_fire_and_forget(
        self,
        project_id: str,
        chat_id: str,
        workflow_run_id: str,
        step_number: int,
        runtime_memory: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        screenshot_path: Optional[str] = None,
    ):
        """
        Fire-and-forget 方式上传 step 数据
        
        不等待上传完成，适合在同步代码中调用。
        
        Args:
            project_id: 项目 ID
            chat_id: 聊天 ID
            workflow_run_id: 工作流运行 ID
            step_number: 步骤编号
            runtime_memory: 运行时内存数据
            metadata: 元数据
            screenshot_path: 截图本地路径
        """
        # 先检查 S3 客户端是否可用
        if _get_s3_client() is None:
            print(f"[S3Uploader] S3 client not available, skipping upload for step {step_number}")
            return
        
        executor = _get_executor()
        
        def _upload_all():
            try:
                # 上传 runtime_memory.json
                if runtime_memory:
                    s3_key = self._build_s3_key(
                        project_id, chat_id, workflow_run_id, step_number, "runtime_memory.json"
                    )
                    self._upload_json_sync(runtime_memory, s3_key)
                
                # 上传 metadata.json
                if metadata:
                    s3_key = self._build_s3_key(
                        project_id, chat_id, workflow_run_id, step_number, "metadata.json"
                    )
                    self._upload_json_sync(metadata, s3_key)
                
                # 上传截图
                if screenshot_path and os.path.exists(screenshot_path):
                    timestamp = datetime.now(UTC_PLUS_8).strftime("%Y%m%d_%H%M%S")
                    filename = f"image_{timestamp}.png"
                    s3_key = self._build_s3_key(
                        project_id, chat_id, workflow_run_id, step_number, filename
                    )
                    self._upload_file_sync(screenshot_path, s3_key)
                    
                print(f"[S3Uploader] Step {step_number} upload completed")
            except Exception as e:
                print(f"[S3Uploader] Error in fire-and-forget upload for step {step_number}: {e}")
        
        executor.submit(_upload_all)
    
    @property
    def upload_count(self) -> int:
        """已上传文件数"""
        return self._upload_count
    
    @property
    def error_count(self) -> int:
        """上传错误数"""
        return self._error_count
    
    def cleanup_chat_data_fire_and_forget(
        self,
        project_id: str,
        chat_id: str,
    ):
        """
        Fire-and-forget 清理 .cua/{chat_id}/ 下所有文件
        
        工作流完成后调用，异步删除该 chat 下的所有运行时数据（runtime_memory、metadata、截图等）。
        
        Args:
            project_id: 项目 ID
            chat_id: 聊天 ID
        """
        if _get_s3_client() is None:
            print(f"[S3Uploader] S3 client not available, skipping cleanup for chat {chat_id}")
            return
        
        executor = _get_executor()
        prefix = f"{self.base_prefix}/{project_id}/{self.node_type_folder}/{chat_id}/"
        
        def _cleanup():
            try:
                client = _get_s3_client()
                if client is None:
                    return
                
                paginator = client.get_paginator("list_objects_v2")
                keys_to_delete = []
                for page in paginator.paginate(Bucket=self.bucket_name, Prefix=prefix):
                    for obj in page.get("Contents", []):
                        keys_to_delete.append({"Key": obj["Key"]})
                
                if not keys_to_delete:
                    print(f"[S3Uploader] No files to clean up under {prefix}")
                    return
                
                for i in range(0, len(keys_to_delete), 1000):
                    batch = keys_to_delete[i:i + 1000]
                    client.delete_objects(
                        Bucket=self.bucket_name,
                        Delete={"Objects": batch},
                    )
                
                print(f"[S3Uploader] Cleaned up {len(keys_to_delete)} .cua files under {prefix}")
            except Exception as e:
                print(f"[S3Uploader] Error cleaning up {prefix}: {e}")
        
        executor.submit(_cleanup)
    
    def get_s3_url(
        self,
        project_id: str,
        chat_id: str,
        workflow_run_id: str,
        step_number: int,
        filename: str,
    ) -> str:
        """
        获取 S3 URL
        
        Returns:
            s3://{bucket}/{key} 格式的 URL
        """
        s3_key = self._build_s3_key(project_id, chat_id, workflow_run_id, step_number, filename)
        return f"s3://{self.bucket_name}/{s3_key}"


# 全局单例
_default_uploader: Optional[S3Uploader] = None


def get_s3_uploader() -> S3Uploader:
    """获取默认的 S3 上传器实例"""
    global _default_uploader
    if _default_uploader is None:
        with _lock:
            if _default_uploader is None:
                _default_uploader = S3Uploader()
    return _default_uploader
