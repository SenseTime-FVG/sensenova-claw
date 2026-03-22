# Search Agent 自我委派并行搜索设计

日期: 2026-03-22

## 概述

让 search-agent 在面对复杂搜索任务时，能够自主拆分为多个子任务，通过 `send_message` 向自己的新 session 并行委派执行，最后汇总结果返回完整报告。同时 office-main 保持跨类型编排职责不变。

## 背景

当前架构中，`send_message` 的循环检测会拦截 agent 向自己发送消息（`target_id in current_send_chain`），导致 search-agent 无法自我委派。但自我委派（同一 agent 的新 session）与真正的循环（A→B→A 无限乒乓）本质不同，`max_send_depth` 已能防止无限递归。

## 职责分离

- **office-main**：跨类型编排（搜索 + 数据分析 + PPT 等），将不同类型任务分发给对应的专业 agent
- **search-agent**：搜索类任务内部的拆分与并行执行，自主判断是否需要拆分

## 设计

### 1. 允许自我委派的授权检查

**文件**: `agentos/capabilities/agents/registry.py`

当前 `get_sendable` 在 `can_send_message_to` 为空时，返回所有**其他**已启用 agent（排除自身）：

```python
if not source.can_send_message_to:
    return [a for a in self._agents.values()
            if a.id != from_agent_id and a.enabled]
```

改为：允许自身出现在可发送列表中：

```python
if not source.can_send_message_to:
    return [a for a in self._agents.values() if a.enabled]
```

这样 `send_message` 的授权检查不会拦截自我委派。对于不需要自我委派的 agent，`max_send_depth: 1` 和循环检测仍然会阻止实际的自我发送。

### 2. 放宽循环检测

**文件**: `agentos/capabilities/tools/send_message_tool.py`

当前逻辑（第 229 行）：

```python
if target_id in current_send_chain:
    chain_str = " -> ".join(current_send_chain + [target_id])
    return f"发送失败：检测到循环链路 {chain_str}。"
```

改为：

```python
# 允许自我委派（同一 agent 的新 session），拦截真正的循环（A→B→A）
if target_id in current_send_chain and target_id != current_agent_id:
    chain_str = " -> ".join(current_send_chain + [target_id])
    return f"发送失败：检测到循环链路 {chain_str}。"
```

注意：此改动后，循环检测对自我委派链完全不起作用（A→A→A 不会被拦截）。防止无限自我递归**完全依赖 `max_send_depth`**。这是有意为之 — `max_send_depth` 是更精确的控制手段。

行为变化：

| 场景 | 改动前 | 改动后 |
|---|---|---|
| `search-agent → search-agent` | 拦截 | 允许（自我委派） |
| `search-agent → data-analyst → search-agent` | 拦截 | 拦截（真正循环） |
| `office-main → search-agent → search-agent` | 拦截 | 允许（自我委派） |

### 3. search-agent 配置调整

**文件**: `.agentos/agents/search-agent/config.yml`

将 `max_send_depth` 从 1 调整为 2：

```yaml
max_send_depth: 2
```

depth 控制逻辑：
- 父 session (depth=0)：可以拆分并派发子任务
- 子 session (depth=1)：独立执行搜索，不能再派发（depth+1=2 到达上限）

### 4. search-agent System Prompt 增强

**文件**: `.agentos/agents/search-agent/SYSTEM_PROMPT.md`

在现有 system prompt 末尾追加：

```markdown
## 任务拆分与并行执行

当你收到的任务带有 [子任务模式] 标记时，直接执行任务，不要再拆分。

当任务没有标记且满足以下条件时，你可以拆分为多个子任务并行执行：
- 任务包含多个独立的调研方向
- 各方向之间没有依赖关系
- 并行执行能显著提升效率

拆分方法：使用 send_message 的多目标模式向自己发送子任务：

{
  "targets": [
    {"target_agent": "search-agent", "message": "[子任务模式] 子任务描述1..."},
    {"target_agent": "search-agent", "message": "[子任务模式] 子任务描述2..."}
  ],
  "mode": "sync",
  "timeout_seconds": 600
}

注意事项：
- 每个子任务的 message 必须以 [子任务模式] 开头
- 每个子任务应包含明确的调研范围和预期输出格式
- 子任务数量建议控制在 2-5 个，避免过度拆分
- 根据任务复杂度设置合理的 timeout_seconds（默认 600 秒）
- 子任务模式下不要使用 ask_user 确认，直接执行

所有子任务完成后，你需要：
- 整合各子任务的结果
- 去重和交叉验证
- 输出一份完整的汇总报告
```

### 5. 递归控制：软引导 + 硬兜底

- **软引导**：子任务 message 以 `[子任务模式]` 开头，system prompt 约定收到标记时直接执行不再拆分
- **硬兜底**：`max_send_depth: 2`，防止无限自我递归。循环检测对自我委派链不起作用，递归深度完全由 `max_send_depth` 控制

### 6. 错误处理

- **子任务部分失败**：当前 `_execute_parallel` 已有 per-target try/catch，失败的子任务返回错误信息不影响其他子任务。search-agent 汇总时用成功结果先汇总，在报告中标注失败的方向。
- **超时控制**：`timeout_seconds` 对整个并行批次生效，所有子任务共享同一超时窗口。深度调研建议设置 600 秒。
- **子任务数量**：不做硬限制，靠 system prompt 引导控制在 2-5 个。

### 7. 调用链路示例

```
用户/office-main → search-agent (session A, depth=0)
  → LLM 判断任务复杂，决定拆分为 3 个子任务
  → send_message(targets=[
      {target_agent: "search-agent", message: "[子任务模式] 调研技术栈..."},
      {target_agent: "search-agent", message: "[子任务模式] 调研竞品..."},
      {target_agent: "search-agent", message: "[子任务模式] 调研商业模式..."},
    ], mode="sync", timeout_seconds=600)
  → 3 个子 session (B, C, D) 并行执行 (depth=1)
     每个子 session 独立多轮搜索 + 分析
  → 结果通过 AgentMessageCoordinator 回传 session A
  → search-agent 整合、去重、交叉验证
  → 返回完整汇总报告
```

## 改动清单

| # | 文件 | 类型 | 改动内容 |
|---|---|---|---|
| 1 | `agentos/capabilities/agents/registry.py` | 代码 | `get_sendable` 不再排除自身，允许自我委派通过授权检查 |
| 2 | `agentos/capabilities/tools/send_message_tool.py` | 代码 | 循环检测条件加 `and target_id != current_agent_id` |
| 3 | `.agentos/agents/search-agent/config.yml` | 配置 | `max_send_depth: 1` → `2` |
| 4 | `.agentos/agents/search-agent/SYSTEM_PROMPT.md` | 配置 | 追加任务拆分与并行执行指引 |

## 测试策略

- **单元测试**：
  - 自我委派通过授权检查（`get_sendable` 包含自身）
  - 自我委派通过循环检测（`search-agent → search-agent`）
  - 真正循环仍被拦截（`A → B → A`）
  - depth 限制生效（depth=2 时 `send_message` 拒绝）
  - 并行自我委派（多个 targets 都指向自身）
- **集成测试**：search-agent 收到复杂任务 → 拆分 → 并行子 session → 汇总返回完整报告
