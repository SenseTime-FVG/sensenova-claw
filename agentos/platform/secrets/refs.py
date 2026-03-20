"""Secret 引用格式工具。"""

from __future__ import annotations

SECRET_REF_PREFIX = "${secret:"
SECRET_REF_SUFFIX = "}"


def is_secret_ref(value: str) -> bool:
    """判断字符串是否为合法的 secret 引用。"""
    return value.startswith(SECRET_REF_PREFIX) and value.endswith(SECRET_REF_SUFFIX)


def parse_secret_ref(value: str) -> str:
    """解析 `${secret:...}` 格式，返回内部 ref。"""
    if not is_secret_ref(value):
        raise ValueError(f"非法 secret 引用: {value}")
    return value[len(SECRET_REF_PREFIX):-len(SECRET_REF_SUFFIX)]


def build_secret_ref(ref: str) -> str:
    """构造 `${secret:...}` 引用。"""
    return f"{SECRET_REF_PREFIX}{ref}{SECRET_REF_SUFFIX}"
