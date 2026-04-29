"""
File System 工具模块

通过 AWS S3 读取项目文件，支持列出和读取项目目录中的文件。
主要用途：读取 outputs 目录中的文件内容（最多 20 个文件）。
"""

from .tool import FileSystemTool, create_file_system_tool, FileSystemInput

__all__ = [
    "FileSystemTool",
    "create_file_system_tool",
    "FileSystemInput",
]
