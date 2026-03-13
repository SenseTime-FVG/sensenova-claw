# Test Audit And Core LLM Coverage Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修正当前测试脚本与目录漂移问题，并补齐 agent 的首轮 LLM、工具调用、二轮 LLM、最终完成这条核心链路的自动化验证。

**Architecture:** 以 `tests/` 作为唯一受支持的自动化测试根目录，保留 `test/` 仅作为兼容入口或清晰标记为旧目录。新增 pytest 级 e2e 用例，在进程内启动完整 runtime 栈，用 mock provider 真实驱动事件流，验证 agent/llm/tool 三段编排，而不是只校验单个 worker 的 mock 行为。

**Tech Stack:** Python 3.12, pytest, pytest-asyncio, FastAPI runtime, Playwright（仅现有前端 e2e，不在本次核心修复范围内）

---

### Task 1: 盘点并修正测试入口

**Files:**
- Modify: `package.json`
- Modify: `test/run_all.sh`
- Modify: `docs/26_thorough_test_plan.md`

- [ ] **Step 1: 写出当前入口与目录漂移的断言清单**

```python
def test_scripts_only_target_supported_test_roots():
    assert supported_root == "tests"
```

- [ ] **Step 2: 运行现有脚本/配置检查，确认失败点**

Run: `python3 -m pytest tests/unit/test_agent_worker.py -q`
Expected: PASS，证明当前主测试根目录可运行；同时人工确认 `test/run_all.sh` 仍指向不存在的 `backend/`

- [ ] **Step 3: 最小修正脚本与文档**

```python
class TestEntryPolicy:
    root_test_dir = "tests"
    legacy_dir = "test"
```

- [ ] **Step 4: 运行目标命令验证入口一致**

Run: `python3 -m pytest tests/ -q`
Expected: 目标子集通过，且脚本路径不再依赖不存在目录

### Task 2: 补齐 agent 核心 LLM 链路 e2e

**Files:**
- Create: `tests/e2e/test_agent_llm_core_flow.py`
- Modify: `tests/e2e/run_e2e.py`

- [ ] **Step 1: 先写失败测试，描述核心链路**

```python
async def test_agent_tool_roundtrip_runs_two_llm_calls():
    events = await run_turn("帮我搜索英超联赛最近3年的冠亚军分别是什么球队")
    assert llm_requested_count == 2
    assert "tool.call_requested" in event_types
    assert final_content
```

- [ ] **Step 2: 跑新测试，确认现状缺口**

Run: `python3 -m pytest tests/e2e/test_agent_llm_core_flow.py -q`
Expected: FAIL，暴露当前缺少自动化覆盖或断言不足

- [ ] **Step 3: 最小实现共享测试辅助逻辑或修正现有脚本**

```python
async def collect_turn_events(...):
    # 进程内启动完整服务栈
    # 发布 user_input
    # 等到 agent.step_completed
    pass
```

- [ ] **Step 4: 重新运行新测试并确认通过**

Run: `python3 -m pytest tests/e2e/test_agent_llm_core_flow.py -q`
Expected: PASS

### Task 3: 验证与结论

**Files:**
- Modify: `AGENTS.md`

- [ ] **Step 1: 跑核心测试子集**

Run: `python3 -m pytest tests/unit/test_agent_worker.py tests/unit/test_llm_worker.py tests/unit/test_openai_provider_message_normalization.py tests/e2e/test_agent_llm_core_flow.py -q`
Expected: PASS

- [ ] **Step 2: 记录本次成功/失败经验**

```python
def record_notes() -> None:
    pass
```

- [ ] **Step 3: 输出审查结论与剩余风险**

Run: `python3 -m pytest tests/e2e/ -q`
Expected: 若环境允许则通过；若有外部依赖限制，明确说明限制与未验证部分
