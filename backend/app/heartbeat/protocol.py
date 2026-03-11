"""HEARTBEAT_OK 协议

检测和剥离 Agent 回复中的 HEARTBEAT_OK 令牌，决定是否跳过投递。
"""

from __future__ import annotations

from dataclasses import dataclass

HEARTBEAT_TOKEN = "HEARTBEAT_OK"


@dataclass
class StripResult:
    """strip_heartbeat_token 的返回值"""
    found: bool           # 是否检测到 HEARTBEAT_OK
    remaining: str        # 剥离令牌后的剩余文本
    should_skip: bool     # 是否应跳过投递


def strip_heartbeat_token(text: str, max_ack_chars: int = 300) -> StripResult:
    """检测并剥离回复文本中的 HEARTBEAT_OK。

    规则：
    - 开头或结尾出现 HEARTBEAT_OK 视为有效
    - 剥离后剩余文本 ≤ max_ack_chars → should_skip=True
    - 空文本 → should_skip=True
    """
    stripped = text.strip()
    if not stripped:
        return StripResult(found=False, remaining="", should_skip=True)

    # 完全匹配
    if stripped == HEARTBEAT_TOKEN:
        return StripResult(found=True, remaining="", should_skip=True)

    found = False
    remaining = stripped

    # 前缀匹配
    if remaining.startswith(HEARTBEAT_TOKEN):
        found = True
        remaining = remaining[len(HEARTBEAT_TOKEN):].strip()
    # 后缀匹配
    elif remaining.endswith(HEARTBEAT_TOKEN):
        found = True
        remaining = remaining[:-len(HEARTBEAT_TOKEN)].strip()

    if found and len(remaining) <= max_ack_chars:
        return StripResult(found=True, remaining=remaining, should_skip=True)

    return StripResult(found=found, remaining=remaining, should_skip=False)
