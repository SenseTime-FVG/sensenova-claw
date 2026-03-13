"""记忆索引：SQLite 存储 + FTS5 全文搜索 + 向量相似度搜索"""

from __future__ import annotations

import logging
import math
import sqlite3
import struct
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agentos.capabilities.memory.config import MemoryConfig

logger = logging.getLogger(__name__)

MEMORY_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS memory_chunks (
    chunk_id TEXT PRIMARY KEY,
    path TEXT NOT NULL,
    start_line INTEGER NOT NULL,
    end_line INTEGER NOT NULL,
    text TEXT NOT NULL,
    embedding BLOB,
    file_mtime REAL NOT NULL,
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_chunks_path ON memory_chunks(path);
"""

# FTS5 需要单独创建（某些 SQLite 编译不支持）
FTS5_SCHEMA_SQL = """
CREATE VIRTUAL TABLE IF NOT EXISTS memory_chunks_fts
USING fts5(chunk_id, text, content=memory_chunks, content_rowid=rowid);
"""

# FTS5 同步触发器
FTS5_TRIGGERS_SQL = """
CREATE TRIGGER IF NOT EXISTS memory_chunks_ai AFTER INSERT ON memory_chunks BEGIN
    INSERT INTO memory_chunks_fts(rowid, chunk_id, text)
    VALUES (new.rowid, new.chunk_id, new.text);
END;
CREATE TRIGGER IF NOT EXISTS memory_chunks_ad AFTER DELETE ON memory_chunks BEGIN
    INSERT INTO memory_chunks_fts(memory_chunks_fts, rowid, chunk_id, text)
    VALUES ('delete', old.rowid, old.chunk_id, old.text);
END;
CREATE TRIGGER IF NOT EXISTS memory_chunks_au AFTER UPDATE ON memory_chunks BEGIN
    INSERT INTO memory_chunks_fts(memory_chunks_fts, rowid, chunk_id, text)
    VALUES ('delete', old.rowid, old.chunk_id, old.text);
    INSERT INTO memory_chunks_fts(rowid, chunk_id, text)
    VALUES (new.rowid, new.chunk_id, new.text);
END;
"""


@dataclass
class MemorySearchResult:
    snippet: str
    path: str
    start_line: int
    end_line: int
    score: float


class MemoryIndex:
    """SQLite 存储和混合搜索引擎"""

    def __init__(self, db_path: Path, config: MemoryConfig):
        self.db_path = db_path
        self.config = config
        self._fts5_available = False
        self._init_db()

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        """初始化数据库表"""
        conn = self._conn()
        conn.executescript(MEMORY_SCHEMA_SQL)
        conn.commit()

        # 尝试创建 FTS5 表（可能不支持）
        try:
            conn.executescript(FTS5_SCHEMA_SQL)
            conn.executescript(FTS5_TRIGGERS_SQL)
            conn.commit()
            self._fts5_available = True
            logger.info("记忆索引: FTS5 全文搜索可用")
        except sqlite3.OperationalError:
            logger.warning("记忆索引: FTS5 不可用，将仅使用向量搜索")
        conn.close()

    def upsert_chunks(self, path: str, chunks: list[dict[str, Any]], file_mtime: float) -> None:
        """写入/更新分块：删除该文件旧 chunks + 插入新 chunks

        Args:
            path: workspace 相对路径
            chunks: 分块列表，每个包含 chunk_id, start_line, end_line, text, embedding(可选)
            file_mtime: 文件修改时间
        """
        conn = self._conn()
        now = time.time()

        # 删除该文件的旧 chunks
        conn.execute("DELETE FROM memory_chunks WHERE path = ?", (path,))

        # 插入新 chunks
        for chunk in chunks:
            embedding_blob = None
            if chunk.get("embedding"):
                embedding_blob = self._encode_embedding(chunk["embedding"])

            conn.execute(
                """INSERT INTO memory_chunks
                   (chunk_id, path, start_line, end_line, text, embedding, file_mtime, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    chunk["chunk_id"],
                    path,
                    chunk["start_line"],
                    chunk["end_line"],
                    chunk["text"],
                    embedding_blob,
                    file_mtime,
                    now,
                ),
            )
        conn.commit()
        conn.close()

    def search_vector(self, embedding: list[float], limit: int) -> list[tuple[str, float]]:
        """向量相似度搜索（cosine similarity）

        Returns:
            (chunk_id, score) 列表，按 score 降序
        """
        conn = self._conn()
        rows = conn.execute(
            "SELECT chunk_id, embedding FROM memory_chunks WHERE embedding IS NOT NULL"
        ).fetchall()
        conn.close()

        if not rows:
            return []

        # 计算 cosine similarity
        results: list[tuple[str, float]] = []
        for row in rows:
            chunk_id = row["chunk_id"]
            stored_embedding = self._decode_embedding(row["embedding"])
            score = self._cosine_similarity(embedding, stored_embedding)
            results.append((chunk_id, score))

        results.sort(key=lambda x: x[1], reverse=True)
        return results[:limit]

    def search_bm25(self, query: str, limit: int) -> list[tuple[str, float]]:
        """BM25 全文搜索

        Returns:
            (chunk_id, score) 列表，按 rank 排序
        """
        if not self._fts5_available:
            return []

        conn = self._conn()
        try:
            rows = conn.execute(
                """SELECT chunk_id, rank
                   FROM memory_chunks_fts
                   WHERE memory_chunks_fts MATCH ?
                   ORDER BY rank
                   LIMIT ?""",
                (query, limit),
            ).fetchall()
            # FTS5 rank 是负数（越小越相关），归一化为正分数
            results = []
            for row in rows:
                # rank 是负数，取绝对值归一化
                score = abs(row["rank"]) if row["rank"] else 0.0
                results.append((row["chunk_id"], score))
            return results
        except sqlite3.OperationalError as e:
            logger.warning("BM25 搜索失败: %s", e)
            return []
        finally:
            conn.close()

    def hybrid_search(
        self,
        query: str,
        embedding: list[float] | None,
        limit: int,
    ) -> list[MemorySearchResult]:
        """混合搜索：向量 + BM25 加权合并

        Args:
            query: 搜索查询文本
            embedding: 查询向量（可为 None，仅 BM25）
            limit: 最大返回数
        """
        multiplier = self.config.search.hybrid.candidate_multiplier
        candidate_limit = limit * multiplier

        # 收集候选
        vector_results: dict[str, float] = {}
        bm25_results: dict[str, float] = {}

        if embedding:
            for chunk_id, score in self.search_vector(embedding, candidate_limit):
                vector_results[chunk_id] = score

        bm25_raw = self.search_bm25(query, candidate_limit)
        if bm25_raw:
            # 归一化 BM25 分数到 [0, 1]
            max_score = max(s for _, s in bm25_raw) if bm25_raw else 1.0
            for chunk_id, score in bm25_raw:
                bm25_results[chunk_id] = score / max_score if max_score > 0 else 0.0

        # 合并候选
        all_chunk_ids = set(vector_results.keys()) | set(bm25_results.keys())
        if not all_chunk_ids:
            return []

        vw = self.config.search.hybrid.vector_weight
        tw = self.config.search.hybrid.text_weight

        scored: list[tuple[str, float]] = []
        for chunk_id in all_chunk_ids:
            v_score = vector_results.get(chunk_id, 0.0)
            t_score = bm25_results.get(chunk_id, 0.0)
            final_score = vw * v_score + tw * t_score
            scored.append((chunk_id, final_score))

        scored.sort(key=lambda x: x[1], reverse=True)
        top_ids = [cid for cid, _ in scored[:limit]]

        # 查询完整 chunk 信息
        return self._fetch_chunks(top_ids, {cid: s for cid, s in scored})

    def get_indexed_mtimes(self) -> dict[str, float]:
        """获取已索引文件的 mtime 映射"""
        conn = self._conn()
        rows = conn.execute(
            "SELECT DISTINCT path, MAX(file_mtime) as mtime FROM memory_chunks GROUP BY path"
        ).fetchall()
        conn.close()
        return {row["path"]: row["mtime"] for row in rows}

    def remove_file(self, path: str) -> None:
        """删除指定文件的所有 chunks"""
        conn = self._conn()
        conn.execute("DELETE FROM memory_chunks WHERE path = ?", (path,))
        conn.commit()
        conn.close()

    def _fetch_chunks(
        self, chunk_ids: list[str], scores: dict[str, float]
    ) -> list[MemorySearchResult]:
        """根据 chunk_id 列表查询完整信息"""
        if not chunk_ids:
            return []

        conn = self._conn()
        placeholders = ",".join("?" for _ in chunk_ids)
        rows = conn.execute(
            f"SELECT chunk_id, path, start_line, end_line, text FROM memory_chunks WHERE chunk_id IN ({placeholders})",
            chunk_ids,
        ).fetchall()
        conn.close()

        # 按 scores 排序
        row_map = {row["chunk_id"]: row for row in rows}
        results = []
        for cid in chunk_ids:
            row = row_map.get(cid)
            if row:
                # 截取 snippet（最多 700 字符）
                text = row["text"]
                snippet = text[:700] + "..." if len(text) > 700 else text
                results.append(MemorySearchResult(
                    snippet=snippet,
                    path=row["path"],
                    start_line=row["start_line"],
                    end_line=row["end_line"],
                    score=scores.get(cid, 0.0),
                ))
        return results

    @staticmethod
    def _encode_embedding(embedding: list[float]) -> bytes:
        """将 float 列表编码为 bytes"""
        return struct.pack(f"{len(embedding)}f", *embedding)

    @staticmethod
    def _decode_embedding(blob: bytes) -> list[float]:
        """将 bytes 解码为 float 列表"""
        count = len(blob) // 4
        return list(struct.unpack(f"{count}f", blob))

    @staticmethod
    def _cosine_similarity(a: list[float], b: list[float]) -> float:
        """计算两个向量的余弦相似度"""
        if len(a) != len(b):
            return 0.0
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = math.sqrt(sum(x * x for x in a))
        norm_b = math.sqrt(sum(x * x for x in b))
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot / (norm_a * norm_b)
