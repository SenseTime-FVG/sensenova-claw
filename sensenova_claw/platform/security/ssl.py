"""SSL 兼容工具。"""

from __future__ import annotations

import ssl

try:
    import certifi

    CERTIFI_SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    # 未安装 certifi 时回退到系统默认证书。
    CERTIFI_SSL_CONTEXT = ssl.create_default_context()
