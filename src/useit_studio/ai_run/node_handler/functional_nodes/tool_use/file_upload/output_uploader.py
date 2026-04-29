"""
工具结果上传到 S3

将 RAG、Web Search 等工具的执行结果上传到 S3，
路径为: projects/{project_id}/outputs/

供后续持久化与检索使用。
"""

from typing import Dict, Any, Optional, Tuple
from datetime import datetime, timedelta, timezone
import asyncio

from useit_studio.ai_run.utils.s3_uploader import get_s3_uploader, _get_s3_client, _get_executor
from useit_studio.ai_run.utils.logger_utils import LoggerUtils

logger = LoggerUtils(component_name="OutputUploader")

UTC_PLUS_8 = timezone(timedelta(hours=8))


async def upload_tool_result_to_s3(
    project_id: Optional[str],
    tool_type: str,
    result: Dict[str, Any],
) -> Tuple[Dict[str, Any], Optional[str]]:
    """
    将工具执行结果上传到 S3，路径为 projects/{project_id}/outputs/。

    Args:
        project_id: 项目 ID，为 None 时不上传，直接返回原结果。
        tool_type: 工具类型，如 "rag" 或 "web_search"，用于生成文件名。
        result: 工具返回的结构化结果（可 JSON 序列化）。

    Returns:
        (result, s3_url): 原 result 与上传后的 S3 URL（s3://bucket/key）。
        若未上传或上传失败，s3_url 为 None；result 始终为传入的 result（可被调用方合并 s3_url）。
    """
    if not project_id or not project_id.strip():
        logger.logger.info("[OutputUploader] project_id not provided, skip S3 upload for tool result")
        return result, None

    timestamp = datetime.now(UTC_PLUS_8).strftime("%Y%m%d_%H%M%S")
    filename = f"{tool_type}_{timestamp}.json"
    s3_key = f"projects/{project_id.strip()}/outputs/{filename}"

    try:
        uploader = get_s3_uploader()
        # 检查 S3 客户端是否可用（未配置凭证时可能为 None）
        from useit_studio.ai_run.utils.s3_uploader import _get_s3_client
        if _get_s3_client() is None:
            logger.logger.info("[OutputUploader] S3 client not available (no AWS credentials?), skip upload")
            return result, None

        ok = await uploader.upload_json_async(result, s3_key)
        if ok:
            s3_url = f"s3://{uploader.bucket_name}/{s3_key}"
            logger.logger.info(f"[OutputUploader] Uploaded {tool_type} result -> {s3_url}")
            return result, s3_url
    except Exception as e:
        logger.logger.warning(f"[OutputUploader] Upload failed: {e}", exc_info=False)

    return result, None


async def upload_markdown_to_s3(
    project_id: Optional[str],
    markdown_content: str,
    filename_prefix: str = "result",
) -> Optional[str]:
    """
    将 markdown 文本上传到 S3，路径为 projects/{project_id}/outputs/。

    Args:
        project_id: 项目 ID，为 None 时不上传，直接返回 None。
        markdown_content: markdown 文本内容
        filename_prefix: 文件名前缀，默认 "result"

    Returns:
        上传后的 S3 URL（s3://bucket/key）。
        若未上传或上传失败，返回 None。
    """
    if not project_id or not project_id.strip():
        logger.logger.info("[OutputUploader] project_id not provided, skip S3 upload for markdown")
        return None

    if not markdown_content or not markdown_content.strip():
        logger.logger.warning("[OutputUploader] markdown_content is empty, skip upload")
        return None

    timestamp = datetime.now(UTC_PLUS_8).strftime("%Y%m%d_%H%M%S")
    filename = f"{filename_prefix}_{timestamp}.md"
    s3_key = f"projects/{project_id.strip()}/outputs/{filename}"

    try:
        # 检查 S3 客户端是否可用
        client = _get_s3_client()
        if client is None:
            logger.logger.info("[OutputUploader] S3 client not available (no AWS credentials?), skip upload")
            return None

        uploader = get_s3_uploader()
        
        # 使用线程池异步上传文本内容
        def _upload_markdown_sync():
            try:
                markdown_bytes = markdown_content.encode('utf-8')
                client.put_object(
                    Bucket=uploader.bucket_name,
                    Key=s3_key,
                    Body=markdown_bytes,
                    ContentType='text/markdown; charset=utf-8'
                )
                return True
            except Exception as e:
                logger.logger.warning(f"[OutputUploader] Markdown upload failed: {e}", exc_info=False)
                return False
        
        loop = asyncio.get_event_loop()
        executor = _get_executor()
        ok = await loop.run_in_executor(executor, _upload_markdown_sync)
        
        if ok:
            s3_url = f"s3://{uploader.bucket_name}/{s3_key}"
            logger.logger.info(f"[OutputUploader] Uploaded markdown -> {s3_url}")
            return s3_url
    except Exception as e:
        logger.logger.warning(f"[OutputUploader] Upload failed: {e}", exc_info=False)

    return None
