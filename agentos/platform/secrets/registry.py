"""Secret 路径注册表。"""

from __future__ import annotations

SECRET_PATH_PATTERNS = (
    "llm.providers.*.api_key",
    "tools.*.api_key",
    "tools.email.password",
    "plugins.feishu.app_secret",
    "plugins.wecom.secret",
)


def _match_pattern(path: str, pattern: str) -> bool:
    path_parts = path.split(".")
    pattern_parts = pattern.split(".")
    if len(path_parts) != len(pattern_parts):
        return False
    return all(
        pattern_part == "*" or pattern_part == path_part
        for path_part, pattern_part in zip(path_parts, pattern_parts, strict=False)
    )


def is_secret_path(path: str) -> bool:
    """判断 dotted path 是否属于敏感字段。"""
    return any(_match_pattern(path, pattern) for pattern in SECRET_PATH_PATTERNS)
