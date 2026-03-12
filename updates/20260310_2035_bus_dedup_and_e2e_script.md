# 双总线事件去重 & 一键 E2E 测试脚本

**日期**: 2026-03-10 20:35

---

## 变更概述

1. **修复 Bug**：Worker 从 PrivateEventBus 重复收到事件（每个事件被投递 2 次）
2. **新增工具**：进程内一键 E2E 测试脚本，无需启动任何外部进程即可验证完整事件链路

---

## 一、双总线事件去重 (Bug Fix)

### 问题描述

Worker 在 PrivateEventBus 上 `publish()` 事件后，该事件经历两条路径到达 Worker：

```
Worker 调用 private_bus.publish(event)
  → PrivateEventBus.publish():
      1. 投递给私有订阅者 (Worker 第1次收到) ✓
      2. 回流到 PublicEventBus
  → BusRouter._route_loop() 从 PublicEventBus 收到
      → 发现该 session 的 PrivateEventBus 已存在
      → 调用 deliver() 投递给私有订阅者 (Worker 第2次收到) ✗ 重复
```

**影响**：所有 Worker 内部产生的事件（LLM 调用、工具执行等）都会被处理两次，导致重复 LLM 请求、重复工具执行、事件数量翻倍。

### 修复方案

通过 `on_forward` 回调机制让 BusRouter 感知哪些事件已经在 PrivateEventBus 内部投递过，路由时跳过这些事件。

### 改动文件

| 文件 | 改动 |
|------|------|
| `backend/app/events/bus.py` | `PrivateEventBus.__init__` 新增可选参数 `on_forward: Callable[[str], None]`；`publish()` 回流前调用回调标记 `event_id` |
| `backend/app/events/router.py` | `BusRouter` 新增 `_forwarded_ids: set[str]` 和 `_mark_forwarded()` 方法；`get_or_create()` 创建 PrivateEventBus 时传入回调；`_route_loop()` 跳过已标记的 `event_id` |
| `backend/tests/test_dual_bus.py` | 新增 `test_no_duplicate_delivery_to_workers` 测试用例 |

### 事件流修复前后对比（tool_calling 场景）

| 指标 | 修复前 | 修复后 |
|------|--------|--------|
| 事件总数 | 42 | 17 |
| 工具调用次数 | 4 | 1 |
| 数据库记录数 | 122 | 26 |

### 向后兼容

`on_forward` 参数默认为 `None`，不传则行为不变。现有直接构造 `PrivateEventBus` 的测试代码无需修改。

---

## 二、一键 E2E 测试脚本 (新增)

### 文件

- `backend/tests/e2e/run_e2e.py`

### 设计

仿照 `main.py` 的 `lifespan`，在进程内初始化完整服务栈（Repository → EventBus → BusRouter → AgentRuntime → LLMRuntime → ToolRuntime → TitleRuntime → Gateway），通过 EventPublisher 直接发送用户消息，监听 PublicEventBus 收集事件，直到 `agent.step_completed` 出现。

### 用法

```bash
cd backend

# Mock 模式（默认，快速验证事件链路）
uv run python tests/e2e/run_e2e.py

# Verbose 模式（打印每个事件详情）
uv run python tests/e2e/run_e2e.py -v

# 真实 API
uv run python tests/e2e/run_e2e.py --provider anthropic --timeout 60

# 自定义查询
uv run python tests/e2e/run_e2e.py --query "hello world"

# npm 快捷命令
npm run test:e2e
npm run test:e2e:verbose
```

### 命令行参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--provider` | `mock` | LLM provider: mock / openai / anthropic |
| `--model` | 配置默认值 | 模型名称 |
| `--query` | 无 | 自定义查询（替代内置用例） |
| `--timeout` | 30 | 单轮超时秒数 |
| `--tmp-dir` | 自动创建 | 临时目录路径 |
| `-v / --verbose` | 关闭 | 打印完整事件链路 |

### 内置测试用例

| 用例 | 说明 |
|------|------|
| `simple_chat` | 简单对话，验证 `user.input → llm.call → agent.step_completed` |
| `tool_calling` | Mock provider 触发 serper_search，验证完整工具调用链路 |
| `db_persistence` | 验证事件持久化到 SQLite |

### 断言策略

- 事件链路检查：验证有序子序列（去重相邻重复后匹配）
- 致命错误检查：区分工具执行错误（非致命）和系统级错误（致命）
- 数据库检查：验证 events 表非空

---

## 三、package.json 新增命令

```json
"test:e2e": "cd backend && uv run python tests/e2e/run_e2e.py",
"test:e2e:verbose": "cd backend && uv run python tests/e2e/run_e2e.py -v"
```

---

## 四、测试结果

### 单元测试

```
tests/test_dual_bus.py — 10 passed (含新增 test_no_duplicate_delivery_to_workers)
tests/test_tool_system.py — 20 passed
tests/test_gateway.py — 4 passed
tests/e2e/test_gateway_integration.py — 1 passed
tests/e2e/test_websocket_flow.py — 1 passed
```

### E2E 测试

```
simple_chat:    PASS (0.25s, 9 events)
tool_calling:   PASS (0.22s, 17 events)
db_persistence: PASS (26 records)
```
