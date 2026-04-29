# Execute Script 调试增强

## 问题描述

用户报告 execute_script 没有任何响应，可能的原因：
1. 命令传输后没有正确解析/执行
2. 运行后出现报错，但没有返回

## 改进内容

### 1. 增强 step() 方法日志

**位置**: `controller.py:190-230`

**改进**：
- 记录执行模式（execute_code / execute_script）
- 记录所有输入参数（skill_id, script_path, parameters, language, timeout）
- 记录脚本路径解析过程
- 记录参数构建过程
- 记录执行结果

**示例日志**：
```
[ExcelController] step() Mode 2: execute_script
  - skill_id: 66666666
  - script_path: scripts/create_column_chart.ps1
  - parameters: {'DataRange': 'A1:C6', 'ChartTitle': 'Monthly Sales and Profit', ...}
  - language: PowerShell
  - timeout: 120
[ExcelController] Script resolved to: D:\develop\Useit-New\AI_Run\SKILLS\skill-66666666\scripts\create_column_chart.ps1
[ExcelController] PowerShell params built: ['-DataRange', 'A1:C6', '-ChartTitle', ...]
[ExcelController] About to execute script...
[ExcelController] Script execution completed, success=True
```

### 2. 增强 _get_skill_script_path() 日志

**位置**: `controller.py:1052-1090`

**改进**：
- 记录 skills_base_dir
- 记录 skill_dir 计算结果
- 检查 skill_dir 是否存在
- 检查 script_full_path 是否存在
- **如果脚本不存在，列出目录中的可用文件**（方便排查路径问题）

**示例日志（成功）**：
```
[ExcelController] Resolving script path...
  skills_base_dir: D:\develop\Useit-New\AI_Run\SKILLS
  skill_id: 66666666
  script_path: scripts/create_column_chart.ps1
  skill_dir: D:\develop\Useit-New\AI_Run\SKILLS\skill-66666666
[ExcelController] ✓ Skill directory exists
  script_full_path: D:\develop\Useit-New\AI_Run\SKILLS\skill-66666666\scripts\create_column_chart.ps1
[ExcelController] ✓ Script file exists: ...
```

**示例日志（失败）**：
```
[ExcelController] Resolving script path...
  skills_base_dir: D:\develop\Useit-New\AI_Run\SKILLS
  skill_id: 66666666
  script_path: scripts/create_column_chart.ps1
  skill_dir: D:\develop\Useit-New\AI_Run\SKILLS\skill-66666666
[ExcelController] ✓ Skill directory exists
  script_full_path: D:\develop\Useit-New\AI_Run\SKILLS\skill-66666666\scripts\create_column_chart.ps1
[ExcelController] Script not found: ...
[ExcelController] Available files in skill directory:
  - SKILL.md
  - scripts/chart_examples.py
  - scripts/create_line_chart.ps1
  - scripts/create_pie_chart.ps1
```

### 3. 增强 _build_powershell_params() 日志

**位置**: `controller.py:1115-1145`

**改进**：
- 记录输入的 parameters 字典
- 记录构建后的参数列表
- 记录完整的命令行参数字符串

**示例日志**：
```
[ExcelController] Building PowerShell params from: {'DataRange': 'A1:C6', 'ChartTitle': 'Monthly Sales and Profit', 'ChartLeft': 200, 'ChartTop': 50, 'ChartWidth': 480, 'ChartHeight': 320}
[ExcelController] PowerShell params built: ['-DataRange', 'A1:C6', '-ChartTitle', '"Monthly Sales and Profit"', '-ChartLeft', '200', '-ChartTop', '50', '-ChartWidth', '480', '-ChartHeight', '320']
[ExcelController] Command line args: -DataRange A1:C6 -ChartTitle "Monthly Sales and Profit" -ChartLeft 200 -ChartTop 50 -ChartWidth 480 -ChartHeight 320
```

### 4. 增强 _execute_script_file() 日志

**位置**: `controller.py:1180-1220`

**改进**：
- 记录脚本路径
- 记录完整命令
- 记录 timeout
- **记录返回码**
- **记录 stdout 和 stderr 的长度和内容**
- **区分成功和失败的日志级别**（成功用 INFO，失败用 ERROR）

**示例日志（成功）**：
```
[ExcelController] Executing script...
  Script path: D:\develop\Useit-New\AI_Run\SKILLS\skill-66666666\scripts\create_column_chart.ps1
  Command: powershell -ExecutionPolicy Bypass -File D:\develop\Useit-New\AI_Run\SKILLS\skill-66666666\scripts\create_column_chart.ps1 -DataRange A1:C6 -ChartTitle "Monthly Sales and Profit" -ChartLeft 200 -ChartTop 50 -ChartWidth 480 -ChartHeight 320
  Timeout: 120s
[ExcelController] Script execution completed:
  Return code: 0
  Stdout length: 45 chars
  Stderr length: 0 chars
[ExcelController] ✓ Script execution successful
[ExcelController] Stdout: Chart created successfully at A1:C6
```

**示例日志（失败）**：
```
[ExcelController] Executing script...
  Script path: D:\develop\Useit-New\AI_Run\SKILLS\skill-66666666\scripts\create_column_chart.ps1
  Command: powershell -ExecutionPolicy Bypass -File ...
  Timeout: 120s
[ExcelController] Script execution completed:
  Return code: 1
  Stdout length: 0 chars
  Stderr length: 234 chars
[ExcelController] ✗ Script execution failed (return code: 1)
[ExcelController] Stderr: At line:15 char:5
+ $chart = $sheet.ChartObjects().Add($ChartLeft, $ChartTop, $ChartWidth, $ChartHeight)
+     ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
You cannot call a method on a null-valued expression.
```

### 5. 增强快照获取错误处理

**位置**: `controller.py:255-275`

**改进**：
- 即使快照获取失败，也返回执行结果
- 记录快照获取成功/失败
- 在返回前记录整体结果

**示例日志**：
```
[ExcelController] Execution completed, getting snapshot...
[ExcelController] ✓ Snapshot retrieved successfully
[ExcelController] step() completed: execution_success=True, has_snapshot=True
```

---

## 调试流程

### Step 1: 查看 Local Engine 日志

```bash
# 查找 Local Engine 日志（通常在 engineering_agent/local_engine/ 下）
grep -r "execute_script" engineering_agent/local_engine/logs/*.log

# 或者查找 ExcelController 相关日志
grep "ExcelController" engineering_agent/local_engine/logs/*.log | grep "step()"
```

### Step 2: 检查参数传递

查找日志中的：
```
[ExcelController] step() Mode 2: execute_script
  - skill_id: ...
  - script_path: ...
  - parameters: ...
```

**检查项**：
- skill_id 是否正确（应该是 "66666666" 或自动填充）
- script_path 是否正确（应该是 "scripts/create_column_chart.ps1"）
- parameters 是否包含所有必需参数

### Step 3: 检查路径解析

查找日志中的：
```
[ExcelController] Resolving script path...
  skills_base_dir: ...
  skill_dir: ...
  script_full_path: ...
```

**检查项**：
- skills_base_dir 是否指向正确的 SKILLS 目录
- skill_dir 是否存在
- script_full_path 是否正确

**如果脚本不存在**：
- 查看日志中的 "Available files in skill directory" 列表
- 确认脚本文件名是否匹配（大小写、扩展名）

### Step 4: 检查参数构建

查找日志中的：
```
[ExcelController] Building PowerShell params from: ...
[ExcelController] PowerShell params built: ...
```

**检查项**：
- 参数类型转换是否正确（bool → $true/$false, string → "...", number → 直接）
- 参数顺序是否正确
- 特殊字符是否正确转义

### Step 5: 检查脚本执行

查找日志中的：
```
[ExcelController] Executing script...
  Command: ...
[ExcelController] Script execution completed:
  Return code: ...
  Stdout: ...
  Stderr: ...
```

**检查项**：
- 完整命令是否正确
- 返回码是否为 0（成功）
- 如果失败，查看 Stderr 中的错误信息

### Step 6: 检查快照获取

查找日志中的：
```
[ExcelController] Execution completed, getting snapshot...
[ExcelController] ✓ Snapshot retrieved successfully
```

**检查项**：
- 快照是否成功获取
- 如果失败，查看错误信息

---

## 常见问题排查

### 问题 1: 脚本路径找不到

**日志特征**：
```
[ExcelController] Script not found: ...
[ExcelController] Available files in skill directory:
  - ...
```

**解决方法**：
1. 检查 script_path 是否正确（大小写、路径分隔符）
2. 检查脚本文件是否存在于 SKILLS/skill-66666666/ 目录下
3. 对比 AI 提供的路径和实际文件名

### 问题 2: 参数传递错误

**日志特征**：
```
[ExcelController] PowerShell params built: ['-DataRange', '...', ...]
[ExcelController] Stderr: Parameter 'DataRange' not recognized
```

**解决方法**：
1. 检查脚本是否定义了对应的参数
2. 检查参数名大小写是否匹配
3. 检查参数类型是否正确

### 问题 3: 脚本执行失败

**日志特征**：
```
[ExcelController] ✗ Script execution failed (return code: 1)
[ExcelController] Stderr: ...
```

**解决方法**：
1. 查看 Stderr 中的完整错误信息
2. 手动运行脚本测试（复制日志中的完整命令）
3. 检查 Excel 是否打开、工作簿是否存在
4. 检查脚本语法是否正确

### 问题 4: 超时

**日志特征**：
```
[ExcelController] Script execution timeout after 120s
```

**解决方法**：
1. 增加 timeout 参数
2. 检查脚本是否有死循环或等待用户输入
3. 检查 Excel 是否响应（可能被其他进程锁定）

### 问题 5: 没有任何日志

**可能原因**：
1. Local Engine 没有启动
2. 请求没有到达 controller
3. API 端点路由错误

**解决方法**：
1. 检查 Local Engine 是否运行
2. 检查 AI_Run Handler 的日志，确认 tool_call 是否发送
3. 检查 API 端点是否正确（/api/v1/excel/step）

---

## 测试建议

### 手动测试脚本

复制日志中的完整命令，手动运行：

```powershell
# 从日志复制命令
powershell -ExecutionPolicy Bypass -File "D:\develop\Useit-New\AI_Run\SKILLS\skill-66666666\scripts\create_column_chart.ps1" -DataRange "A1:C6" -ChartTitle "Monthly Sales and Profit" -ChartLeft 200 -ChartTop 50 -ChartWidth 480 -ChartHeight 320
```

观察：
- 是否有输出
- 是否有错误
- Excel 中是否创建了图表

### 测试简化版脚本

创建一个简单的测试脚本：

```powershell
# test_script.ps1
param(
    [string]$TestParam = "default"
)

Write-Host "Test script executed successfully!"
Write-Host "TestParam: $TestParam"
```

通过 API 测试：

```bash
curl -X POST http://localhost:8000/api/v1/excel/step \
  -H "Content-Type: application/json" \
  -d '{
    "script_path": "scripts/test_script.ps1",
    "parameters": {"TestParam": "hello"}
  }'
```

---

## 总结

增强后的日志系统提供：
- ✅ **完整的执行轨迹**：从参数接收到结果返回
- ✅ **详细的错误信息**：包括 stdout、stderr、return code
- ✅ **调试辅助**：列出可用文件、显示完整命令
- ✅ **清晰的日志级别**：INFO（成功）、ERROR（失败）

这些改进使得调试 execute_script 问题变得简单直接。
