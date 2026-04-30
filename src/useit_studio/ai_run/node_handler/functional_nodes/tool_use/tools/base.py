"""
Tool Use Node - 工具基类

定义工具的基础接口和工厂函数。
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional, TYPE_CHECKING

from langchain_core.tools import BaseTool as LangChainBaseTool

if TYPE_CHECKING:
    from ..models import ToolConfig, ToolType


class ToolUseBaseTool(ABC):
    """
    Tool Use 工具基类
    
    所有预定义工具都继承自此类。
    提供统一的配置接口和 LangChain 工具转换。
    """
    
    name: str = ""
    description: str = ""
    
    @classmethod
    @abstractmethod
    def from_config(
        cls, 
        config: Dict[str, Any],
        api_keys: Optional[Dict[str, str]] = None,
    ) -> "ToolUseBaseTool":
        """
        从配置创建工具实例
        
        Args:
            config: 工具配置字典
            api_keys: API 密钥字典
            
        Returns:
            工具实例
        """
        ...
    
    @abstractmethod
    def as_langchain_tool(self) -> LangChainBaseTool:
        """
        转换为 LangChain 工具
        
        Returns:
            LangChain BaseTool 实例
        """
        ...
    
    @abstractmethod
    async def invoke(self, **kwargs) -> str:
        """
        调用工具
        
        Args:
            **kwargs: 工具参数
            
        Returns:
            工具执行结果
        """
        ...


def create_tool_from_config(
    tool_config: "ToolConfig",
    api_keys: Optional[Dict[str, str]] = None,
    project_id: Optional[str] = None,
    chat_id: Optional[str] = None,
) -> Optional[LangChainBaseTool]:
    """
    根据配置创建 LangChain 工具
    
    Args:
        tool_config: 工具配置
        api_keys: API 密钥字典
        project_id: 项目 ID（部分工具需要，如 doc_extract 的 S3 上传）
        chat_id: 会话 ID（部分工具需要）
        
    Returns:
        LangChain 工具实例，如果工具未启用或类型不支持则返回 None
    """
    from ..models import ToolType
    from .rag import create_rag_tool
    from .web_search import create_web_search_tool
    from .file_system import create_file_system_tool
    from .doc_extract import create_doc_extract_tool
    
    if not tool_config.enabled:
        return None
    
    tool_type = tool_config.tool_type
    config = tool_config.config
    
    if tool_type == ToolType.RAG:
        return create_rag_tool(config, api_keys)
    elif tool_type == ToolType.WEB_SEARCH:
        return create_web_search_tool(config, api_keys)
    elif tool_type == ToolType.FILE_SYSTEM:
        return create_file_system_tool(config, api_keys)
    elif tool_type == ToolType.DOC_EXTRACT:
        return create_doc_extract_tool(config, api_keys, project_id=project_id, chat_id=chat_id)
    else:
        return None


def create_tools_from_configs(
    tool_configs: List["ToolConfig"],
    api_keys: Optional[Dict[str, str]] = None,
    project_id: Optional[str] = None,
    chat_id: Optional[str] = None,
) -> List[LangChainBaseTool]:
    """
    从配置列表创建所有启用的工具
    
    Args:
        tool_configs: 工具配置列表
        api_keys: API 密钥字典
        project_id: 项目 ID（传递给需要的工具）
        chat_id: 会话 ID（传递给需要的工具）
        
    Returns:
        LangChain 工具列表
    """
    tools = []
    for config in tool_configs:
        tool = create_tool_from_config(config, api_keys, project_id=project_id, chat_id=chat_id)
        if tool is not None:
            tools.append(tool)
    return tools
