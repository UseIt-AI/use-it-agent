"""
S3 文件下载工具

用于从 S3 下载用户附件文件到本地缓存目录。

S3 路径结构:
    useit.user.demo.storage/
    └── projects/
        └── {project_id}/
            └── workspace/
                └── {relative_path}  # 如 src/test.py

本地缓存结构:
    .cache/s3_files/
    └── projects/
        └── {project_id}/
            └── workspace/
                └── {relative_path}

使用示例:
    from useit_studio.ai_run.utils.s3_downloader import S3Downloader, get_s3_downloader
    
    downloader = get_s3_downloader()
    
    # 下载单个文件
    local_path = await downloader.download_file_async(
        relative_path="src/test.py",
        project_id="e26eab30-33d1-430b-8491-bf89f8bbdd5a"
    )
    
    # 批量下载 attached_files
    attached_files = [
        {"path": "src/test.py", "name": "test.py", "type": "file"},
        {"path": "data/config.json", "name": "config.json", "type": "file"},
    ]
    updated_files = await downloader.download_attached_files(
        attached_files=attached_files,
        project_id="e26eab30-33d1-430b-8491-bf89f8bbdd5a"
    )
    # updated_files 中每个 item 会新增 local_path 字段
"""

import os
import re
import asyncio
import logging
from typing import Dict, Any, Optional, List
from concurrent.futures import ThreadPoolExecutor
import threading

logger = logging.getLogger(__name__)

# 匹配 Windows 盘符前缀，如 "C:", "c:/", "D:\\"
_WIN_DRIVE_RE = re.compile(r'^[a-zA-Z]:[\\/]?')


def _normalize_relative_path(raw_path: str, project_id: Optional[str] = None) -> str:
    """
    把 attached_files 里的 path 规范化为 S3 相对路径。

    处理场景:
    1. Windows 绝对路径，如 "C:/Users/xxx/projects/<name>/workspace/file.pdf"
    2. Windows 反斜杠路径，如 "workspace\\sub\\file.pdf"
    3. Unix 绝对路径，如 "/home/user/file.pdf"
    4. 已经是相对路径，如 "workspace/file.pdf" 或 "./src/test.py"

    规则:
    - 反斜杠统一成正斜杠
    - 去掉 Windows 盘符（C:、c:/ 等）
    - 去掉开头的 "./" 和 "/"
    - 若路径中包含 "projects/<project_id>/" 锚点，取其后段（避免双重前缀）
    - 若剩余路径仍看起来像本地绝对路径，尝试以 "workspace/" 为锚点，
      取 **包含 workspace/ 在内** 的后段（与前端/后端上传时保留 workspace/ 前缀的行为一致）
    - 兜底：取 basename（只保留文件名），避免把本地目录树当成 S3 key
    """
    if not raw_path:
        return raw_path

    # 统一分隔符
    path = raw_path.replace('\\', '/').strip()

    # 记录原始输入是否是绝对路径（盘符或 Unix 风格），用于兜底判定
    had_drive = bool(_WIN_DRIVE_RE.match(path))
    had_unix_abs = path.startswith('/')

    # 去掉 Windows 盘符
    path = _WIN_DRIVE_RE.sub('', path)

    # 去掉 ./ 与 开头的 /
    while path.startswith('./'):
        path = path[2:]
    path = path.lstrip('/')

    # 合并连续的 /（可能来自反斜杠/正斜杠混合被替换后出现 //）
    path = re.sub(r'/+', '/', path)

    was_absolute = had_drive or had_unix_abs

    # 如果规范化后已经是干净的相对路径（不以 / 开头、不包含盘符），直接返回
    def _is_clean_relative(p: str) -> bool:
        if not p:
            return False
        if _WIN_DRIVE_RE.match(p):
            return False
        return not p.startswith('/')

    # 1) 优先尝试以 "projects/<project_id>/" 作为锚点定位相对部分（去重防止双重前缀）
    if project_id:
        anchor = f"projects/{project_id}/"
        idx = path.find(anchor)
        if idx >= 0:
            candidate = path[idx + len(anchor):]
            if _is_clean_relative(candidate):
                return candidate

    # 2) 仅当原始输入是绝对路径时，才认为路径里混入了用户本地目录结构，
    #    此时按 "workspace/" 锚点截取 **包含 workspace/ 在内** 的后段，
    #    与前端 / 后端上传逻辑（保留 workspace/ 前缀）保持一致。
    #    已经是干净相对路径（如 "workspace/foo.pdf" / "src/test.py"）时不做这一步，
    #    避免把 "workspace/sub/workspace/x" 之类嵌套目录错误剪裁。
    if was_absolute:
        ws_anchor = "workspace/"
        idx = path.rfind(ws_anchor)
        if idx >= 0:
            candidate = path[idx:]  # 保留 workspace/
            if _is_clean_relative(candidate):
                return candidate

    # 3) 此时仍然看起来像本地绝对路径（含 ":" 或空段），兜底使用 basename
    if ':' in path or path.startswith('/'):
        return os.path.basename(path) or path

    # 4) 原始输入是绝对路径但没有命中任何锚点，兜底用 basename，避免把本地目录树当成 S3 key
    if was_absolute:
        return os.path.basename(path) or path

    return path

# boto3 懒加载，避免未安装时报错
_boto3 = None
_s3_client = None
_executor = None
_lock = threading.Lock()


def _get_boto3():
    """懒加载 boto3"""
    global _boto3
    if _boto3 is None:
        try:
            import boto3
            _boto3 = boto3
        except ImportError:
            raise ImportError("boto3 is required for S3 download. Install with: pip install boto3")
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
                    print("[S3Downloader] AWS credentials not configured, S3 download disabled")
                    return None
                
                try:
                    boto3 = _get_boto3()
                    from botocore.config import Config
                    
                    # 配置超时和重试
                    config = Config(
                        connect_timeout=10,
                        read_timeout=30,
                        retries={'max_attempts': 3}
                    )
                    
                    _s3_client = boto3.client(
                        's3',
                        aws_access_key_id=access_key,
                        aws_secret_access_key=secret_key,
                        region_name=os.getenv('AWS_REGION', 'us-west-2'),
                        config=config
                    )
                    print("[S3Downloader] S3 client initialized successfully")
                except Exception as e:
                    print(f"[S3Downloader] Failed to initialize S3 client: {e}")
                    return None
    return _s3_client


def _get_executor():
    """获取线程池执行器（用于异步下载）"""
    global _executor
    if _executor is None:
        with _lock:
            if _executor is None:
                _executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="s3_download_")
    return _executor


class S3Downloader:
    """
    S3 文件下载器
    
    特性:
    - 异步下载，不阻塞主流程
    - 自动创建本地目录结构
    - 支持缓存（已下载的文件可跳过）
    - 线程安全
    """
    
    def __init__(
        self,
        bucket_name: Optional[str] = None,
        local_cache_dir: str = ".cache/s3_files",
        base_prefix: str = "projects",
        workspace_folder: str = "",  # 默认为空，不添加 workspace 层级
    ):
        """
        初始化 S3 下载器
        
        Args:
            bucket_name: S3 bucket 名称，默认从环境变量 S3_BUCKET_NAME 读取
            local_cache_dir: 本地缓存根目录，默认 ".cache/s3_files"
            base_prefix: S3 路径前缀，默认 "projects"
            workspace_folder: 工作区文件夹名，默认为空（不添加额外层级）
        """
        self.bucket_name = bucket_name or os.getenv('S3_BUCKET_NAME', 'useit.user.demo.storage')
        # 移除可能的引号
        self.bucket_name = self.bucket_name.strip('"\'')
        self.local_cache_dir = local_cache_dir
        self.base_prefix = base_prefix
        self.workspace_folder = workspace_folder
        
        # 下载统计
        self._download_count = 0
        self._skip_count = 0
        self._error_count = 0
        self._lock = threading.Lock()
    
    def _build_s3_key(self, project_id: str, relative_path: str) -> str:
        """
        构建 S3 对象键
        
        路径格式: projects/{project_id}/workspace/{relative_path}
        
        Args:
            project_id: 项目 ID
            relative_path: 相对路径（如 src/test.py）
            
        Returns:
            S3 key（如 projects/xxx/workspace/src/test.py）
        """
        # 规范化路径：处理 Windows 盘符 / 反斜杠 / 绝对路径等异常输入
        clean_path = _normalize_relative_path(relative_path, project_id)
        if clean_path != relative_path:
            logger.debug(
                f"[S3Downloader] Normalized relative_path: {relative_path!r} -> {clean_path!r}"
            )
        if self.workspace_folder:
            return f"{self.base_prefix}/{project_id}/{self.workspace_folder}/{clean_path}"
        else:
            return f"{self.base_prefix}/{project_id}/{clean_path}"
    
    def _build_local_path(self, project_id: str, relative_path: str) -> str:
        """
        构建本地缓存路径
        
        路径格式: {local_cache_dir}/projects/{project_id}/workspace/{relative_path}
        
        Args:
            project_id: 项目 ID
            relative_path: 相对路径（如 src/test.py）
            
        Returns:
            本地绝对路径
        """
        # 规范化路径
        clean_path = _normalize_relative_path(relative_path, project_id)
        if self.workspace_folder:
            local_path = os.path.join(
                self.local_cache_dir,
                self.base_prefix,
                project_id,
                self.workspace_folder,
                clean_path
            )
        else:
            local_path = os.path.join(
                self.local_cache_dir,
                self.base_prefix,
                project_id,
                clean_path
            )
        # 返回绝对路径
        return os.path.abspath(local_path)
    
    def _download_file_sync(
        self,
        s3_key: str,
        local_path: str,
        force: bool = False,
    ) -> bool:
        """
        同步下载文件从 S3
        
        Args:
            s3_key: S3 对象键
            local_path: 本地保存路径
            force: 是否强制重新下载（即使本地文件已存在）
            
        Returns:
            是否成功
        """
        try:
            client = _get_s3_client()
            if client is None:
                return False
            
            # 检查本地文件是否已存在
            if not force and os.path.exists(local_path):
                # 可选：检查文件大小是否匹配
                try:
                    head_response = client.head_object(Bucket=self.bucket_name, Key=s3_key)
                    s3_size = head_response.get('ContentLength', 0)
                    local_size = os.path.getsize(local_path)
                    
                    if s3_size == local_size:
                        with self._lock:
                            self._skip_count += 1
                        self._touch_cache(local_path)
                        print(f"[S3Downloader] Skipped (cached): {local_path}")
                        return True
                except Exception:
                    # 如果 HEAD 请求失败，继续下载
                    pass
            
            # 创建目录
            os.makedirs(os.path.dirname(local_path), exist_ok=True)
            
            # 下载文件
            client.download_file(self.bucket_name, s3_key, local_path)
            
            with self._lock:
                self._download_count += 1
            
            self._touch_cache(local_path)
            print(f"[S3Downloader] Downloaded s3://{self.bucket_name}/{s3_key} -> {local_path}")
            return True
            
        except client.exceptions.NoSuchKey:
            with self._lock:
                self._error_count += 1
            print(f"[S3Downloader] File not found: s3://{self.bucket_name}/{s3_key}")
            return False
        except Exception as e:
            with self._lock:
                self._error_count += 1
            print(f"[S3Downloader] Error downloading s3://{self.bucket_name}/{s3_key}: {e}")
            return False
    
    async def download_file_async(
        self,
        relative_path: str,
        project_id: str,
        force: bool = False,
    ) -> Optional[str]:
        """
        异步下载单个文件
        
        Args:
            relative_path: 相对路径（如 src/test.py）
            project_id: 项目 ID
            force: 是否强制重新下载
            
        Returns:
            本地文件绝对路径，失败返回 None
        """
        s3_key = self._build_s3_key(project_id, relative_path)
        local_path = self._build_local_path(project_id, relative_path)
        
        loop = asyncio.get_event_loop()
        executor = _get_executor()
        
        success = await loop.run_in_executor(
            executor,
            self._download_file_sync,
            s3_key,
            local_path,
            force
        )
        
        return local_path if success else None
    
    async def download_attached_files(
        self,
        attached_files: List[Dict[str, Any]],
        project_id: str,
        force: bool = False,
    ) -> List[Dict[str, Any]]:
        """
        批量下载 attached_files，为每个文件添加 local_path 字段
        
        Args:
            attached_files: 附件列表，格式如 [{"path": "src/test.py", "name": "test.py", "type": "file"}]
            project_id: 项目 ID
            force: 是否强制重新下载
            
        Returns:
            更新后的 attached_files 列表，每个 type="file" 的项会新增 local_path 字段
            例如: [{"path": "src/test.py", "name": "test.py", "type": "file", "local_path": "/abs/path/..."}]
        """
        if not attached_files or not project_id:
            return attached_files
        
        # 过滤出需要下载的文件（type="file"）
        files_to_download = [
            f for f in attached_files 
            if f.get("type") == "file" and f.get("path")
        ]
        
        if not files_to_download:
            print(f"[S3Downloader] No files to download (total items: {len(attached_files)})")
            return attached_files
        
        print(f"[S3Downloader] Downloading {len(files_to_download)} files for project {project_id}")
        
        # 并发下载所有文件
        tasks = []
        for file_info in files_to_download:
            task = self.download_file_async(
                relative_path=file_info["path"],
                project_id=project_id,
                force=force,
            )
            tasks.append((file_info, task))
        
        # 等待所有下载完成
        results = await asyncio.gather(*[t[1] for t in tasks], return_exceptions=True)
        
        # 更新 attached_files，添加 local_path
        path_to_local = {}
        for (file_info, _), result in zip(tasks, results):
            if isinstance(result, Exception):
                print(f"[S3Downloader] Exception downloading {file_info['path']}: {result}")
                path_to_local[file_info["path"]] = None
            else:
                path_to_local[file_info["path"]] = result
        
        # 创建更新后的列表（不修改原始列表）
        updated_files = []
        for file_info in attached_files:
            updated_info = file_info.copy()
            if file_info.get("type") == "file" and file_info.get("path"):
                local_path = path_to_local.get(file_info["path"])
                if local_path:
                    updated_info["local_path"] = local_path
            updated_files.append(updated_info)
        
        # 打印统计
        success_count = sum(1 for p in path_to_local.values() if p is not None)
        print(f"[S3Downloader] Download complete: {success_count}/{len(files_to_download)} succeeded")
        
        return updated_files
    
    @staticmethod
    def _touch_cache(path: str) -> None:
        """通知 CacheManager 文件被访问，更新 LRU 时间戳"""
        try:
            from useit_studio.ai_run.utils.cache_manager import get_cache_manager
            get_cache_manager().touch(path)
        except Exception:
            pass

    def get_local_path(self, project_id: str, relative_path: str) -> str:
        """
        获取文件的本地缓存路径（不下载）
        
        Args:
            project_id: 项目 ID
            relative_path: 相对路径
            
        Returns:
            本地绝对路径
        """
        return self._build_local_path(project_id, relative_path)
    
    def file_exists_locally(self, project_id: str, relative_path: str) -> bool:
        """
        检查文件是否已在本地缓存中
        
        Args:
            project_id: 项目 ID
            relative_path: 相对路径
            
        Returns:
            文件是否存在
        """
        local_path = self._build_local_path(project_id, relative_path)
        return os.path.exists(local_path)
    
    @property
    def download_count(self) -> int:
        """已下载文件数"""
        return self._download_count
    
    @property
    def skip_count(self) -> int:
        """跳过的文件数（已缓存）"""
        return self._skip_count
    
    @property
    def error_count(self) -> int:
        """下载错误数"""
        return self._error_count
    
    def get_stats(self) -> Dict[str, int]:
        """获取下载统计"""
        return {
            "downloaded": self._download_count,
            "skipped": self._skip_count,
            "errors": self._error_count,
        }


# 全局单例
_default_downloader: Optional[S3Downloader] = None


def _get_default_cache_dir() -> str:
    """从环境变量或默认值获取缓存目录"""
    import os
    return os.getenv('S3_FILE_CACHE_DIR', '.cache/s3_files')


def get_s3_downloader(
    local_cache_dir: Optional[str] = None,
) -> S3Downloader:
    """
    获取默认的 S3 下载器实例
    
    Args:
        local_cache_dir: 可选，自定义本地缓存目录
        
    Returns:
        S3Downloader 实例
    """
    global _default_downloader
    if _default_downloader is None:
        with _lock:
            if _default_downloader is None:
                cache_dir = local_cache_dir or _get_default_cache_dir()
                _default_downloader = S3Downloader(
                    local_cache_dir=cache_dir
                )
    return _default_downloader
