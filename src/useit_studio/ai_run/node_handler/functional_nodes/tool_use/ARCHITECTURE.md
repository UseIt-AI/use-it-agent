# Tool Use Node 架构设计文档

## 1. 概述

Tool Use Node 是一个支持多步骤 LLM Tool Calling 的节点处理器。它允许用户通过预定义的工具（如 RAG、Web Search）来完成复杂任务，采用 **planner_only** 模式进行规划和执行。

### 1.1 核心特点

| 特性 | 说明 |
|------|------|
| **无需 Local Engine 交互** | 运行过程中不与 local engine 通信，仅在任务结束后传输文件到用户本机 |
| **预定义工具集** | 用户可选择添加 RAG、Web Search 等预定义工具，自动绑定到 LangChain LLM |
| **多步骤执行** | 采用 planner_only 模式，Planner 做总体规划，然后一步一步执行 |
| **Tool Calling** | 使用 LangChain 的 tool calling 机制调用添加的工具 |

### 1.2 与 Word V2 的对比

| 对比项 | Word V2 | Tool Use |
|--------|---------|----------|
| 执行方式 | 发送代码到 Local Engine 执行 | 直接调用 LangChain Tool |
| 交互模式 | 每步需要等待 Local Engine 返回 | 无需等待，直接在服务端执行 |
| 工具来源 | 固定的 PowerShell 代码 | 用户选择的预定义工具（RAG/Web Search） |
| 结果传输 | 每步传输截图/状态 | 仅在任务结束后传输文件 |

---

## 2. 目录结构

```
useit_ai_run/node_handler/functional_nodes/tool_use/
├── __init__.py                 # 模块导出
├── ARCHITECTURE.md             # 本文档
├── handler.py                  # Handler V2 实现（纯桥接层）
├── models.py                   # 数据模型定义
├── tools/                      # 预定义工具
│   ├── __init__.py
│   ├── base.py                 # 工具基类
│   ├── rag_tool.py             # RAG 检索工具
│   ├── web_search_tool.py      # Web 搜索工具
│   └── file_transfer_tool.py   # 文件传输工具（任务结束时使用）
└── core/
    ├── __init__.py             # 工厂函数
    └── planner_only/
        ├── __init__.py
        ├── agent.py            # Tool Use Agent
        └── planner.py          # Tool Use Planner
```

---

## 3. 核心组件

### 3.1 Handler（桥接层）

`ToolUseNodeHandlerV2` 是纯桥接层，负责：
1. 实现 `BaseNodeHandlerV2` 接口
2. 从请求中提取工具配置
3. 运行 `ToolUseAgent` 决策循环
4. 转发事件，处理流式输出
5. 任务结束后触发文件传输

```python
class ToolUseNodeHandlerV2(BaseNodeHandlerV2):
    """
    Tool Use 节点处理器 V2 - 纯桥接层
    
    支持的节点类型：
    - tool-use
    """
    
    @classmethod
    def supported_types(cls) -> List[str]:
        return ["tool-use"]
    
    async def execute(self, ctx: V2NodeContext) -> AsyncGenerator[Dict[str, Any], None]:
        """
        执行 Tool Use 节点
        
        流程：
        1. 解析工具配置（用户选择的工具列表）
        2. 创建 Agent（绑定选定的工具）
        3. 运行决策循环
        4. 转发事件
        5. 任务完成后，如有需要则传输文件到本机
        """
        ...
```

### 3.2 Agent（决策核心）

`ToolUseAgent` 是决策核心，采用 planner_only 模式：

```python
class ToolUseAgent:
    """
    Tool Use Agent - Planner Only 模式
    
    职责：
    1. 调用 Planner 进行总体规划
    2. 根据规划结果调用 LangChain Tools
    3. 收集工具执行结果
    4. 判断任务是否完成
    """
    
    def __init__(
        self,
        planner_model: str = "gpt-4o-mini",
        api_keys: Optional[Dict[str, str]] = None,
        tools: List[BaseTool] = None,  # LangChain 工具列表
        node_id: str = "",
    ):
        ...
    
    async def run(
        self,
        user_goal: str,
        node_instruction: str,
        max_steps: int = 10,
        log_dir: Optional[str] = None,
        history_md: str = "",
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        运行决策循环
        
        Yields:
            - {"type": "step_start", "step": int}
            - {"type": "reasoning_delta", "content": str, "source": "planner"}
            - {"type": "plan_complete", "content": {...}}
            - {"type": "tool_call", "name": str, "args": {...}}
            - {"type": "tool_result", "name": str, "result": str}
            - {"type": "task_completed", "summary": str, "files_to_transfer": [...]}
            - {"type": "error", "content": str}
        """
        ...
```

### 3.3 Planner（规划器）

`ToolUsePlanner` 负责分析任务并决定下一步调用哪个工具：

```python
class ToolUsePlanner:
    """
    Tool Use Planner
    
    使用 LangChain 的 tool calling 机制：
    1. 将工具绑定到 LLM
    2. LLM 自动决定调用哪个工具
    3. 解析 tool_calls 并执行
    """
    
    def __init__(
        self,
        model: str = "gpt-4o-mini",
        api_keys: Optional[Dict[str, str]] = None,
        tools: List[BaseTool] = None,
        node_id: str = "",
    ):
        # 创建 LangChain LLM 并绑定工具
        self.llm = ChatOpenAI(model=model, ...)
        self.llm_with_tools = self.llm.bind_tools(tools)
        ...
```

---

## 4. 数据模型

### 4.1 核心模型

```python
# models.py

from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from enum import Enum


class ToolType(str, Enum):
    """可用的工具类型"""
    RAG = "rag"
    WEB_SEARCH = "web_search"
    FILE_TRANSFER = "file_transfer"  # 内部使用


@dataclass
class ToolConfig:
    """工具配置"""
    tool_type: ToolType
    enabled: bool = True
    config: Dict[str, Any] = field(default_factory=dict)
    # RAG 配置示例: {"index_path": "...", "top_k": 5}
    # Web Search 配置示例: {"max_results": 10}


@dataclass
class ToolCallResult:
    """工具调用结果"""
    tool_name: str
    tool_args: Dict[str, Any]
    result: str
    success: bool = True
    error: Optional[str] = None


@dataclass
class PlannerOutput:
    """
    Planner 输出
    
    与 Word V2 类似，但不包含代码，而是包含工具调用信息
    """
    thinking: str = ""
    next_action: str = ""  # "tool_call" 或 "stop"
    title: Optional[str] = None
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)  # LangChain tool_calls
    is_milestone_completed: bool = False
    completion_summary: Optional[str] = None
    files_to_transfer: List[str] = field(default_factory=list)  # 任务完成时需要传输的文件

    def to_dict(self) -> Dict[str, Any]:
        return {
            "Thinking": self.thinking,
            "Action": self.next_action,
            "Title": self.title,
            "ToolCalls": self.tool_calls,
            "MilestoneCompleted": self.is_milestone_completed,
            "node_completion_summary": self.completion_summary,
            "files_to_transfer": self.files_to_transfer,
        }


@dataclass
class AgentContext:
    """
    Agent 上下文
    """
    user_goal: str
    node_instruction: str
    tool_results: List[ToolCallResult] = field(default_factory=list)  # 历史工具调用结果
    history_md: str = ""
    history: List[Dict[str, Any]] = field(default_factory=list)

    def to_prompt(self) -> str:
        """转换为 Planner 的 prompt"""
        lines = []
        
        # 1. 用户目标
        if self.user_goal:
            lines.append("## User's Overall Goal")
            lines.append(self.user_goal)
            lines.append("")
        
        # 2. 当前节点指令
        lines.append("## Current Node Instruction (YOUR GOAL)")
        lines.append(self.node_instruction or self.user_goal or "(No instruction)")
        lines.append("")
        
        # 3. 历史工具调用结果
        if self.tool_results:
            lines.append("## Previous Tool Results")
            for i, result in enumerate(self.tool_results, 1):
                lines.append(f"### Step {i}: {result.tool_name}")
                lines.append(f"Arguments: {result.tool_args}")
                if result.success:
                    lines.append(f"Result: {result.result[:1000]}...")  # 截断长结果
                else:
                    lines.append(f"Error: {result.error}")
                lines.append("")
        
        # 4. 工作流进度
        if self.history_md:
            lines.append("## Workflow Progress")
            lines.append(self.history_md)
            lines.append("")
        
        return "\n".join(lines)


@dataclass
class AgentStep:
    """Agent 单步执行结果"""
    planner_output: PlannerOutput
    tool_results: List[ToolCallResult] = field(default_factory=list)
    reasoning_text: str = ""
    error: Optional[str] = None

    @property
    def is_completed(self) -> bool:
        return self.planner_output.is_milestone_completed
```

### 4.2 事件模型

```python
# 复用 office_agent 的事件模型，并扩展

@dataclass
class ToolCallEvent:
    """工具调用事件"""
    tool_name: str
    tool_args: Dict[str, Any]
    call_id: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": "tool_call",
            "id": self.call_id,
            "name": self.tool_name,
            "args": self.tool_args,
        }


@dataclass
class ToolResultEvent:
    """工具结果事件"""
    tool_name: str
    result: str
    success: bool
    call_id: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": "tool_result",
            "id": self.call_id,
            "name": self.tool_name,
            "result": self.result,
            "success": self.success,
        }


@dataclass
class FileTransferEvent:
    """文件传输事件（任务结束时）"""
    files: List[str]
    target: str = "local"  # 传输到本机

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": "file_transfer",
            "files": self.files,
            "target": self.target,
        }
```

---

## 5. 预定义工具

### 5.1 工具基类

```python
# tools/base.py

from abc import ABC, abstractmethod
from typing import Dict, Any
from langchain_core.tools import BaseTool as LangChainBaseTool


class ToolUseBaseTool(LangChainBaseTool, ABC):
    """
    Tool Use 工具基类
    
    继承自 LangChain BaseTool，添加额外的配置支持
    """
    
    @classmethod
    @abstractmethod
    def from_config(cls, config: Dict[str, Any]) -> "ToolUseBaseTool":
        """从配置创建工具实例"""
        ...
```

### 5.2 RAG 工具

```python
# tools/rag_tool.py

from langchain_core.tools import tool
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field


class RAGInput(BaseModel):
    """RAG 工具输入"""
    query: str = Field(description="The search query to find relevant documents")
    top_k: int = Field(default=5, description="Number of results to return")


@tool("rag_search", args_schema=RAGInput)
def rag_search(query: str, top_k: int = 5) -> str:
    """
    Search the knowledge base for relevant documents.
    
    Use this tool when you need to find information from the user's documents or knowledge base.
    """
    # 实际实现会调用 RAG 服务
    ...


class RAGTool:
    """RAG 工具封装"""
    
    def __init__(self, index_path: str, embedding_model: str = "text-embedding-3-small"):
        self.index_path = index_path
        self.embedding_model = embedding_model
        # 初始化向量存储等
        ...
    
    @classmethod
    def from_config(cls, config: Dict[str, Any]) -> "RAGTool":
        return cls(
            index_path=config.get("index_path", ""),
            embedding_model=config.get("embedding_model", "text-embedding-3-small"),
        )
    
    def as_langchain_tool(self) -> LangChainBaseTool:
        """转换为 LangChain 工具"""
        ...
```

### 5.3 Web Search 工具

```python
# tools/web_search_tool.py

from langchain_core.tools import tool
from pydantic import BaseModel, Field


class WebSearchInput(BaseModel):
    """Web Search 工具输入"""
    query: str = Field(description="The search query")
    max_results: int = Field(default=10, description="Maximum number of results")


@tool("web_search", args_schema=WebSearchInput)
def web_search(query: str, max_results: int = 10) -> str:
    """
    Search the web for information.
    
    Use this tool when you need up-to-date information from the internet.
    """
    # 实际实现会调用搜索 API
    ...


class WebSearchTool:
    """Web Search 工具封装"""
    
    def __init__(self, api_key: str, search_engine: str = "google"):
        self.api_key = api_key
        self.search_engine = search_engine
    
    @classmethod
    def from_config(cls, config: Dict[str, Any], api_keys: Dict[str, str]) -> "WebSearchTool":
        return cls(
            api_key=api_keys.get("GOOGLE_API_KEY", ""),
            search_engine=config.get("search_engine", "google"),
        )
    
    def as_langchain_tool(self) -> LangChainBaseTool:
        """转换为 LangChain 工具"""
        ...
```

### 5.4 文件传输工具（内部使用）

```python
# tools/file_transfer_tool.py

class FileTransferTool:
    """
    文件传输工具
    
    在任务结束后，将服务端生成的文件传输到用户本机。
    这个工具不暴露给 LLM，由 Handler 在任务完成时自动调用。
    """
    
    @staticmethod
    async def transfer_files(
        files: List[str],
        local_engine_client: Any,  # Local Engine 客户端
        target_dir: str = "",
    ) -> Dict[str, Any]:
        """
        传输文件到用户本机
        
        Args:
            files: 要传输的文件路径列表
            local_engine_client: Local Engine 客户端
            target_dir: 目标目录（用户本机）
        
        Returns:
            传输结果
        """
        ...
```

---

## 6. 消息流规范

### 6.1 事件类型

遵循 Word V2 的事件格式，并扩展 Tool Use 特有的事件：

| 事件类型 | 说明 | 来源 |
|----------|------|------|
| `node_start` | 节点开始 | Handler |
| `cua_start` | CUA 步骤开始 | Handler |
| `cua_delta` | 推理过程增量 | Agent/Planner |
| `planner_complete` | 规划完成 | Planner |
| `tool_call` | 工具调用 | Agent |
| `tool_result` | 工具结果 | Agent |
| `cua_end` | CUA 步骤结束 | Handler |
| `file_transfer` | 文件传输（任务结束） | Handler |
| `node_complete` | 节点完成 | Handler |
| `error` | 错误 | Any |

### 6.2 事件格式

#### node_start
```json
{
  "type": "node_start",
  "nodeId": "node_123",
  "title": "Tool Use Node",
  "nodeType": "tool-use",
  "instruction": "使用 RAG 搜索相关文档"
}
```

#### cua_start
```json
{
  "type": "cua_start",
  "cuaId": "tooluse_abc123_step1",
  "step": 1,
  "title": "Tool Use - Step 1",
  "nodeId": "node_123"
}
```

#### cua_delta
```json
{
  "type": "cua_delta",
  "cuaId": "tooluse_abc123_step1",
  "reasoning": "分析用户需求，需要先搜索相关文档...",
  "kind": "planner"
}
```

#### planner_complete
```json
{
  "type": "planner_complete",
  "content": {
    "Thinking": "用户需要查找关于 X 的信息，我需要使用 RAG 工具搜索知识库",
    "Action": "tool_call",
    "Title": "Search knowledge base",
    "ToolCalls": [
      {
        "id": "call_001",
        "name": "rag_search",
        "args": {"query": "关于 X 的文档", "top_k": 5}
      }
    ],
    "MilestoneCompleted": false
  }
}
```

#### tool_call
```json
{
  "type": "tool_call",
  "id": "call_001",
  "name": "rag_search",
  "args": {"query": "关于 X 的文档", "top_k": 5}
}
```

#### tool_result
```json
{
  "type": "tool_result",
  "id": "call_001",
  "name": "rag_search",
  "result": "Found 5 relevant documents:\n1. Document A...\n2. Document B...",
  "success": true
}
```

#### cua_end
```json
{
  "type": "cua_end",
  "cuaId": "tooluse_abc123_step1",
  "status": "completed",
  "title": "Search knowledge base",
  "action": {
    "type": "tool_call",
    "name": "rag_search",
    "args": {"query": "关于 X 的文档", "top_k": 5}
  }
}
```

#### file_transfer（任务结束时）
```json
{
  "type": "file_transfer",
  "files": ["/tmp/result.txt", "/tmp/summary.pdf"],
  "target": "local",
  "status": "pending"
}
```

#### node_complete
```json
{
  "type": "node_complete",
  "nodeId": "node_123",
  "nodeType": "tool-use",
  "isNodeCompleted": true,
  "handlerResult": {
    "is_node_completed": true,
    "summary": "成功完成知识库搜索任务"
  },
  "actionSummary": "Task completed",
  "nodeCompletionSummary": "使用 RAG 搜索了 3 次，找到了 15 篇相关文档"
}
```

---

## 7. 执行流程

### 7.1 正常执行流程

```
┌─────────────────────────────────────────────────────────────────┐
│                      Tool Use Node 执行流程                       │
└─────────────────────────────────────────────────────────────────┘

1. Handler 接收请求
   │
   ├── 解析节点配置（工具列表）
   │   └── tools: ["rag", "web_search"]
   │
   ├── 创建 Agent（绑定工具）
   │   └── ToolUseAgent(tools=[rag_tool, web_search_tool])
   │
   └── 发送 node_start 事件

2. Agent 决策循环（无需等待 Local Engine）
   │
   ├── Step 1
   │   ├── cua_start
   │   ├── Planner 分析任务（流式输出 cua_delta）
   │   ├── planner_complete（包含 tool_calls）
   │   ├── 执行 Tool Call（直接调用，无需 Local Engine）
   │   │   ├── tool_call 事件
   │   │   └── tool_result 事件
   │   └── cua_end
   │
   ├── Step 2...N（重复上述流程）
   │
   └── 任务完成
       ├── planner_complete (MilestoneCompleted=true)
       └── 返回 files_to_transfer 列表

3. Handler 处理任务完成
   │
   ├── 如有文件需要传输
   │   ├── file_transfer 事件（通知前端）
   │   └── 调用 Local Engine 传输文件
   │
   └── 发送 node_complete 事件
```

### 7.2 与 Word V2 的流程对比

```
Word V2 流程（需要 Local Engine 交互）:
┌────────┐     ┌────────┐     ┌──────────────┐
│ Handler │ ──> │ Agent  │ ──> │ tool_call    │
└────────┘     └────────┘     │ (execute_code)│
                              └──────────────┘
                                     │
                                     v
                              ┌──────────────┐
                              │ Local Engine │ ─── 执行代码
                              │   执行代码    │
                              └──────────────┘
                                     │
                                     v
                              ┌──────────────┐
                              │ 返回结果+快照 │ ─── 需要等待
                              └──────────────┘
                                     │
                                     v
                              ┌──────────────┐
                              │ 下一步决策   │
                              └──────────────┘


Tool Use 流程（无需 Local Engine 交互）:
┌────────┐     ┌────────┐     ┌──────────────┐
│ Handler │ ──> │ Agent  │ ──> │ tool_call    │
└────────┘     └────────┘     │ (rag_search) │
                              └──────────────┘
                                     │
                                     v （直接调用，无需等待）
                              ┌──────────────┐
                              │ 执行 LangChain│
                              │   Tool       │
                              └──────────────┘
                                     │
                                     v
                              ┌──────────────┐
                              │ 立即返回结果 │ ─── 无需等待
                              └──────────────┘
                                     │
                                     v
                              ┌──────────────┐
                              │ 下一步决策   │
                              └──────────────┘
                                     │
                              (任务完成后)
                                     v
                              ┌──────────────┐
                              │ Local Engine │ ─── 传输文件
                              │  传输文件    │
                              └──────────────┘
```

---

## 8. Prompt 设计

### 8.1 System Prompt

```
You are an AI assistant with access to tools. Your job is to complete the user's task by using the available tools.

## Available Tools

{tool_descriptions}

## Response Format

Think step by step, then decide which tool to call (or stop if done).

1. Analyze the current state and previous tool results
2. Decide the next action:
   - If more information is needed → call a tool
   - If the task is complete → stop and summarize

## Rules

1. Use tools when you need external information
2. Don't make assumptions - verify with tools
3. Summarize findings clearly when done
4. If a tool fails, try alternative approaches
```

### 8.2 User Prompt Template

```
## User's Overall Goal
{user_goal}

## Current Node Instruction (YOUR GOAL)
{node_instruction}

## Previous Tool Results
{tool_results}

## Workflow Progress
{history_md}

---

Now analyze the situation and decide the next action.
```

---

## 9. 配置示例

### 9.1 节点配置（来自 Workflow）

```json
{
  "id": "node_tool_use_001",
  "type": "tool-use",
  "data": {
    "instruction": "搜索知识库，找到关于产品定价的文档",
    "tools": [
      {
        "type": "rag",
        "enabled": true,
        "config": {
          "index_path": "/data/knowledge_base/product_docs",
          "top_k": 5
        }
      },
      {
        "type": "web_search",
        "enabled": false
      }
    ],
    "max_steps": 5
  }
}
```

### 9.2 API Keys 配置

```json
{
  "OPENAI_API_KEY": "sk-...",
  "GOOGLE_API_KEY": "..."
}
```

---

## 10. 后续扩展

### 10.1 可扩展的工具类型

- **Code Interpreter**: 执行 Python 代码
- **Database Query**: 查询数据库
- **API Call**: 调用外部 API
- **Image Analysis**: 图像分析

### 10.2 工具组合模式

支持多个工具的组合使用，例如：
1. RAG 搜索 → 获取文档
2. Web Search → 补充最新信息
3. 综合分析 → 生成报告

---

## 11. 实现优先级

1. **Phase 1**: 基础框架
   - Handler 实现
   - Agent 决策循环
   - 事件流转发

2. **Phase 2**: 核心工具
   - RAG 工具
   - Web Search 工具

3. **Phase 3**: 文件传输
   - Local Engine 集成
   - 文件传输逻辑

4. **Phase 4**: 优化
   - 错误处理
   - 重试机制
   - 性能优化
