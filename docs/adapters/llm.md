# LLM 适配器

> 路径：`agentos/adapters/llm/`

LLM 适配器层负责屏蔽不同大模型提供商的 API 差异，为上层 `LLMRuntime` 提供统一的调用接口。

---

## LLMFactory

`LLMFactory` 根据 `provider` 名称实例化对应的 LLM 提供者：

```python
provider = LLMFactory.create("openai", config)
```

当前支持的 provider：

| provider | 说明 |
|----------|------|
| `openai` | OpenAI 兼容 API（支持自定义 base_url） |
| `anthropic` | Anthropic Claude API |
| `gemini` | Google Gemini API |
| `mock` | 测试用，返回固定响应 |

---

## Provider 接口

所有 provider 实现统一的抽象基类：

```python
class LLMProvider(ABC):
    async call(model, messages, tools, temperature) -> dict
    # 返回: {content: str, tool_calls: list[dict] | None}
```

**参数说明**：

| 参数 | 类型 | 说明 |
|------|------|------|
| `model` | `str` | 模型名称，如 `gpt-4o-mini` |
| `messages` | `list[dict]` | 对话消息列表 |
| `tools` | `list[dict]` | 可用工具定义（JSON Schema 格式） |
| `temperature` | `float` | 生成温度 |

**返回值**：

```python
{
    "content": "模型生成的文本回复",
    "tool_calls": [
        {
            "id": "call_xxx",
            "type": "function",
            "function": {
                "name": "bash_command",
                "arguments": "{\"command\": \"ls\"}"
            }
        }
    ]  # 如果模型不调用工具则为 None
}
```

---

## 各 Provider 实现

### OpenAI Provider

- 调用 OpenAI 兼容 API，支持通过 `OPENAI_BASE_URL` 配置自定义端点
- 对消息进行归一化处理（确保 `tool_calls` 包含 `type="function"`）
- 兼容大多数 OpenAI 格式的第三方网关

### Anthropic Provider

- 调用 Anthropic Claude API
- 将 OpenAI 格式的消息和工具定义转换为 Anthropic 格式

### Gemini Provider

- 调用 Google Gemini API
- 处理 Gemini 特有的请求/响应格式转换

### Mock Provider

- 测试专用，返回固定响应
- 不需要 API Key
- 可配置固定的工具调用返回

---

## 消息归一化

不同 provider 的消息格式存在差异，适配器层负责统一处理：

- **tool_calls 规范化**：确保 assistant 消息中的 `tool_calls` 每一项都包含 `type="function"` 字段，避免部分网关返回 `400 invalid_value`
- **tool 消息关联**：确保 `tool` 角色消息包含 `tool_call_id`，与对应的 `tool_calls` 条目正确关联
- **格式统一转换**：不论底层 provider 返回什么格式，统一转换为 `{content, tool_calls}` 结构

```python
# 归一化示例：补全缺失的 type 字段
for tc in tool_calls:
    if "type" not in tc:
        tc["type"] = "function"
```

---

## 配置

在 `config.yml` 中配置 LLM 相关参数：

```yaml
OPENAI_BASE_URL: https://api.openai.com/v1
OPENAI_API_KEY: sk-xxx

agent:
  provider: openai           # 选择 provider
  default_model: gpt-4o-mini # 默认模型
```

配置加载优先级：环境变量 > `config.yml` > 默认值。当 `agent.default_model` 未显式配置时，按当前 provider 自动回填默认模型（如 `openai -> gpt-4o-mini`）。
