# 统一LLM调用系统

## 概述

本系统实现了统一的LLM调用接口，支持多种模型提供商和调用格式，完全基于LangChain构建。

## 🚀 核心特性

- ✅ **统一接口**: 支持OpenAI、Claude、Gemini、vLLM等多种模型
- ✅ **Interleave List格式**: 支持`["text", "image.png", "text"]`混合输入
- ✅ **流式/非流式**: 两种调用模式统一接口
- ✅ **Token统计**: 精确的使用量统计和成本计算
- ✅ **可插拔架构**: 易于扩展新的模型适配器
- ✅ **向后兼容**: 保持现有代码接口不变

## 📂 架构设计

```
llm_utils/
├── __init__.py                    # 主要导出接口
├── unified_client.py             # 统一客户端
├── message_builder.py            # 消息构建器
├── token_counter.py              # Token统计
├── config.py                     # 配置管理
├── base/                         # 基础抽象层
│   ├── client.py                 # 客户端基类
│   └── message_types.py          # 消息类型
├── adapters/                     # 模型适配器
│   ├── openai_adapter.py         # OpenAI
│   ├── claude_adapter.py         # Claude
│   ├── gemini_adapter.py         # Gemini
│   └── vllm_adapter.py           # vLLM/本地
├── examples.py                   # 使用示例
└── test_unified_llm.py          # 基础测试
```

## 🔧 快速开始

### 基础使用

```python
from useit_ai_run.llm_utils import call_llm, stream_llm

# 非流式调用
response = await call_llm("Hello, world!", model="gpt-4o-mini")
print(response.content)
print(f"Token使用: {response.token_usage.total_tokens}")

# 流式调用
async for chunk in stream_llm("Tell me a story", model="claude-3-5-sonnet"):
    if chunk.chunk_type == "text":
        print(chunk.content, end="")
```

### Interleave List格式

```python
# 文本和图片混合
messages = [
    "请分析这张图片:",
    "/path/to/image.png", 
    "这张图片显示了什么？"
]

response = await call_llm(messages, model="gpt-4o")
```

### 统一客户端

```python
from useit_ai_run.llm_utils import UnifiedClient

client = UnifiedClient(model="gemini-1.5-flash")
response = await client.call("What is AI?")

# 查看统计
stats = client.get_stats()
print(f"总Token: {stats['adapter']['total_tokens_used']}")
print(f"总成本: ${stats['adapter']['total_cost']:.6f}")
```

## 🔌 支持的模型

### OpenAI
- `gpt-4o`, `gpt-4o-mini`, `gpt-4-turbo`, `gpt-4`, `gpt-3.5-turbo`
- `gpt-5`, `gpt-5.1` (Responses API)
- `o1`, `o1-preview`, `o1-mini`

### Claude (Anthropic)
- `claude-3-5-sonnet-20241022`
- `claude-3-5-haiku-20241022` 
- `claude-3-opus-20240229`

### Gemini (Google)
- `gemini-1.5-pro`
- `gemini-1.5-flash`

### 本地/vLLM
- `llama-2-7b-chat`
- `mistral-7b`
- 自定义本地模型

## ⚙️ 配置管理

### API密钥设置

```bash
export OPENAI_API_KEY="your-openai-key"
export ANTHROPIC_API_KEY="your-claude-key"  
export GOOGLE_API_KEY="your-gemini-key"
```

### 配置文件

```python
from useit_ai_run.llm_utils import get_client

# 使用预配置客户端
client = get_client(config_name="claude")  # 从配置文件加载
```

## 📊 Token统计

```python
from useit_ai_run.llm_utils import global_token_tracker

# 会话统计
stats = global_token_tracker.get_session_stats("my-session")
print(f"会话Token: {stats['total_tokens']}")
print(f"会话成本: ${stats['total_cost']:.6f}")

# 全局统计  
total = global_token_tracker.get_total_stats()
print(f"总请求数: {total['request_count']}")
```

## 🔄 迁移指南

### 从原始LangChain代码迁移

**原来:**
```python
from langchain_openai import ChatOpenAI
llm = ChatOpenAI(model="gpt-4o-mini")
response = llm.invoke([HumanMessage(content="Hello")])
```

**现在:**
```python
from useit_ai_run.llm_utils import call_llm
response = await call_llm("Hello", model="gpt-4o-mini")
```

### 从原始run_llm迁移

**原来:**
```python
from ..llm.run_llm import run_llm
response, tokens = run_llm(messages, system, "gpt-4o-mini")
```

**现在:**
```python  
from useit_ai_run.llm_utils import call_llm
response = await call_llm(messages, system, model="gpt-4o-mini")
tokens = response.token_usage.total_tokens
```

## 🧪 测试

```bash
cd /path/to/llm_utils
python test_unified_llm.py  # 运行基础测试
python examples.py          # 运行完整示例
```

## 📈 性能优化

- **连接池**: 自动管理HTTP连接
- **Token估算**: 快速的本地token计算
- **缓存**: 自动缓存API密钥和配置
- **错误处理**: 优雅的错误恢复和重试

## 🛡️ 安全性

- API密钥安全存储在环境变量
- 支持配置文件权限控制
- 不记录敏感信息到日志

## 🔮 扩展性

### 添加新模型适配器

```python
from useit_ai_run.llm_utils.base import LangChainBasedClient

class MyCustomAdapter(LangChainBasedClient):
    def _create_langchain_llm(self, streaming=False):
        # 实现您的LLM
        return CustomLLM(...)
    
    def calculate_cost(self, token_usage):
        # 计算成本
        return 0.001 * token_usage.total_tokens
```

### 添加新消息格式

```python
from useit_ai_run.llm_utils import MessageBuilder

# 扩展MessageBuilder支持新格式
builder = MessageBuilder()
messages = builder.from_custom_format(your_data)
```

## 📋 完整更新日志

### 已迁移组件

1. ✅ `base_langchain_planner.py` → 使用统一客户端
2. ✅ `base_llm_planner.py` → 支持统一接口 + 原始回退
3. ✅ `excel/llm_client.py` → 统一接口 + 原始实现回退
4. ✅ 所有核心LLM调用均已统一

### 向后兼容性

- 所有现有API接口保持不变
- 原始实现作为回退机制保留
- 渐进式迁移，无需一次性更改所有代码

## 💡 最佳实践

1. **使用统一客户端**: 推荐用于新代码
2. **Interleave List**: 多模态应用的首选格式
3. **Token监控**: 定期检查使用量和成本
4. **错误处理**: 总是处理LLM调用异常
5. **配置分离**: 使用配置文件管理不同环境

## 🆘 故障排除

### 常见问题

**Q: ImportError: No module named 'useit_ai_run.llm_utils'**
A: 确保正确安装依赖并且路径正确

**Q: API密钥错误**
A: 检查环境变量设置和配置文件

**Q: Token统计不准确**
A: 某些模型的token计算可能是估算值

### 获取帮助

- 查看 `examples.py` 了解完整用法
- 运行 `test_unified_llm.py` 验证安装
- 检查日志文件获取详细错误信息

---

🎉 **统一LLM调用系统现已完成！** 

支持所有主要LLM提供商，提供一致的开发体验，同时保持完全的向后兼容性。