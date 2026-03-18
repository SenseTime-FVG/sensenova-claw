"""ask_user 真实 API 回归脚本

用法示例：
    ./.venv/bin/python tests/e2e/run_ask_user_real_api.py --provider gemini --timeout 120
"""

from __future__ import annotations

import argparse
import asyncio
import copy
import time
import uuid
from pathlib import Path

from agentos.platform.config.config import config
from agentos.kernel.events.envelope import EventEnvelope
from agentos.kernel.events.types import (
    AGENT_STEP_COMPLETED,
    ERROR_RAISED,
    USER_INPUT,
    USER_QUESTION_ANSWERED,
    USER_QUESTION_ASKED,
)
from tests.e2e.run_e2e import setup_services, teardown_services


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="ask_user 真实 API 回归脚本")
    parser.add_argument("--provider", default="gemini", help="provider 名称，例如 gemini/openai/anthropic")
    parser.add_argument("--model", default=None, help="可选模型名，不传则使用 config 默认模型")
    parser.add_argument("--timeout", type=float, default=120, help="整轮超时时间（秒）")
    parser.add_argument("--answer", default="dev", help="自动回答内容")
    parser.add_argument(
        "--query",
        default="请先使用 ask_user 工具向我提一个确认问题，再根据我的回答给出最终建议。",
        help="发送给 Agent 的用户输入",
    )
    return parser


def _print_event(idx: int, event: EventEnvelope) -> None:
    print(f"[{idx:03d}] {event.type:<28} source={event.source:<10} turn={event.turn_id or '-'}")
    if event.type in (USER_QUESTION_ASKED, USER_QUESTION_ANSWERED, ERROR_RAISED):
        print(f"      payload={event.payload}")


async def _run(args: argparse.Namespace) -> int:
    original_config = copy.deepcopy(config.data)
    tmp_dir = Path("/tmp") / f"ask_user_real_api_{uuid.uuid4().hex[:8]}"
    tmp_dir.mkdir(parents=True, exist_ok=True)

    svc = await setup_services(tmp_dir, provider=args.provider, model=args.model)
    session_id = f"sess_{uuid.uuid4().hex[:12]}"
    turn_id = f"turn_{uuid.uuid4().hex[:12]}"

    collected: list[EventEnvelope] = []
    done = asyncio.Event()

    async def collector() -> None:
        async for event in svc["bus"].subscribe():
            if event.session_id != session_id:
                continue
            collected.append(event)
            _print_event(len(collected), event)

            if event.type == USER_QUESTION_ASKED:
                await svc["publisher"].publish(
                    EventEnvelope(
                        type=USER_QUESTION_ANSWERED,
                        session_id=session_id,
                        turn_id=turn_id,
                        source="e2e.real_api",
                        payload={
                            "question_id": event.payload.get("question_id"),
                            "answer": args.answer,
                            "cancelled": False,
                        },
                    )
                )

            if event.type == AGENT_STEP_COMPLETED:
                done.set()
                break

    task = asyncio.create_task(collector())
    await asyncio.sleep(0.05)

    start = time.monotonic()

    try:
        await svc["publisher"].publish(
            EventEnvelope(
                type=USER_INPUT,
                session_id=session_id,
                turn_id=turn_id,
                source="e2e.real_api",
                payload={"content": args.query, "attachments": [], "context_files": []},
            )
        )
        await asyncio.wait_for(done.wait(), timeout=args.timeout)
    except asyncio.TimeoutError:
        print(f"[ERROR] 超时：{args.timeout} 秒内未完成 agent.step_completed")
        return 2
    finally:
        task.cancel()
        await teardown_services(svc)
        config.data = original_config

    elapsed = time.monotonic() - start
    event_types = [event.type for event in collected]

    saw_question_asked = USER_QUESTION_ASKED in event_types
    saw_question_answered = USER_QUESTION_ANSWERED in event_types
    saw_turn_completed = AGENT_STEP_COMPLETED in event_types
    saw_error = ERROR_RAISED in event_types

    print("\n=== 回归摘要 ===")
    print(f"provider={args.provider} model={args.model or config.get('agent.default_model')}")
    print(f"elapsed={elapsed:.2f}s")
    print(f"user.question_asked={saw_question_asked}")
    print(f"user.question_answered={saw_question_answered}")
    print(f"agent.step_completed={saw_turn_completed}")
    print(f"error.raised={saw_error}")

    if not saw_question_asked:
        print("[FAIL] 模型未触发 ask_user 工具调用")
        return 1
    if not saw_question_answered:
        print("[FAIL] 未收到 user.question_answered 事件")
        return 1
    if not saw_turn_completed:
        print("[FAIL] 未完成最终回答")
        return 1

    print("[PASS] ask_user 真实 API 链路回归通过")
    return 0


def main() -> int:
    args = _build_parser().parse_args()
    return asyncio.run(_run(args))


if __name__ == "__main__":
    raise SystemExit(main())
