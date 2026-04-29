"""
RAG Retriever - RAG HTTP 检索客户端

负责调用 RAG 服务的 /api/rag/retrieve 接口。
支持单次检索和并行检索多个查询。
"""

from typing import Dict, Any, Optional, List, Tuple, Callable
import asyncio
import os

from useit_studio.ai_run.utils.logger_utils import LoggerUtils

logger = LoggerUtils(component_name="RAGRetriever")


# 进度回调函数类型: (event_dict) -> None
ProgressCallback = Callable[[Dict[str, Any]], None]


class RAGRetriever:
    """
    RAG HTTP 检索客户端
    
    调用 RAG 服务的 /api/rag/retrieve 接口进行知识库检索。
    支持并行检索多个查询并聚合结果。
    """
    
    def __init__(
        self,
        rag_url: str = "",
        timeout: float = 30.0,
    ):
        """
        初始化 RAG Retriever
        
        Args:
            rag_url: RAG 服务 URL（如果为空，从环境变量 RAG_URL 读取）
            timeout: HTTP 请求超时时间（秒）
        """
        # 从环境变量读取 RAG_URL（如果未提供）
        self.rag_url = rag_url or os.getenv("RAG_URL", "")
        self.timeout = timeout
        
        # 延迟初始化 HTTP 客户端
        self._http_client = None
        
        # 构建完整的 API 端点
        if self.rag_url:
            # 移除末尾斜杠
            self.rag_url = self.rag_url.rstrip("/")
            self._retrieve_endpoint = f"{self.rag_url}/api/rag/retrieve"
        else:
            self._retrieve_endpoint = ""
        
        logger.logger.info(
            f"[RAGRetriever] Initialized with RAG_URL={self.rag_url}, timeout={timeout}"
        )
    
    async def _get_http_client(self):
        """获取 HTTP 客户端（延迟初始化）"""
        if self._http_client is None:
            import httpx
            self._http_client = httpx.AsyncClient(timeout=self.timeout)
        return self._http_client
    
    async def retrieve(
        self, 
        query: str, 
        top_k: int,
        project_id: Optional[str] = None,
        chat_id: Optional[str] = None,
        workflow_run_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        调用 RAG 服务的 /api/rag/retrieve 接口
        
        Args:
            query: 搜索查询
            top_k: 返回结果数
            project_id: Project ID 过滤
            chat_id: Chat ID 过滤
            workflow_run_id: Workflow Run ID 过滤
            
        Returns:
            RAG API 响应 {"chunks": [...]}
        """
        if not self._retrieve_endpoint:
            logger.logger.warning("[RAGRetriever] No RAG_URL configured, returning mock results")
            return self._mock_search_result(query, top_k)
        
        try:
            client = await self._get_http_client()
            
            # 构建请求 payload
            payload: Dict[str, Any] = {
                "query": query,
                "top_k": top_k,
            }
            
            # 添加可选的过滤参数
            if project_id:
                payload["project_id"] = project_id
            # chat_id 不再发送到 RAG 服务
            if workflow_run_id:
                payload["workflow_run_id"] = workflow_run_id
            
            logger.logger.debug(f"[RAGRetriever] Calling RAG API with query: {query[:50]}...")
            
            response = await client.post(
                self._retrieve_endpoint,
                json=payload,
            )
            response.raise_for_status()
            
            result = response.json()
            logger.logger.debug(
                f"[RAGRetriever] RAG API returned {len(result.get('chunks', []))} chunks"
            )
            
            return result
            
        except Exception as e:
            logger.logger.error(f"[RAGRetriever] RAG retrieve failed for '{query[:50]}...': {e}")
            return {
                "chunks": [],
                "error": str(e),
            }
    
    def _mock_search_result(self, query: str, top_k: int) -> Dict[str, Any]:
        """返回模拟搜索结果（无 RAG_URL 时）"""
        return {
            "chunks": [
                {
                    "chunk_id": "mock_001",
                    "content": f"This is a simulated RAG result for query: {query}. Configure RAG_URL environment variable for real results.",
                    "score": 0.95,
                    "path": "mock://example/document.md",
                    "content_type": "text",
                    "metadata": {},
                }
            ],
        }
    
    async def parallel_retrieve(
        self, 
        queries: List[str], 
        top_k_per_query: int,
        project_id: Optional[str] = None,
        chat_id: Optional[str] = None,
        workflow_run_id: Optional[str] = None,
        on_progress: Optional[ProgressCallback] = None,
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """
        并行检索多个查询
        
        Args:
            queries: 查询列表
            top_k_per_query: 每个查询的返回结果数
            project_id: Project ID 过滤
            chat_id: Chat ID 过滤
            workflow_run_id: Workflow Run ID 过滤
            on_progress: 进度回调函数
            
        Returns:
            (合并后的 chunks 列表, 所有响应列表)
        """
        # 初始化查询状态
        query_states = [
            {"query": q, "status": "pending", "results_count": 0}
            for q in queries
        ]
        
        # 发送查询列表（所有查询开始搜索）
        if on_progress:
            # 标记所有查询为 searching
            for qs in query_states:
                qs["status"] = "searching"
            
            on_progress({
                "type": "rag_progress",
                "stage": "searching",
                "message": f"Searching {len(queries)} queries in parallel...",
                "queries": query_states,
            })
        
        # 创建搜索任务
        async def retrieve_with_index(index: int, query: str):
            """带索引的检索任务"""
            result = await self.retrieve(
                query=query,
                top_k=top_k_per_query,
                project_id=project_id,
                chat_id=chat_id,
                workflow_run_id=workflow_run_id,
            )
            return index, query, result
        
        tasks = [
            retrieve_with_index(i, q) 
            for i, q in enumerate(queries)
        ]
        
        # 并行执行，按完成顺序处理结果
        all_responses = []
        all_chunks = []
        seen_chunk_ids = set()
        
        for future in asyncio.as_completed(tasks):
            try:
                index, query, resp = await future
                
                # 更新该查询的状态
                chunks = resp.get("chunks", [])
                results_count = len(chunks)
                query_states[index]["status"] = "done"
                query_states[index]["results_count"] = results_count
                
                # 发送单个搜索完成事件
                if on_progress:
                    on_progress({
                        "type": "rag_progress",
                        "stage": "search_done",
                        "message": f"Search completed for: {query[:50]}...",
                        "current_query": query,
                        "queries": query_states,
                    })
                
                all_responses.append(resp)
                
                # 合并结果（按 chunk_id 去重）
                for chunk in chunks:
                    chunk_id = chunk.get("chunk_id", "")
                    # 如果没有 chunk_id，使用 content hash 作为唯一标识
                    if not chunk_id:
                        chunk_id = str(hash(chunk.get("content", "")))
                    
                    if chunk_id not in seen_chunk_ids:
                        seen_chunk_ids.add(chunk_id)
                        all_chunks.append(chunk)
                        
            except Exception as e:
                logger.logger.error(f"[RAGRetriever] Retrieve task failed: {e}")
                # 标记失败
                for qs in query_states:
                    if qs["status"] == "searching":
                        qs["status"] = "error"
        
        # 按 score 排序
        all_chunks.sort(key=lambda x: x.get("score", 0), reverse=True)
        
        logger.logger.info(
            f"[RAGRetriever] Parallel retrieve completed: "
            f"{len(queries)} queries, {len(all_chunks)} unique chunks"
        )
        
        return all_chunks, all_responses
    
    async def close(self):
        """关闭 HTTP 客户端"""
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None
