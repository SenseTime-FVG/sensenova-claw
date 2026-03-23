"""文档来源适配器基类"""
from __future__ import annotations


class DocSourceAdapter:
    """文档来源适配器基类"""

    @staticmethod
    def can_handle(url: str) -> bool:
        """判断是否能处理该 URL"""
        raise NotImplementedError

    def fetch(self, url: str) -> str:
        """获取文档内容，返回 Markdown 格式"""
        raise NotImplementedError
