"""
Office Agent - Prompts 模块 (向后兼容层)

注意：各 Office 应用的 prompts 已经移动到各自的 node 文件夹中：
- word_v2/prompts.py
- excel_v2/prompts.py
- ppt_v2/prompts.py

此模块保留用于向后兼容，重新导出各应用的 prompts。
新代码应直接从各自的 node 文件夹导入。
"""

# 从各自的 node 文件夹重新导出（向后兼容）
from ...word_v2.prompts import WORD_SYSTEM_PROMPT, WORD_USER_PROMPT_TEMPLATE
from ...excel_v2.prompts import EXCEL_SYSTEM_PROMPT, EXCEL_USER_PROMPT_TEMPLATE
from ...ppt_v2.prompts import PPT_SYSTEM_PROMPT, PPT_USER_PROMPT_TEMPLATE

# 保留基础 prompt 作为参考模板
from .base_prompt import BASE_SYSTEM_PROMPT, BASE_USER_PROMPT_TEMPLATE

__all__ = [
    # Word (来自 word_v2/prompts.py)
    "WORD_SYSTEM_PROMPT",
    "WORD_USER_PROMPT_TEMPLATE",
    # Excel (来自 excel_v2/prompts.py)
    "EXCEL_SYSTEM_PROMPT",
    "EXCEL_USER_PROMPT_TEMPLATE",
    # PowerPoint (来自 ppt_v2/prompts.py)
    "PPT_SYSTEM_PROMPT",
    "PPT_USER_PROMPT_TEMPLATE",
    # Base (保留作为参考模板)
    "BASE_SYSTEM_PROMPT",
    "BASE_USER_PROMPT_TEMPLATE",
]
