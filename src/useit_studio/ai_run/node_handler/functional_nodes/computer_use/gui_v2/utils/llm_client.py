"""
GUI Agent V2 - 统一 LLM 客户端

简化的 LLM 调用封装，支持多模态和流式输出。
直接复用项目已有的 UnifiedClient。
"""

import os
import json
import base64
from datetime import datetime
from typing import List, Dict, Any, Optional, AsyncGenerator, Union
from dataclasses import dataclass

from useit_studio.ai_run.llm_utils import UnifiedClient
from useit_studio.ai_run.utils.logger_utils import LoggerUtils


@dataclass
class LLMConfig:
    """LLM 配置"""
    model: str = "gemini-3-flash-preview"
    max_tokens: int = 4096
    temperature: float = 0.0
    api_key: Optional[str] = None
    # 日志相关配置
    role: str = "unknown"  # planner, actor, intent_refiner, completion_summarizer
    node_id: str = ""
    
    @classmethod
    def from_dict(cls, config: Dict[str, Any]) -> "LLMConfig":
        return cls(
            model=config.get("model", "gemini-3-flash-preview"),
            max_tokens=config.get("max_tokens", 4096),
            temperature=config.get("temperature", 0.0),
            api_key=config.get("api_key") or config.get("OPENAI_API_KEY"),
            role=config.get("role", "unknown"),
            node_id=config.get("node_id", ""),
        )


class VLMClient:
    """
    视觉语言模型客户端
    
    简化的接口，专注于 GUI Agent 的使用场景：
    1. 支持图文混合输入
    2. 支持流式输出
    3. 自动处理截图编码
    """
    
    def __init__(
        self,
        config: Optional[LLMConfig] = None,
        api_keys: Optional[Dict[str, str]] = None,
        logger: Optional[LoggerUtils] = None,
    ):
        self.config = config or LLMConfig()
        self.logger = logger or LoggerUtils(component_name="VLMClient")
        
        # 根据模型类型选择正确的 API Key
        api_key = self._get_api_key_for_model(self.config.model, api_keys)
        
        # 初始化统一客户端
        self._client = UnifiedClient(
            model=self.config.model,
            api_key=api_key,
            max_tokens=self.config.max_tokens,
            temperature=self.config.temperature,
            session_id=f"VLMClient_{id(self)}",
        )
        
        self.logger.logger.info(f"[VLMClient] 初始化完成，模型: {self.config.model}")
    
    def _get_api_key_for_model(
        self,
        model: str,
        api_keys: Optional[Dict[str, str]] = None,
    ) -> Optional[str]:
        """
        根据模型类型自动选择正确的 API Key
        
        Args:
            model: 模型名称
            api_keys: API Keys 字典
            
        Returns:
            对应的 API Key
        """
        model_lower = model.lower()
        
        # Gemini/Google 模型
        if "gemini" in model_lower or "google" in model_lower:
            return (
                self.config.api_key or
                (api_keys.get("GOOGLE_API_KEY") if api_keys else None) or
                os.getenv("GOOGLE_API_KEY")
            )
        
        # Claude/Anthropic 模型
        if "claude" in model_lower or "anthropic" in model_lower:
            return (
                self.config.api_key or
                (api_keys.get("ANTHROPIC_API_KEY") if api_keys else None) or
                (api_keys.get("CLAUDE_API_KEY") if api_keys else None) or
                os.getenv("ANTHROPIC_API_KEY") or
                os.getenv("CLAUDE_API_KEY")
            )
        
        # 默认使用 OpenAI API Key (GPT, O1, etc.)
        return (
            self.config.api_key or
            (api_keys.get("OPENAI_API_KEY") if api_keys else None) or
            os.getenv("OPENAI_API_KEY")
        )
    
    async def call(
        self,
        prompt: str,
        system_prompt: str = "",
        screenshot_path: Optional[str] = None,
        screenshot_base64: Optional[str] = None,
        attached_images_base64: Optional[List[str]] = None,
        log_dir: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        非流式调用
        
        Args:
            prompt: 用户提示
            system_prompt: 系统提示
            screenshot_path: 截图路径（可选）
            screenshot_base64: base64 编码的截图（可选，优先级高于 screenshot_path）
            log_dir: 日志目录（可选）
            
        Returns:
            {"content": str, "token_usage": {...}}
        """
        messages = self._build_messages(
            prompt,
            screenshot_path,
            screenshot_base64,
            attached_images_base64,
        )
        
        if log_dir:
            self._log_request(messages, system_prompt, log_dir)
        
        response = await self._client.call(messages, system_prompt)
        
        # 记录原始响应信息用于调试
        raw_content = response.content
        raw_content_type = type(raw_content).__name__
        finish_reason = response.finish_reason
        response_metadata = response.metadata or {}
        
        # 将 token_usage 详细信息添加到 metadata 中，用于调试
        token_usage_obj = response.token_usage
        response_metadata["_token_usage_details"] = {
            "input_tokens": token_usage_obj.input_tokens if token_usage_obj else 0,
            "output_tokens": token_usage_obj.output_tokens if token_usage_obj else 0,
            "total_tokens": token_usage_obj.total_tokens if token_usage_obj else 0,
            "model": token_usage_obj.model if token_usage_obj else "",
            "cost": token_usage_obj.cost if token_usage_obj else 0.0,
        }
        
        # 处理 content 可能是列表的情况（LangChain Gemini 适配器可能返回列表）
        content = raw_content
        if isinstance(content, list):
            # 提取所有文本内容并拼接
            text_parts = []
            for item in content:
                if isinstance(item, str):
                    text_parts.append(item)
                elif isinstance(item, dict) and "text" in item:
                    text_parts.append(item["text"])
            content = "".join(text_parts)
        
        result = {
            "content": content,
            "token_usage": {
                self.config.model: response.token_usage.total_tokens,
            },
        }
        
        if log_dir:
            self._log_response(
                result, log_dir, 
                streaming=False, 
                raw_content_type=raw_content_type,
                finish_reason=finish_reason,
                response_metadata=response_metadata,
            )
        
        return result
    
    async def stream(
        self,
        prompt: str,
        system_prompt: str = "",
        screenshot_path: Optional[str] = None,
        screenshot_base64: Optional[str] = None,
        attached_images_base64: Optional[List[str]] = None,
        log_dir: Optional[str] = None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        流式调用
        
        Yields:
            {"type": "delta", "content": str} - 增量文本
            {"type": "complete", "content": str, "token_usage": {...}} - 完成
        """
        messages = self._build_messages(
            prompt,
            screenshot_path,
            screenshot_base64,
            attached_images_base64,
        )
        
        if log_dir:
            self._log_request(messages, system_prompt, log_dir)
        
        full_content = []
        
        async for chunk in self._client.stream(messages, system_prompt):
            if chunk.chunk_type == "text":
                full_content.append(chunk.content)
                yield {"type": "delta", "content": chunk.content}
                
            elif chunk.chunk_type == "complete":
                token_usage = chunk.metadata.get("token_usage")
                result = {
                    "type": "complete",
                    "content": "".join(full_content),
                    "token_usage": {
                        self.config.model: token_usage.total_tokens if token_usage else 0,
                    },
                }
                
                if log_dir:
                    self._log_response(result, log_dir, streaming=True)
                
                yield result
                
            elif chunk.chunk_type == "error":
                # 记录错误
                if log_dir:
                    self._log_error(chunk.content, log_dir, {"phase": "streaming"})
                yield {"type": "error", "content": chunk.content}
    
    async def call_with_tools(
        self,
        prompt: str,
        tools: List[Dict],
        system_prompt: str = "",
        tool_choice: str = "auto",
        screenshot_path: Optional[str] = None,
        screenshot_base64: Optional[str] = None,
        attached_images_base64: Optional[List[str]] = None,
        log_dir: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        带 Tool Calling 的调用
        
        Args:
            prompt: 用户提示
            tools: 工具定义列表，格式：
                [{
                    "name": "tool_name",
                    "description": "Tool description",
                    "parameters": {
                        "type": "object",
                        "properties": {...},
                        "required": [...]
                    }
                }]
            system_prompt: 系统提示
            tool_choice: 工具选择策略
                - "auto": 模型自动决定是否调用工具
                - "required": 强制模型调用工具
                - "none": 禁止调用工具
                - 具体工具名: 强制调用指定工具
            screenshot_path: 截图路径（可选）
            screenshot_base64: base64 编码的截图（可选，优先级高于 screenshot_path）
            log_dir: 日志目录（可选）
            
        Returns:
            {
                "content": str,           # 文本内容（可能为空）
                "tool_calls": [...],      # 工具调用列表
                "has_tool_calls": bool,   # 是否有工具调用
                "token_usage": {...}
            }
            
        Example:
            tools = [{
                "name": "execute_powershell",
                "description": "Execute PowerShell code",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "code": {"type": "string", "description": "PowerShell code to execute"}
                    },
                    "required": ["code"]
                }
            }]
            
            result = await vlm.call_with_tools(
                prompt="Open the document",
                tools=tools,
                tool_choice="required",
                system_prompt="Generate PowerShell code"
            )
            
            if result["has_tool_calls"]:
                code = result["tool_calls"][0]["args"]["code"]
        """
        messages = self._build_messages(
            prompt,
            screenshot_path,
            screenshot_base64,
            attached_images_base64,
        )
        
        if log_dir:
            self._log_request(messages, system_prompt, log_dir)
        
        response = await self._client.call_with_tools(
            messages=messages,
            tools=tools,
            system_prompt=system_prompt,
            tool_choice=tool_choice,
        )
        
        # 处理响应
        result = {
            "content": response.content or "",
            "tool_calls": response.tool_calls or [],
            "has_tool_calls": response.has_tool_calls,
            "token_usage": {
                self.config.model: response.token_usage.total_tokens if response.token_usage else 0,
            },
        }
        
        if log_dir:
            self._log_response(
                result, log_dir,
                streaming=False,
                response_metadata=response.metadata,
            )
        
        return result
    
    def _build_messages(
        self,
        prompt: str,
        screenshot_path: Optional[str] = None,
        screenshot_base64: Optional[str] = None,
        attached_images_base64: Optional[List[str]] = None,
    ) -> List[Union[str, Any]]:
        """
        构建消息列表（interleave 格式）
        
        Args:
            prompt: 用户提示文本
            screenshot_path: 截图文件路径（可选）
            screenshot_base64: base64 编码的截图（可选，优先级高于 screenshot_path）
        """
        messages = [prompt]
        
        # 优先使用 base64 截图
        if screenshot_base64:
            # 使用字典格式传递 base64 图片
            messages.append({
                "type": "image",
                "content": self._normalize_base64_image(screenshot_base64),
                "format": "base64",
            })
        elif screenshot_path and os.path.exists(screenshot_path):
            # 直接传递路径，UnifiedClient 会处理
            messages.append(screenshot_path)
        
        if attached_images_base64:
            for img in attached_images_base64:
                if not img:
                    continue
                messages.append({
                    "type": "image",
                    "content": self._normalize_base64_image(img),
                    "format": "base64",
                })
        
        return messages

    def _normalize_base64_image(self, image_data: str) -> str:
        """标准化 base64 图片数据，移除 data URI 前缀"""
        value = image_data.strip()
        if value.startswith("data:") and "," in value:
            return value.split(",", 1)[1]
        return value
    
    def _get_log_filename(self, suffix: str) -> str:
        """
        生成带角色和节点信息的日志文件名
        
        格式: {role}_{node_id}_{suffix}.json
        例如: planner_node123_request.json, actor_node123_response.json
        """
        role = self.config.role or "unknown"
        node_id = self.config.node_id or "unknown"
        # 截断 node_id 避免文件名过长
        if len(node_id) > 20:
            node_id = node_id[:20]
        return f"{role}_{node_id}_{suffix}.json"
    
    def _log_request(self, messages: List, system_prompt: str, log_dir: str):
        """
        记录请求
        
        文件名格式: {role}_{node_id}_request.json
        
        注意：
        - 文本内容完整记录
        - 图片路径记录为 [IMAGE: path]
        - Base64 数据截断为前100字符 + 长度信息
        """
        try:
            filename = self._get_log_filename("request")
            
            # 处理消息内容
            processed_messages = []
            for m in messages:
                processed_messages.append(self._process_message_for_log(m))
            
            log_data = {
                "timestamp": datetime.now().isoformat(),
                "role": self.config.role,
                "node_id": self.config.node_id,
                "model": self.config.model,
                "max_tokens": self.config.max_tokens,
                "temperature": self.config.temperature,
                "system_prompt": system_prompt,  # 完整内容
                "user_prompt": processed_messages[0] if processed_messages else "",  # 完整内容
                "has_image": len(processed_messages) > 1,
                "image_info": processed_messages[1] if len(processed_messages) > 1 else None,
            }
            
            self._write_json(log_dir, filename, log_data)
            
            # 同时生成 markdown 格式的 prompt 文件（方便阅读）
            self._log_request_markdown(system_prompt, processed_messages, log_dir)
            
        except Exception as e:
            self.logger.logger.warning(f"记录请求失败: {e}")
    
    def _log_request_markdown(self, system_prompt: str, processed_messages: List, log_dir: str):
        """
        生成 markdown 格式的 prompt 文件，方便阅读
        
        文件名格式: {role}_{node_id}_prompt.md
        """
        try:
            filename = self._get_log_filename("prompt").replace(".json", ".md")
            filepath = os.path.join(log_dir, filename)
            
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(f"# {self.config.role.upper()} Prompt\n\n")
                f.write(f"**Model**: {self.config.model}\n")
                f.write(f"**Max Tokens**: {self.config.max_tokens}\n")
                f.write(f"**Temperature**: {self.config.temperature}\n")
                f.write(f"**Node ID**: {self.config.node_id}\n")
                f.write(f"**Timestamp**: {datetime.now().isoformat()}\n\n")
                
                f.write("---\n\n")
                f.write("## System Prompt\n\n")
                f.write("```\n")
                f.write(system_prompt)
                f.write("\n```\n\n")
                
                f.write("---\n\n")
                f.write("## User Prompt\n\n")
                if processed_messages:
                    user_prompt = processed_messages[0]
                    # 如果是纯文本，直接显示
                    if isinstance(user_prompt, str) and not user_prompt.startswith("["):
                        f.write(user_prompt)
                    else:
                        f.write("```\n")
                        f.write(str(user_prompt))
                        f.write("\n```\n")
                    f.write("\n\n")
                    
                    # 如果有图片信息
                    if len(processed_messages) > 1:
                        f.write("### Image Info\n\n")
                        f.write(f"```\n{processed_messages[1]}\n```\n")
                
        except Exception as e:
            self.logger.logger.warning(f"记录 markdown prompt 失败: {e}")
    
    def _process_message_for_log(self, message: Any) -> str:
        """
        处理消息内容用于日志记录
        
        - 文件路径: [IMAGE: path]
        - Base64 数据: [BASE64_IMAGE: length=xxx, preview=xxx...]
        - 其他: 原样返回
        """
        if isinstance(message, str):
            # 检查是否是文件路径
            if os.path.exists(message) and (message.endswith('.png') or message.endswith('.jpg') or message.endswith('.jpeg')):
                return f"[IMAGE_PATH: {message}]"
            
            # 检查是否是 base64 数据（通常很长且包含特定字符）
            if len(message) > 1000 and self._looks_like_base64(message):
                return f"[BASE64_IMAGE: length={len(message)}, preview={message[:100]}...]"
            
            # 普通文本
            return message
        
        elif isinstance(message, dict):
            # 可能是包含图片的字典格式
            if 'image' in message or 'image_url' in message or 'data' in message:
                return f"[IMAGE_DICT: keys={list(message.keys())}]"
            return str(message)
        
        else:
            # 其他类型
            result = str(message)
            if len(result) > 1000 and self._looks_like_base64(result):
                return f"[BASE64_DATA: length={len(result)}, preview={result[:100]}...]"
            return result
    
    def _looks_like_base64(self, text: str) -> bool:
        """
        简单判断是否像 base64 数据
        
        Base64 特征：
        - 只包含 A-Z, a-z, 0-9, +, /, = 字符
        - 通常很长
        - 可能以 data:image 开头
        """
        if text.startswith('data:image'):
            return True
        
        # 检查前200个字符是否符合 base64 特征
        sample = text[:200].replace('\n', '').replace('\r', '')
        base64_chars = set('ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/=')
        
        # 如果90%以上的字符都是 base64 字符，认为是 base64
        if len(sample) > 0:
            base64_ratio = sum(1 for c in sample if c in base64_chars) / len(sample)
            return base64_ratio > 0.9
        
        return False
    
    def _log_response(
        self, 
        result: Dict, 
        log_dir: str, 
        error: str = None, 
        streaming: bool = None, 
        raw_content_type: str = None,
        finish_reason: str = None,
        response_metadata: Dict = None,
    ):
        """
        记录响应（完整内容，不截断）
        
        文件名格式: {role}_{node_id}_response.json
        
        Args:
            result: 响应结果
            log_dir: 日志目录
            error: 错误信息
            streaming: 是否是流式调用（True=流式, False=非流式, None=未知）
            raw_content_type: 原始 content 的类型（用于调试）
            finish_reason: LLM 完成原因（stop, length, error 等）
            response_metadata: LLM 响应的元数据
        """
        try:
            filename = self._get_log_filename("response")
            
            log_data = {
                "timestamp": datetime.now().isoformat(),
                "role": self.config.role,
                "node_id": self.config.node_id,
                "model": self.config.model,
                "mode": "streaming" if streaming else ("non-streaming" if streaming is False else "unknown"),
                "status": "error" if error else "success",
                "content": result.get("content", ""),  # 完整内容
                "token_usage": result.get("token_usage", {}),
                "error": error,
            }
            
            # 记录 tool_calls（如果有）
            if result.get("tool_calls"):
                log_data["tool_calls"] = result["tool_calls"]
                log_data["has_tool_calls"] = result.get("has_tool_calls", True)
            
            # 添加调试信息
            if raw_content_type:
                log_data["raw_content_type"] = raw_content_type
            if finish_reason:
                log_data["finish_reason"] = finish_reason
            if response_metadata:
                # 只记录关键的 metadata 字段，避免日志过大
                log_data["finish_reason_from_metadata"] = response_metadata.get("finish_reason")
                log_data["safety_ratings"] = response_metadata.get("safety_ratings")
                
                # 同时将完整的 response_metadata 保存到单独的文件，用于调试 MAX_TOKENS 等问题
                self._log_response_metadata(response_metadata, log_dir)
            
            self._write_json(log_dir, filename, log_data)
            
            # 同时生成 markdown 格式的 response 文件（方便阅读）
            self._log_response_markdown(result, log_dir, error, streaming, finish_reason)
            
        except Exception as e:
            self.logger.logger.warning(f"记录响应失败: {e}")
    
    def _log_response_markdown(
        self, 
        result: Dict, 
        log_dir: str, 
        error: str = None,
        streaming: bool = None,
        finish_reason: str = None,
    ):
        """
        生成 markdown 格式的 response 文件，方便阅读
        
        文件名格式: {role}_{node_id}_response.md
        """
        try:
            filename = self._get_log_filename("response").replace(".json", ".md")
            filepath = os.path.join(log_dir, filename)
            
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(f"# {self.config.role.upper()} Response\n\n")
                f.write(f"**Model**: {self.config.model}\n")
                f.write(f"**Node ID**: {self.config.node_id}\n")
                f.write(f"**Mode**: {'streaming' if streaming else ('non-streaming' if streaming is False else 'unknown')}\n")
                f.write(f"**Status**: {'error' if error else 'success'}\n")
                if finish_reason:
                    f.write(f"**Finish Reason**: {finish_reason}\n")
                f.write(f"**Timestamp**: {datetime.now().isoformat()}\n\n")
                
                # Token usage
                token_usage = result.get("token_usage", {})
                if token_usage:
                    f.write("## Token Usage\n\n")
                    f.write(f"- Input: {token_usage.get('input_tokens', 'N/A')}\n")
                    f.write(f"- Output: {token_usage.get('output_tokens', 'N/A')}\n")
                    f.write(f"- Total: {token_usage.get('total_tokens', 'N/A')}\n\n")
                
                f.write("---\n\n")
                
                # Error
                if error:
                    f.write("## Error\n\n")
                    f.write(f"```\n{error}\n```\n\n")
                    f.write("---\n\n")
                
                # Response content
                f.write("## Response Content\n\n")
                content = result.get("content", "")
                if content:
                    # 尝试格式化 JSON 内容
                    try:
                        import json
                        parsed = json.loads(content)
                        f.write("```json\n")
                        f.write(json.dumps(parsed, indent=2, ensure_ascii=False))
                        f.write("\n```\n")
                    except (json.JSONDecodeError, TypeError):
                        # 不是 JSON，直接输出
                        f.write(content)
                        f.write("\n")
                else:
                    f.write("(empty)\n")
                
                # Tool calls
                if result.get("tool_calls"):
                    f.write("\n---\n\n")
                    f.write("## Tool Calls\n\n")
                    f.write("```json\n")
                    import json
                    f.write(json.dumps(result["tool_calls"], indent=2, ensure_ascii=False))
                    f.write("\n```\n")
                
        except Exception as e:
            self.logger.logger.warning(f"记录 markdown response 失败: {e}")
    
    def _log_response_metadata(self, response_metadata: Dict, log_dir: str):
        """
        将完整的 response_metadata 保存到单独的文件
        
        用于调试 MAX_TOKENS、token usage 等问题
        文件名格式: {role}_{node_id}_response_metadata.json
        """
        try:
            filename = self._get_log_filename("response_metadata")
            
            log_data = {
                "timestamp": datetime.now().isoformat(),
                "role": self.config.role,
                "node_id": self.config.node_id,
                "model": self.config.model,
                "response_metadata": response_metadata,
            }
            
            self._write_json(log_dir, filename, log_data)
            self.logger.logger.debug(f"[VLMClient] 已保存完整 response_metadata 到 {filename}")
            
        except Exception as e:
            self.logger.logger.warning(f"记录 response_metadata 失败: {e}")
    
    def _log_error(self, error_msg: str, log_dir: str, context: Dict = None):
        """
        记录错误
        
        文件名格式: {role}_{node_id}_error.json
        """
        try:
            filename = self._get_log_filename("error")
            
            log_data = {
                "timestamp": datetime.now().isoformat(),
                "role": self.config.role,
                "node_id": self.config.node_id,
                "model": self.config.model,
                "error": error_msg,
                "context": context or {},
            }
            
            self._write_json(log_dir, filename, log_data)
            
        except Exception as e:
            self.logger.logger.warning(f"记录错误失败: {e}")
    
    def _write_json(self, log_dir: str, filename: str, data: Dict):
        """写入 JSON 文件"""
        os.makedirs(log_dir, exist_ok=True)
        filepath = os.path.join(log_dir, filename)
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)


def encode_image_base64(image_path: str) -> str:
    """将图片编码为 base64"""
    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")
