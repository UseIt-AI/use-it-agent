"""
COM 辅助函数
"""

import win32com.client
import pythoncom


def vtPoint(x, y, z=0):
    """
    创建 COM 点坐标
    
    Args:
        x, y, z: 坐标值
    
    Returns:
        VARIANT 类型的点坐标数组
    """
    return win32com.client.VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_R8, (x, y, z))


def vtFloat(data):
    """
    创建 COM 浮点数组
    
    Args:
        data: 浮点数列表或元组
    
    Returns:
        VARIANT 类型的浮点数组
    """
    return win32com.client.VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_R8, data)


def vtInt(data):
    """
    创建 COM 整数数组
    
    Args:
        data: 整数列表或元组
    
    Returns:
        VARIANT 类型的整数数组
    """
    return win32com.client.VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_I2, data)


def get_autocad():
    """
    获取 AutoCAD Application 对象
    
    Returns:
        AutoCAD Application COM 对象
    """
    pythoncom.CoInitialize()
    try:
        return win32com.client.GetActiveObject("AutoCAD.Application")
    except:
        return win32com.client.Dispatch("AutoCAD.Application")


def ensure_document(acad):
    """
    确保有打开的文档
    
    Args:
        acad: AutoCAD Application 对象
    
    Returns:
        当前活动文档
    """
    if acad.Documents.Count == 0:
        return acad.Documents.Add()
    return acad.ActiveDocument
