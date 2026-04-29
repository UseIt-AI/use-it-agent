"""
Tavily API Client - Tavily 搜索 API 客户端

负责调用 Tavily API 进行网络搜索。
支持并行搜索多个查询。
"""

from typing import Dict, Any, Optional, List, Tuple, Callable
import asyncio

from useit_studio.ai_run.utils.logger_utils import LoggerUtils

logger = LoggerUtils(component_name="TavilyClient")


# 进度回调函数类型: (event_dict) -> None
ProgressCallback = Callable[[Dict[str, Any]], None]


class TavilyClient:
    """
    Tavily API 客户端
    
    调用 Tavily API 进行网络搜索。
    支持并行搜索多个查询并聚合结果。
    """
    
    TAVILY_API_URL = "https://api.tavily.com/search"
    
    def __init__(
        self,
        api_key: str = "",
        timeout: float = 30.0,
        search_depth: str = "basic",
        include_answer: bool = True,
        include_images: bool = True,
    ):
        """
        初始化 Tavily Client
        
        Args:
            api_key: Tavily API 密钥
            timeout: HTTP 请求超时时间（秒）
            search_depth: 搜索深度 ("basic" or "advanced")
            include_answer: 是否包含 AI 答案
            include_images: 是否包含图片
        """
        self.api_key = api_key
        self.timeout = timeout
        self.search_depth = search_depth
        self.include_answer = include_answer
        self.include_images = include_images
        
        # 延迟初始化 HTTP 客户端
        self._http_client = None
        
        logger.logger.info(
            f"[TavilyClient] Initialized with search_depth={search_depth}, "
            f"include_answer={include_answer}"
        )
    
    async def _get_http_client(self):
        """获取 HTTP 客户端（延迟初始化）"""
        if self._http_client is None:
            import httpx
            self._http_client = httpx.AsyncClient(timeout=self.timeout)
        return self._http_client
    
    async def search(self, query: str, max_results: int) -> Dict[str, Any]:
        """
        执行单次 Tavily 搜索
        
        Args:
            query: 搜索查询
            max_results: 最大结果数
            
        Returns:
            Tavily API 响应
        """
        if not self.api_key:
            logger.logger.warning("[TavilyClient] No Tavily API key, returning mock results")
            return self._mock_search_result(query)
        
        try:
            client = await self._get_http_client()
            response = await client.post(
                self.TAVILY_API_URL,
                json={
                    "api_key": self.api_key,
                    "query": query,
                    "max_results": max_results,
                    "search_depth": self.search_depth,
                    "include_answer": self.include_answer,
                    "include_images": self.include_images,
                }
            )
            response.raise_for_status()
            return response.json()
            
        except Exception as e:
            logger.logger.error(f"[TavilyClient] Tavily search failed for '{query}': {e}")
            return {
                "query": query,
                "results": [],
                "error": str(e),
            }
    
    def _mock_search_result(self, query: str) -> Dict[str, Any]:
        """返回模拟搜索结果（无 API key 时）"""
        return {
            "query": query,
            "answer": f"[Mock] This is a simulated answer for: {query}. Configure TAVILY_API_KEY for real results.",
            "response_time": 0.5,
            "results": [
                {
                    "title": f"[Mock] Search result for: {query}",
                    "url": "https://example.com/mock-result",
                    "content": "This is mock content. Please configure TAVILY_API_KEY for real search results.",
                    "score": 0.95,
                }
            ],
            "images": [],
            "follow_up_questions": [],
        }
    
    async def parallel_search(
        self, 
        queries: List[str], 
        max_results_per_query: int,
        on_progress: Optional[ProgressCallback] = None,
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """
        并行执行多个搜索查询
        
        Args:
            queries: 查询列表
            max_results_per_query: 每个查询的最大结果数
            on_progress: 进度回调函数
            
        Returns:
            (合并后的结果列表, 所有搜索响应列表)
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
                "type": "search_progress",
                "stage": "searching",
                "message": f"Searching {len(queries)} queries in parallel...",
                "queries": query_states,
            })
        
        # 创建搜索任务
        async def search_with_index(index: int, query: str):
            """带索引的搜索任务"""
            result = await self.search(query, max_results_per_query)
            return index, query, result
        
        tasks = [
            search_with_index(i, q) 
            for i, q in enumerate(queries)
        ]
        
        # 并行执行，按完成顺序处理结果
        all_responses = []
        all_results = []
        seen_urls = set()
        
        for future in asyncio.as_completed(tasks):
            try:
                index, query, resp = await future
                
                # 更新该查询的状态
                results_count = len(resp.get("results", []))
                query_states[index]["status"] = "done"
                query_states[index]["results_count"] = results_count
                
                # 发送单个搜索完成事件
                if on_progress:
                    on_progress({
                        "type": "search_progress",
                        "stage": "search_done",
                        "message": f"Search completed for: {query}",
                        "current_query": query,
                        "queries": query_states,
                    })
                
                all_responses.append(resp)
                
                # 合并结果（按 URL 去重）
                for result in resp.get("results", []):
                    url = result.get("url", "")
                    if url and url not in seen_urls:
                        seen_urls.add(url)
                        all_results.append(result)
                        
            except Exception as e:
                logger.logger.error(f"[TavilyClient] Search task failed: {e}")
                # 标记失败
                for qs in query_states:
                    if qs["status"] == "searching":
                        qs["status"] = "error"
        
        # 按 score 排序
        all_results.sort(key=lambda x: x.get("score", 0), reverse=True)
        
        logger.logger.info(
            f"[TavilyClient] Parallel search completed: "
            f"{len(queries)} queries, {len(all_results)} unique results"
        )
        
        return all_results, all_responses
    
    async def close(self):
        """关闭 HTTP 客户端"""
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None
