"""
截图处理器 - 负责截图的获取、验证和解析
"""
import asyncio
import base64
import io
import logging
import uuid
from typing import Any, AsyncGenerator, Dict, List, Optional, Tuple

from PIL import Image

from ..constants import (
    CALLBACK_TIMEOUT,
    MAX_SCREENSHOT_ATTEMPTS,
    MIN_SCREENSHOT_DIMENSION,
    MIN_SCREENSHOT_SIZE,
    SCREENSHOT_RETRY_DELAY,
)
from ..interaction_manager import WorkflowInteractionManager
from ..utils.message_logger import log_message

logger = logging.getLogger(__name__)


class ScreenshotHandler:
    """
    截图处理器
    
    职责：
    - 通过 SSE 请求前端获取截图
    - 验证截图有效性
    - 从各种回调格式中提取截图
    """

    @staticmethod
    def validate(screenshot_base64: Optional[str]) -> bool:
        """
        验证截图有效性
        
        Args:
            screenshot_base64: 截图的base64数据
            
        Returns:
            bool: 截图是否有效
        """
        if not screenshot_base64:
            return False
        
        try:
            # 验证base64格式
            screenshot_data = base64.b64decode(screenshot_base64)
            
            # 验证图片大小
            if len(screenshot_data) < MIN_SCREENSHOT_SIZE:
                logger.warning("[ScreenshotHandler] 截图数据过小，可能无效")
                return False
            
            # 验证图片格式和尺寸
            img = Image.open(io.BytesIO(screenshot_data))
            width, height = img.size
            if width < MIN_SCREENSHOT_DIMENSION or height < MIN_SCREENSHOT_DIMENSION:
                logger.warning(f"[ScreenshotHandler] 截图尺寸过小: {width}x{height}")
                return False
                
            logger.info(f"[ScreenshotHandler] 截图验证通过: {width}x{height}, {len(screenshot_data)} bytes")
            return True
            
        except Exception as e:
            logger.error(f"[ScreenshotHandler] 截图验证失败: {e}")
            return False

    @staticmethod
    def extract_from_callback(result_data: Any) -> Optional[str]:
        """
        从回调结果中提取截图
        
        支持多种格式：
        1. 顶层 screenshot 字段
        2. action_results 数组
        3. results 数组
        4. type=screenshot 格式
        5. data 字段递归
        6. result 字段递归
        7. snapshot 字段 (Word/Excel)
        8. execution 字段
        
        Args:
            result_data: 回调结果数据
            
        Returns:
            截图的base64字符串，如果未找到则返回None
        """
        if not isinstance(result_data, dict):
            logger.warning(f"[ScreenshotHandler] result_data 不是 dict: {type(result_data)}")
            return None
        
        logger.info(f"[ScreenshotHandler] 开始解析，keys: {list(result_data.keys())}")
        
        # 方式1：直接从顶层 screenshot 字段提取
        screenshot = result_data.get("screenshot")
        if isinstance(screenshot, str) and screenshot:
            logger.info(f"[ScreenshotHandler] ✅ 方式1成功：顶层 screenshot，长度={len(screenshot)}")
            return screenshot
        
        # 方式2：从 action_results 数组中提取
        screenshot = ScreenshotHandler._extract_from_action_results(
            result_data.get("action_results")
        )
        if screenshot:
            return screenshot
        
        # 方式3：从 results 数组中提取
        results = result_data.get("results") or result_data.get("result")
        if isinstance(results, list):
            screenshot = ScreenshotHandler._extract_from_results_list(results)
            if screenshot:
                return screenshot
        
        # 方式4：直接从顶层提取（type=screenshot 格式）
        if result_data.get("type") == "screenshot":
            img = result_data.get("image_base64")
            if img:
                logger.info(f"[ScreenshotHandler] ✅ 方式4成功：顶层 type=screenshot")
                return img
        
        # 方式5：从 data 字段递归提取
        data = result_data.get("data")
        if isinstance(data, dict):
            logger.info(f"[ScreenshotHandler] 尝试方式5：递归 data 字段")
            return ScreenshotHandler.extract_from_callback(data)
        
        # 方式6：从 result 字段递归提取
        result_field = result_data.get("result")
        if isinstance(result_field, dict):
            logger.info(f"[ScreenshotHandler] 尝试方式6：递归 result 字段")
            return ScreenshotHandler.extract_from_callback(result_field)
        
        # 方式7：从 snapshot 字段提取（Word/Excel 节点）
        snapshot = result_data.get("snapshot")
        if isinstance(snapshot, dict):
            logger.info(f"[ScreenshotHandler] 尝试方式7：snapshot 字段")
            snap_screenshot = snapshot.get("screenshot")
            if isinstance(snap_screenshot, str) and snap_screenshot:
                logger.info(f"[ScreenshotHandler] ✅ 方式7成功：snapshot.screenshot")
                return snap_screenshot
            snap_image = snapshot.get("image_base64")
            if isinstance(snap_image, str) and snap_image:
                logger.info(f"[ScreenshotHandler] ✅ 方式7成功：snapshot.image_base64")
                return snap_image
            return ScreenshotHandler.extract_from_callback(snapshot)
        
        # 方式8：从 execution 字段提取
        execution = result_data.get("execution")
        if isinstance(execution, dict):
            logger.info(f"[ScreenshotHandler] 尝试方式8：execution 字段")
            exec_screenshot = execution.get("screenshot")
            if isinstance(exec_screenshot, str) and exec_screenshot:
                logger.info(f"[ScreenshotHandler] ✅ 方式8成功：execution.screenshot")
                return exec_screenshot
        
        logger.warning(f"[ScreenshotHandler] ❌ 所有方式都失败")
        return None

    @staticmethod
    def extract_project_files(result_data: Any) -> Optional[str]:
        """
        从回调结果中提取项目文件列表
        
        支持多种格式：
        1. 顶层 project_files 字段
        2. data.project_files 字段
        3. result.project_files 字段
        4. snapshot.project_files 字段
        
        Args:
            result_data: 回调结果数据
            
        Returns:
            项目文件列表字符串（紧凑 tree 格式），如果未找到则返回 None
        """
        if not isinstance(result_data, dict):
            return None
        
        # 方式1：直接从顶层 project_files 字段提取
        project_files = result_data.get("project_files")
        if isinstance(project_files, str) and project_files:
            logger.info(f"[ScreenshotHandler] ✅ 提取 project_files 成功（顶层），长度={len(project_files)}")
            return project_files
        
        # 方式2：从 data 字段提取
        data = result_data.get("data")
        if isinstance(data, dict):
            project_files = data.get("project_files")
            if isinstance(project_files, str) and project_files:
                logger.info(f"[ScreenshotHandler] ✅ 提取 project_files 成功（data），长度={len(project_files)}")
                return project_files
        
        # 方式3：从 result 字段提取
        result_field = result_data.get("result")
        if isinstance(result_field, dict):
            project_files = result_field.get("project_files")
            if isinstance(project_files, str) and project_files:
                logger.info(f"[ScreenshotHandler] ✅ 提取 project_files 成功（result），长度={len(project_files)}")
                return project_files
        
        # 方式4：从 snapshot 字段提取
        snapshot = result_data.get("snapshot")
        if isinstance(snapshot, dict):
            project_files = snapshot.get("project_files")
            if isinstance(project_files, str) and project_files:
                logger.info(f"[ScreenshotHandler] ✅ 提取 project_files 成功（snapshot），长度={len(project_files)}")
                return project_files
        
        return None

    @staticmethod
    def _extract_from_action_results(action_results: Any) -> Optional[str]:
        """从 action_results 数组中提取截图"""
        if not isinstance(action_results, list) or not action_results:
            return None
        
        logger.info(f"[ScreenshotHandler] 尝试方式2：action_results 数组，长度={len(action_results)}")
        
        for i, r in enumerate(action_results):
            if not isinstance(r, dict):
                continue
            inner_result = r.get("result") or r
            if isinstance(inner_result, dict):
                if inner_result.get("type") == "screenshot":
                    img = inner_result.get("image_base64")
                    if img:
                        logger.info(f"[ScreenshotHandler] ✅ 方式2成功：action_results[{i}]")
                        return img
                if inner_result.get("image_base64"):
                    img = inner_result.get("image_base64")
                    logger.info(f"[ScreenshotHandler] ✅ 方式2成功：action_results[{i}].image_base64")
                    return img
        return None

    @staticmethod
    def _extract_from_results_list(results: List[Any]) -> Optional[str]:
        """从 results 列表中提取截图"""
        logger.info(f"[ScreenshotHandler] 尝试方式3：results 数组，长度={len(results)}")
        
        for r in results:
            if not isinstance(r, dict):
                continue
            inner_result = r.get("result") or r
            if isinstance(inner_result, dict):
                if inner_result.get("type") == "screenshot":
                    img = inner_result.get("image_base64")
                    if img:
                        logger.info(f"[ScreenshotHandler] ✅ 方式3成功")
                        return img
        return None

    @staticmethod
    def extract_screen_info(result_data: Any) -> Tuple[Optional[int], Optional[int]]:
        """
        从回调结果中提取屏幕信息
        
        Args:
            result_data: 回调结果数据
            
        Returns:
            (width, height) 元组，如果未找到则返回 (None, None)
        """
        if not isinstance(result_data, dict):
            return (None, None)
        
        # 方式1：从 action_results 数组中提取
        action_results = result_data.get("action_results") or []
        if isinstance(action_results, list):
            for r in action_results:
                if not isinstance(r, dict):
                    continue
                inner_result = r.get("result") or r
                screen_info = ScreenshotHandler._parse_screen_info(inner_result)
                if screen_info[0] is not None:
                    return screen_info
        
        # 方式2：从 results 数组中提取
        results = result_data.get("results") or result_data.get("result") or []
        if isinstance(results, list):
            for r in results:
                if not isinstance(r, dict):
                    continue
                inner_result = r.get("result") or r
                screen_info = ScreenshotHandler._parse_screen_info(inner_result)
                if screen_info[0] is not None:
                    return screen_info
        
        # 方式3：直接从顶层提取
        screen_info = ScreenshotHandler._parse_screen_info(result_data)
        if screen_info[0] is not None:
            return screen_info
        
        # 方式4：从 data 字段递归提取
        data = result_data.get("data")
        if isinstance(data, dict):
            return ScreenshotHandler.extract_screen_info(data)
        
        return (None, None)

    @staticmethod
    def _parse_screen_info(data: Any) -> Tuple[Optional[int], Optional[int]]:
        """解析屏幕信息"""
        if not isinstance(data, dict):
            return (None, None)
        
        result_type = str(data.get("type") or "").strip().lower()
        if result_type == "screen_info":
            try:
                w = int(data.get("width"))
                h = int(data.get("height"))
                return (w, h)
            except (TypeError, ValueError):
                pass
        return (None, None)

    async def request_via_sse(
        self,
        interaction_manager: WorkflowInteractionManager,
        with_screenshot: bool = True,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        通过 SSE 请求前端获取 screen_info + screenshot
        
        Args:
            interaction_manager: 交互管理器
            with_screenshot: 是否同时获取截图
            
        Yields:
            - client_request 事件（发给前端）
            - _internal_screenshot_result 事件（内部使用）
        """
        if not interaction_manager:
            logger.error("[ScreenshotHandler] interaction_manager 未提供")
            yield {
                "type": "_internal_screenshot_result",
                "screen_width": None,
                "screen_height": None,
                "screenshot_base64": None,
                "error": "interaction_manager not provided"
            }
            return
        
        request_id = str(uuid.uuid4())
        
        # 构造请求
        actions = [{"type": "screen_info"}]
        if with_screenshot:
            actions.append({"type": "screenshot"})
        
        client_request_event = {
            "type": "client_request",
            "requestId": request_id,
            "action": "execute_actions",
            "params": {"actions": actions}
        }
        
        logger.info(f"[ScreenshotHandler] 发送 SSE 请求: request_id={request_id}")
        log_message("SEND", client_request_event, context="screenshot_request")
        yield client_request_event
        
        # 等待回调
        try:
            result_data = await interaction_manager.wait_for_result(request_id, timeout=CALLBACK_TIMEOUT)
            
            # 打印回调数据大小
            import json as _json
            result_json_str = _json.dumps(result_data, ensure_ascii=False, default=str)
            result_size_kb = len(result_json_str.encode('utf-8')) / 1024
            logger.info(f"[ScreenshotHandler] 收到回调数据 大小: {result_size_kb:.2f}KB")
            print(f"[PERF] 📦 收到截图回调数据 大小: {result_size_kb:.2f}KB")
            
            logger.info(f"[ScreenshotHandler] 收到回调: keys={list(result_data.keys()) if isinstance(result_data, dict) else 'N/A'}")
            
            screen_w, screen_h = self.extract_screen_info(result_data)
            screenshot_base64 = self.extract_from_callback(result_data) if with_screenshot else None
            project_files = self.extract_project_files(result_data)
            
            logger.info(f"[ScreenshotHandler] 解析结果: screen={screen_w}x{screen_h}, has_screenshot={screenshot_base64 is not None}, has_project_files={project_files is not None}")
            
            yield {
                "type": "_internal_screenshot_result",
                "screen_width": screen_w,
                "screen_height": screen_h,
                "screenshot_base64": screenshot_base64,
                "project_files": project_files,
                "error": None
            }
            
        except asyncio.TimeoutError:
            logger.error(f"[ScreenshotHandler] 请求超时: request_id={request_id}")
            yield {
                "type": "_internal_screenshot_result",
                "screen_width": None,
                "screen_height": None,
                "screenshot_base64": None,
                "error": "timeout"
            }
        except Exception as e:
            logger.error(f"[ScreenshotHandler] 请求失败: {e}")
            yield {
                "type": "_internal_screenshot_result",
                "screen_width": None,
                "screen_height": None,
                "screenshot_base64": None,
                "error": str(e)
            }

    async def request_with_retry(
        self,
        interaction_manager: WorkflowInteractionManager,
        max_attempts: int = MAX_SCREENSHOT_ATTEMPTS,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        带重试的截图请求
        
        Args:
            interaction_manager: 交互管理器
            max_attempts: 最大重试次数
            
        Yields:
            与 request_via_sse 相同
        """
        for attempt in range(max_attempts):
            try:
                async for event in self.request_via_sse(interaction_manager):
                    if event.get("type") == "_internal_screenshot_result":
                        if event.get("error") is None:
                            yield event
                            return
                        # 有错误，继续重试
                    else:
                        yield event
                
                logger.warning(f"[ScreenshotHandler] 尝试 {attempt + 1}/{max_attempts} 失败")
                
            except Exception as e:
                logger.error(f"[ScreenshotHandler] 尝试 {attempt + 1}/{max_attempts} 异常: {e}")
            
            if attempt < max_attempts - 1:
                await asyncio.sleep(SCREENSHOT_RETRY_DELAY)
        
        # 所有重试都失败
        yield {
            "type": "_internal_screenshot_result",
            "screen_width": None,
            "screen_height": None,
            "screenshot_base64": None,
            "error": f"经过 {max_attempts} 次尝试，无法获取截图"
        }
