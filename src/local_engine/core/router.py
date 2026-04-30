"""
CUA Request 路由器

负责将 AI Run 的 cua_request 路由到对应的 Controller。
使用共享的类型定义确保接口契约一致。
"""

from typing import Dict, Any
import logging

from shared import REQUEST_TYPE_MAPPING, validate_request_type
from core import controller_registry

logger = logging.getLogger(__name__)


async def route_and_execute_cua_request(
    request_type: str,
    params: Dict[str, Any]
) -> Dict[str, Any]:
    """
    路由并执行 CUA Request

    Args:
        request_type: 请求类型（如 excel_snapshot）
        params: AI Run 格式的参数

    Returns:
        执行结果
        {
            "success": bool,
            "data": {...} or None,
            "error": str or None
        }
    """
    logger.info(f"[CUA Router] Processing request: {request_type}")

    # 1. 验证 request_type
    if not validate_request_type(request_type):
        error_msg = f"Unsupported CUA request type: {request_type}"
        logger.error(f"[CUA Router] {error_msg}")
        return {
            "success": False,
            "data": None,
            "error": error_msg
        }

    # 2. 查找映射配置（从共享包）
    mapping = REQUEST_TYPE_MAPPING.get(request_type)
    controller_name = mapping["controller"]
    action = mapping["action"]
    params_mapper = mapping["params_mapper"]

    logger.info(
        f"[CUA Router] {request_type} → "
        f"controller={controller_name}, action={action}"
    )

    # 3. 参数映射（使用共享的映射函数）
    try:
        mapped_params = params_mapper(params)
        logger.debug(f"[CUA Router] Mapped params: {mapped_params}")
    except Exception as e:
        error_msg = f"Parameter mapping failed: {str(e)}"
        logger.error(f"[CUA Router] {error_msg}", exc_info=True)
        return {
            "success": False,
            "data": None,
            "error": error_msg
        }

    # 4. 获取 Controller
    controller = controller_registry.get(controller_name)
    if not controller:
        available = controller_registry.list_controllers()
        error_msg = (
            f"Controller '{controller_name}' not found. "
            f"Available: {available}"
        )
        logger.error(f"[CUA Router] {error_msg}")
        return {
            "success": False,
            "data": None,
            "error": error_msg
        }

    # 5. 执行 Action
    try:
        response = await controller.handle_action(action, mapped_params)
        logger.info(
            f"[CUA Router] {request_type} completed: "
            f"success={response.success}"
        )

        # 6. 返回统一格式
        return {
            "success": response.success,
            "data": response.data,
            "error": response.error
        }

    except Exception as e:
        error_msg = f"Execution failed: {str(e)}"
        logger.error(f"[CUA Router] {error_msg}", exc_info=True)
        return {
            "success": False,
            "data": None,
            "error": error_msg
        }
