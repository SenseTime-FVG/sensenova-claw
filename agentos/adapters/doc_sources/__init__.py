"""文档来源适配器模块"""
from agentos.adapters.doc_sources.base import DocSourceAdapter
from agentos.adapters.doc_sources.registry import DocSourceRegistry
from agentos.adapters.doc_sources.local import LocalFileAdapter
from agentos.adapters.doc_sources.feishu import FeishuDocAdapter

# 自动注册适配器
DocSourceRegistry.register(LocalFileAdapter())
DocSourceRegistry.register(FeishuDocAdapter())

__all__ = ["DocSourceAdapter", "DocSourceRegistry", "LocalFileAdapter", "FeishuDocAdapter"]
