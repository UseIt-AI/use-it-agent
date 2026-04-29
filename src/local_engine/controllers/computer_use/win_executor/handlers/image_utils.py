"""
截图压缩工具

提供统一的截图压缩功能：
1. 尺寸压缩：按比例缩放到目标尺寸
2. 大小压缩：使用 JPEG 格式 + 动态质量调整，目标 ~300KB
"""

import io
import logging
from PIL import Image

logger = logging.getLogger(__name__)

# ==================== 全屏截图配置（16:9 或 16:10）====================
# 16:9 显示器
FULLSCREEN_TARGET_WIDTH_16_9 = 1366
FULLSCREEN_TARGET_HEIGHT_16_9 = 768

# 16:10 显示器
FULLSCREEN_TARGET_WIDTH_16_10 = 1440
FULLSCREEN_TARGET_HEIGHT_16_10 = 900

# 默认使用 16:9
FULLSCREEN_TARGET_WIDTH = 1366
FULLSCREEN_TARGET_HEIGHT = 768

# ==================== 窗口截图配置（Word/PPT/Excel 等）====================
# 窗口截图：最长边超过阈值时，缩放到最长边 = MAX_LONG_EDGE
WINDOW_LONG_EDGE_THRESHOLD = 1568  # 超过此值才缩放
WINDOW_MAX_LONG_EDGE = 1400        # 缩放后的最长边

# ==================== 压缩配置 ====================
SCREENSHOT_TARGET_SIZE_KB = 500    # 目标大小 500KB（允许更高质量）
JPEG_QUALITY_INITIAL = 92          # 初始 JPEG 质量（更高）
JPEG_QUALITY_MIN = 75              # 最低质量（不低于 75，保证清晰度）
JPEG_QUALITY_STEP = 3              # 质量递减步长（更细粒度）


def compress_fullscreen_screenshot(
    image_bytes: bytes,
    target_width: int = FULLSCREEN_TARGET_WIDTH,
    target_height: int = FULLSCREEN_TARGET_HEIGHT,
    target_size_kb: int = SCREENSHOT_TARGET_SIZE_KB,
) -> bytes:
    """
    压缩全屏截图（用于 Computer Use 场景）
    
    缩放逻辑：
    - 以 target_width 为基准，按原始比例缩放
    - 16:9 屏幕 → 1366 × 768
    - 16:10 屏幕 → 1366 × 854（宽度固定，高度按比例）
    
    Args:
        image_bytes: 原始图像字节
        target_width: 目标宽度（默认 1366）
        target_height: 目标高度参考值（用于判断是否需要缩放）
        target_size_kb: 目标文件大小（KB）
    
    Returns:
        压缩后的 JPEG 图像字节
    """
    img = Image.open(io.BytesIO(image_bytes))
    original_width, original_height = img.size
    
    # 1. 缩放尺寸（以宽度为基准，保持比例）
    if original_width > target_width:
        ratio = target_width / original_width
        new_width = target_width
        new_height = int(original_height * ratio)
        img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
        logger.info(f"[compress_fullscreen] Resized: {original_width}x{original_height} -> {new_width}x{new_height}")
    
    # 2. JPEG 压缩
    return _compress_to_jpeg(img, target_size_kb)


def compress_window_screenshot(
    image_bytes: bytes,
    long_edge_threshold: int = WINDOW_LONG_EDGE_THRESHOLD,
    max_long_edge: int = WINDOW_MAX_LONG_EDGE,
    target_size_kb: int = SCREENSHOT_TARGET_SIZE_KB,
) -> bytes:
    """
    压缩窗口截图（用于 Word/PPT/Excel 等窗口场景）
    
    缩放逻辑：
    - 如果最长边超过 long_edge_threshold，则缩放到最长边 = max_long_edge
    - 保持原始比例不变
    
    Args:
        image_bytes: 原始图像字节
        long_edge_threshold: 长边阈值，超过此值才缩放（默认 1568）
        max_long_edge: 缩放后的最长边（默认 1400）
        target_size_kb: 目标文件大小（KB）
    
    Returns:
        压缩后的 JPEG 图像字节
    """
    img = Image.open(io.BytesIO(image_bytes))
    original_width, original_height = img.size
    
    # 1. 计算最长边
    long_edge = max(original_width, original_height)
    
    # 2. 如果最长边超过阈值，按比例缩放
    if long_edge > long_edge_threshold:
        ratio = max_long_edge / long_edge
        new_width = int(original_width * ratio)
        new_height = int(original_height * ratio)
        img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
        logger.info(f"[compress_window] Resized: {original_width}x{original_height} -> {new_width}x{new_height}")
    
    # 3. JPEG 压缩
    return _compress_to_jpeg(img, target_size_kb)


def compress_screenshot_from_pil(
    img: Image.Image,
    long_edge_threshold: int = WINDOW_LONG_EDGE_THRESHOLD,
    max_long_edge: int = WINDOW_MAX_LONG_EDGE,
    target_size_kb: int = SCREENSHOT_TARGET_SIZE_KB,
) -> bytes:
    """
    直接从 PIL Image 对象压缩（用于 Word/PPT 等已经有 Image 对象的场景）
    
    Args:
        img: PIL Image 对象
        long_edge_threshold: 长边阈值，超过此值才缩放（默认 1568）
        max_long_edge: 缩放后的最长边（默认 1400）
        target_size_kb: 目标文件大小（KB）
    
    Returns:
        压缩后的 JPEG 图像字节
    """
    original_width, original_height = img.size
    
    # 1. 计算最长边
    long_edge = max(original_width, original_height)
    
    # 2. 如果最长边超过阈值，按比例缩放
    if long_edge > long_edge_threshold:
        ratio = max_long_edge / long_edge
        new_width = int(original_width * ratio)
        new_height = int(original_height * ratio)
        img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
        logger.info(f"[compress_from_pil] Resized: {original_width}x{original_height} -> {new_width}x{new_height}")
    
    # 3. JPEG 压缩
    return _compress_to_jpeg(img, target_size_kb)


def _compress_to_jpeg(
    img: Image.Image,
    target_size_kb: int = SCREENSHOT_TARGET_SIZE_KB,
) -> bytes:
    """
    将 PIL Image 压缩为 JPEG，动态调整质量以达到目标大小
    
    Args:
        img: PIL Image 对象
        target_size_kb: 目标文件大小（KB）
    
    Returns:
        压缩后的 JPEG 图像字节
    """
    # 1. 确保是 RGB 模式（JPEG 不支持 RGBA）
    if img.mode in ('RGBA', 'P'):
        background = Image.new('RGB', img.size, (255, 255, 255))
        if img.mode == 'RGBA':
            background.paste(img, mask=img.split()[3])
        else:
            background.paste(img)
        img = background
    elif img.mode != 'RGB':
        img = img.convert('RGB')
    
    # 2. 动态调整质量以达到目标大小
    target_size_bytes = target_size_kb * 1024
    quality = JPEG_QUALITY_INITIAL
    
    while quality >= JPEG_QUALITY_MIN:
        output = io.BytesIO()
        img.save(output, format='JPEG', quality=quality, optimize=True)
        size = output.tell()
        
        if size <= target_size_bytes:
            output.seek(0)
            result = output.read()
            logger.info(f"[compress_to_jpeg] Compressed to {len(result) / 1024:.1f}KB (quality={quality})")
            return result
        
        # 减少质量继续尝试
        quality -= JPEG_QUALITY_STEP
    
    # 使用最低质量
    output = io.BytesIO()
    img.save(output, format='JPEG', quality=JPEG_QUALITY_MIN, optimize=True)
    output.seek(0)
    result = output.read()
    logger.info(f"[compress_to_jpeg] Compressed to {len(result) / 1024:.1f}KB (quality={JPEG_QUALITY_MIN}, min)")
    return result
