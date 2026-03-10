# Gemini Provider 接入 & Thought Signature 支持

**日期**: 2026-03-10 22:30

---

## 变更概述

1. **新增 Provider**：接入 Gemini 3.1 Pro（通过 Cloudsway OpenAI 兼容网关）
2. **Thought Signature 透传**：实现 Gemini 特有的 `reasoning_details` / `thought_signature` 多轮拼接逻辑
3. **Bug 修复**：`TitleRuntime` 调用了不存在的 `provider.chat()` 方法

---

## 一、Gemini Provider 接入

### 配置

```yaml
# config.yml
llm_providers:
  gemini:
    api_key: 
    base_url: https://genaiapi.cloudsway.net/v1/ai/vEHkTgVnLcrvHENf
    default_model: MaaS_Ge_3.1_pro_preview_20260219
    timeout: 120
    max_retries: 3

agent:
  provider: gemini
  default_model: MaaS_Ge_3.1_pro_preview_20260219
```

### 新增文件

- `backend/app/llm/providers/gemini_provider.py` — 基于 `AsyncOpenAI` 客户端，走 Cloudsway OpenAI 兼容接口

### 修改文件

| 文件 | 变更 |
|------|------|
| `config.yml` | 新增 `llm_providers.gemini`，切换 `agent.provider` 为 `gemini` |
| `backend/app/core/config.py` | `DEFAULT_CONFIG` 增加 gemini 默认配置 |
| `backend/app/llm/factory.py` | 注册 `GeminiProvider` 到 `LLMFactory` |

---

## 二、Thought Signature 透传

### 背景

Gemini 模型在返回 `tool_calls` 时，会在响应中附带 `reasoning_details`，其中包含 `thought_signature`。下一轮请求必须将此 signature 原样拼回 assistant 消息，否则 API 返回 400：

```
Unable to submit request because function call `xxx` is missing a `thought_signature`
```

### Cloudsway 实际返回格式

Cloudsway 将 `reasoning_details` 直接放在 message 顶层（而非嵌套在 `provider_specific_fields` 下）：

```python
# OpenAI SDK 解析后，存在于 message.model_extra 中
message.model_extra = {
    "reasoning_details": [
        {"type": "tool", "text": "serper_search", "signature": "CsQBAY89a1+0ba..."}
    ]
}
```

代码同时兼容文档描述的 `provider_specific_fields.reasoning_details` 包装格式。

### 数据流

```
GeminiProvider.call()
  → 从 response.choices[0].message.model_extra 提取 reasoning_details
  → 写入 result["reasoning_details"]

llm_worker._handle_llm_requested()
  → LLM_CALL_RESULT event 中透传 reasoning_details

agent_worker._handle_llm_result()
  → assistant_msg["reasoning_details"] = response["reasoning_details"]
  → 存入 state.messages

下一轮 LLM 调用:
  → state.messages 传入 GeminiProvider.call()
  → _clean_messages() 检测到 thought signature:
      1. assistant 消息: 保留 reasoning_details
      2. 紧随的 tool 消息: role 改写为 "user"
```

### 核心逻辑

```python
# 检测 thought signature（兼容两种格式）
def has_thought_signature(message):
    rd = message.get("reasoning_details") or []
    if not rd:
        rd = (message.get("provider_specific_fields") or {}).get("reasoning_details") or []
    return any(item.get("type") == "tool" and item.get("signature") for item in rd)

# 清洗规则
# 1. 带 signature 的 assistant → 保留 reasoning_details + 归一化 tool_calls
# 2. 紧随其后的 tool 消息 → role 从 "tool" 改为 "user"
# 3. 无 signature 的普通消息 → 剥离 reasoning_details
```

### 修改文件

| 文件 | 变更 |
|------|------|
| `backend/app/llm/providers/gemini_provider.py` | `_clean_messages()`, `_rebuild_assistant_message()`, `has_thought_signature()` |
| `backend/app/runtime/workers/llm_worker.py` | `LLM_CALL_RESULT` 事件透传 `reasoning_details` |
| `backend/app/runtime/workers/agent_worker.py` | assistant 消息保留 `reasoning_details` |

---

## 三、Bug 修复：TitleRuntime

`TitleRuntime._generate_title()` 调用了 `provider.chat()`，但所有 provider 只实现了 `call()` 方法，导致标题生成始终失败。

**修复**: `provider.chat(messages=..., tools=..., temperature=0.7)` → `provider.call(model=..., messages=..., tools=None, temperature=0.7)`

| 文件 | 变更 |
|------|------|
| `backend/app/runtime/title_runtime.py` | `provider.chat()` → `provider.call()` |

---

## 四、测试

### 单元测试

新增 `backend/tests/test_gemini_provider_thought_signature.py`（11 个用例）：

- `has_thought_signature` 检测：PSF 格式 / 直接格式 / 缺失 / 空 / 错误 type
- `_clean_messages` 清洗：tool→user 转换 / 无 signature 保持 tool / 多轮混合
- `_rebuild_assistant_message` 深拷贝隔离

```
11 passed in 4.30s
```

### E2E 测试

```bash
uv run python tests/e2e/run_e2e.py --provider gemini --timeout 120 --verbose
```

| 用例 | 结果 | 说明 |
|------|------|------|
| simple_chat（自我介绍） | PASS | Gemini 正常回复，~6s |
| custom_query（hello） | PASS | 正常回复，~4.5s |
| 工具调用（北京天气） | PASS | serper 403 → Gemini 自动切换 bash curl wttr.in → 多轮 thought signature 正确透传 → 成功返回天气 |

关键验证：多轮工具调用场景下 **不再出现 `missing thought_signature` 400 错误**。
