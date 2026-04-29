"""
文件系统操作处理器
"""
import base64
import logging
import os
import shutil
import subprocess
from typing import Dict, Any

logger = logging.getLogger(__name__)


class FilesystemHandler:
    """文件系统操作处理器"""
    
    @staticmethod
    def file_exists(path: str) -> Dict[str, Any]:
        """检查文件是否存在"""
        if not path:
            return {"success": False, "error": "path required"}
        return {"success": True, "exists": os.path.isfile(path)}
    
    @staticmethod
    def directory_exists(path: str) -> Dict[str, Any]:
        """检查目录是否存在"""
        if not path:
            return {"success": False, "error": "path required"}
        return {"success": True, "exists": os.path.isdir(path)}
    
    @staticmethod
    def list_dir(path: str = ".") -> Dict[str, Any]:
        """列出目录内容"""
        try:
            entries = os.listdir(path)
            return {"success": True, "entries": entries}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    @staticmethod
    def read_text(path: str, encoding: str = "utf-8") -> Dict[str, Any]:
        """读取文本文件"""
        if not path:
            return {"success": False, "error": "path required"}
        try:
            with open(path, "r", encoding=encoding) as f:
                content = f.read()
            return {"success": True, "content": content}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    @staticmethod
    def write_text(path: str, content: str, encoding: str = "utf-8") -> Dict[str, Any]:
        """写入文本文件"""
        if not path:
            return {"success": False, "error": "path required"}
        try:
            with open(path, "w", encoding=encoding) as f:
                f.write(content)
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    @staticmethod
    def read_bytes(path: str) -> Dict[str, Any]:
        """读取二进制文件（返回 base64）"""
        if not path:
            return {"success": False, "error": "path required"}
        try:
            with open(path, "rb") as f:
                content = f.read()
            return {"success": True, "content": base64.b64encode(content).decode()}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    @staticmethod
    def write_bytes(path: str, content: str) -> Dict[str, Any]:
        """写入二进制文件（content 为 base64）"""
        if not path:
            return {"success": False, "error": "path required"}
        try:
            data = base64.b64decode(content)
            with open(path, "wb") as f:
                f.write(data)
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    @staticmethod
    def get_file_size(path: str) -> Dict[str, Any]:
        """获取文件大小"""
        if not path:
            return {"success": False, "error": "path required"}
        try:
            size = os.path.getsize(path)
            return {"success": True, "size": size}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    @staticmethod
    def delete_file(path: str) -> Dict[str, Any]:
        """删除文件"""
        if not path:
            return {"success": False, "error": "path required"}
        try:
            os.remove(path)
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    @staticmethod
    def create_dir(path: str) -> Dict[str, Any]:
        """创建目录"""
        if not path:
            return {"success": False, "error": "path required"}
        try:
            os.makedirs(path, exist_ok=True)
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    @staticmethod
    def delete_dir(path: str) -> Dict[str, Any]:
        """删除目录"""
        if not path:
            return {"success": False, "error": "path required"}
        try:
            shutil.rmtree(path)
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    @staticmethod
    def run_command(command: str, timeout: int = 30) -> Dict[str, Any]:
        """运行命令"""
        if not command:
            return {"success": False, "error": "command required"}
        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout
            )
            return {
                "success": True,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "return_code": result.returncode
            }
        except subprocess.TimeoutExpired:
            return {"success": False, "error": "Command timed out"}
        except Exception as e:
            return {"success": False, "error": str(e)}


