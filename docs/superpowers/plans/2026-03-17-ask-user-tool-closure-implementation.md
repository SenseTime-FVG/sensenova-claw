# AskUserTool Closure Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 一次性补齐 AskUserTool 在后端注册、配置白名单、Web 交互闭环、测试闭环和真实 API 回归。  
**Architecture:** 保持现有事件驱动架构（`user.question_asked` / `user.question_answered`）不重构，仅补齐工具注册、前端消息消费与回答回传、以及测试覆盖。前端通过可复用 `QuestionDialog` 组件在 `/chat` 与 `/sessions/[id]` 复用交互逻辑。  
**Tech Stack:** Python 3 + pytest、FastAPI + WebSocket、Next.js + TypeScript + Playwright

---

**Spec:** `docs/superpowers/specs/2026-03-17-ask-user-tool-closure-design.md`  
**Recommended skills during execution:** `@test-driven-development`, `@systematic-debugging`, `@verification-before-completion`

## Chunk 1: 后端可用性与契约收口

### Task 1: ToolRegistry 注册 ask_user（阻断项）

**Files:**
- Modify: `agentos/capabilities/tools/registry.py`
- Modify: `tests/unit/test_tool_registry.py`
- Test: `tests/unit/test_tool_registry.py`

- [ ] **Step 1: 写失败测试（先证明当前未注册）**

```python
def test_builtin_registered(self):
    r = ToolRegistry()
    assert r.get("ask_user") is not None
```

- [ ] **Step 2: 运行单测确认失败**

Run: `./.venv/bin/python -m pytest tests/unit/test_tool_registry.py::TestToolRegistry::test_builtin_registered -q`  
Expected: FAIL，提示 `ask_user` 为 `None`

- [ ] **Step 3: 最小实现注册逻辑**

```python
from agentos.capabilities.tools.ask_user_tool import AskUserTool

for tool in [
    BashCommandTool(),
    SerperSearchTool(),
    ImageSearchTool(),
    FetchUrlTool(),
    ReadFileTool(),
    WriteFileTool(),
    CreateAgentTool(),
    DocSourceTool(),
    SendEmailTool(),
    ListEmailsTool(),
    ReadEmailTool(),
    DownloadAttachmentTool(),
    MarkEmailTool(),
    SearchEmailsTool(),
    AskUserTool(),
]:
    self.register(tool)
```

- [ ] **Step 4: 回归该测试与关联测试**

Run: `./.venv/bin/python -m pytest tests/unit/test_tool_registry.py tests/unit/test_ask_user_tool.py -q`  
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add agentos/capabilities/tools/registry.py tests/unit/test_tool_registry.py
git commit -m "feat: register ask_user tool in registry"
```

### Task 2: 将 ask_user 加入所有 agents 的 tools 白名单

**Files:**
- Modify: `config.yml`
- Create: `tests/unit/test_agent_tools_config.py`
- Test: `tests/unit/test_agent_tools_config.py`

- [ ] **Step 1: 写失败测试（配置契约测试）**

```python
import yaml
from pathlib import Path

def test_all_agents_include_ask_user():
    cfg = yaml.safe_load(Path("config.yml").read_text(encoding="utf-8"))
    agents = cfg.get("agents", {})
    for aid, a in agents.items():
        assert "ask_user" in a.get("tools", []), f"{aid} missing ask_user"
```

- [ ] **Step 2: 运行单测确认失败**

Run: `./.venv/bin/python -m pytest tests/unit/test_agent_tools_config.py -q`  
Expected: FAIL，至少一个 agent 缺少 `ask_user`

- [ ] **Step 3: 最小修改配置**

```yaml
agents:
  office-main:
    tools: ["delegate", "ask_user"]
  ppt-agent:
    tools: ["serper_search", "fetch_url", "read_file", "write_file", "bash_command", "delegate", "ask_user"]
  data-analyst:
    tools: ["read_file", "write_file", "bash_command", "delegate", "feishu_doc", "ask_user"]
  doc-organizer:
    tools: ["read_file", "write_file", "bash_command", "delegate", "feishu_doc", "feishu-wiki", "feishu-drive", "ask_user"]
  email-agent:
    tools: ["bash_command", "read_file", "write_file", "delegate", "ask_user"]
  search-agent:
    tools: ["serper_search", "fetch_url", "read_file", "write_file", "image_search", "delegate", "ask_user"]
```

- [ ] **Step 4: 运行配置测试**

Run: `./.venv/bin/python -m pytest tests/unit/test_agent_tools_config.py -q`  
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add config.yml tests/unit/test_agent_tools_config.py
git commit -m "chore: enable ask_user for all configured agents"
```

### Task 3: CLI 多选返回类型归一化

**Files:**
- Modify: `agentos/app/cli/app.py`
- Create: `tests/unit/test_cli_ask_user_prompt.py`
- Test: `tests/unit/test_cli_ask_user_prompt.py`

- [ ] **Step 1: 写失败测试（多选输入单个编号也应走 list）**

```python
async def test_prompt_question_multi_select_single_index_returns_list(app):
    data = {"payload": {"question": "Q", "options": ["A", "B"], "multi_select": True}}
    # mock input -> "1"
    answer, cancelled = await app._prompt_question(data)
    assert answer == ["A"]
    assert cancelled is False
```

- [ ] **Step 2: 运行测试确认失败**

Run: `./.venv/bin/python -m pytest tests/unit/test_cli_ask_user_prompt.py::test_prompt_question_multi_select_single_index_returns_list -q`  
Expected: FAIL（当前返回 `"A"`）

- [ ] **Step 3: 最小实现**

```python
if options and multi_select and user_input.isdigit():
    idx = int(user_input) - 1
    if 0 <= idx < len(options):
        return [options[idx]], False
```

- [ ] **Step 4: 跑全量 CLI ask_user 相关测试**

Run: `./.venv/bin/python -m pytest tests/unit/test_cli_ask_user_prompt.py tests/unit/test_tool_worker_ask_user.py -q`  
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add agentos/app/cli/app.py tests/unit/test_cli_ask_user_prompt.py
git commit -m "fix: normalize cli ask_user multi-select answer type"
```

## Chunk 2: Web 闭环补齐（/chat + /sessions/[id]）

### Task 4: 新建 QuestionDialog 复用组件

**Files:**
- Create: `agentos/app/web/components/chat/QuestionDialog.tsx`
- Modify: `agentos/app/web/app/chat/page.tsx`
- Test: `agentos/app/web/e2e/ask-user.spec.ts`

- [ ] **Step 1: 写失败 E2E（弹窗出现断言）**

```ts
test('ask_user 问题应显示弹窗', async ({ page }) => {
  await page.request.post('/api/agents', {
    data: {
      id: 'ask-user-e2e',
      name: 'ask-user-e2e',
      system_prompt: '你必须先调用 ask_user 收集补充信息，然后再回答。',
      tools: ['ask_user'],
    },
  });
  await page.goto('/chat?agent=ask-user-e2e');
  await page.getByTestId('chat-input').fill('请先问我一个问题再继续');
  await page.getByTestId('chat-send').click();
  await expect(page.getByTestId('ask-user-dialog')).toBeVisible({ timeout: 60000 });
});
```

- [ ] **Step 2: 运行该用例确认失败**

Run: `cd agentos/app/web && PLAYWRIGHT_BROWSERS_PATH=/tmp/pw-browsers npx playwright test e2e/ask-user.spec.ts -g "弹窗" --reporter=line`  
Expected: FAIL（找不到 `ask-user-dialog`）

- [ ] **Step 3: 实现最小对话框组件**

```tsx
export function QuestionDialog(props: QuestionDialogProps) {
  return props.open ? <div data-testid="ask-user-dialog">{props.question}</div> : null;
}
```

- [ ] **Step 4: 再跑该用例**

Run: `cd agentos/app/web && PLAYWRIGHT_BROWSERS_PATH=/tmp/pw-browsers npx playwright test e2e/ask-user.spec.ts -g "弹窗" --reporter=line`  
Expected: PASS（弹窗渲染）

- [ ] **Step 5: 提交**

```bash
git add agentos/app/web/components/chat/QuestionDialog.tsx agentos/app/web/e2e/ask-user.spec.ts
git commit -m "feat(web): add reusable ask_user question dialog"
```

### Task 5: 接入 /chat 消息消费与回答回传

**Files:**
- Modify: `agentos/app/web/app/chat/page.tsx`
- Modify: `agentos/app/web/e2e/ask-user.spec.ts`
- Test: `agentos/app/web/e2e/ask-user.spec.ts`

- [ ] **Step 1: 写失败 E2E（收到问题后发送 user_question_answered）**

```ts
test('chat 页面可提交 ask_user 回答', async ({ page }) => {
  await expect(page.getByTestId('ask-user-dialog')).toBeVisible();
  await expect(page.locator('[data-testid="chat-input"]')).toBeDisabled();
  await page.getByTestId('ask-user-custom-input').fill('这是自定义补充信息');
  await page.getByRole('button', { name: '确认' }).click();
  await expect(page.getByTestId('ask-user-dialog')).not.toBeVisible();
});
```

- [ ] **Step 2: 运行用例确认失败**

Run: `cd agentos/app/web && PLAYWRIGHT_BROWSERS_PATH=/tmp/pw-browsers npx playwright test e2e/ask-user.spec.ts -g "chat 页面可提交" --reporter=line`  
Expected: FAIL

- [ ] **Step 3: 最小实现 /chat 分支**

```tsx
case 'user_question_asked':
  setPendingQuestion({
    questionId: String(payload.question_id),
    question: String(payload.question || ''),
    options: Array.isArray(payload.options) ? payload.options.map(String) : null,
    multiSelect: Boolean(payload.multi_select),
    timeout: Number(payload.timeout || 300),
    createdAt: Date.now(),
  });
  break;

wsSend({
  type: 'user_question_answered',
  session_id: sessionId,
  payload: { question_id, answer, cancelled }
});
// 为输入框/发送按钮增加 data-testid:
// chat-input, chat-send
```

- [ ] **Step 4: 回归 ask_user Web 用例**

Run: `cd agentos/app/web && PLAYWRIGHT_BROWSERS_PATH=/tmp/pw-browsers npx playwright test e2e/ask-user.spec.ts --reporter=line`  
Expected: PASS（至少 chat 相关场景通过）

- [ ] **Step 5: 提交**

```bash
git add agentos/app/web/app/chat/page.tsx agentos/app/web/e2e/ask-user.spec.ts
git commit -m "feat(web): wire ask_user flow in chat page"
```

### Task 6: 接入 /sessions/[id] 页面同样闭环

**Files:**
- Modify: `agentos/app/web/app/sessions/[id]/page.tsx`
- Modify: `agentos/app/web/e2e/ask-user.spec.ts`
- Test: `agentos/app/web/e2e/ask-user.spec.ts`

- [ ] **Step 1: 写失败 E2E（session 页面 ask_user 回答）**

```ts
test('session 页面可处理 ask_user', async ({ page }) => {
  const sid = await page.getByTestId('current-session-id').textContent();
  await page.goto(`/sessions/${sid}`);
  await expect(page.getByTestId('ask-user-dialog')).toBeVisible();
});
```

- [ ] **Step 2: 运行用例确认失败**

Run: `cd agentos/app/web && PLAYWRIGHT_BROWSERS_PATH=/tmp/pw-browsers npx playwright test e2e/ask-user.spec.ts -g "session 页面" --reporter=line`  
Expected: FAIL

- [ ] **Step 3: 最小实现 /sessions/[id] 分支**

```tsx
switch (data.type) {
  case 'user_question_asked':
    setPendingQuestion({
      questionId: String(data.payload?.question_id || ''),
      question: String(data.payload?.question || ''),
      options: Array.isArray(data.payload?.options) ? data.payload.options.map(String) : null,
      multiSelect: Boolean(data.payload?.multi_select),
      timeout: Number(data.payload?.timeout || 300),
      createdAt: Date.now(),
    });
    break;
}
// 回答提交后发送 user_question_answered
// 为当前 session 标识增加 data-testid: current-session-id
```

- [ ] **Step 4: 回归全部 ask_user 前端用例**

Run: `cd agentos/app/web && PLAYWRIGHT_BROWSERS_PATH=/tmp/pw-browsers npx playwright test e2e/ask-user.spec.ts --reporter=line`  
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add agentos/app/web/app/sessions/[id]/page.tsx agentos/app/web/e2e/ask-user.spec.ts
git commit -m "feat(web): wire ask_user flow in session detail page"
```

## Chunk 3: 测试闭环与真实 API 回归

### Task 7: 后端 ask_user 集成链路测试（可稳定跑）

**Files:**
- Create: `tests/e2e/test_ask_user_core_flow.py`
- Test: `tests/e2e/test_ask_user_core_flow.py`

- [ ] **Step 1: 写失败测试（断言问答事件链）**

```python
assert "user.question_asked" in event_types
assert "user.question_answered" in event_types
assert event_types.count("llm.call_requested") >= 2
```

- [ ] **Step 2: 运行测试确认失败**

Run: `./.venv/bin/python -m pytest tests/e2e/test_ask_user_core_flow.py -q`  
Expected: FAIL

- [ ] **Step 3: 最小实现（测试侧注入可控 provider + 回答事件）**

```python
class AskUserMockProvider:
    async def call(self, model, messages, tools=None, **kwargs):
        if messages and messages[-1].get("role") == "tool":
            return {"content": "收到你的补充信息，继续完成任务。", "tool_calls": []}
        return {
            "content": "先向用户确认关键参数。",
            "tool_calls": [{
                "id": "ask_user_1",
                "name": "ask_user",
                "arguments": {"question": "请选择环境", "options": ["dev", "prod"], "multi_select": False},
            }],
        }

# 订阅总线，收到 user.question_asked 后立即发布 user.question_answered(answer='dev')
```

- [ ] **Step 4: 回归该集成测试**

Run: `./.venv/bin/python -m pytest tests/e2e/test_ask_user_core_flow.py -q`  
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add tests/e2e/test_ask_user_core_flow.py
git commit -m "test: add stable ask_user core flow e2e"
```

### Task 8: 真实 API 后端回归脚本（强制 ask_user 场景）

**Files:**
- Create: `tests/e2e/run_ask_user_real_api.py`
- Modify: `README.md`
- Test: `tests/e2e/run_ask_user_real_api.py`

- [ ] **Step 1: 先写回归脚本断言骨架**

```python
assert saw_question_asked, "模型未触发 ask_user"
assert saw_question_answered, "回传回答未生效"
assert saw_turn_completed, "未完成最终回答"
```

- [ ] **Step 2: 运行脚本确认当前失败或未覆盖**

Run: `./.venv/bin/python tests/e2e/run_ask_user_real_api.py --provider gemini --timeout 120`  
Expected: FAIL 或提示配置缺失（如 key/网络）

- [ ] **Step 3: 最小实现脚本**

```python
async def main():
    svc = await setup_services(tmp_dir, provider=args.provider, model=args.model)
    events = []
    async for ev in svc["bus"].subscribe():
        events.append(ev)
        if ev.type == "user.question_asked":
            await svc["publisher"].publish(EventEnvelope(
                type="user.question_answered",
                session_id=ev.session_id,
                turn_id=ev.turn_id,
                source="e2e_real_api",
                payload={"question_id": ev.payload["question_id"], "answer": "补充信息", "cancelled": False},
            ))
        if ev.type == "agent.step_completed":
            break

    assert any(e.type == "user.question_asked" for e in events)
    assert any(e.type == "user.question_answered" for e in events)
    assert any(e.type == "agent.step_completed" for e in events)
```

- [ ] **Step 4: 再跑脚本并记录结果**

Run: `./.venv/bin/python tests/e2e/run_ask_user_real_api.py --provider gemini --timeout 120`  
Expected: PASS（链路完整）或明确阻断项（不可宣称通过）

- [ ] **Step 5: 提交**

```bash
git add tests/e2e/run_ask_user_real_api.py README.md
git commit -m "test: add real-api ask_user backend regression script"
```

### Task 9: 真实 API 前端 Playwright 回归

**Files:**
- Modify: `agentos/app/web/e2e/ask-user.spec.ts`
- Test: `agentos/app/web/e2e/ask-user.spec.ts`

- [ ] **Step 1: 写真实 API 场景断言**

```ts
await expect(page.getByTestId('ask-user-dialog')).toBeVisible();
await page.getByTestId('ask-user-custom-input').fill('自定义答案');
await page.getByRole('button', { name: '确认' }).click();
await expect(page.locator('.bubble.assistant').last()).not.toHaveText(/^$/);
await expect(page.getByTestId('ask-user-dialog')).not.toBeVisible();
```

- [ ] **Step 2: 运行用例确认失败（现状基线）**

Run: `cd agentos/app/web && PLAYWRIGHT_BROWSERS_PATH=/tmp/pw-browsers npx playwright test e2e/ask-user.spec.ts -g "真实 API" --reporter=line`  
Expected: FAIL

- [ ] **Step 3: 最小实现（选择器与等待策略）**

```ts
test('真实 API ask_user 回归', async ({ page }) => {
  await page.goto('/chat?agent=ask-user-e2e');
  await page.getByTestId('chat-input').fill('请先向我提问');
  await page.getByTestId('chat-send').click();
  await expect(page.getByTestId('ask-user-dialog')).toBeVisible({ timeout: 120000 });
  await page.getByTestId('ask-user-custom-input').fill('真实 API 补充输入');
  await page.getByRole('button', { name: '确认' }).click();
  await expect(page.locator('.bubble.assistant').last()).not.toHaveText(/^$/);
});
```

- [ ] **Step 4: 回归真实 API 前端测试**

Run: `cd agentos/app/web && PLAYWRIGHT_BROWSERS_PATH=/tmp/pw-browsers npx playwright test e2e/ask-user.spec.ts -g "真实 API" --reporter=line`  
Expected: PASS；若失败，输出可复现阻断（依赖缺失/网络失败）

- [ ] **Step 5: 提交**

```bash
git add agentos/app/web/e2e/ask-user.spec.ts
git commit -m "test(web): add real-api ask_user playwright regression"
```

### Task 10: 全量验证、日志核对与收尾文档

**Files:**
- Modify: `docs/superpowers/specs/2026-03-17-ask-user-tool-closure-design.md`（回填状态）
- Modify: `AGENTS.md`（追加本次复盘到自动 Notes）

- [ ] **Step 1: 运行后端测试集**

Run: `./.venv/bin/python -m pytest tests/unit/test_ask_user_tool.py tests/unit/test_tool_worker_ask_user.py tests/unit/test_tool_registry.py tests/e2e/test_ask_user_core_flow.py -q`  
Expected: PASS

- [ ] **Step 2: 运行前端 ask_user E2E**

Run: `cd agentos/app/web && PLAYWRIGHT_BROWSERS_PATH=/tmp/pw-browsers npx playwright test e2e/ask-user.spec.ts --reporter=line`  
Expected: PASS

- [ ] **Step 3: 运行真实 API 后端与前端回归**

Run:
```bash
./.venv/bin/python tests/e2e/run_ask_user_real_api.py --provider gemini --timeout 120
cd agentos/app/web && PLAYWRIGHT_BROWSERS_PATH=/tmp/pw-browsers npx playwright test e2e/ask-user.spec.ts -g "真实 API" --reporter=line
```
Expected: PASS；否则输出阻断与证据日志

- [ ] **Step 4: 更新文档与复盘**

```markdown
- spec 状态改为“已实现并回归”
- AGENTS Notes 记录成功经验/失败风险
```

- [ ] **Step 5: 提交**

```bash
git add docs/superpowers/specs/2026-03-17-ask-user-tool-closure-design.md AGENTS.md
git commit -m "docs: finalize ask_user closure verification notes"
```

---

## 执行顺序建议

1. Chunk 1（后端阻断项）  
2. Chunk 2（Web 闭环）  
3. Chunk 3（测试与真实 API 回归）

## 风险与阻断前置检查

1. 若 `uv` 不可用，统一使用 `./.venv/bin/python -m pytest`。  
2. 若 Playwright 缺少系统库，先记录阻断并安装依赖后再跑。  
3. 若真实 API key 缺失或无网络，立即暂停并向用户请求配置，不伪造通过结果。

## 完成定义（DoD）

1. `ToolRegistry.as_llm_tools()` 可见 `ask_user`。  
2. `/chat` 与 `/sessions/[id]` 均可完成提问→回答→继续对话。  
3. 所有 agent 的 `tools` 白名单包含 `ask_user`。  
4. 单元 + 集成 + 前端 E2E + 真实 API 回归结果可复现。  
5. DEBUG 日志可完整追踪问答事件链。
