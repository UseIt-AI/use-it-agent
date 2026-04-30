"""
File System Tool - 文件系统工具

通过 AWS S3 读取项目文件，支持列出和读取项目目录中的文件。
使用 CloudFront 为二进制文件生成下载链接。

主要功能：
1. list - 列出指定路径下的文件（文件名、大小、类型等）
2. read - 读取文件内容（文本文件返回内容，图片文件可多模态转文本，其它二进制返回 CloudFront URL）

限制：
- 单次操作最多处理 20 个文件
- 单个文本文件最大读取 1MB
- 图片文件会尝试通过多模态模型转文本
- 其它二进制文件返回下载链接

注意：
- 本工具使用同步方式调用 S3 API，以兼容 agent 中的 tool.invoke() 同步调用方式
- project_id 由 agent 在调用时注入到 tool_args 中（与 RAG 工具一致）

S3 路径结构:
    projects/{project_id}/outputs/{filename}
"""

import os
import asyncio
import base64
from typing import Dict, Any, Optional, List

from langchain_core.tools import BaseTool as LangChainBaseTool, tool
from pydantic import BaseModel, Field

from useit_studio.ai_run.utils.logger_utils import LoggerUtils
from useit_studio.ai_run.llm_utils import call_llm

logger = LoggerUtils(component_name="FileSystemTool")


# ==================== 常量定义 ====================

# 文本文件扩展名（可直接读取内容）
TEXT_EXTENSIONS = {
    '.md', '.txt', '.json', '.csv', '.xml', '.html', '.htm',
    '.yaml', '.yml', '.log', '.py', '.js', '.ts', '.css', '.sql',
    '.rst', '.ini', '.cfg', '.toml', '.env', '.sh', '.bat',
}

# 图片文件扩展名（支持多模态转换）
IMAGE_EXTENSIONS = {
    '.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp', '.tiff'
}

# 单次操作最大文件数量
MAX_FILES_LIMIT = 20

# 单个文件最大读取大小 (字节)
MAX_FILE_SIZE = 1 * 1024 * 1024  # 1MB

# 单个图片最大读取大小 (字节) - 过大时回退为下载链接
MAX_IMAGE_SIZE = 10 * 1024 * 1024  # 10MB


# ==================== File System 工具输入 Schema ====================

class FileSystemInput(BaseModel):
    """File System 工具输入 Schema"""
    action: str = Field(
        description=(
            "Action to perform: "
            "'list' to list files in a directory, "
            "'read' to read file contents"
        )
    )
    path: str = Field(
        default="outputs/",
        description=(
            "Path relative to the project root. "
            "For 'list': directory prefix (e.g., 'outputs/'). "
            "For 'read': specific file path (e.g., 'outputs/result.md') "
            "or directory prefix to read all files in that directory."
        )
    )
    max_files: int = Field(
        default=20,
        description="Maximum number of files to list or read (1-20, default: 20)"
    )
    # agent 会自动注入以下字段（与 RAGSearchInput 一致）
    project_id: Optional[str] = Field(
        default=None,
        description="Project ID for scoping the file access"
    )
    chat_id: Optional[str] = Field(
        default=None,
        description="Chat ID (injected by agent)"
    )


# ==================== File System 工具实现 ====================

class FileSystemTool:
    """
    文件系统工具 - 通过 S3 读取项目文件
    
    功能：
    - 列出项目目录中的文件（名称、大小、修改时间、类型）
    - 读取文本文件内容（md, txt, json, csv 等）
    - 图片文件可通过多模态模型转为文本
    - 为其它二进制文件（PDF 等）生成 CloudFront 下载链接
    
    特点：
    - 最多一次处理 20 个文件
    - 同步调用 S3 API（兼容 agent 的 tool.invoke 调用方式）
    - 自动识别文本/二进制文件
    - project_id 由 agent 在调用时注入
    """
    
    name: str = "file_system"
    description: str = (
        "Access the project file system to list and read files. "
        "Use this to explore output files and read their contents."
    )
    
    def __init__(
        self,
        bucket_name: str = "",
        cloudfront_domain: str = "",
        aws_access_key_id: str = "",
        aws_secret_access_key: str = "",
        aws_region: str = "us-west-2",
        max_files: int = 20,
    ):
        """
        初始化文件系统工具
        
        Args:
            bucket_name: S3 bucket 名称
            cloudfront_domain: CloudFront 域名（用于生成下载链接）
            aws_access_key_id: AWS 访问密钥 ID
            aws_secret_access_key: AWS 秘密访问密钥
            aws_region: AWS 区域
            max_files: 单次操作最大文件数（默认 20，最大 20）
        """
        self.bucket_name = (
            bucket_name
            or os.getenv('S3_BUCKET_NAME', 'useit.user.demo.storage')
        ).strip('"\'')
        self.cloudfront_domain = (
            cloudfront_domain
            or os.getenv('CLOUDFRONT_DOMAIN', '')
        ).strip('"\'')
        self.aws_access_key_id = aws_access_key_id or os.getenv('AWS_ACCESS_KEY_ID', '')
        self.aws_secret_access_key = aws_secret_access_key or os.getenv('AWS_SECRET_ACCESS_KEY', '')
        self.aws_region = aws_region or os.getenv('AWS_REGION', 'us-west-2')
        self.max_files = min(max_files, MAX_FILES_LIMIT)
        
        self._s3_client = None
        
        logger.logger.info(
            f"[FileSystemTool] Initialized: "
            f"bucket={self.bucket_name}, cloudfront={self.cloudfront_domain}"
        )
    
    # ==================== S3 客户端 ====================
    
    def _get_s3_client(self):
        """获取或创建 S3 客户端（懒加载）"""
        if self._s3_client is None:
            if not self.aws_access_key_id or not self.aws_secret_access_key:
                raise RuntimeError(
                    "AWS credentials not configured. "
                    "Set AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY."
                )
            try:
                import boto3
                from botocore.config import Config
                
                config = Config(
                    connect_timeout=5,
                    read_timeout=30,
                    retries={'max_attempts': 2}
                )
                
                self._s3_client = boto3.client(
                    's3',
                    aws_access_key_id=self.aws_access_key_id,
                    aws_secret_access_key=self.aws_secret_access_key,
                    region_name=self.aws_region,
                    config=config,
                )
                logger.logger.info("[FileSystemTool] S3 client created successfully")
            except Exception as e:
                logger.logger.error(f"[FileSystemTool] Failed to create S3 client: {e}")
                raise
        return self._s3_client
    
    # ==================== 辅助方法 ====================
    
    def _build_s3_prefix(self, path: str, project_id: Optional[str] = None) -> str:
        """
        构建完整的 S3 前缀路径
        
        将相对路径转换为: projects/{project_id}/{path}
        
        Args:
            path: 相对路径
            project_id: 项目 ID（由 agent 注入）
        """
        # 规范化：处理 Windows 盘符 / 反斜杠 / 绝对路径等异常输入，
        # 避免 LLM 或上游拼入本地绝对路径导致非法 S3 key。
        try:
            from useit_studio.ai_run.utils.s3_downloader import _normalize_relative_path
            normalized = _normalize_relative_path(path or "", project_id)
        except Exception:
            normalized = (path or "").lstrip('/')

        if project_id:
            return f"projects/{project_id}/{normalized}"
        return normalized
    
    def _get_cloudfront_url(self, s3_key: str) -> str:
        """生成文件的 CloudFront 下载 URL"""
        if self.cloudfront_domain:
            return f"https://{self.cloudfront_domain}/{s3_key}"
        return f"s3://{self.bucket_name}/{s3_key}"
    
    def _is_text_file(self, key: str) -> bool:
        """判断是否为可直接读取内容的文本文件"""
        ext = os.path.splitext(key)[1].lower()
        return ext in TEXT_EXTENSIONS

    def _is_image_file(self, key: str) -> bool:
        """判断是否为支持多模态转换的图片文件"""
        ext = os.path.splitext(key)[1].lower()
        return ext in IMAGE_EXTENSIONS
    
    def _extract_relative_path(self, s3_key: str, project_id: Optional[str] = None) -> str:
        """从 S3 key 中提取项目内的相对路径"""
        project_prefix = f"projects/{project_id}/" if project_id else ""
        if project_prefix and s3_key.startswith(project_prefix):
            return s3_key[len(project_prefix):]
        return s3_key

    def _run_async(self, coro):
        """在同步上下文中安全执行异步协程"""
        try:
            loop = asyncio.get_event_loop()
            return loop.run_until_complete(coro)
        except RuntimeError:
            return asyncio.run(coro)

    def _convert_image_to_text(self, image_bytes: bytes, relative_path: str) -> str:
        """
        使用 llm_utils 调用多模态模型将图片转换为文本。
        默认模型为 gpt-4.1-mini（可通过环境变量 FILE_SYSTEM_IMAGE_MODEL 覆盖）。
        """
        model_name = os.getenv("FILE_SYSTEM_IMAGE_MODEL", "gpt-4.1-mini")
        mime_type = "image/png"
        ext = os.path.splitext(relative_path)[1].lower()
        if ext in {".jpg", ".jpeg"}:
            mime_type = "image/jpeg"
        elif ext == ".gif":
            mime_type = "image/gif"
        elif ext == ".webp":
            mime_type = "image/webp"
        elif ext == ".bmp":
            mime_type = "image/bmp"
        elif ext == ".tiff":
            mime_type = "image/tiff"

        image_base64 = base64.b64encode(image_bytes).decode("utf-8")
        image_data_url = f"data:{mime_type};base64,{image_base64}"
        prompt = (
            "You are processing images from a user-specified directory. "
            f"Current image path: {relative_path}. Extract all readable text from this image in full, "
            "and output clean structured plain text only. "
            "If the image has little or no text, provide a brief visual summary."
        )

        async def _call_image_model():
            return await call_llm(
                messages=[prompt, image_data_url],
                model=model_name,
                temperature=0.0,
            )

        response = self._run_async(_call_image_model())
        content = (response.content or "").strip()
        if not content:
            return "[Image converted, but model returned empty content.]"
        return content
    
    @staticmethod
    def _format_size(size_bytes: int) -> str:
        """将字节数格式化为人类可读的大小"""
        if size_bytes < 1024:
            return f"{size_bytes} B"
        elif size_bytes < 1024 * 1024:
            return f"{size_bytes / 1024:.1f} KB"
        else:
            return f"{size_bytes / (1024 * 1024):.1f} MB"
    
    # ==================== 工厂方法 ====================
    
    @classmethod
    def from_config(
        cls,
        config: Dict[str, Any],
        api_keys: Optional[Dict[str, str]] = None,
    ) -> "FileSystemTool":
        """
        从配置创建实例
        
        Args:
            config: 工具配置字典
                - max_files: 最大文件数 (default: 20)
            api_keys: API 密钥字典（主要用于 AWS 凭证，可选，会回退到环境变量）
        """
        api_keys = api_keys or {}
        
        return cls(
            bucket_name=api_keys.get("S3_BUCKET_NAME", "") or config.get("bucket_name", ""),
            cloudfront_domain=api_keys.get("CLOUDFRONT_DOMAIN", "") or config.get("cloudfront_domain", ""),
            aws_access_key_id=api_keys.get("AWS_ACCESS_KEY_ID", ""),
            aws_secret_access_key=api_keys.get("AWS_SECRET_ACCESS_KEY", ""),
            aws_region=api_keys.get("AWS_REGION", "us-west-2"),
            max_files=config.get("max_files", 20),
        )
    
    # ==================== 列出文件（同步）====================
    
    def _list_files_sync(
        self, prefix: str, max_files: int, project_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        同步列出 S3 指定前缀下的文件
        
        Args:
            prefix: 相对路径前缀 (如 "outputs/")
            max_files: 最大返回文件数
            project_id: 项目 ID
            
        Returns:
            文件信息列表
        """
        client = self._get_s3_client()
        s3_prefix = self._build_s3_prefix(prefix, project_id)
        
        logger.logger.info(f"[FileSystemTool] Listing files at: s3://{self.bucket_name}/{s3_prefix}")
        
        files = []
        continuation_token = None
        
        while len(files) < max_files:
            kwargs = {
                'Bucket': self.bucket_name,
                'Prefix': s3_prefix,
                'MaxKeys': min(max_files - len(files), 1000),
            }
            if continuation_token:
                kwargs['ContinuationToken'] = continuation_token
            
            response = client.list_objects_v2(**kwargs)
            
            for obj in response.get('Contents', []):
                key = obj['Key']
                # 跳过目录标记
                if key.endswith('/'):
                    continue
                
                relative_path = self._extract_relative_path(key, project_id)
                last_modified = obj.get('LastModified')
                
                files.append({
                    'path': relative_path,
                    's3_key': key,
                    'size': obj.get('Size', 0),
                    'last_modified': last_modified.isoformat() if last_modified else '',
                    'is_text': self._is_text_file(key),
                    'url': self._get_cloudfront_url(key),
                })
                
                if len(files) >= max_files:
                    break
            
            if not response.get('IsTruncated', False):
                break
            continuation_token = response.get('NextContinuationToken')
        
        logger.logger.info(f"[FileSystemTool] Listed {len(files)} files at prefix: {s3_prefix}")
        return files
    
    # ==================== 读取文件（同步）====================
    
    def _read_single_file_sync(
        self, s3_key: str, project_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        同步读取单个 S3 文件
        
        文本文件返回内容，二进制文件或大文件返回 CloudFront URL。
        
        Args:
            s3_key: 完整的 S3 对象键
            project_id: 项目 ID（用于提取相对路径）
            
        Returns:
            文件读取结果
        """
        client = self._get_s3_client()
        relative_path = self._extract_relative_path(s3_key, project_id)
        
        try:
            response = client.get_object(
                Bucket=self.bucket_name,
                Key=s3_key,
            )
            
            size = response.get('ContentLength', 0)
            
            if self._is_text_file(s3_key) and size <= MAX_FILE_SIZE:
                # 文本文件且不超过大小限制：读取内容
                content = response['Body'].read().decode('utf-8', errors='replace')
                return {
                    'path': relative_path,
                    'type': 'text',
                    'content': content,
                    'size': size,
                    'url': self._get_cloudfront_url(s3_key),
                }
            elif self._is_image_file(s3_key) and size <= MAX_IMAGE_SIZE:
                # 图片文件：通过多模态模型转换为文本
                try:
                    image_bytes = response['Body'].read()
                    converted_text = self._convert_image_to_text(image_bytes, relative_path)
                    return {
                        'path': relative_path,
                        'type': 'image_text',
                        'content': converted_text,
                        'size': size,
                        'url': self._get_cloudfront_url(s3_key),
                    }
                except Exception as e:
                    logger.logger.warning(
                        f"[FileSystemTool] Image convert failed for {s3_key}, fallback to binary: {e}"
                    )
                    url = self._get_cloudfront_url(s3_key)
                    return {
                        'path': relative_path,
                        'type': 'binary',
                        'content': f"[Image convert failed. Download: {url}]",
                        'size': size,
                        'url': url,
                    }
            else:
                # 二进制文件或大文件：返回下载链接
                response['Body'].close()
                url = self._get_cloudfront_url(s3_key)
                return {
                    'path': relative_path,
                    'type': 'binary',
                    'content': f"[Binary file or file too large ({self._format_size(size)}). Download: {url}]",
                    'size': size,
                    'url': url,
                }
        except Exception as e:
            error_str = str(e)
            if "NoSuchKey" in error_str or "Not Found" in error_str:
                logger.logger.warning(f"[FileSystemTool] File not found: {s3_key}")
                return {
                    'path': relative_path,
                    'type': 'error',
                    'content': f"File not found: {relative_path}",
                    'size': 0,
                    'url': '',
                }
            logger.logger.error(f"[FileSystemTool] Error reading {s3_key}: {e}")
            return {
                'path': relative_path,
                'type': 'error',
                'content': f"Error reading file: {error_str}",
                'size': 0,
                'url': '',
            }
    
    def _read_files_by_prefix_sync(
        self, prefix: str, max_files: int, project_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        同步读取指定前缀下所有文件的内容
        
        先列出文件，再依次读取每个文件。
        """
        files = self._list_files_sync(prefix, max_files, project_id)
        
        results = []
        for file_info in files:
            result = self._read_single_file_sync(file_info['s3_key'], project_id)
            results.append(result)
        
        return results
    
    # ==================== 同步调用入口（供 LangChain tool.invoke 使用）====================
    
    def invoke_sync(
        self,
        action: str = "list",
        path: str = "outputs/",
        max_files: int = 20,
        project_id: Optional[str] = None,
    ) -> str:
        """
        同步调用工具，返回格式化文本（供 LLM 阅读）
        
        此方法为 LangChain tool.invoke() 的同步入口，
        直接调用同步的 S3 API，不涉及 asyncio。
        
        Args:
            action: 操作类型 ("list" 或 "read")
            path: 相对路径
            max_files: 最大文件数
            project_id: 项目 ID（由 agent 注入）
            
        Returns:
            格式化的文本结果
        """
        max_files = min(max_files, self.max_files, MAX_FILES_LIMIT)
        
        try:
            if action == "list":
                files = self._list_files_sync(path, max_files, project_id)
                data = {
                    "action": "list", "path": path,
                    "files": files, "total_files": len(files),
                }
                return self._format_list_for_llm(data)
            
            elif action == "read":
                _, ext = os.path.splitext(path)
                if ext:
                    # 具体文件
                    s3_key = self._build_s3_prefix(path, project_id)
                    result = self._read_single_file_sync(s3_key, project_id)
                    data = {
                        "action": "read", "path": path,
                        "files": [result], "total_files": 1,
                    }
                else:
                    # 目录前缀
                    results = self._read_files_by_prefix_sync(path, max_files, project_id)
                    data = {
                        "action": "read", "path": path,
                        "files": results, "total_files": len(results),
                    }
                return self._format_read_for_llm(data)
            
            else:
                return f"Unknown action: '{action}'. Supported actions: 'list', 'read'."
        
        except Exception as e:
            logger.logger.error(f"[FileSystemTool] Error: {e}", exc_info=True)
            return f"Error accessing file system: {str(e)}"
    
    # ==================== 格式化方法 ====================
    
    def _format_list_for_llm(self, data: Dict[str, Any]) -> str:
        """将列表结果格式化为 LLM 可读的文本"""
        files = data.get("files", [])
        path = data.get("path", "")
        
        if not files:
            return f"No files found at path: '{path}'"
        
        lines = [f"**Found {len(files)} file(s) at '{path}':**\n"]
        
        for i, f in enumerate(files, 1):
            size_str = self._format_size(f.get('size', 0))
            type_icon = "text" if f.get('is_text') else "binary"
            lines.append(
                f"{i}. [{type_icon}] `{f['path']}` ({size_str})"
            )
            if f.get('last_modified'):
                lines.append(f"   Last modified: {f['last_modified']}")
        
        return "\n".join(lines)
    
    def _format_read_for_llm(self, data: Dict[str, Any]) -> str:
        """将读取结果格式化为 LLM 可读的文本"""
        files = data.get("files", [])
        path = data.get("path", "")
        
        if not files:
            return f"No files found at path: '{path}'"
        
        lines = [f"**Read {len(files)} file(s) from '{path}':**\n"]
        
        for i, f in enumerate(files, 1):
            size_str = self._format_size(f.get('size', 0))
            file_path = f.get('path', 'unknown')
            lines.append(f"### [{i}] {file_path} ({size_str})")
            
            content = f.get('content', '')
            file_type = f.get('type', 'unknown')
            
            if file_type == 'text':
                # 截断过长的内容
                if len(content) > 3000:
                    content = content[:3000] + "\n... (truncated, full file available via URL)"
                lines.append(f"```\n{content}\n```")
            elif file_type == 'image_text':
                if len(content) > 3000:
                    content = content[:3000] + "\n... (truncated)"
                lines.append("Converted from image by multimodal model:")
                lines.append(f"```\n{content}\n```")
                if f.get('url'):
                    lines.append(f"Original image URL: {f['url']}")
            elif file_type == 'binary':
                lines.append(content)
            else:
                # error
                lines.append(f"**Error:** {content}")
            
            lines.append("")
        
        return "\n".join(lines)
    
    # ==================== LangChain 工具转换 ====================
    
    def as_langchain_tool(self) -> LangChainBaseTool:
        """
        转换为 LangChain 工具
        
        注意：使用同步 def（非 async def），以兼容 agent 中的
        tool.invoke() 同步调用方式。project_id 由 agent 自动
        注入到 tool_args，与 RAG 工具的处理方式一致。
        """
        fs_tool = self
        
        @tool("file_system", args_schema=FileSystemInput)
        def file_system(
            action: str = "list",
            path: str = "outputs/",
            max_files: int = 20,
            project_id: Optional[str] = None,
            chat_id: Optional[str] = None,
        ) -> str:
            """
            Access the project file system to list and read files stored in cloud storage (S3).
            
            Use this tool when you need to:
            - Browse files in the project storage (e.g., output documents)
            - Read document contents (markdown, text, JSON, CSV, etc.)
            - Get download links for binary files (images, PDFs, etc.)
            
            Supported actions:
            - 'list': List files at a given path. Returns file names, sizes, and types.
            - 'read': Read file contents. If path points to a specific file, reads that file.
                      If path is a directory prefix (e.g., 'outputs/'), reads ALL files 
                      in that directory (up to max_files).
            
            Common paths:
            - 'outputs/' - Project output files
            
            Examples:
            - List all output files: action="list", path="outputs/"
            - Read a specific file: action="read", path="outputs/report_20250210.md"
            - Read all output files: action="read", path="outputs/", max_files=20
            
            Args:
                action: 'list' to list files, 'read' to read file contents
                path: Relative path in the project (e.g., 'outputs/', 'outputs/file.md')
                max_files: Maximum number of files to return (1-20, default: 20)
                project_id: Project ID (automatically injected, do not set manually)
                chat_id: Chat ID (automatically injected, do not set manually)
            """
            return fs_tool.invoke_sync(
                action=action,
                path=path,
                max_files=max_files,
                project_id=project_id,
            )
        
        return file_system
    
    # ==================== 清理 ====================
    
    async def close(self):
        """关闭资源"""
        pass


# ==================== 工厂函数 ====================

def create_file_system_tool(
    config: Dict[str, Any],
    api_keys: Optional[Dict[str, str]] = None,
) -> LangChainBaseTool:
    """
    创建 File System LangChain 工具
    
    Args:
        config: File System 配置
            - max_files: 单次最大文件数 (default: 20)
        api_keys: API 密钥字典（AWS 凭证可选，会回退到环境变量）
        
    Returns:
        LangChain 工具实例
    """
    fs = FileSystemTool.from_config(config, api_keys)
    return fs.as_langchain_tool()
