"""
一键 E2E 测试脚本 - 进程内启动所有服务，无需外部依赖。

用法:
    python3 tests/e2e/run_e2e.py                                 # 使用 mock provider
    uv run python tests/e2e/run_e2e.py --provider anthropic      # 使用真实 Anthropic API
    uv run python tests/e2e/run_e2e.py --provider openai          # 使用真实 OpenAI API
    uv run python tests/e2e/run_e2e.py --query "帮我搜索天气"     # 自定义查询
    uv run python tests/e2e/run_e2e.py --timeout 60               # 调整超时（秒）
"""

from __future__ import annotations

import argparse
import asyncio
import io
import logging
import os
import sqlite3
import sys
import time
import uuid
from pathlib import Path

# Windows 终端 UTF-8 支持
if sys.platform == "win32":
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# 确保能 import app 包
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import yaml

from sensenova_claw.platform.config.config import config
from sensenova_claw.platform.logging.setup import setup_logging

# run_e2e.py -> tests/e2e/ -> tests/ -> 项目根目录
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
from sensenova_claw.adapters.storage.repository import Repository
from sensenova_claw.kernel.events.bus import PublicEventBus
from sensenova_claw.kernel.events.envelope import EventEnvelope
from sensenova_claw.kernel.events.persister import EventPersister
from sensenova_claw.kernel.events.router import BusRouter
from sensenova_claw.kernel.events.types import (
    AGENT_STEP_COMPLETED,
    AGENT_STEP_STARTED,
    ERROR_RAISED,
    LLM_CALL_COMPLETED,
    LLM_CALL_REQUESTED,
    LLM_CALL_RESULT,
    LLM_CALL_STARTED,
    TOOL_CALL_COMPLETED,
    TOOL_CALL_REQUESTED,
    TOOL_CALL_RESULT,
    TOOL_CALL_STARTED,
    USER_INPUT,
)
from sensenova_claw.interfaces.ws.gateway import Gateway
from sensenova_claw.adapters.llm.factory import LLMFactory
from sensenova_claw.kernel.runtime.agent_runtime import AgentRuntime
from sensenova_claw.kernel.runtime.context_builder import ContextBuilder
from sensenova_claw.kernel.runtime.llm_runtime import LLMRuntime
from sensenova_claw.kernel.runtime.publisher import EventPublisher
from sensenova_claw.kernel.runtime.state import SessionStateStore
from sensenova_claw.kernel.runtime.title_runtime import TitleRuntime
from sensenova_claw.kernel.runtime.tool_runtime import ToolRuntime
from sensenova_claw.capabilities.skills.registry import SkillRegistry
from sensenova_claw.capabilities.tools.registry import ToolRegistry
from sensenova_claw.platform.config.workspace import ensure_workspace

logger = logging.getLogger("e2e")

# ── 格式化输出 ──────────────────────────────────────────────

EVENT_ICONS = {
    USER_INPUT:           "📨",
    AGENT_STEP_STARTED:   "🚀",
    AGENT_STEP_COMPLETED: "✅",
    LLM_CALL_REQUESTED:   "🧠",
    LLM_CALL_STARTED:     "⏳",
    LLM_CALL_RESULT:      "💬",
    LLM_CALL_COMPLETED:   "🧠",
    TOOL_CALL_REQUESTED:  "🔧",
    TOOL_CALL_STARTED:    "⏳",
    TOOL_CALL_RESULT:     "📎",
    TOOL_CALL_COMPLETED:  "🔧",
    ERROR_RAISED:         "❌",
}


def fmt_event(idx: int, event: EventEnvelope) -> str:
    icon = EVENT_ICONS.get(event.type, "📌")
    elapsed = f"{event.ts:.3f}"
    line = f"  [{idx:>3}] {icon} {event.type:<30s}  source={event.source:<10s}  turn={event.turn_id or '-'}"

    payload_summary = _summarize_payload(event)
    if payload_summary:
        line += f"\n        {payload_summary}"
    return line


def _summarize_payload(event: EventEnvelope) -> str:
    p = event.payload
    t = event.type

    if t == USER_INPUT:
        return f"content: {_trunc(p.get('content', ''), 80)}"
    if t == LLM_CALL_REQUESTED:
        return f"provider={p.get('provider')} model={p.get('model')} messages_count={len(p.get('messages', []))}"
    if t == LLM_CALL_RESULT:
        resp = p.get("response", {})
        tc = resp.get("tool_calls", [])
        text = _trunc(resp.get("content", ""), 120)
        return f"content: {text}" + (f" | tool_calls: {[c.get('name') for c in tc]}" if tc else "")
    if t == AGENT_STEP_COMPLETED:
        result = p.get("result", {})
        return f"final_content: {_trunc(result.get('content', ''), 120)}"
    if t == TOOL_CALL_REQUESTED:
        return f"tool={p.get('tool_name')} args={_trunc(str(p.get('arguments', {})), 80)}"
    if t == TOOL_CALL_RESULT:
        return f"tool={p.get('tool_name')} result={_trunc(str(p.get('result', '')), 100)}"
    if t == ERROR_RAISED:
        return f"error: {p.get('error_type')}: {_trunc(str(p.get('message', '')), 120)}"
    return ""


def _trunc(s: str, max_len: int) -> str:
    s = s.replace("\n", "\\n")
    return s if len(s) <= max_len else s[:max_len] + "..."


# ── 核心测试流程 ────────────────────────────────────────────

def _deep_merge(base: dict, override: dict) -> dict:
    """递归合并字典，override 覆盖 base"""
    from copy import deepcopy
    result = deepcopy(base)
    for k, v in override.items():
        if k in result and isinstance(result[k], dict) and isinstance(v, dict):
            result[k] = _deep_merge(result[k], v)
        else:
            result[k] = v
    return result


def _load_config_yml() -> dict:
    """从项目根目录读取 config.yml"""
    config_path = PROJECT_ROOT / "config.yml"
    if not config_path.exists():
        return {}
    with config_path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return data if isinstance(data, dict) else {}


async def setup_services(tmp_dir: Path, provider: str, model: str | None):
    """仿照 main.py lifespan 初始化所有服务"""
    db_path = tmp_dir / "test_e2e.db"
    workspace = tmp_dir / "workspace"

    # 从项目根目录 config.yml 读取配置并深度合并
    yml = _load_config_yml()
    if yml:
        config.data = _deep_merge(config.data, yml)
        logger.info("已加载 config.yml: %s", PROJECT_ROOT / "config.yml")

    config.data["system"]["database_path"] = str(db_path)
    config.data["system"]["workspace_dir"] = str(workspace)
    config.data["system"]["log_level"] = "DEBUG"

    if provider == "mock":
        config.data["agent"]["model"] = "mock"
        config.data["llm"]["default_model"] = "mock"
        config.data["tools"]["serper_search"]["api_key"] = ""
    else:
        if model:
            config.data["agent"]["model"] = model
            config.data["llm"]["default_model"] = model

    setup_logging()

    repo = Repository()
    await repo.init()
    await ensure_workspace(str(workspace))

    bus = PublicEventBus()
    publisher = EventPublisher(bus=bus)
    persister = EventPersister(bus=bus, repo=repo)
    bus_router = BusRouter(public_bus=bus, ttl_seconds=3600, gc_interval=9999)

    tool_registry = ToolRegistry()
    state_store = SessionStateStore()

    skills_dir = Path(str(workspace)) / "skills"
    skill_registry = SkillRegistry(workspace_dir=skills_dir)
    skill_registry.load_skills(config.data)

    context_builder = ContextBuilder(skill_registry=skill_registry, tool_registry=tool_registry)

    agent_runtime = AgentRuntime(
        bus_router=bus_router,
        repo=repo,
        context_builder=context_builder,
        tool_registry=tool_registry,
        state_store=state_store,
    )
    llm_runtime = LLMRuntime(bus_router=bus_router, factory=LLMFactory())
    tool_runtime = ToolRuntime(bus_router=bus_router, registry=tool_registry)
    title_runtime = TitleRuntime(bus=bus, repo=repo)

    gateway = Gateway(publisher=publisher)

    await persister.start()
    await bus_router.start()
    await agent_runtime.start()
    await llm_runtime.start()
    await tool_runtime.start()
    await title_runtime.start()
    await gateway.start()
    await asyncio.sleep(0.1)

    return {
        "repo": repo,
        "bus": bus,
        "publisher": publisher,
        "persister": persister,
        "bus_router": bus_router,
        "agent_runtime": agent_runtime,
        "llm_runtime": llm_runtime,
        "tool_runtime": tool_runtime,
        "title_runtime": title_runtime,
        "gateway": gateway,
        "db_path": db_path,
    }


async def teardown_services(svc: dict):
    """按顺序关闭所有服务"""
    await svc["agent_runtime"].stop()
    await svc["llm_runtime"].stop()
    await svc["tool_runtime"].stop()
    await svc["title_runtime"].stop()
    await svc["gateway"].stop()
    await svc["bus_router"].stop()
    await svc["persister"].stop()


async def run_single_turn(
    svc: dict,
    query: str,
    timeout: float,
) -> tuple[list[EventEnvelope], float]:
    """发送一条用户消息，收集整轮事件直到 agent.step_completed 或超时"""
    bus: PublicEventBus = svc["bus"]
    publisher: EventPublisher = svc["publisher"]

    session_id = f"sess_{uuid.uuid4().hex[:12]}"
    turn_id = f"turn_{uuid.uuid4().hex[:12]}"

    collected: list[EventEnvelope] = []
    done = asyncio.Event()

    async def collector():
        async for event in bus.subscribe():
            if event.session_id != session_id:
                continue
            collected.append(event)
            if event.type == AGENT_STEP_COMPLETED:
                done.set()
                break

    collect_task = asyncio.create_task(collector())
    await asyncio.sleep(0.05)

    start_time = time.monotonic()

    await publisher.publish(
        EventEnvelope(
            type=USER_INPUT,
            session_id=session_id,
            turn_id=turn_id,
            source="e2e_test",
            payload={"content": query, "attachments": [], "context_files": []},
        )
    )

    try:
        await asyncio.wait_for(done.wait(), timeout=timeout)
    except asyncio.TimeoutError:
        pass
    finally:
        collect_task.cancel()
        try:
            await collect_task
        except asyncio.CancelledError:
            pass

    elapsed = time.monotonic() - start_time
    return collected, elapsed


# ── 断言检查 ────────────────────────────────────────────────

EXPECTED_SIMPLE_CHAIN = [
    AGENT_STEP_STARTED,
    LLM_CALL_REQUESTED,
    LLM_CALL_COMPLETED,
    AGENT_STEP_COMPLETED,
]

EXPECTED_TOOL_CHAIN = [
    AGENT_STEP_STARTED,
    LLM_CALL_REQUESTED,
    LLM_CALL_COMPLETED,
    TOOL_CALL_REQUESTED,
    TOOL_CALL_RESULT,
    LLM_CALL_REQUESTED,
    LLM_CALL_COMPLETED,
    AGENT_STEP_COMPLETED,
]


def check_chain(events: list[EventEnvelope], expected: list[str], label: str) -> list[str]:
    """检查事件链是否包含预期的有序子序列（去重后检查），返回失败信息列表"""
    failures: list[str] = []
    types = [e.type for e in events]
    # 去重：保持顺序但相邻重复只保留一个
    deduped: list[str] = []
    for t in types:
        if not deduped or deduped[-1] != t:
            deduped.append(t)

    j = 0
    for t in deduped:
        if j < len(expected) and t == expected[j]:
            j += 1
    if j < len(expected):
        missing = expected[j:]
        failures.append(f"[{label}] 缺少事件: {missing}  (去重链路: {deduped})")

    return failures


def check_no_fatal_errors(events: list[EventEnvelope], label: str) -> list[str]:
    """检查是否有致命错误（工具执行错误不算致命，只是警告）"""
    failures: list[str] = []
    for e in events:
        if e.type == ERROR_RAISED:
            ctx = e.payload.get("context", {})
            if ctx.get("tool_name"):
                logger.warning("[%s] 工具执行错误(非致命): %s", label, e.payload.get("error_message", ""))
            else:
                failures.append(f"[{label}] 致命错误: {e.payload}")
    return failures


def check_db(db_path: Path, session_id_prefix: str) -> list[str]:
    """检查数据库持久化"""
    failures: list[str] = []
    if not db_path.exists():
        failures.append("数据库文件不存在")
        return failures

    conn = sqlite3.connect(db_path)
    try:
        count = conn.execute("SELECT COUNT(1) FROM events").fetchone()[0]
        if count == 0:
            failures.append("events 表为空，事件未持久化")
    except Exception as exc:
        failures.append(f"数据库查询失败: {exc}")
    finally:
        conn.close()
    return failures


# ── 测试用例 ────────────────────────────────────────────────

def _print_event_trace(events: list[EventEnvelope], verbose: bool) -> None:
    """verbose 模式下打印完整事件链路"""
    if not verbose:
        return
    print("  事件链路:")
    for i, ev in enumerate(events):
        print(fmt_event(i, ev))


async def test_simple_chat(svc: dict, timeout: float, verbose: bool = False) -> tuple[bool, list[str]]:
    """测试 1: 简单对话（无工具调用）"""
    events, elapsed = await run_single_turn(svc, "你好，请做个自我介绍", timeout)
    failures = check_chain(events, EXPECTED_SIMPLE_CHAIN, "simple_chat")
    failures.extend(check_no_fatal_errors(events, "simple_chat"))

    step_completed = [e for e in events if e.type == AGENT_STEP_COMPLETED]
    if step_completed:
        content = step_completed[0].payload.get("result", {}).get("content", "")
        if not content:
            failures.append("[simple_chat] agent.step_completed 的 content 为空")
    else:
        failures.append("[simple_chat] 未收到 agent.step_completed")

    print(f"  耗时: {elapsed:.2f}s | 事件数: {len(events)}")
    _print_event_trace(events, verbose)
    return len(failures) == 0, failures


async def test_tool_calling(svc: dict, timeout: float, verbose: bool = False) -> tuple[bool, list[str]]:
    """测试 2: 工具调用流程（mock provider 会触发 serper_search）"""
    events, elapsed = await run_single_turn(svc, "帮我搜索英超联赛最近3年的冠亚军分别是什么球队", timeout)
    failures = check_chain(events, EXPECTED_TOOL_CHAIN, "tool_calling")

    tool_reqs = [e for e in events if e.type == TOOL_CALL_REQUESTED]
    tool_results = [e for e in events if e.type == TOOL_CALL_RESULT]

    if not tool_reqs:
        failures.append("[tool_calling] 未触发任何工具调用")
    if tool_reqs and not tool_results:
        failures.append("[tool_calling] 工具调用无结果返回")

    print(f"  耗时: {elapsed:.2f}s | 事件数: {len(events)} | 工具调用: {len(tool_reqs)}")
    _print_event_trace(events, verbose)
    return len(failures) == 0, failures


async def test_custom_query(svc: dict, query: str, timeout: float, verbose: bool = False) -> tuple[bool, list[str]]:
    """测试 3: 自定义查询"""
    events, elapsed = await run_single_turn(svc, query, timeout)

    failures = []
    types = [e.type for e in events]
    if AGENT_STEP_COMPLETED not in types:
        failures.append(f"[custom] 超时或未完成，已收集事件: {types}")

    failures.extend(check_no_fatal_errors(events, "custom"))

    step_completed = [e for e in events if e.type == AGENT_STEP_COMPLETED]
    if step_completed:
        content = step_completed[0].payload.get("result", {}).get("content", "")
        print(f"  耗时: {elapsed:.2f}s | 事件数: {len(events)}")
        print(f"  回复: {_trunc(content, 200)}")
    else:
        print(f"  耗时: {elapsed:.2f}s | 事件数: {len(events)} | 未完成")

    _print_event_trace(events, verbose)
    return len(failures) == 0, failures


# ── 主入口 ──────────────────────────────────────────────────

async def main():
    parser = argparse.ArgumentParser(description="Sensenova-Claw E2E 一键测试")
    parser.add_argument("--provider", default="gemini", help="LLM provider: mock / openai / anthropic / gemini")
    parser.add_argument("--model", default=None, help="模型名称（不指定则使用配置默认值）")
    parser.add_argument("--query", default=None, help="自定义测试查询（替代内置用例）")
    parser.add_argument("--timeout", type=float, default=30, help="单轮超时秒数（默认 30s）")
    parser.add_argument("--tmp-dir", default=None, help="临时目录路径（默认自动创建）")
    parser.add_argument("--verbose", "-v", action="store_true", help="打印完整事件链路")
    args = parser.parse_args()

    import tempfile
    tmp_dir = Path(args.tmp_dir) if args.tmp_dir else Path(tempfile.mkdtemp(prefix="sensenova_claw_e2e_"))

    config_yml = PROJECT_ROOT / "config.yml"

    print("=" * 70)
    print("  Sensenova-Claw E2E 一键测试")
    print("=" * 70)
    print(f"  Provider  : {args.provider}")
    print(f"  Model     : {args.model or '(配置默认值)'}")
    print(f"  Timeout   : {args.timeout}s")
    print(f"  Config    : {config_yml}" + (" [已找到]" if config_yml.exists() else " [未找到]"))
    print(f"  Tmp Dir   : {tmp_dir}")
    print("=" * 70)

    svc = await setup_services(tmp_dir, args.provider, args.model)
    all_pass = True

    try:
        v = args.verbose
        if args.query:
            tests = [("custom_query", lambda: test_custom_query(svc, args.query, args.timeout, v))]
        elif args.provider == "mock":
            tests = [
                ("simple_chat", lambda: test_simple_chat(svc, args.timeout, v)),
                ("tool_calling", lambda: test_tool_calling(svc, args.timeout, v)),
            ]
        else:
            tests = [
                ("simple_chat", lambda: test_simple_chat(svc, args.timeout, v)),
                ("custom_query", lambda: test_custom_query(svc, "hello, who are you?", args.timeout, v)),
            ]

        for test_name, make_coro in tests:
            print(f"\n{'─' * 60}")
            print(f"  测试: {test_name}")
            print(f"{'─' * 60}")

            passed, failures = await make_coro()

            if passed:
                print("  结果: PASS")
            else:
                print("  结果: FAIL")
                for f in failures:
                    print(f"    - {f}")
                all_pass = False

        # 数据库持久化检查
        print(f"\n{'─' * 60}")
        print(f"  检查: 数据库持久化")
        print(f"{'─' * 60}")
        db_failures = check_db(svc["db_path"], "")
        if db_failures:
            print("  结果: FAIL")
            for f in db_failures:
                print(f"    - {f}")
            all_pass = False
        else:
            conn = sqlite3.connect(svc["db_path"])
            event_count = conn.execute("SELECT COUNT(1) FROM events").fetchone()[0]
            conn.close()
            print(f"  结果: PASS (events 表共 {event_count} 条记录)")

    finally:
        await teardown_services(svc)

    print(f"\n{'=' * 70}")
    if all_pass:
        print("  [PASS] 所有测试通过!")
    else:
        print("  [FAIL] 存在失败测试，请查看上方详情")
    print(f"{'=' * 70}")

    sys.exit(0 if all_pass else 1)


if __name__ == "__main__":
    asyncio.run(main())
