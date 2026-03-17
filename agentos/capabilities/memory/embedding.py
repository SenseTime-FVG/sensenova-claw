"""嵌入服务封装：通过 OpenAI SDK 获取文本向量"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from agentos.platform.config.config import config
from agentos.capabilities.memory.config import MemoryConfig

logger = logging.getLogger(__name__)


class EmbeddingService:
    def __init__(self, mem_config: MemoryConfig):
        self._config = mem_config
        self._client: Any = None
        self._available = False
        self._init_client()

    def _init_client(self) -> None:
        """尝试初始化 OpenAI 客户端（复用 llm_providers.openai 配置）"""
        try:
            from openai import OpenAI

            # 优先使用 openai provider 配置
            provider_cfg = config.get("llm.providers.openai", {})
            api_key = provider_cfg.get("api_key", "")
            base_url = provider_cfg.get("base_url") or None

            if not api_key:
                logger.info("嵌入服务: OpenAI API key 未配置，将使用 BM25 降级搜索")
                return

            self._client = OpenAI(api_key=api_key, base_url=base_url)
            self._available = True
            logger.info("嵌入服务: 初始化成功 (model=%s)", self._config.search.embedding_model)
        except Exception:
            logger.warning("嵌入服务: 初始化失败，将使用 BM25 降级搜索", exc_info=True)

    def available(self) -> bool:
        """嵌入服务是否可用"""
        return self._available

    def dimensions(self) -> int:
        """当前模型的向量维度"""
        model = self._config.search.embedding_model
        # text-embedding-3-small 默认 1536 维
        dims = {
            "text-embedding-3-small": 1536,
            "text-embedding-3-large": 3072,
            "text-embedding-ada-002": 1536,
        }
        return dims.get(model, 1536)

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """批量文本 → 向量（通过 asyncio.to_thread 调用 OpenAI SDK）

        Args:
            texts: 待嵌入的文本列表

        Returns:
            向量列表，每个向量是 float 列表

        Raises:
            RuntimeError: 嵌入服务不可用
        """
        if not self._available or not self._client:
            raise RuntimeError("嵌入服务不可用")

        def _call() -> list[list[float]]:
            model = self._config.search.embedding_model
            response = self._client.embeddings.create(input=texts, model=model)
            return [item.embedding for item in response.data]

        return await asyncio.to_thread(_call)
