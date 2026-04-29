"""
RAG Query Extender - 查询分解/扩展逻辑

将用户问题分解为多个子查询，用于并行检索知识库。
参考 web_search 的 Query Decomposition 实现。
"""

from typing import List, Optional, Dict, Any, Callable
import json
import re

from useit_studio.ai_run.utils.logger_utils import LoggerUtils
from useit_studio.ai_run.llm_utils import UnifiedClient

logger = LoggerUtils(component_name="RAGQueryExtender")


# 进度回调函数类型: (event_dict) -> None
ProgressCallback = Callable[[Dict[str, Any]], None]


class RAGQueryExtender:
    """
    RAG 查询扩展器

    将用户问题分解为 1-3 个子查询，用于更全面的知识库检索。
    使用 LLM (gpt-4o-mini) 进行智能分解。
    """

    def __init__(
        self,
        openai_api_key: str = "",
        max_sub_queries: int = 3,
        model: str = "gpt-4o-mini",
    ):
        """
        初始化 Query Extender

        Args:
            openai_api_key: OpenAI API 密钥
            max_sub_queries: 最大子查询数量
            model: 使用的 LLM 模型
        """
        self.openai_api_key = openai_api_key
        self.max_sub_queries = max_sub_queries
        self.model = model

        # 延迟初始化 UnifiedClient
        self._client: Optional[UnifiedClient] = None

        logger.logger.info(
            f"[RAGQueryExtender] Initialized with model={model}, "
            f"max_sub_queries={max_sub_queries}"
        )

    def _get_client(self) -> Optional[UnifiedClient]:
        """获取 UnifiedClient（延迟初始化）"""
        if self._client is None and self.openai_api_key:
            self._client = UnifiedClient(
                model=self.model,
                api_key=self.openai_api_key,
                max_tokens=200,
                temperature=0.0,
                session_id="RAGQueryExtender",
            )
        return self._client

    async def extend(
        self,
        query: str,
        on_progress: Optional[ProgressCallback] = None,
    ) -> List[str]:
        """
        将用户问题分解为多个搜索子查询

        Args:
            query: 用户原始问题
            on_progress: 进度回调函数

        Returns:
            子查询列表（1-3 个）
        """
        # 发送分解开始事件
        if on_progress:
            on_progress({
                "type": "rag_progress",
                "stage": "decomposing",
                "message": "Analyzing the query...",
            })

        client = self._get_client()
        if not client:
            logger.logger.info("[RAGQueryExtender] No API key, using original query")
            return [query]

        try:
            prompt = self._build_prompt(query)

            response = await client.call(prompt)

            content = response.content.strip()
            
            # 解析 JSON
            json_match = re.search(r'\[.*\]', content, re.DOTALL)
            if json_match:
                sub_queries = json.loads(json_match.group())
                # 限制数量
                sub_queries = sub_queries[:self.max_sub_queries]
                logger.logger.info(
                    f"[RAGQueryExtender] Decomposed into {len(sub_queries)} sub-queries: {sub_queries}"
                )
                return sub_queries if sub_queries else [query]
            else:
                logger.logger.warning(
                    f"[RAGQueryExtender] Failed to parse JSON from: {content}"
                )
                return [query]
                
        except Exception as e:
            logger.logger.error(f"[RAGQueryExtender] Query extension failed: {e}")
            return [query]
    
    def _build_prompt(self, query: str) -> str:
        """
        构建 Query 分解的 Prompt
        
        针对知识库检索优化，与 web_search 的 Prompt 有所不同：
        - 更注重语义相似性
        - 关注关键概念和实体
        - 考虑同义词和相关术语
        """
        return f"""You are a knowledge base query optimizer. Decompose the user's question into 1-3 search queries for semantic retrieval.

Rules:
1. If the question is simple and specific (like "what is X"), return just 1 query
2. If the question involves multiple concepts or aspects, return 2-3 queries
3. Each query should focus on a specific aspect, concept, or keyword
4. Queries should be optimized for semantic similarity search (vector retrieval)
5. Consider synonyms and related terms that might appear in documents
6. Keep queries concise but informative
7. Return ONLY a JSON array of strings, no explanation

Examples:
- "How to configure database connection?" -> ["database connection configuration", "database setup guide"]
- "What is machine learning?" -> ["machine learning definition"]
- "Compare React and Vue for large projects" -> ["React large scale applications", "Vue enterprise projects", "React vs Vue comparison"]

User question: {query}

Output (JSON array only):"""
