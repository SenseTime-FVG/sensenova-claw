"""记忆系统配置数据类"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class HybridSearchConfig:
    vector_weight: float = 0.7
    text_weight: float = 0.3
    candidate_multiplier: int = 4


@dataclass
class SearchConfig:
    enabled: bool = True
    embedding_model: str = "text-embedding-3-small"
    chunk_size: int = 400
    chunk_overlap: int = 80
    hybrid: HybridSearchConfig = field(default_factory=HybridSearchConfig)


@dataclass
class MemoryConfig:
    enabled: bool = False
    bootstrap_max_chars: int = 8000
    search: SearchConfig = field(default_factory=SearchConfig)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MemoryConfig:
        """从完整配置字典中提取 memory 部分构建 MemoryConfig"""
        mem = data.get("memory", {})
        search_raw = mem.get("search", {})
        hybrid_raw = search_raw.get("hybrid", {})

        hybrid = HybridSearchConfig(
            vector_weight=hybrid_raw.get("vector_weight", 0.7),
            text_weight=hybrid_raw.get("text_weight", 0.3),
            candidate_multiplier=hybrid_raw.get("candidate_multiplier", 4),
        )
        search = SearchConfig(
            enabled=search_raw.get("enabled", True),
            embedding_model=search_raw.get("embedding_model", "text-embedding-3-small"),
            chunk_size=search_raw.get("chunk_size", 400),
            chunk_overlap=search_raw.get("chunk_overlap", 80),
            hybrid=hybrid,
        )
        return cls(
            enabled=mem.get("enabled", False),
            bootstrap_max_chars=mem.get("bootstrap_max_chars", 8000),
            search=search,
        )
