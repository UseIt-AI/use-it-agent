"""
统一消息类型定义

支持 Interleave list 格式: ["image", "text", "image", ...]
"""

from typing import Union, List, Dict, Any, Literal, Optional, Tuple
from dataclasses import dataclass
from abc import ABC, abstractmethod
import base64
import os


def split_image_data_uri(s: str) -> Tuple[Optional[str], str]:
    """If ``s`` is a ``data:image/...;base64,...`` URI, return ``(mime, raw_b64)``.

    Otherwise return ``(None, s)`` (second value is the original string for callers
    that need to fall back to path / plain base64 heuristics).
    """
    if not isinstance(s, str):
        return None, s
    t = s.strip()
    if not t.startswith("data:image/"):
        return None, t
    comma = t.find(",")
    if comma == -1:
        return None, t
    meta = t[len("data:") : comma]
    payload = t[comma + 1 :]
    if "base64" not in meta.lower():
        return None, t
    mime = meta.split(";", 1)[0].strip() or "image/png"
    return mime, payload


@dataclass
class TextContent:
    """文本内容"""
    type: Literal["text"] = "text"
    content: str = ""


@dataclass 
class ImageContent:
    """图像内容"""
    type: Literal["image"] = "image"
    content: str = ""  # 可以是文件路径或base64数据
    format: str = "auto"  # auto, base64, file_path
    
    
@dataclass
class Message:
    """统一消息格式"""
    role: Literal["system", "user", "assistant"] = "user"
    content: List[Union[TextContent, ImageContent]] = None
    
    def __post_init__(self):
        if self.content is None:
            self.content = []


class MessageContent(ABC):
    """消息内容基类"""
    
    @abstractmethod
    def to_langchain_format(self) -> Dict[str, Any]:
        """转换为LangChain格式"""
        pass
    
    @abstractmethod
    def to_openai_format(self) -> Dict[str, Any]:
        """转换为OpenAI格式"""
        pass


class TextMessageContent(MessageContent):
    """文本消息内容"""
    
    def __init__(self, text: str):
        self.text = text
    
    def to_langchain_format(self) -> Dict[str, Any]:
        return {"type": "text", "text": self.text}
    
    def to_openai_format(self) -> Dict[str, Any]:
        return {"type": "text", "text": self.text}


class ImageMessageContent(MessageContent):
    """图像消息内容"""
    
    def __init__(self, image_data: str, format: str = "auto"):
        self.image_data = image_data
        self.format = format
        self._base64_data = None
        self._mime_type = None  # 缓存检测到的 MIME type
        
    def _ensure_base64(self) -> str:
        """确保图像数据为base64格式"""
        if self._base64_data:
            return self._base64_data

        work = self.image_data
        mime_hint, stripped = split_image_data_uri(work)
        if mime_hint:
            if not stripped:
                raise ValueError("Empty base64 payload in data:image URI")
            if not self._mime_type:
                self._mime_type = mime_hint
            self._base64_data = stripped
            return self._base64_data
        work = stripped

        if self.format == "base64" or self._is_base64(work):
            self._base64_data = work
        elif self.format == "file_path" or os.path.exists(work):
            self._base64_data = self._file_to_base64(work)
        else:
            # Auto detect
            if self._is_base64(work):
                self._base64_data = work
            elif os.path.exists(work):
                self._base64_data = self._file_to_base64(work)
            else:
                raise ValueError(f"Invalid image data: {self.image_data[:100]}...")

        return self._base64_data

    def _is_base64(self, data: str) -> bool:
        """检查是否为base64格式"""
        try:
            mime_hint, payload = split_image_data_uri(data)
            if mime_hint is not None:
                data = payload
            if len(data) < 100:
                return False
            # 简单检查base64格式
            return all(
                c in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/="
                for c in data[:100]
            )
        except Exception:
            return False
    
    def _file_to_base64(self, file_path: str) -> str:
        """文件转base64"""
        try:
            with open(file_path, 'rb') as f:
                return base64.b64encode(f.read()).decode('utf-8')
        except Exception as e:
            raise ValueError(f"Failed to read image file {file_path}: {e}")
    
    def _detect_mime_type(self, base64_data: str) -> str:
        """
        根据 base64 数据检测图像的 MIME type
        
        通过解码 base64 数据的前几个字节来检测图像格式（magic bytes）
        支持: PNG, JPEG, GIF, WebP
        """
        if self._mime_type:
            return self._mime_type
        
        try:
            # 解码前 16 个字节足够检测大多数图像格式
            decoded = base64.b64decode(base64_data[:24])
            
            # PNG: 89 50 4E 47 0D 0A 1A 0A
            if decoded[:8] == b'\x89PNG\r\n\x1a\n':
                self._mime_type = "image/png"
            # JPEG: FF D8 FF
            elif decoded[:3] == b'\xff\xd8\xff':
                self._mime_type = "image/jpeg"
            # GIF: 47 49 46 38 (GIF8)
            elif decoded[:4] == b'GIF8':
                self._mime_type = "image/gif"
            # WebP: 52 49 46 46 ... 57 45 42 50 (RIFF...WEBP)
            elif decoded[:4] == b'RIFF' and decoded[8:12] == b'WEBP':
                self._mime_type = "image/webp"
            else:
                # 默认使用 PNG
                self._mime_type = "image/png"
        except Exception:
            # 解码失败时默认使用 PNG
            self._mime_type = "image/png"
        
        return self._mime_type
    
    def to_langchain_format(self) -> Dict[str, Any]:
        base64_data = self._ensure_base64()
        mime_type = self._detect_mime_type(base64_data)
        return {
            "type": "image_url",
            "image_url": {"url": f"data:{mime_type};base64,{base64_data}"}
        }
    
    def to_openai_format(self) -> Dict[str, Any]:
        base64_data = self._ensure_base64()
        mime_type = self._detect_mime_type(base64_data)
        return {
            "type": "image_url", 
            "image_url": {"url": f"data:{mime_type};base64,{base64_data}"}
        }


class UnifiedMessage:
    """统一消息类"""
    
    def __init__(self, role: str = "user", contents: List[MessageContent] = None):
        self.role = role
        self.contents = contents or []
    
    def add_text(self, text: str) -> "UnifiedMessage":
        """添加文本内容"""
        self.contents.append(TextMessageContent(text))
        return self
    
    def add_image(self, image_data: str, format: str = "auto") -> "UnifiedMessage":
        """添加图像内容"""
        self.contents.append(ImageMessageContent(image_data, format))
        return self
    
    def to_langchain_format(self) -> Dict[str, Any]:
        """转换为LangChain格式"""
        if len(self.contents) == 1 and isinstance(self.contents[0], TextMessageContent):
            # 纯文本消息简化格式
            return {"role": self.role, "content": self.contents[0].text}
        
        # 多模态消息
        content_list = [content.to_langchain_format() for content in self.contents]
        return {"role": self.role, "content": content_list}
    
    def to_openai_format(self) -> Dict[str, Any]:
        """转换为OpenAI格式"""
        content_list = [content.to_openai_format() for content in self.contents]
        return {"role": self.role, "content": content_list}


def interleave_to_messages(interleave_list: List[str], system_prompt: str = "") -> List[UnifiedMessage]:
    """
    将interleave list转换为统一消息格式
    
    Args:
        interleave_list: ["text", "image.png", "text", ...] 格式的列表
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
    
    # 处理用户消息 - 将所有内容合并为一个消息
    if interleave_list:
        user_msg = UnifiedMessage("user")
        
        for item in interleave_list:
            if isinstance(item, str):
                # 判断是图片路径还是文本
                if _is_image_path(item):
                    user_msg.add_image(item)
                else:
                    user_msg.add_text(item)
            else:
                # 其他类型转为字符串
                user_msg.add_text(str(item))
        
        messages.append(user_msg)
    
    return messages


def _is_image_path(text: str) -> bool:
    """判断是否为图片路径"""
    if not isinstance(text, str):
        return False
    t = text.strip()
    if t.startswith("data:image/"):
        return True

    image_extensions = {'.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp', '.tiff'}

    # 检查文件扩展名
    if any(t.lower().endswith(ext) for ext in image_extensions):
        return True
    
    # 检查文件是否存在且为图片
    if os.path.exists(t):
        try:
            from PIL import Image
            Image.open(t)
            return True
        except:
            pass
    
    return False