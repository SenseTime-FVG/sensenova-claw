"""Skill $ARGUMENTS 参数替换逻辑，兼容 Claude Code Agent Skills 标准"""
from __future__ import annotations

import re
import shlex


def parse_arguments(raw: str) -> list[str]:
    """按空格分割参数，引号内空格保留"""
    raw = raw.strip()
    if not raw:
        return []
    try:
        return shlex.split(raw)
    except ValueError:
        return raw.split()


def substitute_arguments(body: str, raw_args: str) -> str:
    """将 skill body 中的占位符替换为实际参数值"""
    args = parse_arguments(raw_args)
    has_placeholder = False

    def _replace_indexed(m: re.Match) -> str:
        nonlocal has_placeholder
        has_placeholder = True
        idx = int(m.group(1))
        return args[idx] if idx < len(args) else ""

    result = re.sub(r"\$ARGUMENTS\[(\d+)\]", _replace_indexed, body)

    if "$ARGUMENTS" in result:
        has_placeholder = True
        result = result.replace("$ARGUMENTS", raw_args)

    def _replace_shorthand(m: re.Match) -> str:
        nonlocal has_placeholder
        has_placeholder = True
        idx = int(m.group(1))
        return args[idx] if idx < len(args) else ""

    result = re.sub(r"\$(\d+)(?!\w)", _replace_shorthand, result)

    if not has_placeholder and raw_args.strip():
        result = result.rstrip() + f"\n\nARGUMENTS: {raw_args}"

    return result
