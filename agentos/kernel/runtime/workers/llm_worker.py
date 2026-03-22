from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

from agentos.platform.config.config import config
from agentos.kernel.events.bus import PrivateEventBus
from agentos.kernel.events.envelope import EventEnvelope
from agentos.kernel.events.types import (
    ERROR_RAISED,
    LLM_CALL_COMPLETED,
    LLM_CALL_REQUESTED,
    LLM_CALL_RESULT,
    LLM_CALL_STARTED,
)
from agentos.kernel.runtime.workers.base import SessionWorker

if TYPE_CHECKING:
    from agentos.kernel.runtime.llm_runtime import LLMRuntime

logger = logging.getLogger(__name__)

_LLM_DEBUG = os.environ.get("AGENTOS_DEBUG_LLM", "").strip() not in ("", "0", "false")


def _get_debug_base() -> Path:
    """获取 debug 日志根目录: $AGENTOS_HOME/logs/debug/llm"""
    from agentos.platform.config.workspace import resolve_agentos_home
    return resolve_agentos_home(config) / "logs" / "debug" / "llm"


def _save_llm_debug(
    session_id: str,
    llm_call_id: str,
    provider: str,
    model: str,
    input_data: dict[str, Any],
    output_data: dict[str, Any],
    duration_ms: int,
    error: str | None = None,
) -> None:
    """将单次 LLM 调用的输入输出保存为 JSON 文件。

    目录结构: $AGENTOS_HOME/logs/debug/llm/{date}/{session_id}/{llm_call_id}.json
    """
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    out_dir = _get_debug_base() / today / session_id
    out_dir.mkdir(parents=True, exist_ok=True)

    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "session_id": session_id,
        "llm_call_id": llm_call_id,
        "provider": provider,
        "model": model,
        "duration_ms": duration_ms,
        "input": input_data,
        "output": output_data,
    }
    if error:
        record["error"] = error

    filepath = out_dir / f"{llm_call_id}.json"
    try:
        filepath.write_text(
            json.dumps(record, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        logger.debug("LLM debug log saved: %s", filepath)
    except Exception:
        logger.warning("Failed to save LLM debug log: %s", filepath, exc_info=True)


class LLMSessionWorker(SessionWorker):
    """LLM 会话级 Worker：处理 LLM 调用"""

    def __init__(self, session_id: str, private_bus: PrivateEventBus, runtime: LLMRuntime):
        super().__init__(session_id, private_bus)
        self.rt = runtime

    async def _handle(self, event: EventEnvelope) -> None:
        if event.type == LLM_CALL_REQUESTED:
            await self._handle_llm_requested(event)

    async def _handle_llm_requested(self, event: EventEnvelope) -> None:
        llm_call_id = event.payload.get("llm_call_id")
        # model/provider 可能由事件直接指定（已是 model_id），也可能需要从 model key 解析
        raw_model = event.payload.get("model")
        raw_provider = event.payload.get("provider")
        if raw_provider and raw_model:
            # 事件已显式指定 provider 和 model_id，直接使用
            provider_name, model = raw_provider, raw_model
        else:
            # 通过 model key 解析
            model_key = raw_model or config.get("llm.default_model", "mock")
            provider_name, model = config.resolve_model(model_key)
        messages = event.payload.get("messages", [])
        tools = event.payload.get("tools")
        temperature = float(event.payload.get("temperature", config.get("agent.temperature", 0.2)))
        max_tokens = event.payload.get("max_tokens")
        extra_body = event.payload.get("extra_body") or None

        logger.debug(
            "LLM call input | provider=%s model=%s llm_call_id=%s extra_body=%s messages=%s tools=%s",
            provider_name, model, llm_call_id, extra_body, messages, tools,
        )

        await self.bus.publish(
            EventEnvelope(
                type=LLM_CALL_STARTED,
                session_id=event.session_id,
                turn_id=event.turn_id,
                trace_id=llm_call_id,
                source="llm",
                payload={"llm_call_id": llm_call_id, "model": model},
            )
        )

        input_data = {
            "messages": messages,
            "tools": tools,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "extra_body": extra_body,
        }

        provider = self.rt.factory.get_provider(provider_name)
        t0 = time.monotonic()
        try:
            resp = await provider.call(
                model=model,
                messages=messages,
                tools=tools,
                temperature=temperature,
                max_tokens=max_tokens,
                extra_body=extra_body,
            )
            duration_ms = int((time.monotonic() - t0) * 1000)

            if _LLM_DEBUG:
                _save_llm_debug(
                    session_id=event.session_id,
                    llm_call_id=llm_call_id,
                    provider=provider_name,
                    model=model,
                    input_data=input_data,
                    output_data=resp,
                    duration_ms=duration_ms,
                )

            await self.bus.publish(
                EventEnvelope(
                    type=LLM_CALL_RESULT,
                    session_id=event.session_id,
                    turn_id=event.turn_id,
                    trace_id=llm_call_id,
                    source="llm",
                    payload={
                        "llm_call_id": llm_call_id,
                        "response": {
                            "content": resp.get("content", ""),
                            "tool_calls": resp.get("tool_calls", []),
                            **({"reasoning_details": resp["reasoning_details"]} if resp.get("reasoning_details") else {}),
                            **({"provider_specific_fields": resp["provider_specific_fields"]} if resp.get("provider_specific_fields") else {}),
                        },
                        "usage": resp.get("usage", {}),
                        "finish_reason": resp.get("finish_reason", "stop"),
                    },
                )
            )
            await self.bus.publish(
                EventEnvelope(
                    type=LLM_CALL_COMPLETED,
                    session_id=event.session_id,
                    turn_id=event.turn_id,
                    trace_id=llm_call_id,
                    source="llm",
                    payload={"llm_call_id": llm_call_id},
                )
            )
        except Exception as exc:  # noqa: BLE001
            duration_ms = int((time.monotonic() - t0) * 1000)
            logger.exception("llm call failed")
            error_message = str(exc).strip() or type(exc).__name__

            if _LLM_DEBUG:
                _save_llm_debug(
                    session_id=event.session_id,
                    llm_call_id=llm_call_id,
                    provider=provider_name,
                    model=model,
                    input_data=input_data,
                    output_data={},
                    duration_ms=duration_ms,
                    error=error_message,
                )
            await self.bus.publish(
                EventEnvelope(
                    type=ERROR_RAISED,
                    session_id=event.session_id,
                    turn_id=event.turn_id,
                    trace_id=llm_call_id,
                    source="llm",
                    payload={
                        "error_type": type(exc).__name__,
                        "error_message": error_message,
                        "context": {"model": model, "provider": provider_name},
                    },
                )
            )
            await self.bus.publish(
                EventEnvelope(
                    type=LLM_CALL_RESULT,
                    session_id=event.session_id,
                    turn_id=event.turn_id,
                    trace_id=llm_call_id,
                    source="llm",
                    payload={
                        "llm_call_id": llm_call_id,
                        "response": {"content": f"LLM调用失败: {error_message}", "tool_calls": []},
                        "usage": {},
                        "finish_reason": "error",
                    },
                )
            )
            await self.bus.publish(
                EventEnvelope(
                    type=LLM_CALL_COMPLETED,
                    session_id=event.session_id,
                    turn_id=event.turn_id,
                    trace_id=llm_call_id,
                    source="llm",
                    payload={"llm_call_id": llm_call_id},
                )
            )
