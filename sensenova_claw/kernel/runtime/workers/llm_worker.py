from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

from sensenova_claw.platform.config.config import config
from sensenova_claw.kernel.events.bus import PrivateEventBus
from sensenova_claw.kernel.events.envelope import EventEnvelope
from sensenova_claw.kernel.events.types import (
    ERROR_RAISED,
    LLM_CALL_COMPLETED,
    LLM_CALL_DELTA,
    LLM_CALL_REQUESTED,
    LLM_CALL_RESULT,
    LLM_CALL_STARTED,
    NOTIFICATION_SESSION,
    USER_TURN_CANCEL_REQUESTED,
)
from sensenova_claw.kernel.runtime.workers.base import SessionWorker

if TYPE_CHECKING:
    from sensenova_claw.kernel.runtime.llm_runtime import LLMRuntime

logger = logging.getLogger(__name__)

_LLM_DEBUG = os.environ.get("SENSENOVA_CLAW_DEBUG_LLM", "").strip() not in ("", "0", "false")


def _merge_default_extra_body(extra_body: dict[str, Any] | None) -> dict[str, Any]:
    merged = dict(config.get("agent.extra_body", {}))
    if extra_body:
        merged.update(extra_body)
    return merged


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
    cloudsway_match = re.search(r"supports at most\s*(\d+)\s*completion tokens", error_message, flags=re.IGNORECASE)
    gemini_range_match = re.search(
        r"supported range is from\s*(\d+)\s*\(inclusive\)\s*to\s*(\d+)\s*\(exclusive\)",
        error_message,
        flags=re.IGNORECASE,
    )
    if match or alt_match or cloudsway_match or gemini_range_match:
        if match:
            limit = int(match.group(2))
        elif alt_match:
            limit = int(alt_match.group(1))
        elif gemini_range_match:
            limit = int(gemini_range_match.group(2)) - 1
        else:
            limit = int(cloudsway_match.group(1))
        context["limit"] = limit
        normalized["error_code"] = "max_tokens_out_of_range"
        normalized["user_message"] = (
            f"当前模型允许的最大输出长度超限，最大不能超过 {limit}。"
            "请调小 max_tokens 或模型输出长度配置后重试。"
        )

    unsupported_params = _extract_unsupported_parameters(error_message)
    if unsupported_params:
        context["unsupported_params"] = unsupported_params
        normalized["error_code"] = "unsupported_parameters"
        normalized["user_message"] = (
            "当前模型或网关不支持以下请求参数："
            f"{', '.join(unsupported_params)}。"
            "系统会尝试自动移除后重试。"
        )

    conflicting_params = _extract_conflicting_parameters(error_message)
    if conflicting_params:
        context["conflicting_params"] = conflicting_params
        normalized["error_code"] = "conflicting_parameters"
        normalized["user_message"] = (
            "当前模型或网关不允许同时指定以下参数："
            f"{', '.join(conflicting_params)}。"
            "系统会尝试仅保留第一个参数后重试。"
        )
    return normalized


def _extract_unsupported_parameters(error_message: str) -> list[str]:
    """从错误消息中提取不支持的参数名。"""
    normalized_message = error_message.replace("\\'", "'").replace('\\"', '"')
    candidates: list[str] = []

    single_patterns = [
        r"Unknown parameter:\s*['\"]([^'\"]+)['\"]",
        r"Unsupported parameter:\s*['\"]([^'\"]+)['\"]",
    ]
    for pattern in single_patterns:
        candidates.extend(re.findall(pattern, normalized_message, flags=re.IGNORECASE))

    list_patterns = [
        r"Unknown parameters:\s*\[([^\]]+)\]",
        r"Unsupported parameters:\s*\[([^\]]+)\]",
    ]
    for pattern in list_patterns:
        for raw_group in re.findall(pattern, normalized_message, flags=re.IGNORECASE):
            candidates.extend(re.findall(r"['\"]([^'\"]+)['\"]", raw_group))

    if re.search(r'"code"\s*:\s*"unknown_parameter"', normalized_message, flags=re.IGNORECASE):
        candidates.extend(re.findall(r'"param"\s*:\s*"([^"]+)"', normalized_message, flags=re.IGNORECASE))

    unique_params: list[str] = []
    for name in candidates:
        param = str(name).strip()
        if param and param not in unique_params:
            unique_params.append(param)
    return unique_params


def _extract_conflicting_parameters(error_message: str) -> list[str]:
    """从错误消息中提取互斥参数名，保留原始顺序。"""
    normalized_message = error_message.replace("\\'", "'").replace('\\"', '"')
    match = re.search(
        r"[`'\"]?([a-zA-Z_][a-zA-Z0-9_]*)[`'\"]?\s+and\s+[`'\"]?([a-zA-Z_][a-zA-Z0-9_]*)[`'\"]?\s+cannot both be specified",
        normalized_message,
        flags=re.IGNORECASE,
    )
    if not match:
        return []
    return [match.group(1), match.group(2)]


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


async def _stream_llm_provider(
    provider: Any,
    *,
    bus: PrivateEventBus,
    session_id: str,
    turn_id: str | None,
    trace_id: str | None,
    llm_call_id: str | None,
    model: str,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None,
    temperature: float,
    max_tokens: int | None,
    extra_body: dict[str, Any] | None,
    should_stop: Callable[[], bool] | None = None,
) -> dict[str, Any]:
    """流式调用 provider，逐 chunk 发布 LLM_CALL_DELTA，最终返回聚合结果。"""
    content_acc = ""
    reasoning_acc = ""
    finish_data: dict[str, Any] = {}

    async for chunk in provider.stream_call(
        model=model,
        messages=messages,
        tools=tools,
        temperature=temperature,
        max_tokens=max_tokens,
        extra_body=extra_body,
    ):
        if should_stop and should_stop():
            raise asyncio.CancelledError
        chunk_type = chunk.get("type")

        if chunk_type == "delta":
            content_piece = chunk.get("content", "")
            reasoning_piece = chunk.get("reasoning_content", "")
            content_acc += content_piece
            reasoning_acc += reasoning_piece

            await bus.publish(
                EventEnvelope(
                    type=LLM_CALL_DELTA,
                    session_id=session_id,
                    turn_id=turn_id,
                    trace_id=trace_id,
                    source="llm",
                    payload={
                        "llm_call_id": llm_call_id,
                        "content_delta": content_piece,
                        "reasoning_delta": reasoning_piece,
                        "content_snapshot": content_acc,
                    },
                )
            )
        elif chunk_type == "finish":
            finish_data = chunk

    if should_stop and should_stop():
        raise asyncio.CancelledError

    result: dict[str, Any] = {
        "content": content_acc,
        "tool_calls": finish_data.get("tool_calls", []),
        "finish_reason": finish_data.get("finish_reason", "stop"),
        "usage": finish_data.get("usage", {}),
    }
    if reasoning_acc:
        result["reasoning_details"] = [{"type": "thinking", "thinking": reasoning_acc}]
    if finish_data.get("reasoning_details"):
        result["reasoning_details"] = finish_data["reasoning_details"]
    return result


def _format_target(provider_name: str, model: str) -> str:
    """格式化 provider:model 目标标识，用于提示文案。"""
    return f"{provider_name}:{model}"


def _provider_is_available(provider_name: str) -> bool:
    """判断 provider 当前是否可用。"""
    if provider_name == "mock":
        return True
    provider_cfg = config.get(f"llm.providers.{provider_name}", {})
    api_key = str(provider_cfg.get("api_key", ""))
    return bool(api_key) and not api_key.startswith("${")


def _first_available_llm_target(
    excluded_targets: set[tuple[str, str]],
) -> tuple[str, str] | None:
    """按 llm.models 配置顺序，返回第一个可用的非 mock 模型。"""
    models = config.get("llm.models", {})
    for model_key, entry in models.items():
        if not isinstance(entry, dict):
            continue
        provider_name = str(entry.get("provider", "mock"))
        if provider_name == "mock" or not _provider_is_available(provider_name):
            continue
        target = (provider_name, str(entry.get("model_id", model_key)))
        if target not in excluded_targets:
            return target
    return None


def _fallback_targets(provider_name: str, model: str) -> list[tuple[str, str]]:
    """构造受控回退链路：当前模型 -> default model -> 第一个可用 LLM。

    不会自动回退到 mock provider——当所有真实 provider 不可用时，
    应明确报错而非返回无意义的 mock 响应。
    """
    targets: list[tuple[str, str]] = []
    # mock 不作为回退目标——生产环境下静默返回 mock 文案会破坏正确性
    if provider_name != "mock":
        targets.append((provider_name, model))
    default_target = config.resolve_model(config.get("llm.default_model", "mock"))

    # 仅当 default_model 不是 mock 时才加入回退链
    if default_target[0] != "mock" and default_target not in targets:
        targets.append(default_target)
    available_target = _first_available_llm_target(set(targets))
    if available_target and available_target not in targets:
        targets.append(available_target)
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
        self._active_tasks: set[asyncio.Task[None]] = set()
        self._turn_tasks: dict[str, set[asyncio.Task[None]]] = {}

    async def stop(self) -> None:
        for task in list(self._active_tasks):
            task.cancel()
        await super().stop()
        for task in list(self._active_tasks):
            with contextlib.suppress(asyncio.CancelledError):
                await task
        self._active_tasks.clear()
        self._turn_tasks.clear()

    async def _handle(self, event: EventEnvelope) -> None:
        if event.type == LLM_CALL_REQUESTED:
            self._start_llm_request(event)
        elif event.type == USER_TURN_CANCEL_REQUESTED:
            self._cancel_turn_requests(event)

    def _start_llm_request(self, event: EventEnvelope) -> None:
        task = asyncio.create_task(self._run_llm_request(event))
        self._active_tasks.add(task)
        if event.turn_id:
            self._turn_tasks.setdefault(event.turn_id, set()).add(task)
        task.add_done_callback(lambda done_task, turn_id=event.turn_id: self._cleanup_task(turn_id, done_task))

    async def _run_llm_request(self, event: EventEnvelope) -> None:
        try:
            await self._handle_llm_requested(event)
        except asyncio.CancelledError:
            logger.info(
                "cancel llm request task session=%s turn=%s trace=%s",
                event.session_id,
                event.turn_id,
                event.trace_id,
            )
        except Exception:
            logger.exception(
                "llm request task crashed session=%s turn=%s trace=%s",
                event.session_id,
                event.turn_id,
                event.trace_id,
            )

    def _cleanup_task(self, turn_id: str | None, task: asyncio.Task[None]) -> None:
        self._active_tasks.discard(task)
        if not turn_id:
            return
        tasks = self._turn_tasks.get(turn_id)
        if not tasks:
            return
        tasks.discard(task)
        if not tasks:
            self._turn_tasks.pop(turn_id, None)

    def _resolve_turn_id(self, event: EventEnvelope) -> str | None:
        if event.turn_id:
            return event.turn_id
        state_store = getattr(self.rt, "state_store", None)
        if state_store is None:
            return None
        latest_turn = state_store.latest_turn(event.session_id)
        return latest_turn.turn_id if latest_turn else None

    def _cancel_turn_requests(self, event: EventEnvelope) -> None:
        turn_id = self._resolve_turn_id(event)
        if not turn_id:
            return
        tasks = list(self._turn_tasks.get(turn_id, ()))
        if not tasks:
            return
        logger.info(
            "cancel active llm tasks session=%s turn=%s count=%s",
            event.session_id,
            turn_id,
            len(tasks),
        )
        for task in tasks:
            task.cancel()

    def _is_turn_cancelled(self, event: EventEnvelope) -> bool:
        if not event.turn_id:
            return False
        state_store = getattr(self.rt, "state_store", None)
        if state_store is None:
            return False
        return state_store.is_turn_cancelled(event.session_id, event.turn_id)

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
        stream: bool = False,
    ) -> _RequestBlockSuccess | _RequestBlockFailure:
        """执行单个 provider:model 的完整请求块，内部可做同目标重试。"""
        attempt_max_tokens = max_tokens
        attempt_temperature = temperature
        attempt_extra_body = dict(extra_body) if extra_body else None
        retried_for_max_tokens = False
        unsupported_retry_count = 0
        conflicting_retry_count = 0
        retry_actions: list[dict[str, Any]] = []

        while True:
            t0 = time.monotonic()
            try:
                provider = self.rt.factory.get_provider(provider_name)
                should_stop = lambda: self._is_turn_cancelled(event)
                if stream:
                    resp = await _stream_llm_provider(
                        provider,
                        bus=self.bus,
                        session_id=event.session_id,
                        turn_id=event.turn_id,
                        trace_id=llm_call_id,
                        llm_call_id=llm_call_id,
                        model=model,
                        messages=messages,
                        tools=tools,
                        temperature=attempt_temperature,
                        max_tokens=attempt_max_tokens,
                        extra_body=attempt_extra_body,
                        should_stop=should_stop,
                    )
                else:
                    resp = await _call_llm_provider(
                        provider,
                        model=model,
                        messages=messages,
                        tools=tools,
                        temperature=attempt_temperature,
                        max_tokens=attempt_max_tokens,
                        extra_body=attempt_extra_body,
                    )
                duration_ms = int((time.monotonic() - t0) * 1000)

                if _LLM_DEBUG:
                    success_input = dict(input_data)
                    success_input["provider"] = provider_name
                    success_input["model"] = model
                    success_input["max_tokens"] = attempt_max_tokens
                    success_input["temperature"] = attempt_temperature
                    success_input["extra_body"] = attempt_extra_body
                    if retry_actions:
                        success_input["auto_retry"] = list(retry_actions)
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
                    retry_actions.append(
                        {
                            "reason": "max_tokens_out_of_range",
                            "original_max_tokens": max_tokens,
                            "retry_max_tokens": limit,
                        }
                    )
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

                unsupported_params = normalized_error["context"].get("unsupported_params") or []
                removable_params = [
                    param for param in unsupported_params
                    if isinstance(attempt_extra_body, dict) and param in attempt_extra_body
                ]
                if (
                    normalized_error["error_code"] == "unsupported_parameters"
                    and removable_params
                    and unsupported_retry_count < 3
                ):
                    unsupported_retry_count += 1
                    logger.warning(
                        "llm call has unsupported parameters, retry without params provider=%s model=%s params=%s attempt=%s",
                        provider_name,
                        model,
                        removable_params,
                        unsupported_retry_count,
                    )
                    await _publish_session_notification(
                        self.bus,
                        session_id=event.session_id,
                        turn_id=event.turn_id,
                        trace_id=llm_call_id,
                        title="LLM 参数调整",
                        body=(
                            f"{_format_target(provider_name, model)} 不支持参数 "
                            f"{', '.join(removable_params)}，已自动移除后重试。"
                        ),
                    )
                    retry_actions.append(
                        {
                            "reason": "unsupported_parameters",
                            "removed_params": list(removable_params),
                            "retry_round": unsupported_retry_count,
                        }
                    )
                    next_extra_body = dict(attempt_extra_body)
                    for param in removable_params:
                        next_extra_body[param] = None
                    attempt_extra_body = next_extra_body
                    continue

                conflicting_params = normalized_error["context"].get("conflicting_params") or []
                removable_conflicting_params = list(conflicting_params[1:]) if len(conflicting_params) > 1 else []
                if (
                    normalized_error["error_code"] == "conflicting_parameters"
                    and removable_conflicting_params
                    and conflicting_retry_count < 3
                ):
                    conflicting_retry_count += 1
                    removed_params: list[str] = []
                    next_extra_body = dict(attempt_extra_body) if attempt_extra_body else {}
                    for param in removable_conflicting_params:
                        if param == "temperature":
                            attempt_temperature = None
                            removed_params.append(param)
                            continue
                        if param in next_extra_body:
                            next_extra_body[param] = None
                            removed_params.append(param)

                    if removed_params:
                        logger.warning(
                            "llm call has conflicting parameters, retry keeping first param provider=%s model=%s params=%s kept=%s attempt=%s",
                            provider_name,
                            model,
                            removed_params,
                            conflicting_params[0],
                            conflicting_retry_count,
                        )
                        await _publish_session_notification(
                            self.bus,
                            session_id=event.session_id,
                            turn_id=event.turn_id,
                            trace_id=llm_call_id,
                            title="LLM 参数调整",
                            body=(
                                f"{_format_target(provider_name, model)} 的参数 "
                                f"{', '.join(conflicting_params)} 互斥，已仅保留 {conflicting_params[0]} 后重试。"
                            ),
                        )
                        retry_actions.append(
                            {
                                "reason": "conflicting_parameters",
                                "kept_param": conflicting_params[0],
                                "removed_params": list(removed_params),
                                "retry_round": conflicting_retry_count,
                            }
                        )
                        attempt_extra_body = next_extra_body or None
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
                    failed_input["temperature"] = attempt_temperature
                    failed_input["extra_body"] = attempt_extra_body
                    if retry_actions:
                        failed_input["auto_retry"] = list(retry_actions)
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
        stream: bool = False,
    ) -> _RequestBlockSuccess | _RequestBlockFailure:
        """按 current -> default -> 其他可用模型 顺序执行多个请求块。"""
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
                stream=stream,
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
            else:
                # 所有 provider 均已失败，发出最终通知
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
                    title="无可用 LLM",
                    body="当前没有可用的 LLM，请前往「配置」页面添加至少一个可用的大模型，然后联系运维工程师完成其余配置。",
                )

        if last_failure is None:
            raise RuntimeError("fallback chain produced no result")
        return last_failure

    async def _handle_llm_requested(self, event: EventEnvelope) -> None:
        if self._is_turn_cancelled(event):
            logger.info(
                "skip llm request for cancelled turn session=%s turn=%s",
                event.session_id,
                event.turn_id,
            )
            return
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
        temperature = float(event.payload.get("temperature", config.get("agent.temperature", 1.0)))
        max_tokens = event.payload.get("max_tokens")
        extra_body = _merge_default_extra_body(event.payload.get("extra_body") or None)

        logger.debug(
            "LLM call input | provider=%s model=%s llm_call_id=%s extra_body=%s messages=%s tools=%s",
            provider_name, model, llm_call_id, extra_body, messages, tools,
        )

        if self._is_turn_cancelled(event):
            logger.info(
                "skip llm started publish for cancelled turn session=%s turn=%s",
                event.session_id,
                event.turn_id,
            )
            return

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

        # 流式开关：事件 payload 优先，否则读全局配置
        stream = event.payload.get("stream")
        if stream is None:
            stream = config.get("agent.stream", True)
        stream = bool(stream)

        input_data = {
            "messages": messages,
            "tools": tools,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "extra_body": extra_body,
            "stream": stream,
        }

        targets = _fallback_targets(provider_name, model)
        if not targets:
            # 所有解析出的 provider 都是 mock，没有可用的真实 LLM
            logger.error(
                "无可用的真实 LLM provider，当前解析结果为 mock | session=%s turn=%s",
                event.session_id, event.turn_id,
            )
            await _publish_session_notification(
                self.bus,
                session_id=event.session_id,
                turn_id=event.turn_id,
                trace_id=llm_call_id,
                title="无可用 LLM",
                body="当前没有可用的 LLM，请前往「配置」页面添加至少一个可用的大模型。",
            )
            await _publish_llm_error(
                self.bus,
                session_id=event.session_id,
                turn_id=event.turn_id,
                trace_id=llm_call_id,
                llm_call_id=llm_call_id,
                exc=RuntimeError("no real LLM provider available"),
                normalized_error={
                    "error_type": "no_provider",
                    "user_message": "当前没有可用的 LLM，请检查配置。",
                },
                error_message="no real LLM provider available",
            )
            return

        result = await self._run_fallback_chain(
            event=event,
            llm_call_id=llm_call_id,
            fallback_targets=targets,
            messages=messages,
            tools=tools,
            temperature=temperature,
            max_tokens=max_tokens,
            extra_body=extra_body,
            input_data=input_data,
            stream=stream,
        )

        if self._is_turn_cancelled(event):
            logger.info(
                "drop llm result for cancelled turn session=%s turn=%s",
                event.session_id,
                event.turn_id,
            )
            return

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
