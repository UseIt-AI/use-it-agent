"""
GUI Agent V2 - 图片处理工具

简化的图片处理函数。
"""

import os
from PIL import Image, ImageDraw, ImageFont
from typing import Optional, Tuple


def resize_screenshot(
    input_path: str,
    output_path: Optional[str] = None,
    max_side: int = 1024,
) -> str:
    """
    调整截图大小，保持宽高比
    
    Args:
        input_path: 输入图片路径
        output_path: 输出路径（可选，默认覆盖原文件）
        max_side: 最大边长
        
    Returns:
        输出图片路径
    """
    if not os.path.exists(input_path):
        raise FileNotFoundError(f"图片不存在: {input_path}")
    
    output_path = output_path or input_path
    
    with Image.open(input_path) as img:
        width, height = img.size
        
        # 如果已经足够小，直接返回
        if width <= max_side and height <= max_side:
            if output_path != input_path:
                img.save(output_path)
            return output_path
        
        # 计算缩放比例
        scale = max_side / max(width, height)
        new_width = int(width * scale)
        new_height = int(height * scale)
        
        # 缩放并保存
        resized = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
        resized.save(output_path)
        
    return output_path


def get_image_size(image_path: str) -> Tuple[int, int]:
    """获取图片尺寸"""
    with Image.open(image_path) as img:
        return img.size


def draw_crosshair(
    image_path: str,
    x: int,
    y: int,
    output_path: Optional[str] = None,
    coordinate_system: str = "screen_pixel",
    crosshair_size: int = 30,
    crosshair_color: Tuple[int, int, int] = (255, 0, 0),  # 红色
    line_width: int = 3,
    show_label: bool = True,
) -> str:
    """
    在截图上绘制十字准星，标记 AI 点击位置
    
    Args:
        image_path: 输入图片路径
        x: X 坐标
        y: Y 坐标
        output_path: 输出路径（可选，默认添加 _crosshair 后缀）
        coordinate_system: 坐标系类型 ("normalized_1000" 或 "screen_pixel")
        crosshair_size: 准星大小（单臂长度）
        crosshair_color: 准星颜色 RGB
        line_width: 线条宽度
        show_label: 是否显示坐标标签
        
    Returns:
        输出图片路径
    """
    if not os.path.exists(image_path):
        raise FileNotFoundError(f"图片不存在: {image_path}")
    
    output_path = output_path or image_path.replace(".png", "_crosshair.png")
    
    with Image.open(image_path) as img:
        width, height = img.size
        
        # 如果是千分位坐标，转换为像素坐标
        if coordinate_system == "normalized_1000":
            actual_x = int((x / 1000.0) * width)
            actual_y = int((y / 1000.0) * height)
        else:
            actual_x = x
            actual_y = y
        
        # 创建绘图对象
        draw = ImageDraw.Draw(img)
        
        # 绘制十字准星
        # 水平线
        draw.line(
            [(actual_x - crosshair_size, actual_y), (actual_x + crosshair_size, actual_y)],
            fill=crosshair_color,
            width=line_width
        )
        # 垂直线
        draw.line(
            [(actual_x, actual_y - crosshair_size), (actual_x, actual_y + crosshair_size)],
            fill=crosshair_color,
            width=line_width
        )
        
        # 绘制中心圆点
        circle_radius = 5
        draw.ellipse(
            [
                (actual_x - circle_radius, actual_y - circle_radius),
                (actual_x + circle_radius, actual_y + circle_radius)
            ],
            fill=crosshair_color,
            outline=(255, 255, 255),
            width=2
        )
        
        # 绘制外圈（瞄准镜效果）
        outer_radius = crosshair_size - 5
        draw.arc(
            [
                (actual_x - outer_radius, actual_y - outer_radius),
                (actual_x + outer_radius, actual_y + outer_radius)
            ],
            start=0,
            end=360,
            fill=crosshair_color,
            width=line_width
        )
        
        # 显示坐标标签
        if show_label:
            if coordinate_system == "normalized_1000":
                label = f"({x}, {y}) → ({actual_x}, {actual_y})"
            else:
                label = f"({actual_x}, {actual_y})"
            
            # 标签位置（在准星右下方）
            label_x = actual_x + crosshair_size + 10
            label_y = actual_y + crosshair_size + 5
            
            # 确保标签不超出图片边界
            if label_x + 150 > width:
                label_x = actual_x - crosshair_size - 160
            if label_y + 20 > height:
                label_y = actual_y - crosshair_size - 25
            
            # 绘制标签背景
            try:
                font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 14)
            except (IOError, OSError):
                font = ImageFont.load_default()
            
            # 获取文本边界框
            bbox = draw.textbbox((label_x, label_y), label, font=font)
            padding = 4
            draw.rectangle(
                [bbox[0] - padding, bbox[1] - padding, bbox[2] + padding, bbox[3] + padding],
                fill=(0, 0, 0, 180)
            )
            draw.text((label_x, label_y), label, fill=(255, 255, 255), font=font)
        
        img.save(output_path)
    
    return output_path


def draw_action_visualization(
    image_path: str,
    action_dict: dict,
    output_path: Optional[str] = None,
) -> str:
    """
    根据 DeviceAction 字典可视化动作
    
    Args:
        image_path: 输入图片路径
        action_dict: DeviceAction.to_dict() 的输出
        output_path: 输出路径
        
    Returns:
        输出图片路径
    """
    action_type = action_dict.get("type", "")
    coordinate = action_dict.get("coordinate", [])
    coordinate_system = action_dict.get("coordinate_system", "screen_pixel")
    
    # 只对有坐标的动作进行可视化
    if action_type in ["click", "double_click", "move", "scroll"] and len(coordinate) >= 2:
        # 根据动作类型选择颜色
        color_map = {
            "click": (255, 0, 0),        # 红色 - 单击
            "double_click": (255, 165, 0),  # 橙色 - 双击
            "move": (0, 255, 0),          # 绿色 - 移动
            "scroll": (0, 0, 255),        # 蓝色 - 滚动
        }
        color = color_map.get(action_type, (255, 0, 0))
        
        return draw_crosshair(
            image_path=image_path,
            x=coordinate[0],
            y=coordinate[1],
            output_path=output_path,
            coordinate_system=coordinate_system,
            crosshair_color=color,
        )
    
    # 非坐标动作，直接返回原图路径
    return image_path
