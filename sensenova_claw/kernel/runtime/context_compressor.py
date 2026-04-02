"""上下文压缩模块

当对话历史过长时，通过两阶段压缩策略减少 token 数量：
- 第一阶段：Turn 级压缩（摘要用户输入和工具调用）
- 第二阶段：合并压缩（多 Turn 合并为单个对话对）
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class TokenCounter:
    """基于 tiktoken 的 token 计数器，tiktoken 不可用时回退到字符估算。"""

    def __init__(self):
        self._encoder = None
        try:
            import tiktoken
            self._encoder = tiktoken.get_encoding("cl100k_base")
        except Exception:
            logger.warning("tiktoken 初始化失败，回退到字符估算")

    def count_text(self, text: str) -> int:
        if not text:
            return 0
        if self._encoder:
            return len(self._encoder.encode(text))
        return self._estimate_tokens(text)

    def count_messages(self, messages: list[dict[str, Any]]) -> int:
        total = 0
        for msg in messages:
            total += 4  # 结构开销
            content = msg.get("content") or ""
            total += self.count_text(content)
            if msg.get("name"):
                total += self.count_text(msg["name"])
            if msg.get("tool_calls"):
                total += self.count_text(json.dumps(msg["tool_calls"], ensure_ascii=False))
            if msg.get("tool_call_id"):
                total += self.count_text(msg["tool_call_id"])
        return total

    @staticmethod
    def _estimate_tokens(text: str) -> int:
        return max(1, len(text) // 3)


def parse_turn_boundaries(history: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """根据 role='user' 消息位置解析 turn 边界。

    返回:
        [{"start": int, "end": int, "messages": list[dict]}, ...]
    """
    if not history:
        return []

    turns: list[dict[str, Any]] = []
    current_start: int | None = None

    for i, msg in enumerate(history):
        if msg.get("role") == "user":
            if current_start is not None:
                turns.append({
                    "start": current_start,
                    "end": i,
                    "messages": history[current_start:i],
                })
            current_start = i

    if current_start is not None:
        turns.append({
            "start": current_start,
            "end": len(history),
            "messages": history[current_start:],
        })

    return turns


def save_original_messages(
    base_dir: str,
    session_id: str,
    phase: int,
    messages: list[dict[str, Any]],
    original_token_count: int,
    compressed_token_count: int,
    turn_id: str | None = None,
    chunk_index: int | None = None,
) -> str:
    """将压缩前的原始消息保存为 JSON 文件，返回文件路径。"""
    session_dir = Path(base_dir) / session_id
    session_dir.mkdir(parents=True, exist_ok=True)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    if phase == 1 and turn_id:
        filename = f"compression_phase1_{turn_id}_{ts}.json"
    else:
        chunk_label = f"chunk{chunk_index}" if chunk_index is not None else "chunk"
        filename = f"compression_phase2_{chunk_label}_{ts}.json"

    record = {
        "phase": phase,
        "session_id": session_id,
        "turn_id": turn_id,
        "timestamp": datetime.now().isoformat(),
        "original_messages": messages,
        "original_token_count": original_token_count,
        "compressed_token_count": compressed_token_count,
    }

    filepath = session_dir / filename
    filepath.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(filepath)


# ── LLM 摘要 Prompt ────────────────────────────────────────

PROMPT_SUMMARIZE_USER_INPUT = (
    "请将以下用户输入总结为不超过{max_tokens}个token的简洁摘要，保留关键意图和信息：\n\n{content}"
)

PROMPT_SUMMARIZE_TOOL_CALLS = (
    "请将以下工具调用过程总结为不超过{max_tokens}个token的简洁描述，"
    "包含：调用了什么工具、输入参数要点、返回结果要点：\n\n{content}"
)

PROMPT_MERGE_TURNS = (
    "请将以下多轮对话合并总结为一个不超过{max_tokens}个token的对话摘要，"
    "格式为\"用户请求→助手响应\"，保留关键决策和结论：\n\n{content}"
)

PROMPT_RE_SUMMARIZE = (
    "以下摘要仍然过长，请进一步精简至不超过{max_tokens}个token，只保留最核心的信息：\n\n{content}"
)

COMPRESSION_MARKER = "\n\n[此部分已压缩，原文保存在: {file_path}]"


@dataclass
class CompressedTurn:
    turn_id: str
    original_token_count: int
    compressed_token_count: int
    phase: int
    original_file_path: str


class ContextCompressor:
    """上下文压缩器：两阶段压缩策略"""

    def __init__(
        self,
        config: Any,
        llm_factory: Any,
        provider_name: str,
        model: str,
        sensenova_claw_home: str,
    ):
        self._config = config
        self._llm_factory = llm_factory
        self._provider_name = provider_name
        self._model = model
        self._sensenova_claw_home = sensenova_claw_home
        self._token_counter = TokenCounter()
        self._locks: dict[str, asyncio.Lock] = {}

    def _get_lock(self, session_id: str) -> asyncio.Lock:
        if session_id not in self._locks:
            self._locks[session_id] = asyncio.Lock()
        return self._locks[session_id]

    def cleanup_session(self, session_id: str) -> None:
        """清理会话相关资源（锁），防止内存泄漏。"""
        self._locks.pop(session_id, None)

    def _get_save_dir(self, session_id: str, agent_id: str) -> str:
        from sensenova_claw.platform.config.workspace import resolve_session_artifact_dir
        return str(resolve_session_artifact_dir(self._sensenova_claw_home, session_id, agent_id=agent_id).parent)

    def _cfg(self, key: str, default: Any = None) -> Any:
        return self._config.get(f"context_compression.{key}", default)

    async def compress_if_needed(
        self,
        session_id: str,
        history: list[dict[str, Any]],
        agent_id: str = "default",
    ) -> list[dict[str, Any]]:
        """LLM 调用前兜底：检查并压缩，返回处理后的 history"""
        lock = self._get_lock(session_id)
        async with lock:
            return await self._do_compress(session_id, history, agent_id)

    async def compress_async(
        self,
        session_id: str,
        history: list[dict[str, Any]],
        agent_id: str = "default",
    ) -> list[dict[str, Any]]:
        """轮末异步压缩"""
        lock = self._get_lock(session_id)
        async with lock:
            return await self._do_compress(session_id, history, agent_id)

    async def _do_compress(
        self,
        session_id: str,
        history: list[dict[str, Any]],
        agent_id: str = "default",
    ) -> list[dict[str, Any]]:
        max_tokens = self._cfg("max_context_tokens", 128000)
        total_tokens = self._token_counter.count_messages(history)

        if total_tokens <= max_tokens * self._cfg("phase1_threshold", 0.8):
            return history

        turns = parse_turn_boundaries(history)
        if len(turns) <= 1:
            return history

        # 第一阶段
        history = await self._phase1_compress(session_id, history, turns, max_tokens, agent_id)

        # 检查第二阶段
        total_tokens = self._token_counter.count_messages(history)
        if total_tokens > max_tokens * self._cfg("phase2_trigger", 0.6):
            history = await self._phase2_compress(session_id, history, max_tokens, agent_id)

        return history

    async def _phase1_compress(
        self,
        session_id: str,
        history: list[dict[str, Any]],
        turns: list[dict[str, Any]],
        max_tokens: int,
        agent_id: str = "default",
    ) -> list[dict[str, Any]]:
        """第一阶段：Turn 级压缩

        IMPORTANT: 由于压缩会改变 history 长度，需要从前往后逐个处理，
        每次压缩后重新计算后续 turn 的索引偏移。
        使用 __compressed__ 标记已压缩的 turn，避免基于索引跟踪的问题。
        """
        threshold = max_tokens * self._cfg("phase1_threshold", 0.8)
        user_max = self._cfg("user_input_max_tokens", 1000)
        tool_max = self._cfg("tool_summary_max_tokens", 3000)

        # 从最早的 turn 开始累计 token，找到需要压缩的 turn
        # 跳过已压缩的 turn（首条消息带有 __compressed__ 标记）
        cumulative = 0
        turns_to_compress: list[int] = []
        for i, turn in enumerate(turns[:-1]):  # 不压缩最后一个 turn
            turn_tokens = self._token_counter.count_messages(turn["messages"])
            cumulative += turn_tokens
            first_msg = turn["messages"][0] if turn["messages"] else {}
            if not first_msg.get("__compressed__"):
                turns_to_compress.append(i)
            if cumulative > threshold:
                break

        if not turns_to_compress:
            return history

        # 从前往后处理，跟踪累积偏移量
        new_history = list(history)
        offset = 0
        save_dir = self._get_save_dir(session_id, agent_id)

        for turn_idx in turns_to_compress:
            turn = turns[turn_idx]
            start = turn["start"] + offset
            end = turn["end"] + offset
            original_msgs = new_history[start:end]
            orig_tokens = self._token_counter.count_messages(original_msgs)

            # 分离用户输入和 assistant/tool 部分
            user_msgs = [m for m in original_msgs if m.get("role") == "user"]
            non_user_msgs = [m for m in original_msgs if m.get("role") != "user"]

            compressed_msgs: list[dict[str, Any]] = []

            # 压缩用户输入
            for um in user_msgs:
                user_content = um.get("content", "")
                user_tokens = self._token_counter.count_text(user_content)
                if user_tokens > user_max:
                    summary = await self._llm_summarize(
                        PROMPT_SUMMARIZE_USER_INPUT, user_content, user_max,
                    )
                    compressed_msgs.append({"role": "user", "content": summary, "__compressed__": True})
                else:
                    compressed_msgs.append({**um, "__compressed__": True})

            # 压缩 assistant + tool 部分
            if non_user_msgs:
                non_user_text = self._messages_to_text(non_user_msgs)
                summary = await self._llm_summarize(
                    PROMPT_SUMMARIZE_TOOL_CALLS, non_user_text, tool_max,
                )
                compressed_msgs.append({"role": "assistant", "content": summary})

            comp_tokens = self._token_counter.count_messages(compressed_msgs)

            # 保存原文
            try:
                file_path = save_original_messages(
                    base_dir=save_dir,
                    session_id=session_id,
                    phase=1,
                    messages=original_msgs,
                    original_token_count=orig_tokens,
                    compressed_token_count=comp_tokens,
                    turn_id=f"turn_{turn_idx}",
                )
                if compressed_msgs:
                    last = compressed_msgs[-1]
                    last["content"] = (last.get("content") or "") + COMPRESSION_MARKER.format(file_path=file_path)
            except Exception:
                logger.warning("保存压缩原文失败 session=%s turn=%d", session_id, turn_idx, exc_info=True)

            # 替换 history 中的对应部分
            new_history[start:end] = compressed_msgs
            # 更新偏移量
            offset += len(compressed_msgs) - (end - start)

        return new_history

    async def _phase2_compress(
        self,
        session_id: str,
        history: list[dict[str, Any]],
        max_tokens: int,
        agent_id: str = "default",
    ) -> list[dict[str, Any]]:
        """第二阶段：合并压缩"""
        chunk_ratio = self._cfg("phase2_chunk_ratio", 0.3)
        merge_max = self._cfg("phase2_merge_max_tokens", 2000)
        chunk_limit = max_tokens * chunk_ratio

        turns = parse_turn_boundaries(history)
        if len(turns) <= 1:
            return history

        compressible = [
            turn
            for turn in turns[:-1]
            if not (turn["messages"] and turn["messages"][0].get("__phase2_compressed__"))
        ]
        last_turn = turns[-1]

        if not compressible:
            return history

        # 按 chunk_ratio 分块
        chunks: list[dict[str, Any]] = []
        current_chunk_msgs: list[dict[str, Any]] = []
        chunk_tokens = 0

        for turn in compressible:
            turn_tokens = self._token_counter.count_messages(turn["messages"])
            if chunk_tokens + turn_tokens > chunk_limit and current_chunk_msgs:
                chunks.append({"messages": list(current_chunk_msgs)})
                current_chunk_msgs = []
                chunk_tokens = 0
            current_chunk_msgs.extend(turn["messages"])
            chunk_tokens += turn_tokens

        if current_chunk_msgs:
            chunks.append({"messages": list(current_chunk_msgs)})

        # 合并压缩每个 chunk
        new_history: list[dict[str, Any]] = []
        save_dir = self._get_save_dir(session_id, agent_id)

        for ci, chunk in enumerate(chunks):
            original_msgs = chunk["messages"]
            orig_tokens = self._token_counter.count_messages(original_msgs)

            text = self._messages_to_text(original_msgs)
            summary = await self._llm_summarize(PROMPT_MERGE_TURNS, text, merge_max)

            comp_tokens = self._token_counter.count_text(summary)

            file_path = ""
            try:
                file_path = save_original_messages(
                    base_dir=save_dir,
                    session_id=session_id,
                    phase=2,
                    messages=original_msgs,
                    original_token_count=orig_tokens,
                    compressed_token_count=comp_tokens,
                    chunk_index=ci,
                )
            except Exception:
                logger.warning("保存第二阶段压缩原文失败 session=%s chunk=%d", session_id, ci, exc_info=True)

            marker = COMPRESSION_MARKER.format(file_path=file_path) if file_path else ""
            new_history.append({
                "role": "user",
                "content": f"[历史对话摘要 #{ci + 1}]",
                "__compressed__": True,
                "__phase2_compressed__": True,
            })
            new_history.append({
                "role": "assistant",
                "content": summary + marker,
                "__compressed__": True,
                "__phase2_compressed__": True,
            })

        # 追加最后一个 turn
        new_history.extend(last_turn["messages"])

        return new_history

    async def _llm_summarize(
        self,
        prompt_template: str,
        content: str,
        max_tokens: int,
    ) -> str:
        """调用 LLM 进行摘要，超限则再做一次"""
        prompt = prompt_template.format(max_tokens=max_tokens, content=content)
        provider = self._llm_factory.get_provider(self._provider_name)

        try:
            resp = await provider.call(
                model=self._model,
                messages=[{"role": "user", "content": prompt}],
                temperature=1.0,
                max_tokens=max_tokens * 2,
            )
            summary = resp.get("content", "")

            summary_tokens = self._token_counter.count_text(summary)
            if summary_tokens > max_tokens:
                re_prompt = PROMPT_RE_SUMMARIZE.format(max_tokens=max_tokens, content=summary)
                resp = await provider.call(
                    model=self._model,
                    messages=[{"role": "user", "content": re_prompt}],
                    temperature=1.0,
                    max_tokens=max_tokens * 2,
                )
                summary = resp.get("content", summary)

            return summary
        except Exception:
            logger.warning("LLM 摘要调用失败，返回原文截断", exc_info=True)
            max_chars = max_tokens * 3
            if len(content) > max_chars:
                return content[:max_chars] + "...[截断]"
            return content

    @staticmethod
    def _messages_to_text(messages: list[dict[str, Any]]) -> str:
        lines: list[str] = []
        for msg in messages:
            role = msg.get("role", "unknown")
            content = msg.get("content") or ""
            if msg.get("tool_calls"):
                tc_text = json.dumps(msg["tool_calls"], ensure_ascii=False)
                lines.append(f"[{role}] {content}\nTool calls: {tc_text}")
            elif msg.get("tool_call_id"):
                lines.append(f"[tool:{msg.get('name', '')}] {content}")
            else:
                lines.append(f"[{role}] {content}")
        return "\n".join(lines)
