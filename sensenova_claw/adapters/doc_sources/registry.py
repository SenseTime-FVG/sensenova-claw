"""文档来源注册表"""
from __future__ import annotations

from sensenova_claw.adapters.doc_sources.base import DocSourceAdapter


class DocSourceRegistry:
    """文档来源注册表，自动发现和注册适配器"""
    _adapters: list[DocSourceAdapter] = []

    @classmethod
    def register(cls, adapter: DocSourceAdapter):
        """注册适配器"""
        cls._adapters.append(adapter)

    @classmethod
    def get_adapter(cls, url: str) -> DocSourceAdapter | None:
        """根据 URL 获取适配器"""
        for adapter in cls._adapters:
            if adapter.can_handle(url):
                return adapter
        return None
