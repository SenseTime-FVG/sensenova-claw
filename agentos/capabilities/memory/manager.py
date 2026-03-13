"""记忆管理器：统一管理记忆文件读取和向量索引"""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
from typing import Any

from agentos.capabilities.memory.chunker import Chunker
from agentos.capabilities.memory.config import MemoryConfig
from agentos.capabilities.memory.embedding import EmbeddingService
from agentos.capabilities.memory.index import MemoryIndex, MemorySearchResult

logger = logging.getLogger(__name__)


class MemoryManager:
    def __init__(self, workspace_dir: str, config: MemoryConfig, db_path: Path):
        self.workspace_dir = workspace_dir
        self.config = config
        self.index = MemoryIndex(db_path, config)
        self.chunker = Chunker()
        self.embedding_service = EmbeddingService(config)

    async def load_memory_md(self) -> str | None:
        """读取 MEMORY.md，格式化为 system prompt 片段

        1. 读取 {workspace}/MEMORY.md
        2. 文件不存在返回 None
        3. 超过 bootstrap_max_chars 截断
        4. 包装为 Memory 指令段落
        """
        memory_path = Path(self.workspace_dir) / "MEMORY.md"
        if not memory_path.exists():
            return None

        try:
            content = await asyncio.to_thread(memory_path.read_text, "utf-8")
        except Exception:
            logger.warning("读取 MEMORY.md 失败", exc_info=True)
            return None

        if not content.strip():
            return None

        max_chars = self.config.bootstrap_max_chars
        if len(content) > max_chars:
            content = content[:max_chars] + "\n...(内容已截断，使用 memory_search 检索完整内容)"

        return self._format_memory_prompt(content)

    async def search(self, query: str, max_results: int = 5) -> list[MemorySearchResult]:
        """搜索记忆文件

        1. 确保索引已同步（lazy sync）
        2. 执行混合搜索
        3. 通过 asyncio.to_thread() 不阻塞事件循环
        """
        # lazy sync
        await self.sync_index()

        # 获取查询向量
        embedding: list[float] | None = None
        if self.embedding_service.available():
            try:
                embeddings = await self.embedding_service.embed([query])
                embedding = embeddings[0] if embeddings else None
            except Exception:
                logger.warning("查询嵌入失败，降级为 BM25 搜索", exc_info=True)

        # 执行混合搜索（在线程池中）
        results = await asyncio.to_thread(
            self.index.hybrid_search, query, embedding, max_results
        )
        return results

    async def sync_index(self) -> None:
        """增量同步索引：扫描文件变更 → 重新分块 → 嵌入 → 存储"""
        try:
            await asyncio.to_thread(self._sync_index_blocking)
        except Exception:
            logger.warning("索引同步失败", exc_info=True)

    def _sync_index_blocking(self) -> None:
        """阻塞式索引同步（在线程池中执行）"""
        workspace = Path(self.workspace_dir)

        # 扫描 memory 文件
        memory_files: dict[str, Path] = {}

        # MEMORY.md
        memory_md = workspace / "MEMORY.md"
        if memory_md.exists():
            memory_files["MEMORY.md"] = memory_md

        # memory/*.md
        memory_dir = workspace / "memory"
        if memory_dir.exists():
            for md_file in memory_dir.glob("**/*.md"):
                rel_path = str(md_file.relative_to(workspace)).replace("\\", "/")
                memory_files[rel_path] = md_file

        # 获取已索引的 mtime
        indexed_mtimes = self.index.get_indexed_mtimes()

        # 删除已不存在的文件
        for indexed_path in list(indexed_mtimes.keys()):
            if indexed_path not in memory_files:
                self.index.remove_file(indexed_path)
                logger.debug("删除已不存在的索引: %s", indexed_path)

        # 增量更新
        updated_count = 0
        for rel_path, file_path in memory_files.items():
            file_mtime = os.path.getmtime(file_path)
            indexed_mtime = indexed_mtimes.get(rel_path, 0.0)

            if file_mtime <= indexed_mtime:
                continue

            # 文件有变更，重新分块
            try:
                text = file_path.read_text(encoding="utf-8")
            except Exception:
                logger.warning("读取文件失败: %s", rel_path, exc_info=True)
                continue

            chunks = self.chunker.chunk(
                text,
                path=rel_path,
                chunk_size=self.config.search.chunk_size,
                overlap=self.config.search.chunk_overlap,
            )

            if not chunks:
                self.index.remove_file(rel_path)
                continue

            # 准备 chunk 数据
            chunk_dicts: list[dict[str, Any]] = []
            for chunk in chunks:
                chunk_dicts.append({
                    "chunk_id": chunk.chunk_id,
                    "start_line": chunk.start_line,
                    "end_line": chunk.end_line,
                    "text": chunk.text,
                    "embedding": None,  # 嵌入异步处理
                })

            self.index.upsert_chunks(rel_path, chunk_dicts, file_mtime)
            updated_count += 1

        if updated_count > 0:
            logger.info("索引更新: %d 个文件重新索引", updated_count)

    async def embed_pending_chunks(self) -> None:
        """为没有嵌入向量的 chunks 生成嵌入（可选后台任务）"""
        if not self.embedding_service.available():
            return

        conn = self.index._conn()
        rows = conn.execute(
            "SELECT chunk_id, text FROM memory_chunks WHERE embedding IS NULL"
        ).fetchall()
        conn.close()

        if not rows:
            return

        # 批量嵌入
        texts = [row["text"] for row in rows]
        chunk_ids = [row["chunk_id"] for row in rows]

        try:
            embeddings = await self.embedding_service.embed(texts)
        except Exception:
            logger.warning("批量嵌入失败", exc_info=True)
            return

        # 更新嵌入
        conn = self.index._conn()
        for chunk_id, embedding in zip(chunk_ids, embeddings):
            blob = MemoryIndex._encode_embedding(embedding)
            conn.execute(
                "UPDATE memory_chunks SET embedding = ? WHERE chunk_id = ?",
                (blob, chunk_id),
            )
        conn.commit()
        conn.close()
        logger.info("嵌入更新: %d 个 chunks", len(chunk_ids))

    def _format_memory_prompt(self, content: str) -> str:
        """将 MEMORY.md 内容包装为 system prompt 片段

        注意：prompt_builder._build_memory 会自动添加 '## Memory' 标题，
        这里只输出正文内容。
        """
        return (
            "你拥有长期记忆能力。\n\n"
            "### 记忆读取\n"
            "- 回答涉及过往工作、决策、日期、人物、偏好的问题前，先调用 memory_search 搜索记忆\n"
            "- 搜索后可用 read_file 获取完整上下文\n\n"
            "### 记忆写入\n"
            "- 用户提到偏好、个人信息、重要决策时，用 write_file 写入 MEMORY.md\n"
            "- 日常笔记和运行上下文追加到 memory/{今天日期}.md\n"
            "- 已有文件时追加内容，不要覆盖\n\n"
            "### 当前 MEMORY.md 内容\n"
            f"{content}"
        )
