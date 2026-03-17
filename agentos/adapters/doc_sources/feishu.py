"""飞书文档适配器（预留接口）"""
from __future__ import annotations

from agentos.adapters.doc_sources.base import DocSourceAdapter


class FeishuDocAdapter(DocSourceAdapter):
    """飞书文档适配器"""

    @staticmethod
    def can_handle(url: str) -> bool:
        """判断是否为飞书文档链接"""
        return "feishu.cn" in url or "larksuite.com" in url

    def fetch(self, url: str) -> str:
        """获取飞书文档内容（待实现）"""
        # TODO: 实现飞书 API 调用
        raise NotImplementedError("飞书文档访问功能待实现，需要配置 API token")
