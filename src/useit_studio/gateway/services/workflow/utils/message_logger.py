"""
消息落盘功能 - 用于调试和追踪工作流消息
"""
import datetime
import json
import logging
from typing import Any, Dict

from ..constants import MESSAGE_LOG_DIR, MESSAGE_LOG_ENABLED

logger = logging.getLogger(__name__)


def log_message(direction: str, message: Dict[str, Any], context: str = "") -> None:
    """
    将消息落盘到文件，用于调试
    
    Args:
        direction: "RECV" (接收) 或 "SEND" (发送)
        message: 消息内容
        context: 额外上下文信息
    """
    if not MESSAGE_LOG_ENABLED:
        return
    
    try:
        MESSAGE_LOG_DIR.mkdir(parents=True, exist_ok=True)
        
        # 按日期创建日志文件
        today = datetime.datetime.now().strftime("%Y%m%d")
        log_file = MESSAGE_LOG_DIR / f"messages_{today}.jsonl"
        
        # 准备日志条目
        log_entry = {
            "timestamp": datetime.datetime.now().isoformat(),
            "direction": direction,
            "context": context,
            "message_type": message.get("type", "unknown"),
            "message": sanitize_message(message),
        }
        
        # 追加写入
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(log_entry, ensure_ascii=False, default=str) + "\n")
            
    except Exception as e:
        logger.warning(f"[MessageLog] 落盘失败: {e}")


def sanitize_message(message: Dict[str, Any]) -> Dict[str, Any]:
    """
    清理消息，移除过大的字段（如 base64 截图）
    
    Args:
        message: 原始消息
        
    Returns:
        清理后的消息
    """
    if not isinstance(message, dict):
        return message
    
    # 需要清理的大字段
    large_fields = ("screenshot", "screenshot_base64", "image_base64", "image")
    
    sanitized = {}
    for key, value in message.items():
        if key in large_fields:
            if isinstance(value, str) and len(value) > 100:
                sanitized[key] = f"<base64_image, length={len(value)}>"
            else:
                sanitized[key] = value
        elif isinstance(value, dict):
            sanitized[key] = sanitize_message(value)
        elif isinstance(value, list):
            sanitized[key] = [
                sanitize_message(item) if isinstance(item, dict) else item 
                for item in value
            ]
        else:
            sanitized[key] = value
    
    return sanitized
