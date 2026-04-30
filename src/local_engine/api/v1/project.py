"""
Project API 端点 - 项目文件列表

提供项目文件结构查询功能，供 AI Agent 了解项目上下文。

主要端点:
- GET  /api/v1/project/files    获取项目文件列表（扁平）
- POST /api/v1/project/tree     获取项目文件树（树形结构）
"""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from typing import Dict, Any, List, Optional
from pathlib import Path
import logging
import os

logger = logging.getLogger(__name__)
router = APIRouter()


# ==================== 配置 ====================

# 默认忽略的目录和文件
DEFAULT_IGNORE_DIRS = {
    # 版本控制
    '.git', '.svn', '.hg',
    # 依赖目录
    'node_modules', 'vendor', 'packages',
    # Python
    '__pycache__', '.pytest_cache', '.mypy_cache', 
    'venv', '.venv', 'env', '.env',
    '.eggs', '*.egg-info',
    # IDE
    '.idea', '.vscode', '.cursor',
    # 构建输出
    'dist', 'build', 'out', 'target',
    '.next', '.nuxt', '.output',
    # 其他
    '.cache', '.temp', '.tmp',
    'coverage', '.nyc_output',
}

DEFAULT_IGNORE_FILES = {
    '.DS_Store', 'Thumbs.db',
    '*.pyc', '*.pyo', '*.pyd',
    '*.so', '*.dll', '*.dylib',
    '*.log', '*.lock',
}

# 常见代码文件扩展名
CODE_EXTENSIONS = {
    '.py', '.js', '.ts', '.jsx', '.tsx',
    '.java', '.kt', '.scala',
    '.go', '.rs', '.c', '.cpp', '.h', '.hpp',
    '.cs', '.fs',
    '.rb', '.php', '.swift',
    '.vue', '.svelte',
    '.html', '.css', '.scss', '.less',
    '.json', '.yaml', '.yml', '.toml', '.xml',
    '.md', '.txt', '.rst',
    '.sql', '.sh', '.bash', '.ps1',
    '.dockerfile', '.env.example',
}

# 图片文件扩展名
IMAGE_EXTENSIONS = {
    '.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp', '.ico', '.svg', '.tiff', '.tif',
}


# ==================== 请求/响应模型 ====================

class ProjectFilesRequest(BaseModel):
    """获取项目文件列表请求"""
    project_path: str = Field(..., description="项目根目录路径")
    max_depth: int = Field(default=4, ge=1, le=10, description="最大遍历深度")
    max_files: int = Field(default=500, ge=1, le=2000, description="最大文件数量")
    include_hidden: bool = Field(default=False, description="是否包含隐藏文件/目录")
    code_only: bool = Field(default=False, description="是否只返回代码文件")
    extensions: Optional[List[str]] = Field(default=None, description="指定文件扩展名过滤，如 ['.py', '.js']")
    ignore_dirs: Optional[List[str]] = Field(default=None, description="额外忽略的目录名")
    format: str = Field(default="json", description="输出格式: json 或 text（紧凑树形文本）")


class FileInfo(BaseModel):
    """文件信息"""
    path: str = Field(..., description="相对于项目根目录的路径")
    name: str = Field(..., description="文件/目录名")
    type: str = Field(..., description="类型: file 或 dir")
    ext: Optional[str] = Field(default=None, description="文件扩展名")
    size: Optional[int] = Field(default=None, description="文件大小（字节）")
    children: Optional[int] = Field(default=None, description="目录下的直接子项数量")


class ProjectFilesResponse(BaseModel):
    """项目文件列表响应"""
    project_path: str
    total_files: int
    total_dirs: int
    truncated: bool = Field(default=False, description="是否因达到限制而截断")
    files: List[FileInfo]


class TreeNode(BaseModel):
    """树形结构节点"""
    name: str
    path: str
    type: str
    ext: Optional[str] = None
    size: Optional[int] = None
    children: Optional[List['TreeNode']] = None


# ==================== 工具函数 ====================

def get_image_dimensions(file_path: Path) -> Optional[str]:
    """
    获取图片分辨率，返回格式如 "1920x1080"
    
    使用 PIL 读取图片尺寸，失败时返回 None
    """
    try:
        from PIL import Image
        with Image.open(file_path) as img:
            width, height = img.size
            return f"{width}x{height}"
    except Exception:
        return None


def should_ignore(name: str, is_dir: bool, include_hidden: bool, extra_ignore_dirs: set) -> bool:
    """判断是否应该忽略该文件/目录"""
    # 隐藏文件
    if not include_hidden and name.startswith('.'):
        return True
    
    if is_dir:
        # 检查目录名
        if name in DEFAULT_IGNORE_DIRS or name in extra_ignore_dirs:
            return True
        # 检查通配符模式
        for pattern in DEFAULT_IGNORE_DIRS:
            if '*' in pattern:
                import fnmatch
                if fnmatch.fnmatch(name, pattern):
                    return True
    else:
        # 检查文件名
        for pattern in DEFAULT_IGNORE_FILES:
            if '*' in pattern:
                import fnmatch
                if fnmatch.fnmatch(name, pattern):
                    return True
            elif name == pattern:
                return True
    
    return False


def list_project_files(
    project_path: str,
    max_depth: int = 4,
    max_files: int = 500,
    include_hidden: bool = False,
    code_only: bool = False,
    extensions: Optional[List[str]] = None,
    ignore_dirs: Optional[List[str]] = None,
) -> ProjectFilesResponse:
    """
    列出项目文件（扁平列表）
    
    Args:
        project_path: 项目根目录
        max_depth: 最大遍历深度
        max_files: 最大文件数量
        include_hidden: 是否包含隐藏文件
        code_only: 是否只返回代码文件
        extensions: 指定扩展名过滤
        ignore_dirs: 额外忽略的目录
    
    Returns:
        ProjectFilesResponse
    """
    root = Path(project_path)
    if not root.exists():
        raise ValueError(f"Project path does not exist: {project_path}")
    if not root.is_dir():
        raise ValueError(f"Project path is not a directory: {project_path}")
    
    extra_ignore = set(ignore_dirs) if ignore_dirs else set()
    allowed_extensions = set(extensions) if extensions else (CODE_EXTENSIONS if code_only else None)
    
    files: List[FileInfo] = []
    total_files = 0
    total_dirs = 0
    truncated = False
    
    def walk(current_path: Path, depth: int, rel_prefix: str):
        nonlocal total_files, total_dirs, truncated
        
        if depth > max_depth:
            return
        
        if len(files) >= max_files:
            truncated = True
            return
        
        try:
            entries = sorted(current_path.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower()))
        except PermissionError:
            return
        
        for entry in entries:
            if len(files) >= max_files:
                truncated = True
                return
            
            name = entry.name
            is_dir = entry.is_dir()
            
            # 检查是否忽略
            if should_ignore(name, is_dir, include_hidden, extra_ignore):
                continue
            
            rel_path = f"{rel_prefix}/{name}" if rel_prefix else name
            
            if is_dir:
                total_dirs += 1
                # 统计子项数量
                try:
                    children_count = len(list(entry.iterdir()))
                except PermissionError:
                    children_count = 0
                
                files.append(FileInfo(
                    path=rel_path,
                    name=name,
                    type="dir",
                    children=children_count,
                ))
                
                # 递归
                walk(entry, depth + 1, rel_path)
            else:
                # 文件扩展名过滤
                ext = entry.suffix.lower() if entry.suffix else None
                if allowed_extensions and ext not in allowed_extensions:
                    continue
                
                total_files += 1
                try:
                    size = entry.stat().st_size
                except:
                    size = None
                
                files.append(FileInfo(
                    path=rel_path,
                    name=name,
                    type="file",
                    ext=ext,
                    size=size,
                ))
    
    walk(root, 1, "")
    
    return ProjectFilesResponse(
        project_path=str(root.absolute()),
        total_files=total_files,
        total_dirs=total_dirs,
        truncated=truncated,
        files=files,
    )


def build_project_tree(
    project_path: str,
    max_depth: int = 3,
    include_hidden: bool = False,
    code_only: bool = False,
    extensions: Optional[List[str]] = None,
    ignore_dirs: Optional[List[str]] = None,
) -> TreeNode:
    """
    构建项目文件树（树形结构）
    """
    root = Path(project_path)
    if not root.exists():
        raise ValueError(f"Project path does not exist: {project_path}")
    if not root.is_dir():
        raise ValueError(f"Project path is not a directory: {project_path}")
    
    extra_ignore = set(ignore_dirs) if ignore_dirs else set()
    allowed_extensions = set(extensions) if extensions else (CODE_EXTENSIONS if code_only else None)
    
    def build_node(current_path: Path, depth: int, rel_prefix: str) -> Optional[TreeNode]:
        name = current_path.name
        is_dir = current_path.is_dir()
        rel_path = f"{rel_prefix}/{name}" if rel_prefix else name
        
        if is_dir:
            if depth > max_depth:
                return TreeNode(name=name, path=rel_path, type="dir", children=[])
            
            children = []
            try:
                entries = sorted(current_path.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower()))
            except PermissionError:
                entries = []
            
            for entry in entries:
                entry_name = entry.name
                entry_is_dir = entry.is_dir()
                
                if should_ignore(entry_name, entry_is_dir, include_hidden, extra_ignore):
                    continue
                
                child_node = build_node(entry, depth + 1, rel_path)
                if child_node:
                    children.append(child_node)
            
            return TreeNode(name=name, path=rel_path, type="dir", children=children)
        else:
            ext = current_path.suffix.lower() if current_path.suffix else None
            if allowed_extensions and ext not in allowed_extensions:
                return None
            
            try:
                size = current_path.stat().st_size
            except:
                size = None
            
            return TreeNode(name=name, path=rel_path, type="file", ext=ext, size=size)
    
    # 构建根节点
    children = []
    try:
        entries = sorted(root.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower()))
    except PermissionError:
        entries = []
    
    for entry in entries:
        if should_ignore(entry.name, entry.is_dir(), include_hidden, extra_ignore):
            continue
        
        child_node = build_node(entry, 1, "")
        if child_node:
            children.append(child_node)
    
    return TreeNode(
        name=root.name,
        path=str(root.absolute()),
        type="dir",
        children=children,
    )


def format_tree_as_text(
    project_path: str,
    max_depth: int = 4,
    include_hidden: bool = False,
    code_only: bool = False,
    extensions: Optional[List[str]] = None,
    ignore_dirs: Optional[List[str]] = None,
) -> str:
    """
    生成紧凑的树形文本格式（类似 Cursor 给 AI 的格式）
    
    输出格式示例:
    ```
    Project Root: C:/Users/example/my_project
    
    my_project/
    ├── src/
    │   ├── main.py
    │   ├── utils/
    │   │   ├── helper.py
    │   │   └── config.py
    │   └── models/
    │       └── user.py
    ├── assets/
    │   ├── logo.png [512x512]
    │   └── banner.jpg [1920x400]
    ├── tests/
    │   └── test_main.py
    ├── README.md
    └── requirements.txt
    ```
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed
    
    root = Path(project_path)
    if not root.exists():
        raise ValueError(f"Project path does not exist: {project_path}")
    if not root.is_dir():
        raise ValueError(f"Project path is not a directory: {project_path}")
    
    extra_ignore = set(ignore_dirs) if ignore_dirs else set()
    allowed_extensions = set(extensions) if extensions else (CODE_EXTENSIONS if code_only else None)
    
    # 第一遍：收集所有条目和图片文件
    # 使用列表存储 (line_index, prefix, connector, entry) 元组
    entries_info: List[tuple] = []  # (prefix, connector, entry, is_dir)
    image_files: List[Path] = []  # 需要获取分辨率的图片
    
    def collect_entries(current_path: Path, prefix: str, depth: int):
        if depth > max_depth:
            return
        
        try:
            entries = sorted(current_path.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower()))
        except PermissionError:
            return
        
        # 过滤
        filtered_entries = []
        for entry in entries:
            name = entry.name
            is_dir = entry.is_dir()
            
            if should_ignore(name, is_dir, include_hidden, extra_ignore):
                continue
            
            if not is_dir and allowed_extensions:
                ext = entry.suffix.lower() if entry.suffix else None
                if ext not in allowed_extensions:
                    continue
            
            filtered_entries.append(entry)
        
        for i, entry in enumerate(filtered_entries):
            is_last = (i == len(filtered_entries) - 1)
            connector = "└── " if is_last else "├── "
            
            entries_info.append((prefix, connector, entry, entry.is_dir()))
            
            if entry.is_dir():
                # 递归子目录
                new_prefix = prefix + ("    " if is_last else "│   ")
                collect_entries(entry, new_prefix, depth + 1)
            else:
                # 收集图片文件
                ext = entry.suffix.lower() if entry.suffix else None
                if ext in IMAGE_EXTENSIONS:
                    image_files.append(entry)
    
    collect_entries(root, "", 1)
    
    # 第二遍：并行获取图片分辨率
    image_dimensions: Dict[Path, Optional[str]] = {}
    
    if image_files:
        # 使用线程池并行读取，最多 8 个线程
        with ThreadPoolExecutor(max_workers=min(8, len(image_files))) as executor:
            future_to_path = {
                executor.submit(get_image_dimensions, img_path): img_path 
                for img_path in image_files
            }
            for future in as_completed(future_to_path):
                img_path = future_to_path[future]
                try:
                    image_dimensions[img_path] = future.result()
                except Exception:
                    image_dimensions[img_path] = None
    
    # 第三遍：生成输出
    abs_path = str(root.absolute())
    lines = [f"Project Root: {abs_path}", "", f"{root.name}/"]
    
    for prefix, connector, entry, is_dir in entries_info:
        if is_dir:
            lines.append(f"{prefix}{connector}{entry.name}/")
        else:
            ext = entry.suffix.lower() if entry.suffix else None
            if ext in IMAGE_EXTENSIONS:
                dimensions = image_dimensions.get(entry)
                if dimensions:
                    lines.append(f"{prefix}{connector}{entry.name} [{dimensions}]")
                else:
                    lines.append(f"{prefix}{connector}{entry.name}")
            else:
                lines.append(f"{prefix}{connector}{entry.name}")
    
    return "\n".join(lines)


# ==================== API 端点 ====================

@router.get("/files")
async def get_project_files(
    path: str = Query(..., description="项目根目录路径"),
    max_depth: int = Query(default=4, ge=1, le=10, description="最大遍历深度"),
    max_files: int = Query(default=500, ge=1, le=2000, description="最大文件数量"),
    include_hidden: bool = Query(default=False, description="是否包含隐藏文件"),
    code_only: bool = Query(default=False, description="是否只返回代码文件"),
) -> Dict[str, Any]:
    """
    获取项目文件列表（扁平结构）
    
    返回项目目录下的所有文件和目录列表，自动过滤常见的无关目录
    （如 node_modules, .git, __pycache__ 等）。
    
    适合 AI Agent 快速了解项目结构。
    
    示例请求:
    ```
    GET /api/v1/project/files?path=/path/to/project&max_depth=3
    ```
    
    返回:
    ```json
    {
        "success": true,
        "data": {
            "project_path": "/path/to/project",
            "total_files": 42,
            "total_dirs": 8,
            "truncated": false,
            "files": [
                {"path": "src", "name": "src", "type": "dir", "children": 10},
                {"path": "src/main.py", "name": "main.py", "type": "file", "ext": ".py", "size": 1234},
                ...
            ]
        }
    }
    ```
    """
    logger.info(f"[Project API] get_files: path={path}, max_depth={max_depth}")
    
    try:
        result = list_project_files(
            project_path=path,
            max_depth=max_depth,
            max_files=max_files,
            include_hidden=include_hidden,
            code_only=code_only,
        )
        
        return {
            "success": True,
            "data": result.model_dump(),
        }
    
    except ValueError as e:
        logger.error(f"[Project API] get_files failed: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"[Project API] get_files failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/files")
async def post_project_files(request: ProjectFilesRequest) -> Dict[str, Any]:
    """
    获取项目文件列表（POST 版本，支持更多参数）
    
    与 GET /files 功能相同，但支持更复杂的过滤条件。
    
    **format 参数**:
    - `json`: 返回详细的 JSON 结构（默认）
    - `text`: 返回紧凑的树形文本格式（适合 AI 阅读）
    
    示例请求 (JSON 格式):
    ```json
    {
        "project_path": "/path/to/project",
        "max_depth": 4,
        "format": "json"
    }
    ```
    
    示例请求 (Text 格式):
    ```json
    {
        "project_path": "/path/to/project",
        "max_depth": 4,
        "format": "text"
    }
    ```
    
    Text 格式返回示例:
    ```
    project/
    ├── src/
    │   ├── main.py
    │   └── utils/
    │       └── helper.py
    ├── README.md
    └── requirements.txt
    ```
    """
    logger.info(f"[Project API] post_files: path={request.project_path}, format={request.format}")
    
    try:
        # 如果请求文本格式
        if request.format == "text":
            tree_text = format_tree_as_text(
                project_path=request.project_path,
                max_depth=request.max_depth,
                include_hidden=request.include_hidden,
                code_only=request.code_only,
                extensions=request.extensions,
                ignore_dirs=request.ignore_dirs,
            )
            return {
                "success": True,
                "data": {
                    "project_path": request.project_path,
                    "format": "text",
                    "tree": tree_text,
                },
            }
        
        # 默认 JSON 格式
        result = list_project_files(
            project_path=request.project_path,
            max_depth=request.max_depth,
            max_files=request.max_files,
            include_hidden=request.include_hidden,
            code_only=request.code_only,
            extensions=request.extensions,
            ignore_dirs=request.ignore_dirs,
        )
        
        return {
            "success": True,
            "data": result.model_dump(),
        }
    
    except ValueError as e:
        logger.error(f"[Project API] post_files failed: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"[Project API] post_files failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/tree")
async def get_project_tree(request: ProjectFilesRequest) -> Dict[str, Any]:
    """
    获取项目文件树（树形结构）
    
    返回嵌套的树形结构，适合展示项目目录层级。
    
    示例请求:
    ```json
    {
        "project_path": "/path/to/project",
        "max_depth": 3
    }
    ```
    
    返回:
    ```json
    {
        "success": true,
        "data": {
            "name": "project",
            "path": "/path/to/project",
            "type": "dir",
            "children": [
                {
                    "name": "src",
                    "path": "src",
                    "type": "dir",
                    "children": [
                        {"name": "main.py", "path": "src/main.py", "type": "file", "ext": ".py", "size": 1234}
                    ]
                }
            ]
        }
    }
    ```
    """
    logger.info(f"[Project API] get_tree: path={request.project_path}")
    
    try:
        result = build_project_tree(
            project_path=request.project_path,
            max_depth=request.max_depth,
            include_hidden=request.include_hidden,
            code_only=request.code_only,
            extensions=request.extensions,
            ignore_dirs=request.ignore_dirs,
        )
        
        return {
            "success": True,
            "data": result.model_dump(),
        }
    
    except ValueError as e:
        logger.error(f"[Project API] get_tree failed: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"[Project API] get_tree failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/text")
async def get_project_text(
    path: str = Query(..., description="项目根目录路径"),
    max_depth: int = Query(default=4, ge=1, le=10, description="最大遍历深度"),
    include_hidden: bool = Query(default=False, description="是否包含隐藏文件"),
    code_only: bool = Query(default=False, description="是否只返回代码文件"),
) -> Dict[str, Any]:
    """
    获取项目文件树的紧凑文本格式（推荐给 AI 使用）
    
    返回类似 `tree` 命令的紧凑格式，token 效率高，适合 AI 阅读。
    
    示例请求:
    ```
    GET /api/v1/project/text?path=/path/to/project&max_depth=3
    ```
    
    返回:
    ```json
    {
        "success": true,
        "data": {
            "project_path": "/path/to/project",
            "tree": "project/\\n├── src/\\n│   ├── main.py\\n│   └── utils/\\n├── README.md\\n└── requirements.txt"
        }
    }
    ```
    
    tree 字段内容示例:
    ```
    project/
    ├── src/
    │   ├── main.py
    │   └── utils/
    │       └── helper.py
    ├── tests/
    │   └── test_main.py
    ├── README.md
    └── requirements.txt
    ```
    """
    logger.info(f"[Project API] get_text: path={path}, max_depth={max_depth}")
    
    try:
        tree_text = format_tree_as_text(
            project_path=path,
            max_depth=max_depth,
            include_hidden=include_hidden,
            code_only=code_only,
        )
        
        return {
            "success": True,
            "data": {
                "project_path": path,
                "tree": tree_text,
            },
        }
    
    except ValueError as e:
        logger.error(f"[Project API] get_text failed: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"[Project API] get_text failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# 导出工具函数供其他模块使用
__all__ = [
    'list_project_files',
    'build_project_tree',
    'format_tree_as_text',
    'ProjectFilesRequest',
    'ProjectFilesResponse',
    'FileInfo',
    'TreeNode',
]
