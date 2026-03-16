"""本地文件适配器"""
from __future__ import annotations

from pathlib import Path

from agentos.adapters.doc_sources.base import DocSourceAdapter


class LocalFileAdapter(DocSourceAdapter):
    """本地文件适配器"""

    @staticmethod
    def can_handle(url: str) -> bool:
        """判断是否为本地文件路径"""
        return Path(url).exists()

    def fetch(self, url: str) -> str:
        """读取本地文件内容"""
        return Path(url).read_text(encoding="utf-8")
