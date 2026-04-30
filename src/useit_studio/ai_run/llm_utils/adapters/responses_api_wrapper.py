"""
OpenAI Responses API 包装器

用于支持gpt-5等新模型的Responses API，包装为LangChain兼容的接口
"""

import os
from typing import Dict, List, Any, Optional, AsyncGenerator, Iterator
from openai import OpenAI
from langchain_core.language_models import BaseLLM
from langchain_core.messages import BaseMessage, AIMessage
from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.outputs import LLMResult, Generation
from pydantic import PrivateAttr


class ResponsesAPILLM(BaseLLM):
    """
    OpenAI Responses API 的 LangChain 包装器
    """
    
    model: str = "gpt-5.2"
    api_key: Optional[str] = None
    max_tokens: int = 4096
    temperature: Optional[float] = None  # gpt-5不支持temperature
    streaming: bool = False
    
    # Pydantic(BaseLLM) 默认不允许动态字段；OpenAI client 用 PrivateAttr 存储
    _client: OpenAI = PrivateAttr()
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        
        # 获取API密钥
        if self.api_key is None:
            self.api_key = os.getenv("OPENAI_API_KEY")
        
        if not self.api_key:
            raise ValueError("OpenAI API key is required")
        
        # 初始化OpenAI客户端
        self._client = OpenAI(api_key=self.api_key)
    
    @property
    def _llm_type(self) -> str:
        return "openai-responses-api"
    
    def _generate(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> LLMResult:
        """同步生成"""
        import logging
        logger = logging.getLogger(__name__)

        # 转换消息格式
        responses_input = self._convert_messages_to_responses_format(messages)

        # Debug: 记录请求内容
        logger.info(f"[ResponsesAPI] Sending request with {len(responses_input)} messages")
        for i, msg in enumerate(responses_input):
            role = msg.get("role")
            content_items = msg.get("content", [])
            logger.info(f"[ResponsesAPI] Message {i}: role={role}, content_items={len(content_items)}")
            for j, item in enumerate(content_items):
                item_type = item.get("type")
                if item_type == "input_text":
                    text_preview = item.get("text", "")[:100]
                    logger.info(f"[ResponsesAPI]   Item {j}: type=input_text, text={text_preview}...")
                elif item_type == "input_image":
                    image_url = item.get("image_url", "")
                    url_preview = image_url[:100] if isinstance(image_url, str) else str(image_url)[:100]
                    logger.info(f"[ResponsesAPI]   Item {j}: type=input_image, url={url_preview}...")

        # 构建请求参数
        create_kwargs = {
            "model": self.model,
            "input": responses_input,
            "max_output_tokens": self.max_tokens,
        }

        # gpt-5特殊参数
        if self.model.startswith("gpt-5"):
            create_kwargs.update({
                "reasoning": {"effort": "none"},  # none = 关闭reasoning，最快
                "text": {"verbosity": "medium"},
            })
        else:
            # 其他模型支持temperature
            if self.temperature is not None:
                create_kwargs["temperature"] = self.temperature

        # 调用API
        try:
            response = self._client.responses.create(**create_kwargs)
            logger.info(f"[ResponsesAPI] Received response from {response.model}")
        except Exception as e:
            logger.error(f"[ResponsesAPI] API call failed: {e}")
            raise
        
        # 提取响应文本
        text = self._extract_text_from_response(response)
        
        # 提取token使用信息
        token_usage = self._extract_token_usage_from_response(response)
        
        # 创建Generation对象
        generation = Generation(
            text=text,
            generation_info={
                "token_usage": token_usage,
                "model": response.model,
                "finish_reason": "stop"
            }
        )
        
        return LLMResult(generations=[[generation]])
    
    async def _agenerate(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> LLMResult:
        """真正的异步生成"""
        import asyncio

        # 在线程池中运行同步的 _generate
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            lambda: self._generate(messages, stop, run_manager, **kwargs)
        )
    
    def _stream(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> Iterator[str]:
        """流式生成（Responses API目前不支持流式，返回完整响应）"""
        result = self._generate(messages, stop, run_manager, **kwargs)
        if result.generations and result.generations[0]:
            yield result.generations[0][0].text
    
    async def astream(self, messages: List[BaseMessage], **kwargs):
        """异步流式生成（模拟流式）"""
        import asyncio
        import re
        import logging
        from langchain_core.messages import AIMessageChunk

        logger = logging.getLogger(__name__)

        # 调用非流式API获取完整响应
        result = await self._agenerate(messages, **kwargs)

        if not result.generations or not result.generations[0]:
            logger.warning("[ResponsesAPI] astream: No generations in result")
            yield AIMessageChunk(content="")
            return

        generation = result.generations[0][0]
        text = generation.text
        generation_info = generation.generation_info or {}

        if not text:
            logger.warning("[ResponsesAPI] astream: Empty text in generation")
            yield AIMessageChunk(content="")
            return

        logger.info(f"[ResponsesAPI] astream: Starting simulated streaming for {len(text)} characters")

        # 按句子分块模拟流式
        # 使用正则表达式分割，保留分隔符
        sentences = re.split(r'([。！？\.\!\?\n]+)', text)

        chunk_count = 0
        for i in range(0, len(sentences), 2):
            sentence = sentences[i]
            if i + 1 < len(sentences):
                sentence += sentences[i + 1]  # 加上标点符号

            if sentence.strip():
                chunk_count += 1
                # Yield AIMessageChunk 而不是纯字符串
                yield AIMessageChunk(content=sentence)
                # 添加小延迟模拟真实流式
                await asyncio.sleep(0.01)

        # 最后一个 chunk 包含完整的 response_metadata（含 token usage）
        final_chunk = AIMessageChunk(
            content="",
            response_metadata=generation_info
        )
        yield final_chunk

        logger.info(f"[ResponsesAPI] astream: Completed streaming {chunk_count} chunks")
    
    def _convert_messages_to_responses_format(self, messages: List[BaseMessage]) -> List[Dict]:
        """转换LangChain消息为Responses API格式"""
        responses_input = []
        
        for message in messages:
            role = "user"  # 默认为user
            
            if hasattr(message, 'type'):
                if message.type == "system":
                    role = "system"
                elif message.type == "ai":
                    role = "assistant"
                elif message.type == "human":
                    role = "user"
            
            # 处理消息内容
            content = message.content
            content_list = []
            
            if isinstance(content, str):
                # 纯文本
                content_list = [{"type": "input_text", "text": content}]
            elif isinstance(content, list):
                # 多模态内容
                for item in content:
                    if isinstance(item, dict):
                        if item.get("type") == "text":
                            content_list.append({"type": "input_text", "text": item.get("text", "")})
                        elif item.get("type") == "image_url":
                            image_url = item.get("image_url", {}).get("url", "")
                            content_list.append({"type": "input_image", "image_url": image_url})
                    else:
                        content_list.append({"type": "input_text", "text": str(item)})
            else:
                content_list = [{"type": "input_text", "text": str(content)}]
            
            responses_input.append({
                "role": role,
                "content": content_list
            })
        
        return responses_input
    
    def _extract_text_from_response(self, response) -> str:
        """从Responses API响应中提取文本"""
        import logging
        logger = logging.getLogger(__name__)

        outputs = getattr(response, "output", [])
        logger.info(f"[ResponsesAPI] Response has {len(outputs) if outputs else 0} output(s)")

        if not outputs:
            logger.warning("[ResponsesAPI] No outputs in response")
            return ""

        for idx, output in enumerate(outputs):
            output_type = getattr(output, "type", None)
            logger.info(f"[ResponsesAPI] Output {idx}: type={output_type}")

            # 跳过thinking/reasoning输出
            if output_type in ["thinking", "reasoning"]:
                logger.info(f"[ResponsesAPI] Skipping {output_type} output")
                continue

            # 获取第一个content
            if hasattr(output, "content") and output.content:
                logger.info(f"[ResponsesAPI] Output {idx} has {len(output.content)} content item(s)")
                for content_idx, content in enumerate(output.content):
                    if hasattr(content, "text"):
                        text = content.text
                        logger.info(f"[ResponsesAPI] Found text content (length={len(text)}): {text[:100]}...")
                        return text
                    else:
                        logger.warning(f"[ResponsesAPI] Content {content_idx} has no text attribute")
            else:
                logger.warning(f"[ResponsesAPI] Output {idx} has no content")

        logger.warning("[ResponsesAPI] No text content found in response")
        return ""
    
    def _extract_token_usage_from_response(self, response) -> Dict[str, int]:
        """从Responses API响应中提取token使用信息"""
        usage = getattr(response, "usage", None)
        if not usage:
            return {"total_tokens": 0, "prompt_tokens": 0, "completion_tokens": 0}
        
        return {
            "total_tokens": getattr(usage, "total_tokens", 0),
            "prompt_tokens": getattr(usage, "input_tokens", 0),
            "completion_tokens": getattr(usage, "output_tokens", 0)
        }
    
    def invoke(self, input_messages, **kwargs) -> AIMessage:
        """LangChain兼容的invoke方法"""
        result = self._generate(input_messages, **kwargs)
        
        if result.generations and result.generations[0]:
            generation = result.generations[0][0]
            return AIMessage(
                content=generation.text,
                response_metadata=generation.generation_info or {}
            )
        
        return AIMessage(content="")
    
    async def ainvoke(self, input_messages, **kwargs) -> AIMessage:
        """LangChain兼容的异步invoke方法"""
        result = await self._agenerate(input_messages, **kwargs)
        
        if result.generations and result.generations[0]:
            generation = result.generations[0][0]
            return AIMessage(
                content=generation.text,
                response_metadata=generation.generation_info or {}
            )
        
        return AIMessage(content="")