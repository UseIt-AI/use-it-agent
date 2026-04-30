"""
AutoCAD Agent - 图纸快照数据结构

AutoCADSnapshot 实现了 BaseSnapshot Protocol，
用于表示 AutoCAD 图纸的状态。
"""

from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any

# 导入 toon_format 用于压缩输出
try:
    from toon_format import encode as toon_encode
except ImportError:
    import json
    def toon_encode(obj):
        return json.dumps(obj, ensure_ascii=False, indent=2)


# ==================== 图元信息 ====================

@dataclass
class LineInfo:
    """直线信息"""
    start: List[float]  # [x, y, z]
    end: List[float]    # [x, y, z]
    layer: str = "0"
    color: int = 256    # 256 = ByLayer

    def to_dict(self) -> Dict[str, Any]:
        return {
            "start": self.start,
            "end": self.end,
            "layer": self.layer,
            "color": self.color,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "LineInfo":
        return cls(
            start=data.get("start", [0, 0, 0]),
            end=data.get("end", [0, 0, 0]),
            layer=data.get("layer", "0"),
            color=data.get("color", 256),
        )


@dataclass
class CircleInfo:
    """圆信息"""
    center: List[float]  # [x, y, z]
    radius: float
    layer: str = "0"
    color: int = 256

    def to_dict(self) -> Dict[str, Any]:
        return {
            "center": self.center,
            "radius": self.radius,
            "layer": self.layer,
            "color": self.color,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CircleInfo":
        return cls(
            center=data.get("center", [0, 0, 0]),
            radius=data.get("radius", 0),
            layer=data.get("layer", "0"),
            color=data.get("color", 256),
        )


@dataclass
class ArcInfo:
    """圆弧信息"""
    center: List[float]  # [x, y, z]
    radius: float
    start_angle: float   # 度
    end_angle: float     # 度
    layer: str = "0"
    color: int = 256

    def to_dict(self) -> Dict[str, Any]:
        return {
            "center": self.center,
            "radius": self.radius,
            "start_angle": self.start_angle,
            "end_angle": self.end_angle,
            "layer": self.layer,
            "color": self.color,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ArcInfo":
        return cls(
            center=data.get("center", [0, 0, 0]),
            radius=data.get("radius", 0),
            start_angle=data.get("start_angle", 0),
            end_angle=data.get("end_angle", 0),
            layer=data.get("layer", "0"),
            color=data.get("color", 256),
        )


@dataclass
class PolylineInfo:
    """多段线信息"""
    vertices: List[List[float]]  # [[x, y], ...]
    closed: bool = False
    layer: str = "0"
    color: int = 256

    def to_dict(self) -> Dict[str, Any]:
        return {
            "vertices": self.vertices,
            "closed": self.closed,
            "layer": self.layer,
            "color": self.color,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PolylineInfo":
        return cls(
            vertices=data.get("vertices", []),
            closed=data.get("closed", False),
            layer=data.get("layer", "0"),
            color=data.get("color", 256),
        )


@dataclass
class TextInfo:
    """文字信息"""
    text: str
    position: List[float]  # [x, y, z]
    height: float = 2.5
    layer: str = "0"
    color: int = 256

    def to_dict(self) -> Dict[str, Any]:
        return {
            "text": self.text,
            "position": self.position,
            "height": self.height,
            "layer": self.layer,
            "color": self.color,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TextInfo":
        return cls(
            text=data.get("text", ""),
            position=data.get("position", [0, 0, 0]),
            height=data.get("height", 2.5),
            layer=data.get("layer", "0"),
            color=data.get("color", 256),
        )


@dataclass
class DimensionInfo:
    """标注信息"""
    dim_type: str  # "Aligned", "Rotated", "Radial", "Angular"
    point1: Optional[List[float]] = None
    point2: Optional[List[float]] = None
    text_position: Optional[List[float]] = None
    center: Optional[List[float]] = None
    chord_point: Optional[List[float]] = None
    rotation: float = 0
    layer: str = "0"

    def to_dict(self) -> Dict[str, Any]:
        result = {
            "type": self.dim_type,
            "layer": self.layer,
        }
        if self.point1:
            result["point1"] = self.point1
        if self.point2:
            result["point2"] = self.point2
        if self.text_position:
            result["text_position"] = self.text_position
        if self.center:
            result["center"] = self.center
        if self.chord_point:
            result["chord_point"] = self.chord_point
        if self.rotation:
            result["rotation"] = self.rotation
        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DimensionInfo":
        return cls(
            dim_type=data.get("type", "Aligned"),
            point1=data.get("point1"),
            point2=data.get("point2"),
            text_position=data.get("text_position"),
            center=data.get("center"),
            chord_point=data.get("chord_point"),
            rotation=data.get("rotation", 0),
            layer=data.get("layer", "0"),
        )


# ==================== 图纸内容 ====================

@dataclass
class DrawingContent:
    """图纸内容"""
    layer_colors: Dict[str, int] = field(default_factory=dict)
    lines: List[LineInfo] = field(default_factory=list)
    circles: List[CircleInfo] = field(default_factory=list)
    arcs: List[ArcInfo] = field(default_factory=list)
    polylines: List[PolylineInfo] = field(default_factory=list)
    texts: List[TextInfo] = field(default_factory=list)
    dimensions: List[DimensionInfo] = field(default_factory=list)
    summary: Dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "layer_colors": self.layer_colors,
            "elements": {
                "lines": [l.to_dict() for l in self.lines],
                "circles": [c.to_dict() for c in self.circles],
                "arcs": [a.to_dict() for a in self.arcs],
                "polylines": [p.to_dict() for p in self.polylines],
                "texts": [t.to_dict() for t in self.texts],
                "dimensions": [d.to_dict() for d in self.dimensions],
            },
            "summary": self.summary or {
                "lines": len(self.lines),
                "circles": len(self.circles),
                "arcs": len(self.arcs),
                "polylines": len(self.polylines),
                "texts": len(self.texts),
                "dimensions": len(self.dimensions),
            },
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DrawingContent":
        elements = data.get("elements", {})
        return cls(
            layer_colors=data.get("layer_colors", {}),
            lines=[LineInfo.from_dict(l) for l in elements.get("lines", [])],
            circles=[CircleInfo.from_dict(c) for c in elements.get("circles", [])],
            arcs=[ArcInfo.from_dict(a) for a in elements.get("arcs", [])],
            polylines=[PolylineInfo.from_dict(p) for p in elements.get("polylines", [])],
            texts=[TextInfo.from_dict(t) for t in elements.get("texts", [])],
            dimensions=[DimensionInfo.from_dict(d) for d in elements.get("dimensions", [])],
            summary=data.get("summary", {}),
        )


# ==================== 文档信息 ====================

@dataclass
class DocumentInfo:
    """图纸文档信息"""
    name: str
    path: Optional[str] = None
    bounds: Optional[Dict[str, List[float]]] = None  # {"min": [x, y], "max": [x, y]}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "path": self.path,
            "bounds": self.bounds,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DocumentInfo":
        return cls(
            name=data.get("name", "Unknown"),
            path=data.get("path"),
            bounds=data.get("bounds"),
        )


# ==================== AutoCAD 状态信息 ====================

@dataclass
class AutoCADStatus:
    """AutoCAD 运行状态"""
    running: bool = False
    version: str = ""
    documents: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "running": self.running,
            "version": self.version,
            "documents": self.documents,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AutoCADStatus":
        return cls(
            running=data.get("running", False),
            version=data.get("version", ""),
            documents=data.get("documents", []),
        )


# ==================== AutoCAD 快照 ====================

@dataclass
class AutoCADSnapshot:
    """
    AutoCAD 图纸快照
    
    实现 BaseSnapshot Protocol。
    """
    status: AutoCADStatus
    document_info: Optional[DocumentInfo] = None
    content: Optional[DrawingContent] = None
    _screenshot: Optional[str] = None

    @property
    def screenshot(self) -> Optional[str]:
        """base64 编码的截图"""
        return self._screenshot

    @property
    def has_data(self) -> bool:
        """是否有有效数据（AutoCAD 正在运行即视为有数据）"""
        return self.status.running

    @property
    def file_path(self) -> Optional[str]:
        """获取文件路径"""
        if self.document_info:
            return self.document_info.path or self.document_info.name
        return None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status.to_dict(),
            "document_info": self.document_info.to_dict() if self.document_info else None,
            "content": self.content.to_dict() if self.content else None,
            "screenshot": self._screenshot,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AutoCADSnapshot":
        """从字典创建 AutoCADSnapshot"""
        # 解析 status
        status_data = data.get("status", data.get("data", {}))
        if "running" in status_data:
            status = AutoCADStatus.from_dict(status_data)
        elif "running" in data:
            # 直接在顶层数据中查找 running 字段
            status = AutoCADStatus(
                running=data.get("running", False),
                version=data.get("version", ""),
                documents=data.get("documents", []),
            )
        else:
            # 无法确定状态时，默认为未运行（比默认运行更安全）
            # 这样 AI 会尝试启动 AutoCAD 而不是错误地认为已经在运行
            status = AutoCADStatus(running=False)
        
        # 解析 document_info
        document_info = None
        doc_data = data.get("document_info") or data.get("data", {}).get("document_info")
        if doc_data:
            document_info = DocumentInfo.from_dict(doc_data)
        
        # 解析 content
        content = None
        content_data = data.get("content") or data.get("data", {}).get("content")
        if content_data:
            content = DrawingContent.from_dict(content_data)
        
        screenshot = data.get("screenshot") or data.get("data", {}).get("screenshot")
        
        return cls(
            status=status,
            document_info=document_info,
            content=content,
            _screenshot=screenshot,
        )

    @classmethod
    def empty(cls) -> "AutoCADSnapshot":
        """创建空的图纸快照"""
        return cls(
            status=AutoCADStatus(running=False),
        )

    def to_context_format(self, max_items: int = 50, max_text_length: int = 100) -> str:
        """
        转换为 LLM 可用的文本格式
        
        Args:
            max_items: 最大图元数量
            max_text_length: 文本最大长度
        
        Returns:
            格式化的文本描述
        """
        result_parts = []
        
        # 1. AutoCAD 状态
        result_parts.append("# AutoCAD Status")
        result_parts.append(toon_encode(self.status.to_dict()))
        result_parts.append("")
        
        # 2. 文档信息
        if self.document_info:
            result_parts.append("# Document Information")
            result_parts.append(toon_encode(self.document_info.to_dict()))
            result_parts.append("")
        elif self.status.running:
            result_parts.append("# Document Information")
            result_parts.append("AutoCAD is running but no document is currently open.")
            if self.status.documents:
                result_parts.append(f"Available documents: {len(self.status.documents)}")
            else:
                result_parts.append("You may need to open or create a new drawing file.")
            result_parts.append("")
        
        # 3. 图纸内容
        if self.content:
            result_parts.append("# Drawing Content")
            
            # 图层颜色
            if self.content.layer_colors:
                result_parts.append("## Layers")
                result_parts.append(toon_encode(self.content.layer_colors))
                result_parts.append("")
            
            # 内容摘要
            summary = self.content.summary or {
                "lines": len(self.content.lines),
                "circles": len(self.content.circles),
                "arcs": len(self.content.arcs),
                "polylines": len(self.content.polylines),
                "texts": len(self.content.texts),
                "dimensions": len(self.content.dimensions),
            }
            result_parts.append("## Summary")
            result_parts.append(toon_encode(summary))
            result_parts.append("")
            
            # 详细图元（限制数量）
            total_elements = sum(summary.values())
            if total_elements > 0 and total_elements <= max_items:
                result_parts.append("## Elements Detail")
                
                if self.content.lines:
                    result_parts.append(f"### Lines ({len(self.content.lines)})")
                    for i, line in enumerate(self.content.lines[:max_items]):
                        result_parts.append(f"  {i+1}. {line.start} -> {line.end} (layer: {line.layer})")
                
                if self.content.circles:
                    result_parts.append(f"### Circles ({len(self.content.circles)})")
                    for i, circle in enumerate(self.content.circles[:max_items]):
                        result_parts.append(f"  {i+1}. center={circle.center}, r={circle.radius} (layer: {circle.layer})")
                
                if self.content.arcs:
                    result_parts.append(f"### Arcs ({len(self.content.arcs)})")
                    for i, arc in enumerate(self.content.arcs[:max_items]):
                        result_parts.append(f"  {i+1}. center={arc.center}, r={arc.radius}, {arc.start_angle}°-{arc.end_angle}° (layer: {arc.layer})")
                
                if self.content.polylines:
                    result_parts.append(f"### Polylines ({len(self.content.polylines)})")
                    for i, pline in enumerate(self.content.polylines[:max_items]):
                        closed_str = "closed" if pline.closed else "open"
                        result_parts.append(f"  {i+1}. {len(pline.vertices)} vertices, {closed_str} (layer: {pline.layer})")
                
                if self.content.texts:
                    result_parts.append(f"### Texts ({len(self.content.texts)})")
                    for i, text in enumerate(self.content.texts[:max_items]):
                        text_content = text.text[:max_text_length] + "..." if len(text.text) > max_text_length else text.text
                        result_parts.append(f"  {i+1}. \"{text_content}\" at {text.position} (layer: {text.layer})")
                
                if self.content.dimensions:
                    result_parts.append(f"### Dimensions ({len(self.content.dimensions)})")
                    for i, dim in enumerate(self.content.dimensions[:max_items]):
                        result_parts.append(f"  {i+1}. {dim.dim_type} (layer: {dim.layer})")
                
                result_parts.append("")
            elif total_elements > max_items:
                result_parts.append(f"(Drawing contains {total_elements} elements, showing summary only)")
                result_parts.append("")
        else:
            result_parts.append("# Drawing Content")
            result_parts.append("No drawing content available. The drawing may be empty or not loaded.")
            result_parts.append("")
        
        return "\n".join(result_parts)


# ==================== 辅助函数 ====================

def autocad_snapshot_from_dict(data: Dict[str, Any]) -> AutoCADSnapshot:
    """将字典转换为 AutoCADSnapshot"""
    return AutoCADSnapshot.from_dict(data)
