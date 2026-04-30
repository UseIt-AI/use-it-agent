"""
消息构建器

支持Interleave list格式的消息构建和转换
格式：["image", "text", "image", ...] 
"""

from typing import List, Union, Dict, Any
import os
from .base.message_types import UnifiedMessage, TextMessageContent, ImageMessageContent, interleave_to_messages


class MessageBuilder:
    """统一消息构建器"""
    
    @staticmethod
    def from_interleave_list(
        interleave_list: List[Union[str, Dict[str, Any]]],
        system_prompt: str = ""
    ) -> List[UnifiedMessage]:
        """
        从interleave list创建消息
        
        Args:
            interleave_list: 交错列表，支持以下格式：
                - ["text", "image.png", "text"] - 字符串列表
                - [{"type": "text", "content": "..."}, {"type": "image", "path": "..."}] - 字典列表
                - 混合格式
            system_prompt: 系统提示词
            
        Returns:
            统一消息列表
        """
        messages = []
        
        # 添加系统消息
        if system_prompt:
            system_msg = UnifiedMessage("system")
            system_msg.add_text(system_prompt)
            messages.append(system_msg)
        
        if not interleave_list:
            return messages
        
        # 构建用户消息
        user_msg = UnifiedMessage("user")
        
        for item in interleave_list:
            if isinstance(item, str):
                # 字符串：判断是文本还是图片路径
                if MessageBuilder._is_image_path(item):
                    user_msg.add_image(item)
                else:
                    user_msg.add_text(item)
            
            elif isinstance(item, dict):
                # 字典格式
                item_type = item.get("type", "text")
                
                if item_type == "text":
                    content = item.get("content", item.get("text", ""))
                    user_msg.add_text(content)
                
                elif item_type == "image":
                    image_data = item.get("content", item.get("path", item.get("data", "")))
                    image_format = item.get("format", "auto")
                    user_msg.add_image(image_data, image_format)
                
                else:
                    # 未知类型，当作文本处理
                    user_msg.add_text(str(item))
            
            else:
                # 其他类型转为字符串
                user_msg.add_text(str(item))
        
        if user_msg.contents:
            messages.append(user_msg)
        
        return messages
    
    @staticmethod
    def from_simple_format(
        text: str = "",
        images: List[str] = None,
        system_prompt: str = ""
    ) -> List[UnifiedMessage]:
        """
        从简单格式创建消息
        
        Args:
            text: 文本内容
            images: 图片路径列表
            system_prompt: 系统提示词
            
        Returns:
            统一消息列表
        """
        messages = []
        
        # 系统消息
        if system_prompt:
            system_msg = UnifiedMessage("system")
            system_msg.add_text(system_prompt)
            messages.append(system_msg)
        
        # 用户消息
        user_msg = UnifiedMessage("user")
        
        # 添加文本
        if text:
            user_msg.add_text(text)
        
        # 添加图片
        if images:
            for image_path in images:
                user_msg.add_image(image_path)
        
        if user_msg.contents:
            messages.append(user_msg)
        
        return messages
    
    @staticmethod
    def from_chat_format(
        messages: List[Dict[str, Any]],
        system_prompt: str = ""
    ) -> List[UnifiedMessage]:
        """
        从聊天格式创建消息
        
        Args:
            messages: 聊天消息列表，格式：
                [{"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}]
            system_prompt: 系统提示词
            
        Returns:
            统一消息列表
        """
        unified_messages = []
        
        # 系统消息
        if system_prompt:
            system_msg = UnifiedMessage("system")
            system_msg.add_text(system_prompt)
            unified_messages.append(system_msg)
        
        # 转换其他消息
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            
            unified_msg = UnifiedMessage(role)
            
            if isinstance(content, str):
                unified_msg.add_text(content)
            elif isinstance(content, list):
                # 多模态内容
                for item in content:
                    if isinstance(item, dict):
                        item_type = item.get("type", "text")
                        if item_type == "text":
                            unified_msg.add_text(item.get("text", ""))
                        elif item_type == "image_url":
                            image_url = item.get("image_url", {}).get("url", "")
                            unified_msg.add_image(image_url)
                    else:
                        unified_msg.add_text(str(item))
            
            if unified_msg.contents:
                unified_messages.append(unified_msg)
        
        return unified_messages
    
    @staticmethod
    def to_chat_format(messages: List[UnifiedMessage]) -> List[Dict[str, Any]]:
        """
        转换为聊天格式
        
        Args:
            messages: 统一消息列表
            
        Returns:
            聊天格式消息列表
        """
        chat_messages = []
        
        for msg in messages:
            chat_format = msg.to_openai_format()
            chat_messages.append(chat_format)
        
        return chat_messages
    
    @staticmethod
    def to_langchain_format(messages: List[UnifiedMessage]) -> List[Any]:
        """
        转换为LangChain格式
        
        Args:
            messages: 统一消息列表
            
        Returns:
            LangChain格式消息列表
        """
        from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
        
        lc_messages = []
        
        for msg in messages:
            lc_format = msg.to_langchain_format()
            
            if msg.role == "system":
                lc_messages.append(SystemMessage(content=lc_format["content"]))
            elif msg.role == "user":
                lc_messages.append(HumanMessage(content=lc_format["content"]))
            elif msg.role == "assistant":
                lc_messages.append(AIMessage(content=lc_format["content"]))
        
        return lc_messages
    
    @staticmethod
    def _is_image_path(text: str) -> bool:
        """判断字符串是否为图片路径"""
        if not isinstance(text, str):
            return False
        t = text.strip()
        # data URI 可能极长，必须在长度启发式之前识别
        if t.startswith("data:image/"):
            return True
        if len(t) > 1000:
            return False

        # 检查常见图片扩展名
        image_extensions = {'.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp', '.tiff', '.svg'}
        if any(t.lower().endswith(ext) for ext in image_extensions):
            return True

        # 检查文件是否存在且为图片
        if os.path.exists(t):
            try:
                # 尝试用PIL打开
                from PIL import Image
                with Image.open(t) as img:
                    return True
            except:
                pass
        
        return False


class InterleaveListBuilder:
    """Interleave List 构建器"""
    
    def __init__(self):
        self.items = []
    
    def add_text(self, text: str) -> "InterleaveListBuilder":
        """添加文本"""
        if text:
            self.items.append(text)
        return self
    
    def add_image(self, image_path: str) -> "InterleaveListBuilder":
        """添加图片"""
        if image_path:
            self.items.append(image_path)
        return self
    
    def add_item(self, item: Union[str, Dict[str, Any]]) -> "InterleaveListBuilder":
        """添加任意项目"""
        self.items.append(item)
        return self
    
    def build(self) -> List[Union[str, Dict[str, Any]]]:
        """构建interleave list"""
        return self.items.copy()
    
    def to_messages(self, system_prompt: str = "") -> List[UnifiedMessage]:
        """转换为统一消息"""
        return MessageBuilder.from_interleave_list(self.items, system_prompt)
    
    def clear(self) -> "InterleaveListBuilder":
        """清空"""
        self.items.clear()
        return self