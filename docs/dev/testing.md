# 测试规范

AgentOS 采用分层测试策略，覆盖从单元到端到端的完整测试链路。

---

## 测试分层

```
tests/
  unit/            # 单元测试 — 纯逻辑，无外部依赖
  integration/     # 集成测试 — 模块间协作，进程内事件流
  e2e/             # 端到端测试 — 完整链路，真实 API 调用
  cross_feature/   # 跨功能测试 — 多功能交叉验证
```

| 层级 | 目的 | 外部依赖 | 运行速度 |
|------|------|---------|---------|
| 单元测试 | 验证单个函数/类的逻辑正确性 | 无 | 快 |
| 集成测试 | 验证模块间事件驱动协作 | 无（使用 Mock Provider） | 中 |
| 端到端测试 | 验证完整用户交互链路 | 真实 API Key | 慢 |
| 跨功能测试 | 验证多功能组合场景 | 视情况 | 中~慢 |

---

## 运行测试

### 全部测试

```bash
python3 -m pytest tests/ -q
```

### 后端单元测试

```bash
python3 -m pytest tests/unit/ -q
```

适合在本地快速验证代码改动，无需任何外部依赖。

### 后端端到端测试

```bash
npm run test:e2e
# 等价于：
python3 -m pytest tests/e2e -q
```

> **注意**：e2e 测试需要在 `config.yml` 中配置真实的 `OPENAI_API_KEY`（以及 `SERPER_API_KEY`，如果测试涉及搜索工具）。

### 前端端到端测试

```bash
npm run test:web:e2e
```

前端 e2e 测试使用 Playwright 无头浏览器，需要事先安装：

```bash
npx playwright install --with-deps
```

### 运行特定测试文件

```bash
python3 -m pytest tests/unit/test_event_bus.py -q
python3 -m pytest tests/e2e/test_chat_flow.py -q -v
```

### 查看详细输出

```bash
python3 -m pytest tests/unit/ -v --tb=short
```

---

## 测试要求

### 新功能必须编写测试

- 每个新功能**必须**编写 e2e 测试，验证完整的事件链路
- 核心逻辑建议同时编写单元测试

### 后端 e2e 测试规范

后端 e2e 测试模拟用户输入，验证从事件发布到最终响应的完整链路：

```python
async def test_basic_chat_flow():
    """验证基本对话流程的完整事件链路"""
    # 1. 初始化服务
    services = await create_test_services()

    # 2. 创建会话
    session_id = await services.repo.create_session("test_session")

    # 3. 模拟用户输入
    event = EventEnvelope(
        type="user.input",
        session_id=session_id,
        payload={"content": "你好"},
        source="test",
    )
    await services.publisher.publish(event)

    # 4. 等待并验证事件链路
    events = await collect_events(session_id, timeout=30)

    # 验证事件类型（不验证具体文案）
    event_types = [e.type for e in events]
    assert "agent.step_started" in event_types
    assert "agent.step_completed" in event_types
```

### 前端 e2e 测试规范

前端 e2e 使用 Playwright 进行无头浏览器测试：

```typescript
test('用户可以发送消息并收到回复', async ({ page }) => {
  await page.goto('http://localhost:3000');

  // 等待 WebSocket 连接
  await page.waitForSelector('[data-testid="ws-connected"]');

  // 发送消息
  await page.fill('[data-testid="message-input"]', '你好');
  await page.click('[data-testid="send-button"]');

  // 验证消息回显
  await expect(page.locator('[data-testid="user-message"]')).toBeVisible();

  // 等待助手回复（不验证具体文案）
  await expect(page.locator('[data-testid="assistant-message"]')).toBeVisible({
    timeout: 30000,
  });
});
```

---

## 测试最佳实践

### 断言策略

- **不要依赖固定文案**：LLM 输出不稳定，断言应基于事件类型或结构化字段
- **验证事件链路**：检查关键事件是否按预期顺序出现
- **验证数据结构**：检查响应中包含必要字段，不验证具体值

```python
# 推荐 - 验证事件类型
assert any(e.type == "agent.step_completed" for e in events)

# 推荐 - 验证结构
assert "content" in completed_event.payload.get("result", {})

# 不推荐 - 验证固定文案
assert completed_event.payload["result"]["content"] == "你好！有什么可以帮你的？"
```

### 优先使用进程内集成测试

对于后端逻辑验证，优先使用进程内事件流集成测试，而非基于真实端口的 e2e 测试：

- 进程内测试更稳定，不受网络和端口限制
- 可以精确控制事件时序
- 运行速度更快

### Mock Provider

不需要真实 LLM 的测试场景，使用 Mock Provider：

```python
# Mock Provider 会返回预设的响应，不调用真实 API
config = {
    "agent": {
        "provider": "mock",
        "default_model": "mock-model"
    }
}
```

### 并发工具测试

测试并发工具执行时，需验证 `pending_tool_calls` 的完成跟踪：

```python
async def test_concurrent_tool_calls():
    """验证多个工具并发执行时的状态跟踪"""
    # 发送触发多工具调用的输入
    # ...

    # 验证所有工具调用都已完成
    tool_results = [e for e in events if e.type == "tool.call_result"]
    assert len(tool_results) == expected_tool_count

    # 验证最终响应包含所有工具结果
    completed = next(e for e in events if e.type == "agent.step_completed")
    assert completed is not None
```

### 超时设置

e2e 测试中 LLM 调用可能较慢，建议设置合理的超时时间：

```python
# 单个测试的超时
@pytest.mark.timeout(60)
async def test_complex_flow():
    ...

# 事件收集的超时
events = await collect_events(session_id, timeout=30)
```

---

## 测试环境注意事项

| 问题 | 解决方案 |
|------|---------|
| `python` 命令不存在 | 使用 `python3` |
| `pytest` 未安装 | 执行 `uv sync --extra dev` |
| uv 缓存权限不足 | 设置 `UV_CACHE_DIR=/tmp/uv_cache` |
| Playwright 系统库缺失 | `npx playwright install --with-deps`（可能需要 sudo） |
| 前端 e2e 本机无法运行 | 当前环境可能缺少 Chromium 系统库，改用 CI 环境运行 |
| API Key 未配置 | e2e 测试需要在 `config.yml` 配置真实 API Key |
| `localhost` 访问受限 | 优先使用进程内集成测试替代基于端口的 e2e |
