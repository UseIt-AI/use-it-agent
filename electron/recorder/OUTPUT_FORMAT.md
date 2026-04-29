# Recorder 输出格式定义

## 输出目录结构

```
~/Downloads/record_save/
├── Recording-HH-MM-SS.mkv          # 屏幕录制视频（内嵌加密 SRT）
├── action_trace_YYYYMMDD_HHMMSS.txt  # 明文操作日志（调试用）
└── input_log_YYYYMMDD_HHMMSS.srt     # 加密事件日志（临时，最终嵌入 MKV）
```

---

## 事件类型定义

### 1. 窗口切换事件 `WINDOW_SWITCH`

当用户焦点切换到不同窗口时记录。

**触发时机**：在用户输入事件（键盘/鼠标）触发时检测，如果当前活动窗口与上次不同则记录。

**明文格式** (`action_trace_*.txt`):
```
HH:MM:SS.mmm	WINDOW_SWITCH from="processName:windowTitle" to="processName:windowTitle"
```

**加密 JSON 结构**:
```json
{
  "timestamp": "HH:MM:SS.mmm",
  "type": "WINDOW_SWITCH",
  "from": {
    "title": "窗口标题",
    "process": "进程名.exe"
  },
  "to": {
    "title": "窗口标题", 
    "process": "进程名.exe"
  }
}
```

> 注：`from` 可能为 `null`（录制开始时的首次窗口记录）

---

### 2. 键盘事件

#### KEY_DOWN
```
HH:MM:SS.mmm	KEY_DOWN {keycode}
```

#### KEY_UP
```
HH:MM:SS.mmm	KEY_UP {keycode}
```

**加密 JSON 结构**:
```json
{
  "timestamp": "HH:MM:SS.mmm",
  "message": "KEY_DOWN 65",
  "window": "当前窗口标题",
  "process": "进程名.exe"
}
```

---

### 3. 鼠标事件

#### MOUSE_DOWN / MOUSE_UP
```
HH:MM:SS.mmm	MOUSE_DOWN btn={button} x={x} y={y}
HH:MM:SS.mmm	MOUSE_UP btn={button} x={x} y={y}
```

#### DBL_CLICK（双击）
```
HH:MM:SS.mmm	DBL_CLICK btn={button} x={x} y={y}
```

#### DRAG_START / DRAG_MOVE
```
HH:MM:SS.mmm	DRAG_START x={x} y={y}
HH:MM:SS.mmm	DRAG_MOVE x={x} y={y}
```

#### WHEEL（滚轮）
```
HH:MM:SS.mmm	WHEEL rotation={rotation} x={x} y={y}
```

**加密 JSON 结构**:
```json
{
  "timestamp": "HH:MM:SS.mmm",
  "message": "MOUSE_DOWN btn=1 x=500 y=300",
  "window": "当前窗口标题",
  "process": "进程名.exe"
}
```

---

## 文件格式详情

### action_trace_*.txt（明文日志）

用于调试，包含：
- 头部元信息（开始时间、屏幕信息）
- 所有事件的时间戳和消息

```
Start Time: 2025-12-28T10:30:00.000Z
Screen Info: {"0":{"x0":0,"y0":0,"width":1920,"height":1080,"scale_factor":1}}

00:00:00.100	WINDOW_SWITCH from="null" to="chrome.exe:Google Chrome"
00:00:00.150	MOUSE_DOWN btn=1 x=500 y=300
00:00:00.200	MOUSE_UP btn=1 x=500 y=300
00:00:01.500	WINDOW_SWITCH from="chrome.exe:Google Chrome" to="Code.exe:input-listener.ts"
00:00:01.550	KEY_DOWN 65
00:00:01.600	KEY_UP 65
```

### input_log_*.srt（加密日志）

每行一个 Fernet 加密的 JSON 对象：

```
{processedKey}                    # 第1行：混淆后的加密密钥
{encrypted_screen_info}           # 第2行：加密的屏幕信息
{encrypted_metadata}              # 第3行：加密的元数据
{encrypted_event_1}               # 第4行起：加密的事件数据
{encrypted_event_2}
...
```

**密钥处理**:
- 原始密钥：32字节 urlsafe base64
- processedKey：前17字符反转 + 后续字符不变
- 解密时需要还原原始密钥

---

## 字段说明

| 字段 | 类型 | 说明 |
|------|------|------|
| `timestamp` | string | 相对于录制开始的时间，格式 `HH:MM:SS.mmm` |
| `message` | string | 事件描述（ASCII 字符） |
| `window` | string | 事件发生时的窗口标题 |
| `process` | string | 事件发生时的进程名（可选） |
| `type` | string | 事件类型（仅 WINDOW_SWITCH） |
| `from` | object | 切换前的窗口信息（仅 WINDOW_SWITCH） |
| `to` | object | 切换后的窗口信息（仅 WINDOW_SWITCH） |

---

## 性能说明

窗口切换检测采用**事件驱动 + 去重**策略：

1. **触发时机**：仅在用户输入事件（键盘/鼠标）时检查当前活动窗口
2. **节流控制**：同一窗口 50ms 内不重复检查
3. **API 调用**：使用 koffi 直接调用 Win32 API（GetForegroundWindow + GetWindowText），单次调用约 0.1-0.5ms
4. **零轮询**：不使用定时器轮询，不增加 CPU 负担

这种方式确保：
- 不影响用户正常操作
- 不会漏掉有意义的窗口切换（切换后必有输入）
- 性能开销可忽略不计



