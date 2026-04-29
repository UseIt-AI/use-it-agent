"""
Attached Files 智能路由

使用小模型判断当前请求是否需要加载附件文件内容，避免不必要的 token 消耗。

设计原理：
- 在多步任务执行过程中，只有部分步骤需要访问文件内容
- 使用 GPT-4o-mini 等快速模型判断当前步骤是否需要文件
- 成本约 $0.0001/次，相比节省的 35K tokens 主模型成本，ROI 很高
"""

import json
import logging
from typing import List, Dict, Optional, Any

logger = logging.getLogger(__name__)


# ==================== 快速规则判断 ====================

def _quick_check_need_files(
    query: str,
    file_names: List[str],
) -> Optional[bool]:
    """
    快速规则判断，避免不必要的 LLM 调用
    
    Returns:
        True: 确定需要文件
        False: 确定不需要文件
        None: 不确定，需要调用 LLM
    """
    query_lower = query.lower()
    
    # 规则 1: 如果 query 中包含文件名，直接返回 True
    for name in file_names:
        if name.lower() in query_lower:
            return True
    
    # 规则 2: 如果是纯 UI 操作词汇，且不包含文件相关词汇，返回 False
    ui_keywords = [
        "click", "点击", "scroll", "滚动", "type", "输入", "press", "按",
        "hover", "悬停", "drag", "拖", "drop", "放", "select", "选择",
        "wait", "等待", "sleep", "screenshot", "截图",
    ]
    file_keywords = [
        "file", "文件", "document", "文档", "content", "内容",
        "read", "读", "analyze", "分析", "extract", "提取",
        "report", "报告", "data", "数据", "table", "表",
    ]
    
    has_ui_keyword = any(kw in query_lower for kw in ui_keywords)
    has_file_keyword = any(kw in query_lower for kw in file_keywords)
    
    if has_ui_keyword and not has_file_keyword:
        return False
    
    # 不确定，需要 LLM 判断
    return None


# ==================== LLM 判断 ====================

ROUTER_PROMPT = """You are a routing assistant. Determine if the current request needs access to the attached files.

## Attached Files
{file_list}

## Current Query
{query}

## Task History (Summary)
{history_md}

## Instructions
Return {{"need_files": true}} if:
- The query asks to analyze, read, summarize, or reference file content
- The query mentions specific file names
- This is the first step and files are clearly relevant to the task
- The task requires information that can only come from the files

Return {{"need_files": false}} if:
- The query is about UI operations (clicking, typing, scrolling, navigating)
- The task has progressed past the file analysis phase
- The query is about executing actions based on previously extracted information
- The query is unrelated to file content

Output JSON only, no explanation:"""


async def _llm_check_need_files(
    query: str,
    history_md: str,
    file_names: List[str],
    api_keys: Optional[Dict[str, str]] = None,
    model: str = "gpt-4o-mini",
) -> bool:
    """
    使用 LLM 判断是否需要加载文件
    
    Args:
        query: 用户当前查询
        history_md: 任务历史摘要
        file_names: 附件文件名列表
        api_keys: API 密钥
        model: 使用的模型
        
    Returns:
        是否需要加载文件
    """
    try:
        from openai import AsyncOpenAI
        
        # 获取 API key
        api_key = None
        if api_keys:
            api_key = api_keys.get("OPENAI_API_KEY") or api_keys.get("openai")
        
        if not api_key:
            # 尝试从环境变量获取
            import os
            api_key = os.environ.get("OPENAI_API_KEY")
        
        if not api_key:
            logger.warning("No OpenAI API key found, defaulting to load files")
            return True
        
        client = AsyncOpenAI(api_key=api_key)
        
        # 构建 prompt
        file_list = "\n".join(f"- {name}" for name in file_names)
        prompt = ROUTER_PROMPT.format(
            file_list=file_list,
            query=query,
            history_md=history_md[:2000] if history_md else "(No history yet)",
        )
        
        # 调用 LLM
        response = await client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=50,
            temperature=0,
        )
        
        # 解析结果
        content = response.choices[0].message.content.strip()
        
        # 尝试解析 JSON
        try:
            result = json.loads(content)
            need_files = result.get("need_files", True)
            logger.info(f"Attached files router: need_files={need_files}, query='{query[:50]}...'")
            return need_files
        except json.JSONDecodeError:
            # 如果解析失败，尝试简单匹配
            if "false" in content.lower():
                return False
            return True
            
    except Exception as e:
        logger.warning(f"Attached files router failed: {e}, defaulting to load files")
        return True  # 降级策略：默认加载文件


# ==================== 主入口 ====================

async def should_include_attached_files(
    query: str,
    history_md: str,
    file_names: List[str],
    api_keys: Optional[Dict[str, str]] = None,
    model: str = "gpt-4o-mini",
) -> bool:
    """
    判断当前请求是否需要加载附件文件
    
    先使用快速规则判断，不确定时再调用 LLM。
    
    Args:
        query: 用户当前查询
        history_md: 任务历史摘要
        file_names: 附件文件名列表
        api_keys: API 密钥
        model: 使用的模型
        
    Returns:
        是否需要加载文件
    """
    if not file_names:
        return False
    
    # 快速规则判断
    quick_result = _quick_check_need_files(query, file_names)
    if quick_result is not None:
        logger.info(f"Attached files router (quick): need_files={quick_result}, query='{query[:50]}...'")
        return quick_result
    
    # LLM 判断
    return await _llm_check_need_files(
        query=query,
        history_md=history_md,
        file_names=file_names,
        api_keys=api_keys,
        model=model,
    )
