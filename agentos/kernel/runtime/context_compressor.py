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
