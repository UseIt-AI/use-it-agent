"""
Python COM Executor - 执行 Python COM 代码

Action: execute_python_com
"""

from typing import Dict, Any
import logging
import sys
import io
import traceback

logger = logging.getLogger(__name__)


class PythonComExecutor:
    """
    执行 Python COM 代码
    
    在受限环境中执行用户提供的 Python 代码，
    代码可以访问 acad, doc, model_space 等对象。
    """
    
    def __init__(self, acad, doc):
        """
        初始化
        
        Args:
            acad: AutoCAD Application 对象
            doc: AutoCAD Document 对象
        """
        self.acad = acad
        self.doc = doc
        self.model_space = doc.ModelSpace
    
    def execute(self, code: str, timeout: int = 60) -> Dict[str, Any]:
        """
        执行 Python 代码
        
        Args:
            code: Python 代码
            timeout: 超时时间（秒）- 暂不实现超时控制
        
        Returns:
            {
                "success": bool,
                "output": str,
                "error": str or None,
                "entities_created": int,
                "entities_modified": int,
                "entities_deleted": int
            }
        """
        import win32com.client
        import pythoncom
        import math
        
        # 记录执行前的实体数量
        entities_before = self.model_space.Count
        
        # 准备执行环境
        local_vars = {
            # AutoCAD 对象
            "acad": self.acad,
            "doc": self.doc,
            "model_space": self.model_space,
            "ms": self.model_space,  # 别名
            
            # 辅助函数
            "vtPoint": self._vt_point,
            "vtFloat": self._vt_float,
            "vtInt": self._vt_int,
            "get_entity": self._get_entity,
            
            # 常用模块
            "math": math,
            "win32com": win32com,
            "pythoncom": pythoncom,
        }
        
        # 捕获输出
        old_stdout = sys.stdout
        old_stderr = sys.stderr
        stdout_capture = io.StringIO()
        stderr_capture = io.StringIO()
        
        try:
            sys.stdout = stdout_capture
            sys.stderr = stderr_capture
            
            # 执行代码
            exec(code, local_vars, local_vars)
            
            # 获取输出
            output = stdout_capture.getvalue()
            error_output = stderr_capture.getvalue()
            
            # 计算实体变化
            entities_after = self.model_space.Count
            entities_created = max(0, entities_after - entities_before)
            
            # 从 local_vars 获取可能的返回值
            entities_modified = local_vars.get("_entities_modified", 0)
            entities_deleted = local_vars.get("_entities_deleted", 0)
            
            if error_output:
                logger.warning(f"[PythonComExecutor] Stderr: {error_output}")
            
            return {
                "success": True,
                "output": output,
                "error": error_output if error_output else None,
                "entities_created": entities_created,
                "entities_modified": entities_modified,
                "entities_deleted": entities_deleted
            }
            
        except Exception as e:
            error_msg = traceback.format_exc()
            logger.error(f"[PythonComExecutor] Execution error: {error_msg}")
            
            return {
                "success": False,
                "output": stdout_capture.getvalue(),
                "error": error_msg,
                "entities_created": 0,
                "entities_modified": 0,
                "entities_deleted": 0
            }
            
        finally:
            sys.stdout = old_stdout
            sys.stderr = old_stderr
    
    def _vt_point(self, x, y, z=0):
        """创建 COM 点坐标"""
        import win32com.client
        import pythoncom
        return win32com.client.VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_R8, (x, y, z))
    
    def _vt_float(self, data):
        """创建 COM 浮点数组"""
        import win32com.client
        import pythoncom
        return win32com.client.VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_R8, data)
    
    def _vt_int(self, data):
        """创建 COM 整数数组"""
        import win32com.client
        import pythoncom
        return win32com.client.VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_I2, data)
    
    def _get_entity(self, handle: str):
        """根据 Handle 获取实体"""
        try:
            return self.doc.HandleToObject(handle)
        except Exception as e:
            logger.warning(f"[PythonComExecutor] Entity not found: {handle}")
            return None
