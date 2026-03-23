from __future__ import annotations

import json
import logging
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

from sensenova_claw.platform.config.config import config
from sensenova_claw.kernel.events.bus import PrivateEventBus
from sensenova_claw.kernel.events.envelope import EventEnvelope
from sensenova_claw.kernel.events.types import (
    ERROR_RAISED,
    LLM_CALL_COMPLETED,
    LLM_CALL_REQUESTED,
    LLM_CALL_RESULT,
    LLM_CALL_STARTED,
    NOTIFICATION_SESSION,
)
from sensenova_claw.kernel.runtime.workers.base import SessionWorker

if TYPE_CHECKING:
    from sensenova_claw.kernel.runtime.llm_runtime import LLMRuntime

logger = logging.getLogger(__name__)

_LLM_DEBUG = os.environ.get("SENSENOVA_CLAW_DEBUG_LLM", "").strip() not in ("", "0", "false")


def _normalize_llm_error(provider_name: str, model: str, error_message: str) -> dict[str, Any]:
    """将 provider 原始错误归一化为更友好的前端可消费结构。"""
    context: dict[str, Any] = {"model": model, "provider": provider_name}
    normalized = {
        "error_type": None,
        "error_code": "llm_call_failed",
        "error_message": error_message,
        "user_message": f"LLM调用失败: {error_message}",
        "context": context,
    }

    match = re.search(r"Range of max_tokens should be \[(\d+),\s*(\d+)\]", error_message)
    alt_match = re.search(r"does not support max tokens >\s*(\d+)", error_message)
    if match or alt_match:
        limit = int(match.group(2)) if match else int(alt_match.group(1))
        context["limit"] = limit
        normalized["error_code"] = "max_tokens_out_of_range"
        normalized["user_message"] = (
            f"当前模型允许的最大输出长度超限，最大不能超过 {limit}。"
            "请调小 max_tokens 或模型输出长度配置后重试。"
        )
    return normalized


async def _call_llm_provider(
    provider: Any,
    *,
    model: str,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None,
    temperature: float,
    max_tokens: int | None,
    extra_body: dict[str, Any] | None,
) -> dict[str, Any]:
    return await provider.call(
        model=model,
        messages=messages,
        tools=tools,
        temperature=temperature,
        max_tokens=max_tokens,
        extra_body=extra_body,
    )


def _format_target(provider_name: str, model: str) -> str:
    """格式化 provider:model 目标标识，用于提示文案。"""
    return f"{provider_name}:{model}"


def _fallback_targets(provider_name: str, model: str) -> list[tuple[str, str]]:
    """构造受控回退链路：当前模型 -> default model -> mock。"""
    targets: list[tuple[str, str]] = [(provider_name, model)]
    default_target = config.resolve_model(config.get("llm.default_model", "mock"))
    mock_target = config.resolve_model("mock")

    if default_target not in targets:
        targets.append(default_target)
    if mock_target not in targets:
        targets.append(mock_target)
    return targets


class _RequestBlockSuccess:
    """单个 provider:model 请求块执行成功结果。"""

    def __init__(
        self,
        *,
        provider_name: str,
        model: str,
        response: dict[str, Any],
        duration_ms: int,
        used_max_tokens: int | None,
        retried_for_max_tokens: bool,
    ):
        self.provider_name = provider_name
        self.model = model
        self.response = response
        self.duration_ms = duration_ms
        self.used_max_tokens = used_max_tokens
        self.retried_for_max_tokens = retried_for_max_tokens


class _RequestBlockFailure:
    """单个 provider:model 请求块执行失败结果。"""

    def __init__(
        self,
        *,
        provider_name: str,
        model: str,
        exc: Exception,
        error_message: str,
        normalized_error: dict[str, Any],
        duration_ms: int,
        used_max_tokens: int | None,
        retried_for_max_tokens: bool,
    ):
        self.provider_name = provider_name
        self.model = model
        self.exc = exc
        self.error_message = error_message
        self.normalized_error = normalized_error
        self.duration_ms = duration_ms
        self.used_max_tokens = used_max_tokens
        self.retried_for_max_tokens = retried_for_max_tokens


async def _publish_session_notification(
    bus: PrivateEventBus,
    *,
    session_id: str,
    turn_id: str | None,
    trace_id: str | None,
    title: str,
    body: str,
) -> None:
    """向当前对话追加一条系统提示。"""
    await bus.publish(
        EventEnvelope(
            type=NOTIFICATION_SESSION,
            session_id=session_id,
            turn_id=turn_id,
            trace_id=trace_id,
            source="llm",
            payload={
                "title": title,
                "body": body,
                "level": "info",
                "metadata": {"append_to_chat": True, "show_toast": False, "show_browser": False},
            },
        )
    )


async def _publish_llm_success(
    bus: PrivateEventBus,
    *,
    session_id: str,
    turn_id: str | None,
    trace_id: str | None,
    llm_call_id: str | None,
    response: dict[str, Any],
) -> None:
    """发布成功的 LLM 结果事件。"""
    await bus.publish(
        EventEnvelope(
            type=LLM_CALL_RESULT,
            session_id=session_id,
            turn_id=turn_id,
            trace_id=trace_id,
            source="llm",
            payload={
                "llm_call_id": llm_call_id,
                "response": {
                    "content": response.get("content", ""),
                    "tool_calls": response.get("tool_calls", []),
                    **({"reasoning_details": response["reasoning_details"]} if response.get("reasoning_details") else {}),
                    **({"provider_specific_fields": response["provider_specific_fields"]} if response.get("provider_specific_fields") else {}),
                },
                "usage": response.get("usage", {}),
                "finish_reason": response.get("finish_reason", "stop"),
            },
        )
    )
    await bus.publish(
        EventEnvelope(
            type=LLM_CALL_COMPLETED,
            session_id=session_id,
            turn_id=turn_id,
            trace_id=trace_id,
            source="llm",
            payload={"llm_call_id": llm_call_id},
        )
    )


async def _publish_llm_error(
    bus: PrivateEventBus,
    *,
    session_id: str,
    turn_id: str | None,
    trace_id: str | None,
    llm_call_id: str | None,
    exc: Exception,
    normalized_error: dict[str, Any],
    error_message: str,
) -> None:
    """发布最终失败的错误结果事件。"""
    await bus.publish(
        EventEnvelope(
            type=ERROR_RAISED,
            session_id=session_id,
            turn_id=turn_id,
            trace_id=trace_id,
            source="llm",
            payload={
                "error_type": type(exc).__name__,
                "error_code": normalized_error["error_code"],
                "error_message": error_message,
                "user_message": normalized_error["user_message"],
                "context": normalized_error["context"],
            },
        )
    )
    await bus.publish(
        EventEnvelope(
            type=LLM_CALL_RESULT,
            session_id=session_id,
            turn_id=turn_id,
            trace_id=trace_id,
            source="llm",
            payload={
                "llm_call_id": llm_call_id,
                "response": {"content": normalized_error["user_message"], "tool_calls": []},
                "usage": {},
                "finish_reason": "error",
            },
        )
    )
    await bus.publish(
        EventEnvelope(
            type=LLM_CALL_COMPLETED,
            session_id=session_id,
            turn_id=turn_id,
            trace_id=trace_id,
            source="llm",
            payload={"llm_call_id": llm_call_id},
        )
    )


def _get_debug_base() -> Path:
    """获取 debug 日志根目录: $SENSENOVA_CLAW_HOME/logs/debug/llm"""
    from sensenova_claw.platform.config.workspace import resolve_sensenova_claw_home
    return resolve_sensenova_claw_home(config) / "logs" / "debug" / "llm"


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

    目录结构: $SENSENOVA_CLAW_HOME/logs/debug/llm/{date}/{session_id}/{llm_call_id}.json
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

    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    filepath = out_dir / f"llm_{ts}_{llm_call_id}.json"
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

    async def _execute_request_block(
        self,
        *,
        event: EventEnvelope,
        llm_call_id: str | None,
        provider_name: str,
        model: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
        temperature: float,
        max_tokens: int | None,
        extra_body: dict[str, Any] | None,
        input_data: dict[str, Any],
    ) -> _RequestBlockSuccess | _RequestBlockFailure:
        """执行单个 provider:model 的完整请求块，内部可做同目标重试。"""
        attempt_max_tokens = max_tokens
        retried_for_max_tokens = False

        while True:
            t0 = time.monotonic()
            try:
                provider = self.rt.factory.get_provider(provider_name)
                resp = await _call_llm_provider(
                    provider,
                    model=model,
                    messages=messages,
                    tools=tools,
                    temperature=temperature,
                    max_tokens=attempt_max_tokens,
                    extra_body=extra_body,
                )
                duration_ms = int((time.monotonic() - t0) * 1000)

                if _LLM_DEBUG:
                    success_input = dict(input_data)
                    success_input["provider"] = provider_name
                    success_input["model"] = model
                    success_input["max_tokens"] = attempt_max_tokens
                    if retried_for_max_tokens:
                        success_input["auto_retry"] = {
                            "reason": "max_tokens_out_of_range",
                            "original_max_tokens": max_tokens,
                            "retry_max_tokens": attempt_max_tokens,
                        }
                    _save_llm_debug(
                        session_id=event.session_id,
                        llm_call_id=llm_call_id,
                        provider=provider_name,
                        model=model,
                        input_data=success_input,
                        output_data=resp,
                        duration_ms=duration_ms,
                    )

                return _RequestBlockSuccess(
                    provider_name=provider_name,
                    model=model,
                    response=resp,
                    duration_ms=duration_ms,
                    used_max_tokens=attempt_max_tokens,
                    retried_for_max_tokens=retried_for_max_tokens,
                )
            except Exception as exc:  # noqa: BLE001
                error_message = str(exc).strip() or type(exc).__name__
                normalized_error = _normalize_llm_error(provider_name, model, error_message)
                limit = normalized_error["context"].get("limit")

                if (
                    not retried_for_max_tokens
                    and normalized_error["error_code"] == "max_tokens_out_of_range"
                    and isinstance(limit, int)
                    and isinstance(attempt_max_tokens, int)
                    and attempt_max_tokens > limit
                ):
                    retried_for_max_tokens = True
                    logger.warning(
                        "llm call max_tokens out of range, retry with capped value provider=%s model=%s requested=%s limit=%s",
                        provider_name,
                        model,
                        attempt_max_tokens,
                        limit,
                    )
                    await _publish_session_notification(
                        self.bus,
                        session_id=event.session_id,
                        turn_id=event.turn_id,
                        trace_id=llm_call_id,
                        title="LLM 参数调整",
                        body=(
                            f"{_format_target(provider_name, model)} 的 max_tokens 超出模型上限，"
                            f"已自动调整为 {limit} 并重试。"
                        ),
                    )
                    attempt_max_tokens = limit
                    continue

                duration_ms = int((time.monotonic() - t0) * 1000)
                logger.exception(
                    "llm call failed provider=%s model=%s",
                    provider_name,
                    model,
                )

                if _LLM_DEBUG:
                    failed_input = dict(input_data)
                    failed_input["provider"] = provider_name
                    failed_input["model"] = model
                    failed_input["max_tokens"] = attempt_max_tokens
                    if retried_for_max_tokens:
                        failed_input["auto_retry"] = {
                            "reason": "max_tokens_out_of_range",
                            "original_max_tokens": max_tokens,
                            "retry_max_tokens": attempt_max_tokens,
                        }
                    _save_llm_debug(
                        session_id=event.session_id,
                        llm_call_id=llm_call_id,
                        provider=provider_name,
                        model=model,
                        input_data=failed_input,
                        output_data={},
                        duration_ms=duration_ms,
                        error=error_message,
                    )

                return _RequestBlockFailure(
                    provider_name=provider_name,
                    model=model,
                    exc=exc,
                    error_message=error_message,
                    normalized_error=normalized_error,
                    duration_ms=duration_ms,
                    used_max_tokens=attempt_max_tokens,
                    retried_for_max_tokens=retried_for_max_tokens,
                )

    async def _run_fallback_chain(
        self,
        *,
        event: EventEnvelope,
        llm_call_id: str | None,
        fallback_targets: list[tuple[str, str]],
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
        temperature: float,
        max_tokens: int | None,
        extra_body: dict[str, Any] | None,
        input_data: dict[str, Any],
    ) -> _RequestBlockSuccess | _RequestBlockFailure:
        """按 current -> default -> mock 顺序执行多个请求块。"""
        last_failure: _RequestBlockFailure | None = None

        for index, (provider_name, model) in enumerate(fallback_targets):
            result = await self._execute_request_block(
                event=event,
                llm_call_id=llm_call_id,
                provider_name=provider_name,
                model=model,
                messages=messages,
                tools=tools,
                temperature=temperature,
                max_tokens=max_tokens,
                extra_body=extra_body,
                input_data=input_data,
            )
            if isinstance(result, _RequestBlockSuccess):
                return result

            last_failure = result
            next_index = index + 1
            if next_index < len(fallback_targets):
                fallback_provider, fallback_model = fallback_targets[next_index]
                await _publish_session_notification(
                    self.bus,
                    session_id=event.session_id,
                    turn_id=event.turn_id,
                    trace_id=llm_call_id,
                    title="LLM 调用失败",
                    body=(
                        f"{_format_target(result.provider_name, result.model)} 调用失败："
                        f"{result.normalized_error['user_message']}"
                    ),
                )
                await _publish_session_notification(
                    self.bus,
                    session_id=event.session_id,
                    turn_id=event.turn_id,
                    trace_id=llm_call_id,
                    title="LLM 回退",
                    body=(
                        f"已回退到 {_format_target(fallback_provider, fallback_model)}。"
                    ),
                )

        if last_failure is None:
            raise RuntimeError("fallback chain produced no result")
        return last_failure

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

        result = await self._run_fallback_chain(
            event=event,
            llm_call_id=llm_call_id,
            fallback_targets=_fallback_targets(provider_name, model),
            messages=messages,
            tools=tools,
            temperature=temperature,
            max_tokens=max_tokens,
            extra_body=extra_body,
            input_data=input_data,
        )

        if isinstance(result, _RequestBlockSuccess):
            await _publish_llm_success(
                self.bus,
                session_id=event.session_id,
                turn_id=event.turn_id,
                trace_id=llm_call_id,
                llm_call_id=llm_call_id,
                response=result.response,
            )
            return

        if isinstance(result, _RequestBlockFailure):
            await _publish_llm_error(
                self.bus,
                session_id=event.session_id,
                turn_id=event.turn_id,
                trace_id=llm_call_id,
                llm_call_id=llm_call_id,
                exc=result.exc,
                normalized_error=result.normalized_error,
                error_message=result.error_message,
            )
            return

        raise RuntimeError("unexpected fallback result")
