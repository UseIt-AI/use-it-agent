"""
Web Search Tool - 网络搜索工具主类

整合 QueryDecomposer 和 TavilyClient，提供完整的 Web 搜索功能。
支持 Query 分解 + 并行搜索 + 结果聚合。

架构：
1. Query 分解: 将用户问题分解为多个子查询
2. 并行搜索: 同时搜索所有子查询
3. 结果聚合: 合并去重，按 score 排序
4. 返回结构化数据供前端可视化
"""

from typing import Dict, Any, Optional, List, AsyncGenerator, Callable
import asyncio
import time

from langchain_core.tools import BaseTool as LangChainBaseTool, tool
from pydantic import BaseModel, Field

from .query_decomposer import WebSearchQueryDecomposer
from .tavily_client import TavilyClient
from useit_studio.ai_run.utils.logger_utils import LoggerUtils

logger = LoggerUtils(component_name="WebSearchTool")


# ==================== Web Search 工具输入 Schema ====================

class WebSearchInput(BaseModel):
    """Web 搜索工具输入"""
    query: str = Field(description="The search query to look up on the web")
    max_results: int = Field(default=5, description="Maximum number of results to return per sub-query")


# ==================== 进度回调类型 ====================

ProgressCallback = Callable[[Dict[str, Any]], None]


# ==================== Web Search 工具实现 ====================

class WebSearchTool:
    """
    Web 搜索工具 - Tavily 实现
    
    架构：Query 分解 + 并行搜索
    - 将用户问题分解为 1-3 个子查询
    - 并行搜索所有子查询
    - 实时发送搜索进度事件
    - 合并去重结果
    - 返回结构化数据
    """
    
    name: str = "web_search"
    description: str = "Search the web for up-to-date information. Use this tool when you need current information from the internet."
    
    def __init__(
        self,
        api_key: str = "",
        openai_api_key: str = "",
        max_results: int = 5,
        search_depth: str = "basic",
        include_answer: bool = True,
        include_images: bool = True,
        enable_query_decomposition: bool = True,
        max_sub_queries: int = 3,
    ):
        """
        初始化 Web 搜索工具
        
        Args:
            api_key: Tavily API 密钥
            openai_api_key: OpenAI API 密钥（用于 Query 分解）
            max_results: 每个子查询最大结果数
            search_depth: 搜索深度 ("basic" or "advanced")
            include_answer: 是否包含 AI 答案
            include_images: 是否包含图片
            enable_query_decomposition: 是否启用查询分解
            max_sub_queries: 最大子查询数
        """
        self.max_results = max_results
        self.enable_query_decomposition = enable_query_decomposition
        self.max_sub_queries = max_sub_queries
        
        # 初始化组件
        self.query_decomposer = WebSearchQueryDecomposer(
            openai_api_key=openai_api_key,
            max_sub_queries=max_sub_queries,
        )
        
        self.tavily_client = TavilyClient(
            api_key=api_key,
            search_depth=search_depth,
            include_answer=include_answer,
            include_images=include_images,
        )
        
        logger.logger.info(
            f"[WebSearchTool] Initialized with Tavily API "
            f"(query_decomposition={enable_query_decomposition}, max_sub_queries={max_sub_queries})"
        )
    
    @classmethod
    def from_config(
        cls,
        config: Dict[str, Any],
        api_keys: Optional[Dict[str, str]] = None,
    ) -> "WebSearchTool":
        """从配置创建实例"""
        api_keys = api_keys or {}
        
        return cls(
            api_key=api_keys.get("TAVILY_API_KEY", ""),
            openai_api_key=api_keys.get("OPENAI_API_KEY", ""),
            max_results=config.get("max_results", 5),
            search_depth=config.get("search_depth", "basic"),
            include_answer=config.get("include_answer", True),
            include_images=config.get("include_images", True),
            enable_query_decomposition=config.get("enable_query_decomposition", True),
            max_sub_queries=config.get("max_sub_queries", 3),
        )
    
    # ==================== 主搜索方法（带流式进度）====================
    
    async def search_with_progress(
        self, 
        query: str, 
        max_results: Optional[int] = None,
        on_progress: Optional[ProgressCallback] = None,
    ) -> Dict[str, Any]:
        """
        执行完整的 Web 搜索流程（带进度回调）
        
        流程：
        1. Query 分解（发送 decomposing 事件）
        2. 并行搜索（发送 queries_ready + search_done 事件）
        3. 结果聚合（发送 aggregating 事件）
        4. 返回结构化数据（发送 completed 事件）
        """
        start_time = time.time()
        
        num_results = max_results or self.max_results
        
        logger.logger.info(f"[WebSearchTool] Starting search: {query[:80]}...")
        
        # Step 1: Query 分解
        if self.enable_query_decomposition:
            sub_queries = await self.query_decomposer.decompose(query, on_progress)
        else:
            sub_queries = [query]
        
        decompose_time = time.time() - start_time
        
        # 发送查询分解完成事件
        if on_progress:
            query_states = [
                {"query": q, "status": "pending", "results_count": 0}
                for q in sub_queries
            ]
            on_progress({
                "type": "search_progress",
                "stage": "queries_ready",
                "message": f"Query decomposed into {len(sub_queries)} sub-queries.",
                "queries": query_states,
            })
        
        # Step 2: 并行搜索（带进度事件）
        search_start = time.time()
        all_results, all_responses = await self.tavily_client.parallel_search(
            queries=sub_queries,
            max_results_per_query=min(num_results, 5),
            on_progress=on_progress,
        )
        search_time = time.time() - search_start
        
        # Step 3: 聚合结果
        if on_progress:
            on_progress({
                "type": "search_progress",
                "stage": "aggregating",
                "message": f"Aggregating {len(all_results)} search results...",
                "total_results": len(all_results),
            })
        
        # 截取最终结果
        final_results = all_results[:num_results]
        
        # 聚合答案和其他信息
        answer = None
        all_images = []
        all_follow_up_questions = []
        
        for resp in all_responses:
            if resp.get("answer") and not answer:
                answer = resp["answer"]
            images = resp.get("images") or []
            all_images.extend(images)
            follow_up = resp.get("follow_up_questions") or []
            all_follow_up_questions.extend(follow_up)
        
        # 去重
        all_images = list(dict.fromkeys(all_images))[:5]
        all_follow_up_questions = list(dict.fromkeys(all_follow_up_questions))[:3]
        
        total_time = time.time() - start_time
        
        # Step 4: 发送完成事件
        if on_progress:
            on_progress({
                "type": "search_progress",
                "stage": "completed",
                "message": f"Search completed with {len(final_results)} relevant results.",
                "total_results": len(final_results),
                "elapsed_time": round(total_time, 2),
            })
        
        # 构建结构化响应
        structured_result = {
            "query": query,
            "sub_queries": sub_queries,
            "answer": answer,
            "results": [
                {
                    "title": r.get("title", ""),
                    "url": r.get("url", ""),
                    "snippet": r.get("content", ""),
                    "score": r.get("score", 0),
                }
                for r in final_results
            ],
            "images": all_images,
            "follow_up_questions": all_follow_up_questions,
            "metadata": {
                "total_results": len(all_results),
                "returned_results": len(final_results),
                "sub_query_count": len(sub_queries),
                "decompose_time": round(decompose_time, 2),
                "search_time": round(search_time, 2),
                "total_time": round(total_time, 2),
            }
        }
        
        logger.logger.info(
            f"[WebSearchTool] Search completed: "
            f"{len(final_results)} results in {total_time:.2f}s"
        )
        
        return structured_result
    
    # ==================== 流式搜索（AsyncGenerator）====================
    
    async def search_streaming(
        self, 
        query: str, 
        max_results: Optional[int] = None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        执行完整的 Web 搜索流程，流式返回进度事件
        """
        start_time = time.time()
        num_results = max_results or self.max_results
        
        logger.logger.info(f"[WebSearchTool] Starting streaming search: {query[:80]}...")
        
        # Step 1: Query 分解
        yield {
            "type": "search_progress",
            "stage": "decomposing",
            "message": "Analyzing the query...",
        }
        
        if self.enable_query_decomposition:
            sub_queries = await self.query_decomposer.decompose(query)
        else:
            sub_queries = [query]
        
        decompose_time = time.time() - start_time
        
        # 初始化查询状态
        query_states = [
            {"query": q, "status": "pending", "results_count": 0}
            for q in sub_queries
        ]
        
        yield {
            "type": "search_progress",
            "stage": "queries_ready",
            "message": f"Query decomposed into {len(sub_queries)} sub-queries.",
            "queries": query_states,
        }
        
        # Step 2: 并行搜索
        for qs in query_states:
            qs["status"] = "searching"
        
        yield {
            "type": "search_progress",
            "stage": "searching",
            "message": f"Searching {len(sub_queries)} queries in parallel...",
            "queries": query_states,
        }
        
        # 收集结果
        search_start = time.time()
        all_results = []
        all_responses = []
        seen_urls = set()
        
        async def search_with_index(index: int, q: str):
            result = await self.tavily_client.search(q, min(num_results, 5))
            return index, q, result
        
        tasks = [search_with_index(i, q) for i, q in enumerate(sub_queries)]
        
        for future in asyncio.as_completed(tasks):
            try:
                index, q, resp = await future
                
                results_count = len(resp.get("results", []))
                query_states[index]["status"] = "done"
                query_states[index]["results_count"] = results_count
                
                yield {
                    "type": "search_progress",
                    "stage": "search_done",
                    "message": f"Search completed for: {q}",
                    "current_query": q,
                    "queries": query_states,
                }
                
                all_responses.append(resp)
                
                for result in resp.get("results", []):
                    url = result.get("url", "")
                    if url and url not in seen_urls:
                        seen_urls.add(url)
                        all_results.append(result)
                        
            except Exception as e:
                logger.logger.error(f"[WebSearchTool] Search task failed: {e}")
                for qs in query_states:
                    if qs["status"] == "searching":
                        qs["status"] = "error"
        
        search_time = time.time() - search_start
        
        # Step 3: 聚合结果
        yield {
            "type": "search_progress",
            "stage": "aggregating",
            "message": f"Aggregating {len(all_results)} search results...",
            "total_results": len(all_results),
        }
        
        all_results.sort(key=lambda x: x.get("score", 0), reverse=True)
        final_results = all_results[:num_results]
        
        # 聚合其他信息
        answer = None
        all_images = []
        all_follow_up_questions = []
        
        for resp in all_responses:
            if resp.get("answer") and not answer:
                answer = resp["answer"]
            images = resp.get("images") or []
            all_images.extend(images)
            follow_up = resp.get("follow_up_questions") or []
            all_follow_up_questions.extend(follow_up)
        
        all_images = list(dict.fromkeys(all_images))[:5]
        all_follow_up_questions = list(dict.fromkeys(all_follow_up_questions))[:3]
        
        total_time = time.time() - start_time
        
        # Step 4: 完成
        yield {
            "type": "search_progress",
            "stage": "completed",
            "message": f"Search completed with {len(final_results)} relevant results.",
            "total_results": len(final_results),
            "elapsed_time": round(total_time, 2),
        }
        
        # 最终返回完整结果
        yield {
            "type": "search_complete",
            "result": {
                "query": query,
                "sub_queries": sub_queries,
                "answer": answer,
                "results": [
                    {
                        "title": r.get("title", ""),
                        "url": r.get("url", ""),
                        "snippet": r.get("content", ""),
                        "score": r.get("score", 0),
                    }
                    for r in final_results
                ],
                "images": all_images,
                "follow_up_questions": all_follow_up_questions,
                "metadata": {
                    "total_results": len(all_results),
                    "returned_results": len(final_results),
                    "sub_query_count": len(sub_queries),
                    "decompose_time": round(decompose_time, 2),
                    "search_time": round(search_time, 2),
                    "total_time": round(total_time, 2),
                }
            }
        }
    
    # ==================== 原有方法（保持兼容）====================
    
    async def search(
        self, 
        query: str, 
        max_results: Optional[int] = None
    ) -> Dict[str, Any]:
        """执行完整的 Web 搜索流程（无进度回调）"""
        return await self.search_with_progress(query, max_results, on_progress=None)
    
    async def invoke(self, query: str, max_results: int = 5) -> str:
        """调用搜索并返回格式化文本（供 LLM 阅读）"""
        try:
            data = await self.search(query, max_results)
            return self._format_for_llm(data)
            
        except Exception as e:
            logger.logger.error(f"[WebSearchTool] Search failed: {e}", exc_info=True)
            return f"Error performing web search: {str(e)}"
    
    async def invoke_with_structured_data(
        self, 
        query: str, 
        max_results: int = 5
    ) -> Dict[str, Any]:
        """调用搜索并返回结构化数据（供前端渲染）"""
        try:
            data = await self.search(query, max_results)
            text = self._format_for_llm(data)
            
            return {
                "text": text,
                "structured_data": {
                    "result_type": "web_search",
                    **data,
                }
            }
            
        except Exception as e:
            logger.logger.error(f"[WebSearchTool] Search failed: {e}", exc_info=True)
            return {
                "text": f"Error: {str(e)}",
                "structured_data": None,
            }
    
    def _format_for_llm(self, data: Dict[str, Any]) -> str:
        """将搜索结果格式化为 LLM 可读的文本"""
        lines = []
        
        metadata = data.get("metadata", {})
        sub_queries = data.get("sub_queries", [])
        
        if len(sub_queries) > 1:
            lines.append(f"**Search Strategy:** Decomposed into {len(sub_queries)} sub-queries:")
            for i, sq in enumerate(sub_queries, 1):
                lines.append(f"  {i}. {sq}")
            lines.append("")
        
        if data.get("answer"):
            lines.append(f"**AI Answer:**")
            lines.append(data["answer"])
            lines.append("")
        
        results = data.get("results", [])
        if results:
            lines.append(f"**Found {len(results)} result(s):**")
            lines.append("")
            
            for i, r in enumerate(results, 1):
                score_pct = f"{r.get('score', 0):.0%}" if r.get('score') else "N/A"
                lines.append(f"### [{i}] {r.get('title', 'No title')} (Relevance: {score_pct})")
                lines.append(f"**URL:** {r.get('url', '')}")
                lines.append(f"{r.get('snippet', '')}")
                lines.append("")
        else:
            lines.append("No search results found.")
        
        follow_up = data.get("follow_up_questions", [])
        if follow_up:
            lines.append("**Related Questions:**")
            for q in follow_up:
                lines.append(f"  - {q}")
        
        if metadata:
            lines.append("")
            lines.append(f"*Search completed in {metadata.get('total_time', 0)}s*")
        
        return "\n".join(lines)
    
    # ==================== LangChain 工具转换 ====================
    
    def as_langchain_tool(self) -> LangChainBaseTool:
        """转换为 LangChain 工具"""
        search_tool = self
        
        @tool("web_search", args_schema=WebSearchInput)
        async def web_search(query: str, max_results: int = 5) -> str:
            """
            Search the web for up-to-date information.
            
            Use this tool when you need:
            - Current news or events
            - Recent information not in your knowledge
            - Facts that need verification
            - Technical documentation or tutorials
            
            The search will automatically:
            1. Decompose complex questions into sub-queries
            2. Search multiple sources in parallel
            3. Aggregate and rank results by relevance
            
            Args:
                query: The search query or question
                max_results: Maximum number of results to return (default: 5)
            """
            return await search_tool.invoke(query=query, max_results=max_results)
        
        return web_search
    
    # ==================== 清理 ====================
    
    async def close(self):
        """关闭资源"""
        await self.tavily_client.close()


# ==================== 工厂函数 ====================

def create_web_search_tool(
    config: Dict[str, Any],
    api_keys: Optional[Dict[str, str]] = None,
) -> LangChainBaseTool:
    """
    创建 Web Search LangChain 工具
    
    Args:
        config: Web Search 配置
            - max_results: 最大结果数 (default: 5)
            - search_depth: "basic" or "advanced" (default: "basic")
            - include_answer: 是否包含 AI 答案 (default: True)
            - include_images: 是否包含图片 (default: True)
            - enable_query_decomposition: 是否启用查询分解 (default: True)
            - max_sub_queries: 最大子查询数 (default: 3)
        api_keys: API 密钥字典
            - TAVILY_API_KEY: Tavily API 密钥
            - OPENAI_API_KEY: OpenAI API 密钥（用于查询分解）
        
    Returns:
        LangChain 工具实例
    """
    web_search = WebSearchTool.from_config(config, api_keys)
    return web_search.as_langchain_tool()
