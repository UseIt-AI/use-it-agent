"""
AutoCAD Controller V2

支持的 Action 类型：
- draw_from_json: 从 JSON 数据绘制图纸
- execute_python_com: 执行 Python COM 代码

参照 PPT Controller 架构，采用异步接口 + 同步 COM 实现。
"""

from .controller import AutoCADControllerV2

__all__ = ["AutoCADControllerV2"]
