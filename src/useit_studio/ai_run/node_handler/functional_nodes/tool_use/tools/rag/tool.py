"""
RAG Tool - 知识库检索工具主类

整合 QueryExtender 和 Retriever，提供完整的 RAG 检索功能。
支持 Query Extend（查询分解）+ 并行检索 + 结果聚合。

架构：
1. Query Extend: 将用户问题分解为多个子查询
2. 并行检索: 同时检索所有子查询
3. 结果聚合: 合并去重，按 score 排序
4. 返回结构化数据供前端可视化
"""

from typing import Dict, Any, Optional, List, AsyncGenerator, Callable
import time

from langchain_core.tools import BaseTool as LangChainBaseTool, tool
from pydantic import BaseModel, Field

from .query_extender import RAGQueryExtender
from .retriever import RAGRetriever
from useit_studio.ai_run.utils.logger_utils import LoggerUtils

logger = LoggerUtils(component_name="RAGTool")


# ==================== RAG 工具输入 Schema ====================

class RAGSearchInput(BaseModel):
    """RAG 搜索工具输入"""
    query: str = Field(description="The search query to find relevant documents in the knowledge base")
    top_k: int = Field(default=5, description="Number of top results to return (1-100, default: 5)")
    project_id: Optional[str] = Field(default=None, description="Project ID filter for scoping the search")
    chat_id: Optional[str] = Field(default=None, description="Chat ID filter for scoping the search")
    workflow_run_id: Optional[str] = Field(default=None, description="Workflow Run ID filter for scoping the search")


# ==================== 进度回调类型 ====================

ProgressCallback = Callable[[Dict[str, Any]], None]


# ==================== RAG 工具实现 ====================

class RAGTool:
    """
    RAG 检索工具 - 完整实现
    
    通过调用 RAG 服务的 /api/rag/retrieve 接口进行知识库检索。
    
    特点：
    - Query Extend: 智能分解查询为多个子查询
    - 并行检索: 同时检索所有子查询
    - 结果聚合: 合并去重，按 score 排序
    - 流式进度事件: 实时显示搜索进度
    - 结构化数据: 供前端可视化
    """
    
    name: str = "rag_search"
    description: str = "Search the knowledge base for relevant documents. Use this tool when you need to find information from the user's documents or knowledge base."
    
    def __init__(
        self,
        rag_url: str = "",
        openai_api_key: str = "",
        top_k: int = 5,
        timeout: float = 30.0,
        enable_query_extend: bool = True,
        max_sub_queries: int = 3,
    ):
        """
        初始化 RAG 工具
        
        Args:
            rag_url: RAG 服务 URL（如果为空，从环境变量 RAG_URL 读取）
            openai_api_key: OpenAI API 密钥（用于 Query Extend）
            top_k: 默认返回结果数
            timeout: HTTP 请求超时时间（秒）
            enable_query_extend: 是否启用 Query Extend
            max_sub_queries: 最大子查询数量
        """
        self.top_k = top_k
        self.enable_query_extend = enable_query_extend
        self.max_sub_queries = max_sub_queries
        
        # 初始化组件
        self.query_extender = RAGQueryExtender(
            openai_api_key=openai_api_key,
            max_sub_queries=max_sub_queries,
        )
        
        self.retriever = RAGRetriever(
            rag_url=rag_url,
            timeout=timeout,
        )
        
        logger.logger.info(
            f"[RAGTool] Initialized with enable_query_extend={enable_query_extend}, "
            f"max_sub_queries={max_sub_queries}, top_k={top_k}"
        )
    
    @classmethod
    def from_config(
        cls,
        config: Dict[str, Any],
        api_keys: Optional[Dict[str, str]] = None,
    ) -> "RAGTool":
        """从配置创建实例"""
        api_keys = api_keys or {}
        
        return cls(
            rag_url=api_keys.get("RAG_URL", "") or config.get("rag_url", ""),
            openai_api_key=api_keys.get("OPENAI_API_KEY", ""),
            top_k=config.get("top_k", 5),
            timeout=config.get("timeout", 30.0),
            enable_query_extend=config.get("enable_query_extend", True),
            max_sub_queries=config.get("max_sub_queries", 3),
        )
    
    # ==================== 主搜索方法（带流式进度）====================
    
    async def search_with_progress(
        self, 
        query: str, 
        top_k: Optional[int] = None,
        project_id: Optional[str] = None,
        chat_id: Optional[str] = None,
        workflow_run_id: Optional[str] = None,
        on_progress: Optional[ProgressCallback] = None,
    ) -> Dict[str, Any]:
        """
        执行完整的 RAG 搜索流程（带进度回调）
        
        流程：
        1. Query Extend（发送 decomposing → queries_ready 事件）
        2. 并行检索（发送 searching → search_done 事件）
        3. 结果聚合（发送 aggregating 事件）
        4. 返回结构化数据（发送 completed 事件）
        
        Args:
            query: 用户搜索问题
            top_k: 最终返回的最大结果数
            project_id: Project ID 过滤
            chat_id: Chat ID 过滤
            workflow_run_id: Workflow Run ID 过滤
            on_progress: 进度回调函数
            
        Returns:
            结构化搜索结果
        """
        start_time = time.time()
        
        num_results = top_k or self.top_k
        
        logger.logger.info(f"[RAGTool] Starting search: {query[:80]}...")
        
        # Step 1: Query Extend
        if self.enable_query_extend:
            sub_queries = await self.query_extender.extend(query, on_progress)
        else:
            sub_queries = [query]
        
        extend_time = time.time() - start_time
        
        # 发送查询分解完成事件
        if on_progress:
            query_states = [
                {"query": q, "status": "pending", "results_count": 0}
                for q in sub_queries
            ]
            on_progress({
                "type": "rag_progress",
                "stage": "queries_ready",
                "message": f"Query extended into {len(sub_queries)} sub-queries.",
                "queries": query_states,
            })
        
        # Step 2: 并行检索（带进度事件）
        search_start = time.time()
        all_chunks, all_responses = await self.retriever.parallel_retrieve(
            queries=sub_queries,
            top_k_per_query=min(num_results, 5),  # 每个子查询最多返回 5 个结果
            project_id=project_id,
            chat_id=chat_id,
            workflow_run_id=workflow_run_id,
            on_progress=on_progress,
        )
        search_time = time.time() - search_start
        
        # Step 3: 聚合结果
        if on_progress:
            on_progress({
                "type": "rag_progress",
                "stage": "aggregating",
                "message": f"Aggregating {len(all_chunks)} chunks from {len(sub_queries)} queries...",
                "total_results": len(all_chunks),
            })
        
        # 截取最终结果
        final_chunks = all_chunks[:num_results]
        
        total_time = time.time() - start_time
        
        # Step 4: 发送完成事件
        if on_progress:
            on_progress({
                "type": "rag_progress",
                "stage": "completed",
                "message": f"Search completed with {len(final_chunks)} relevant documents.",
                "total_results": len(final_chunks),
                "elapsed_time": round(total_time, 2),
            })
        
        # 构建过滤器信息
        filters = {}
        if project_id:
            filters["project_id"] = project_id
        if chat_id:
            filters["chat_id"] = chat_id
        if workflow_run_id:
            filters["workflow_run_id"] = workflow_run_id
        
        # 构建结构化响应
        structured_result = {
            "query": query,
            "sub_queries": sub_queries,
            "chunks": final_chunks,
            "metadata": {
                "total_results": len(all_chunks),
                "returned_results": len(final_chunks),
                "sub_query_count": len(sub_queries),
                "extend_time": round(extend_time, 2),
                "search_time": round(search_time, 2),
                "total_time": round(total_time, 2),
                "filters": filters if filters else None,
            }
        }
        
        logger.logger.info(
            f"[RAGTool] Search completed: "
            f"{len(final_chunks)} chunks in {total_time:.2f}s"
        )
        
        return structured_result
    
    # ==================== 流式搜索（AsyncGenerator）====================
    
    async def search_streaming(
        self, 
        query: str, 
        top_k: Optional[int] = None,
        project_id: Optional[str] = None,
        chat_id: Optional[str] = None,
        workflow_run_id: Optional[str] = None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        执行完整的 RAG 搜索流程，流式返回进度事件
        
        Yields:
            进度事件字典，最后一个事件包含完整的搜索结果
        """
        start_time = time.time()
        num_results = top_k or self.top_k
        
        logger.logger.info(f"[RAGTool] Starting streaming search: {query[:80]}...")
        
        # Step 1: Query Extend
        yield {
            "type": "rag_progress",
            "stage": "decomposing",
            "message": "Analyzing the query...",
        }
        
        if self.enable_query_extend:
            sub_queries = await self.query_extender.extend(query)
        else:
            sub_queries = [query]
        
        extend_time = time.time() - start_time
        
        # 初始化查询状态
        query_states = [
            {"query": q, "status": "pending", "results_count": 0}
            for q in sub_queries
        ]
        
        yield {
            "type": "rag_progress",
            "stage": "queries_ready",
            "message": f"Query extended into {len(sub_queries)} sub-queries.",
            "queries": query_states,
        }
        
        # Step 2: 并行检索
        # 标记所有查询为 searching
        for qs in query_states:
            qs["status"] = "searching"
        
        yield {
            "type": "rag_progress",
            "stage": "searching",
            "message": f"Searching {len(sub_queries)} queries in parallel...",
            "queries": query_states,
        }
        
        # 收集进度事件
        search_start = time.time()
        all_chunks = []
        seen_chunk_ids = set()
        
        # 使用带进度的并行检索
        import asyncio
        
        async def retrieve_with_index(index: int, q: str):
            result = await self.retriever.retrieve(
                query=q,
                top_k=min(num_results, 5),
                project_id=project_id,
                chat_id=chat_id,
                workflow_run_id=workflow_run_id,
            )
            return index, q, result
        
        tasks = [retrieve_with_index(i, q) for i, q in enumerate(sub_queries)]
        
        for future in asyncio.as_completed(tasks):
            try:
                index, q, resp = await future
                
                chunks = resp.get("chunks", [])
                results_count = len(chunks)
                query_states[index]["status"] = "done"
                query_states[index]["results_count"] = results_count
                
                # 发送单个搜索完成事件
                yield {
                    "type": "rag_progress",
                    "stage": "search_done",
                    "message": f"Search completed for: {q[:50]}...",
                    "current_query": q,
                    "queries": query_states,
                }
                
                # 合并结果
                for chunk in chunks:
                    chunk_id = chunk.get("chunk_id", "")
                    if not chunk_id:
                        chunk_id = str(hash(chunk.get("content", "")))
                    
                    if chunk_id not in seen_chunk_ids:
                        seen_chunk_ids.add(chunk_id)
                        all_chunks.append(chunk)
                        
            except Exception as e:
                logger.logger.error(f"[RAGTool] Retrieve task failed: {e}")
                for qs in query_states:
                    if qs["status"] == "searching":
                        qs["status"] = "error"
        
        search_time = time.time() - search_start
        
        # Step 3: 聚合结果
        yield {
            "type": "rag_progress",
            "stage": "aggregating",
            "message": f"Aggregating {len(all_chunks)} chunks...",
            "total_results": len(all_chunks),
        }
        
        # 按 score 排序
        all_chunks.sort(key=lambda x: x.get("score", 0), reverse=True)
        final_chunks = all_chunks[:num_results]
        
        total_time = time.time() - start_time
        
        # Step 4: 完成
        yield {
            "type": "rag_progress",
            "stage": "completed",
            "message": f"Search completed with {len(final_chunks)} relevant documents.",
            "total_results": len(final_chunks),
            "elapsed_time": round(total_time, 2),
        }
        
        # 构建过滤器信息
        filters = {}
        if project_id:
            filters["project_id"] = project_id
        if chat_id:
            filters["chat_id"] = chat_id
        if workflow_run_id:
            filters["workflow_run_id"] = workflow_run_id
        
        # 最终返回完整结果
        yield {
            "type": "rag_complete",
            "result": {
                "query": query,
                "sub_queries": sub_queries,
                "chunks": final_chunks,
                "metadata": {
                    "total_results": len(all_chunks),
                    "returned_results": len(final_chunks),
                    "sub_query_count": len(sub_queries),
                    "extend_time": round(extend_time, 2),
                    "search_time": round(search_time, 2),
                    "total_time": round(total_time, 2),
                    "filters": filters if filters else None,
                }
            }
        }
    
    # ==================== 原有方法（保持兼容）====================
    
    async def search(
        self, 
        query: str, 
        top_k: Optional[int] = None,
        project_id: Optional[str] = None,
        chat_id: Optional[str] = None,
        workflow_run_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        执行 RAG 搜索（无进度回调）
        """
        return await self.search_with_progress(
            query=query,
            top_k=top_k,
            project_id=project_id,
            chat_id=chat_id,
            workflow_run_id=workflow_run_id,
            on_progress=None,
        )
    
    async def invoke(
        self, 
        query: str, 
        top_k: int = 5,
        project_id: Optional[str] = None,
        chat_id: Optional[str] = None,
        workflow_run_id: Optional[str] = None,
    ) -> str:
        """
        调用 RAG 搜索并返回格式化文本（供 LLM 阅读）
        """
        try:
            data = await self.search(
                query=query, 
                top_k=top_k,
                project_id=project_id,
                chat_id=chat_id,
                workflow_run_id=workflow_run_id,
            )
            return self._format_for_llm(data)
            
        except Exception as e:
            logger.logger.error(f"[RAGTool] Search failed: {e}", exc_info=True)
            return f"Error searching knowledge base: {str(e)}"
    
    async def invoke_with_structured_data(
        self, 
        query: str, 
        top_k: int = 5,
        project_id: Optional[str] = None,
        chat_id: Optional[str] = None,
        workflow_run_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        调用 RAG 搜索并返回结构化数据（供前端渲染）
        """
        try:
            data = await self.search(
                query=query, 
                top_k=top_k,
                project_id=project_id,
                chat_id=chat_id,
                workflow_run_id=workflow_run_id,
            )
            text = self._format_for_llm(data)
            
            return {
                "text": text,
                "structured_data": {
                    "result_type": "rag_search",
                    **data,
                }
            }
            
        except Exception as e:
            logger.logger.error(f"[RAGTool] Search failed: {e}", exc_info=True)
            return {
                "text": f"Error: {str(e)}",
                "structured_data": None,
            }
    
    def _format_for_llm(self, data: Dict[str, Any]) -> str:
        """
        将搜索结果格式化为 LLM 可读的文本
        """
        lines = []
        
        chunks = data.get("chunks", [])
        metadata = data.get("metadata", {})
        sub_queries = data.get("sub_queries", [])
        
        # 搜索策略信息
        if len(sub_queries) > 1:
            lines.append(f"**Search Strategy:** Decomposed into {len(sub_queries)} sub-queries:")
            for i, sq in enumerate(sub_queries, 1):
                lines.append(f"  {i}. {sq}")
            lines.append("")
        
        # 搜索结果
        if chunks:
            lines.append(f"**Found {len(chunks)} relevant document(s):**")
            lines.append("")
            
            for i, chunk in enumerate(chunks, 1):
                score = chunk.get("score", 0)
                score_pct = f"{score:.0%}" if isinstance(score, (int, float)) else "N/A"
                
                lines.append(f"### [{i}] Document chunk (Relevance: {score_pct})")
                
                # 路径信息
                path = chunk.get("path", "")
                if path:
                    lines.append(f"**Path:** {path}")
                
                # 内容类型
                content_type = chunk.get("content_type", "")
                if content_type:
                    lines.append(f"**Type:** {content_type}")
                
                # 文档内容
                content = chunk.get("content", "")
                if content:
                    # 截断过长的内容
                    if len(content) > 1500:
                        content = content[:1500] + "\n... (truncated)"
                    lines.append(f"**Content:**\n{content}")
                
                lines.append("")
        else:
            lines.append("No relevant documents found in the knowledge base.")
        
        # 性能信息
        if metadata:
            total_time = metadata.get("total_time", 0)
            if total_time:
                lines.append(f"*Search completed in {total_time}s*")
        
        return "\n".join(lines)
    
    # ==================== LangChain 工具转换 ====================
    
    def as_langchain_tool(self) -> LangChainBaseTool:
        """转换为 LangChain 工具"""
        rag_tool = self
        
        @tool("rag_search", args_schema=RAGSearchInput)
        async def rag_search(
            query: str, 
            top_k: int = 5,
            project_id: Optional[str] = None,
            chat_id: Optional[str] = None,
            workflow_run_id: Optional[str] = None,
        ) -> str:
            """
            Search the knowledge base for relevant documents.
            
            Use this tool when you need to find information from the user's 
            documents or knowledge base. Returns the most relevant documents
            based on semantic similarity.
            
            The search will automatically:
            1. Decompose complex questions into sub-queries
            2. Search multiple queries in parallel
            3. Aggregate and rank results by relevance
            
            Args:
                query: The search query to find relevant documents
                top_k: Number of top results to return (default: 5)
                project_id: Optional Project ID to filter results
                chat_id: Optional Chat ID to filter results
                workflow_run_id: Optional Workflow Run ID to filter results
            """
            return await rag_tool.invoke(
                query=query, 
                top_k=top_k,
                project_id=project_id,
                chat_id=chat_id,
                workflow_run_id=workflow_run_id,
            )
        
        return rag_search
    
    # ==================== 清理 ====================
    
    async def close(self):
        """关闭资源"""
        await self.retriever.close()


# ==================== 工厂函数 ====================

def create_rag_tool(
    config: Dict[str, Any],
    api_keys: Optional[Dict[str, str]] = None,
) -> LangChainBaseTool:
    """
    创建 RAG LangChain 工具
    
    Args:
        config: RAG 配置
            - rag_url: RAG 服务 URL（可选，默认从环境变量读取）
            - top_k: 默认返回结果数 (default: 5)
            - timeout: HTTP 请求超时时间 (default: 30.0)
            - enable_query_extend: 是否启用 Query Extend (default: True)
            - max_sub_queries: 最大子查询数 (default: 3)
        api_keys: API 密钥字典
            - RAG_URL: RAG 服务 URL
            - OPENAI_API_KEY: OpenAI API 密钥（用于 Query Extend）
        
    Returns:
        LangChain 工具实例
    """
    rag = RAGTool.from_config(config, api_keys)
    return rag.as_langchain_tool()
