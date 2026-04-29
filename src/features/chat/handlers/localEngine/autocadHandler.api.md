# AutoCAD Handler API 文档

## 概述

AutoCAD Handler 处理与 AutoCAD V2 API 的交互。AI 通过发送 `tool_call` 事件来控制 AutoCAD。

**API 前缀**: `/api/v1/autocad/v2`

## Tool Call 格式

```json
{
  "type": "tool_call",
  "id": "call_xxx",
  "target": "autocad",
  "name": "<action_name>",
  "args": { ... }
}
```

---

## 动作列表

### 1. 获取状态 - `status`

获取 AutoCAD 运行状态和当前文档信息。

```json
{
  "type": "tool_call",
  "id": "call_001",
  "target": "autocad",
  "name": "status",
  "args": {}
}
```

**返回示例**:
```json
{
  "success": true,
  "data": {
    "running": true,
    "version": "AutoCAD 2024",
    "documents": [
      { "name": "Drawing1.dwg", "path": "C:\\Projects\\Drawing1.dwg", "active": true }
    ]
  }
}
```

---

### 2. 获取快照 - `snapshot`

获取当前图纸的内容和截图。

```json
{
  "type": "tool_call",
  "id": "call_002",
  "target": "autocad",
  "name": "snapshot",
  "args": {
    "include_content": true,
    "include_screenshot": true,
    "only_visible": false,
    "max_entities": 1000
  }
}
```

**参数说明**:
| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `include_content` | boolean | true | 是否包含图纸内容（图元数据） |
| `include_screenshot` | boolean | true | 是否包含截图 base64 |
| `only_visible` | boolean | false | 是否只提取可见区域 |
| `max_entities` | number | null | 最大实体数量限制 |

**返回示例**:
```json
{
  "success": true,
  "data": {
    "document_info": {
      "name": "Drawing1.dwg",
      "path": "C:\\Projects\\Drawing1.dwg",
      "bounds": { "min": [0, 0], "max": [1000, 800] }
    },
    "content": {
      "layer_colors": { "0": 7, "轮廓": 1, "标注": 3 },
      "elements": {
        "lines": [
          { "start": [0, 0, 0], "end": [100, 0, 0], "layer": "轮廓", "color": 256 }
        ],
        "circles": [],
        "arcs": [],
        "polylines": [],
        "texts": [],
        "dimensions": []
      },
      "summary": { "lines": 1, "circles": 0, "arcs": 0, "polylines": 0, "texts": 0, "dimensions": 0 }
    },
    "screenshot": "data:image/png;base64,iVBORw0KGgo..."
  }
}
```

---

### 3. 绘制 JSON 数据 - `draw_from_json`

使用 JSON 结构化数据绘制图形。这是最常用的绘图方式。

#### 3.1 绘制直线

```json
{
  "type": "tool_call",
  "id": "call_003",
  "target": "autocad",
  "name": "draw_from_json",
  "args": {
    "data": {
      "layer_colors": { "轮廓": 7 },
      "elements": {
        "lines": [
          { "start": [0, 0, 0], "end": [100, 0, 0], "layer": "轮廓" },
          { "start": [100, 0, 0], "end": [100, 50, 0], "layer": "轮廓" },
          { "start": [100, 50, 0], "end": [0, 50, 0], "layer": "轮廓" },
          { "start": [0, 50, 0], "end": [0, 0, 0], "layer": "轮廓" }
        ]
      }
    },
    "timeout": 60,
    "return_screenshot": true
  }
}
```

#### 3.2 绘制圆和圆弧

```json
{
  "type": "tool_call",
  "id": "call_004",
  "target": "autocad",
  "name": "draw_from_json",
  "args": {
    "data": {
      "layer_colors": { "圆": 1, "弧": 3 },
      "elements": {
        "circles": [
          { "center": [50, 50, 0], "radius": 25, "layer": "圆" },
          { "center": [150, 50, 0], "radius": 10, "layer": "圆", "color": 5 }
        ],
        "arcs": [
          { "center": [100, 100, 0], "radius": 30, "start_angle": 0, "end_angle": 90, "layer": "弧" },
          { "center": [200, 100, 0], "radius": 20, "start_angle": 45, "end_angle": 270, "layer": "弧" }
        ]
      }
    }
  }
}
```

#### 3.3 绘制多段线

```json
{
  "type": "tool_call",
  "id": "call_005",
  "target": "autocad",
  "name": "draw_from_json",
  "args": {
    "data": {
      "layer_colors": { "多段线": 4 },
      "elements": {
        "polylines": [
          {
            "vertices": [[0, 0], [50, 0], [50, 30], [25, 50], [0, 30]],
            "closed": true,
            "layer": "多段线"
          },
          {
            "vertices": [[100, 0], [150, 20], [200, 0], [250, 20]],
            "closed": false,
            "layer": "多段线"
          }
        ]
      }
    }
  }
}
```

#### 3.4 绘制文字

```json
{
  "type": "tool_call",
  "id": "call_006",
  "target": "autocad",
  "name": "draw_from_json",
  "args": {
    "data": {
      "layer_colors": { "文字": 7 },
      "elements": {
        "texts": [
          { "text": "标题", "position": [50, 100, 0], "height": 10, "layer": "文字" },
          { "text": "说明文字", "position": [50, 80, 0], "height": 5, "layer": "文字" },
          { "text": "尺寸: 100x50", "position": [0, -10, 0], "height": 3, "layer": "文字", "color": 3 }
        ]
      }
    }
  }
}
```

#### 3.5 绘制标注

```json
{
  "type": "tool_call",
  "id": "call_007",
  "target": "autocad",
  "name": "draw_from_json",
  "args": {
    "data": {
      "layer_colors": { "标注": 3 },
      "elements": {
        "dimensions": [
          {
            "type": "Aligned",
            "point1": [0, 0, 0],
            "point2": [100, 0, 0],
            "text_position": [50, -15, 0],
            "layer": "标注"
          },
          {
            "type": "Rotated",
            "point1": [0, 0, 0],
            "point2": [0, 50, 0],
            "text_position": [-15, 25, 0],
            "rotation": 90,
            "layer": "标注"
          },
          {
            "type": "Radial",
            "center": [50, 50, 0],
            "chord_point": [75, 50, 0],
            "layer": "标注"
          }
        ]
      }
    }
  }
}
```

#### 3.6 综合示例：绘制一个带标注的矩形

```json
{
  "type": "tool_call",
  "id": "call_008",
  "target": "autocad",
  "name": "draw_from_json",
  "args": {
    "data": {
      "layer_colors": {
        "轮廓": 7,
        "标注": 3,
        "文字": 1
      },
      "elements": {
        "lines": [
          { "start": [0, 0, 0], "end": [200, 0, 0], "layer": "轮廓" },
          { "start": [200, 0, 0], "end": [200, 100, 0], "layer": "轮廓" },
          { "start": [200, 100, 0], "end": [0, 100, 0], "layer": "轮廓" },
          { "start": [0, 100, 0], "end": [0, 0, 0], "layer": "轮廓" }
        ],
        "dimensions": [
          {
            "type": "Aligned",
            "point1": [0, 0, 0],
            "point2": [200, 0, 0],
            "text_position": [100, -20, 0],
            "layer": "标注"
          },
          {
            "type": "Aligned",
            "point1": [200, 0, 0],
            "point2": [200, 100, 0],
            "text_position": [220, 50, 0],
            "layer": "标注"
          }
        ],
        "texts": [
          { "text": "矩形示例", "position": [100, 110, 0], "height": 8, "layer": "文字" }
        ]
      }
    },
    "timeout": 60,
    "return_screenshot": true
  }
}
```

---

### 4. 执行 Python COM 代码 - `execute_python_com`

直接执行 Python COM 代码，适用于复杂操作或 `draw_from_json` 不支持的功能。

**预置变量**:
- `acad`: AutoCAD Application 对象
- `doc`: 当前 Document 对象
- `ms`: ModelSpace 对象
- `vtPoint(x, y, z)`: 创建 COM 点坐标的辅助函数

#### 4.1 绘制简单图形

```json
{
  "type": "tool_call",
  "id": "call_009",
  "target": "autocad",
  "name": "execute_python_com",
  "args": {
    "code": "line = ms.AddLine(vtPoint(0, 0, 0), vtPoint(100, 100, 0))\nline.Color = 1",
    "timeout": 60,
    "return_screenshot": true
  }
}
```

#### 4.2 执行 AutoCAD 命令

```json
{
  "type": "tool_call",
  "id": "call_010",
  "target": "autocad",
  "name": "execute_python_com",
  "args": {
    "code": "doc.SendCommand('ZOOM E\\n')",
    "timeout": 30
  }
}
```

#### 4.3 缩放到范围

```json
{
  "type": "tool_call",
  "id": "call_011",
  "target": "autocad",
  "name": "execute_python_com",
  "args": {
    "code": "doc.SendCommand('ZOOM E\\n')",
    "timeout": 30,
    "return_screenshot": true
  }
}
```

#### 4.4 创建图层

```json
{
  "type": "tool_call",
  "id": "call_012",
  "target": "autocad",
  "name": "execute_python_com",
  "args": {
    "code": "layer = doc.Layers.Add('新图层')\nlayer.Color = 5\nlayer.Linetype = 'DASHED'",
    "timeout": 30
  }
}
```

#### 4.5 绘制填充

```json
{
  "type": "tool_call",
  "id": "call_013",
  "target": "autocad",
  "name": "execute_python_com",
  "args": {
    "code": "import win32com.client\nimport array\n\n# 创建边界多段线\npts = [0, 0, 0, 100, 0, 0, 100, 100, 0, 0, 100, 0]\npts_array = array.array('d', pts)\npline = ms.AddLightWeightPolyline(pts_array)\npline.Closed = True\n\n# 创建填充\nouter_loop = [pline]\nhatch = ms.AddHatch(0, 'ANSI31', True)\nhatch.AppendOuterLoop(outer_loop)\nhatch.Evaluate()",
    "timeout": 60,
    "return_screenshot": true
  }
}
```

#### 4.6 修改现有实体

```json
{
  "type": "tool_call",
  "id": "call_014",
  "target": "autocad",
  "name": "execute_python_com",
  "args": {
    "code": "# 遍历所有实体，将红色实体改为蓝色\nfor entity in ms:\n    if entity.Color == 1:  # 红色\n        entity.Color = 5  # 蓝色",
    "timeout": 60,
    "return_screenshot": true
  }
}
```

#### 4.7 删除所有实体

```json
{
  "type": "tool_call",
  "id": "call_015",
  "target": "autocad",
  "name": "execute_python_com",
  "args": {
    "code": "for entity in list(ms):\n    entity.Delete()",
    "timeout": 60,
    "return_screenshot": true
  }
}
```

---

### 5. 图纸管理

#### 5.1 打开图纸 - `open`

```json
{
  "type": "tool_call",
  "id": "call_016",
  "target": "autocad",
  "name": "open",
  "args": {
    "file_path": "C:\\Projects\\example.dwg",
    "read_only": false
  }
}
```

#### 5.2 关闭图纸 - `close`

```json
{
  "type": "tool_call",
  "id": "call_017",
  "target": "autocad",
  "name": "close",
  "args": {
    "save": true
  }
}
```

#### 5.3 新建图纸 - `new`

```json
{
  "type": "tool_call",
  "id": "call_018",
  "target": "autocad",
  "name": "new",
  "args": {}
}
```

使用模板新建：

```json
{
  "type": "tool_call",
  "id": "call_019",
  "target": "autocad",
  "name": "new",
  "args": {
    "template": "C:\\Templates\\A3.dwt"
  }
}
```

#### 5.4 切换活动图纸 - `activate`

按名称切换：

```json
{
  "type": "tool_call",
  "id": "call_020",
  "target": "autocad",
  "name": "activate",
  "args": {
    "name": "Drawing2.dwg"
  }
}
```

按索引切换：

```json
{
  "type": "tool_call",
  "id": "call_021",
  "target": "autocad",
  "name": "activate",
  "args": {
    "index": 1
  }
}
```

---

### 6. 标准件操作

#### 6.1 列出所有标准件 - `list_standard_parts`

```json
{
  "type": "tool_call",
  "id": "call_022",
  "target": "autocad",
  "name": "list_standard_parts",
  "args": {}
}
```

**返回示例**:
```json
{
  "success": true,
  "data": {
    "parts": [
      {
        "type": "flange",
        "name": "法兰",
        "parameters": ["dn", "pn"],
        "presets": ["DN50", "DN100", "DN150"]
      },
      {
        "type": "valve",
        "name": "阀门",
        "parameters": ["dn", "type"],
        "presets": ["DN50-球阀", "DN100-闸阀"]
      }
    ]
  }
}
```

#### 6.2 获取标准件预设 - `get_standard_part_presets`

```json
{
  "type": "tool_call",
  "id": "call_023",
  "target": "autocad",
  "name": "get_standard_part_presets",
  "args": {
    "part_type": "flange"
  }
}
```

**返回示例**:
```json
{
  "success": true,
  "data": {
    "presets": [
      { "name": "DN50", "dn": 50, "pn": 10, "d": 165, "k": 125 },
      { "name": "DN100", "dn": 100, "pn": 10, "d": 220, "k": 180 },
      { "name": "DN150", "dn": 150, "pn": 10, "d": 285, "k": 240 }
    ]
  }
}
```

#### 6.3 绘制标准件 - `draw_standard_part`

使用预设：

```json
{
  "type": "tool_call",
  "id": "call_024",
  "target": "autocad",
  "name": "draw_standard_part",
  "args": {
    "part_type": "flange",
    "preset": "DN100",
    "position": [100, 100]
  }
}
```

使用自定义参数：

```json
{
  "type": "tool_call",
  "id": "call_025",
  "target": "autocad",
  "name": "draw_standard_part",
  "args": {
    "part_type": "flange",
    "parameters": {
      "dn": 80,
      "pn": 16,
      "d": 200,
      "k": 160
    },
    "position": [200, 100]
  }
}
```

---

### 7. 停止任务 - `stop`

```json
{
  "type": "tool_call",
  "id": "call_026",
  "target": "autocad",
  "name": "stop",
  "args": {}
}
```

---

## 常用工作流示例

### 工作流 1：查看当前图纸状态并截图

```json
// Step 1: 获取状态
{
  "type": "tool_call",
  "id": "call_wf1_1",
  "target": "autocad",
  "name": "status",
  "args": {}
}

// Step 2: 获取快照
{
  "type": "tool_call",
  "id": "call_wf1_2",
  "target": "autocad",
  "name": "snapshot",
  "args": {
    "include_content": true,
    "include_screenshot": true
  }
}
```

### 工作流 2：新建图纸并绘制内容

```json
// Step 1: 新建图纸
{
  "type": "tool_call",
  "id": "call_wf2_1",
  "target": "autocad",
  "name": "new",
  "args": {}
}

// Step 2: 绘制内容
{
  "type": "tool_call",
  "id": "call_wf2_2",
  "target": "autocad",
  "name": "draw_from_json",
  "args": {
    "data": {
      "layer_colors": { "轮廓": 7, "中心线": 1 },
      "elements": {
        "lines": [
          { "start": [0, 0, 0], "end": [100, 0, 0], "layer": "轮廓" },
          { "start": [100, 0, 0], "end": [100, 50, 0], "layer": "轮廓" },
          { "start": [100, 50, 0], "end": [0, 50, 0], "layer": "轮廓" },
          { "start": [0, 50, 0], "end": [0, 0, 0], "layer": "轮廓" }
        ],
        "circles": [
          { "center": [50, 25, 0], "radius": 10, "layer": "轮廓" }
        ]
      }
    },
    "return_screenshot": true
  }
}

// Step 3: 缩放到范围
{
  "type": "tool_call",
  "id": "call_wf2_3",
  "target": "autocad",
  "name": "execute_python_com",
  "args": {
    "code": "doc.SendCommand('ZOOM E\\n')",
    "return_screenshot": true
  }
}
```

### 工作流 3：打开现有图纸并修改

```json
// Step 1: 打开图纸
{
  "type": "tool_call",
  "id": "call_wf3_1",
  "target": "autocad",
  "name": "open",
  "args": {
    "file_path": "C:\\Projects\\existing.dwg"
  }
}

// Step 2: 获取当前内容
{
  "type": "tool_call",
  "id": "call_wf3_2",
  "target": "autocad",
  "name": "snapshot",
  "args": {
    "include_content": true,
    "include_screenshot": true
  }
}

// Step 3: 添加新内容
{
  "type": "tool_call",
  "id": "call_wf3_3",
  "target": "autocad",
  "name": "draw_from_json",
  "args": {
    "data": {
      "elements": {
        "texts": [
          { "text": "修改日期: 2024-01-15", "position": [0, -20, 0], "height": 5 }
        ]
      }
    },
    "return_screenshot": true
  }
}

// Step 4: 保存并关闭
{
  "type": "tool_call",
  "id": "call_wf3_4",
  "target": "autocad",
  "name": "close",
  "args": {
    "save": true
  }
}
```

---

## 元素类型参考

### lines (直线)

```typescript
{
  start: [x, y, z],      // 起点坐标
  end: [x, y, z],        // 终点坐标
  layer?: string,        // 图层名（可选）
  color?: number         // 颜色索引（可选，256=ByLayer）
}
```

### circles (圆)

```typescript
{
  center: [x, y, z],     // 圆心坐标
  radius: number,        // 半径
  layer?: string,
  color?: number
}
```

### arcs (圆弧)

```typescript
{
  center: [x, y, z],     // 圆心坐标
  radius: number,        // 半径
  start_angle: number,   // 起始角度（度）
  end_angle: number,     // 结束角度（度）
  layer?: string,
  color?: number
}
```

### polylines (多段线)

```typescript
{
  vertices: [[x, y], ...],  // 顶点坐标数组
  closed?: boolean,         // 是否闭合（默认 false）
  layer?: string,
  color?: number
}
```

### texts (文字)

```typescript
{
  text: string,          // 文字内容
  position: [x, y, z],   // 插入点坐标
  height?: number,       // 文字高度（默认 2.5）
  layer?: string,
  color?: number
}
```

### dimensions (标注)

```typescript
// Aligned 对齐标注
{
  type: "Aligned",
  point1: [x, y, z],
  point2: [x, y, z],
  text_position: [x, y, z],
  layer?: string
}

// Rotated 旋转标注
{
  type: "Rotated",
  point1: [x, y, z],
  point2: [x, y, z],
  text_position: [x, y, z],
  rotation: number,      // 旋转角度（度）
  layer?: string
}

// Radial 半径标注
{
  type: "Radial",
  center: [x, y, z],
  chord_point: [x, y, z],
  layer?: string
}

// Angular 角度标注
{
  type: "Angular",
  center: [x, y, z],
  point1: [x, y, z],
  point2: [x, y, z],
  text_position: [x, y, z],
  layer?: string
}
```

---

## 颜色索引参考

| 索引 | 颜色 |
|------|------|
| 1 | 红色 |
| 2 | 黄色 |
| 3 | 绿色 |
| 4 | 青色 |
| 5 | 蓝色 |
| 6 | 洋红 |
| 7 | 白色/黑色 |
| 256 | ByLayer（跟随图层） |
| 0 | ByBlock（跟随块） |

---

## 常用 AutoCAD 命令（用于 execute_python_com）

```python
# 缩放到范围
doc.SendCommand('ZOOM E\n')

# 缩放到全部
doc.SendCommand('ZOOM A\n')

# 重生成
doc.SendCommand('REGEN\n')

# 保存
doc.SendCommand('QSAVE\n')

# 撤销
doc.SendCommand('U\n')

# 删除所有
doc.SendCommand('ERASE ALL\n\n')
```

> **注意**: 命令末尾必须加 `\n` 表示回车确认。
