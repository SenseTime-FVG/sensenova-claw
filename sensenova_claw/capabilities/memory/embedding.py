"""嵌入服务封装：通过 OpenAI 兼容 SDK 获取文本向量，支持多 provider"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from sensenova_claw.platform.config.config import config
from sensenova_claw.capabilities.memory.config import MemoryConfig

logger = logging.getLogger(__name__)


class EmbeddingService:
    def __init__(self, mem_config: MemoryConfig):
        self._config = mem_config
        self._client: Any = None
        self._model_id: str = ""
        self._available = False
        self._init_client()

    def _init_client(self) -> None:
        """初始化 embedding 客户端，优先使用 llm.default_embedding_model 配置"""
        try:
            from openai import OpenAI

            resolved = config.resolve_embedding_model()
            if resolved:
                provider_name, model_id = resolved
                provider_cfg = config.get(f"llm.providers.{provider_name}", {})
                api_key = provider_cfg.get("api_key", "")
                base_url = provider_cfg.get("base_url") or None
                self._model_id = model_id
            else:
                # fallback: 使用 memory.search.embedding_model + openai provider
                provider_cfg = config.get("llm.providers.openai", {})
                api_key = provider_cfg.get("api_key", "")
                base_url = provider_cfg.get("base_url") or None
                self._model_id = self._config.search.embedding_model

            if not api_key:
                logger.info("嵌入服务: API key 未配置，将使用 BM25 降级搜索")
                return

            self._client = OpenAI(api_key=api_key, base_url=base_url)
            self._available = True
            logger.info("嵌入服务: 初始化成功 (model=%s)", self._model_id)
        except Exception:
            logger.warning("嵌入服务: 初始化失败，将使用 BM25 降级搜索", exc_info=True)

    def available(self) -> bool:
        """嵌入服务是否可用"""
        return self._available

    def dimensions(self) -> int:
        """当前模型的向量维度"""
        dims = {
            "text-embedding-3-small": 1536,
            "text-embedding-3-large": 3072,
            "text-embedding-ada-002": 1536,
        }
        return dims.get(self._model_id, 1536)

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

        model_id = self._model_id

        def _call() -> list[list[float]]:
            # 使用 httpx 直接调用，避免某些兼容 API 返回非标准格式
            # 导致 OpenAI SDK 解析失败（如 data[*] 为 str 而非 object）
            import httpx

            base = self._client.base_url
            url = f"{str(base).rstrip('/')}/embeddings"
            headers = {
                "Authorization": f"Bearer {self._client.api_key}",
                "Content-Type": "application/json",
            }
            payload = {"input": texts, "model": model_id}
            resp = httpx.post(url, json=payload, headers=headers, timeout=60)
            resp.raise_for_status()
            data = resp.json().get("data", [])
            results: list[list[float]] = []
            for item in data:
                if isinstance(item, dict):
                    results.append(item["embedding"])
                elif isinstance(item, list):
                    # 某些 API 直接返回向量列表
                    results.append(item)
                else:
                    raise ValueError(f"无法解析 embedding 响应: {type(item)}")
            return results

        return await asyncio.to_thread(_call)
