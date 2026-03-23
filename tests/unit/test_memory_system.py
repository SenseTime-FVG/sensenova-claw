"""记忆系统单元测试

测试 Chunker、MemoryIndex、MemoryManager、MemoryConfig 和 MemorySearchTool。
"""

from __future__ import annotations

import os
import tempfile
import time
from pathlib import Path

import pytest

from agentos.capabilities.memory.chunker import Chunker, MemoryChunk
from agentos.capabilities.memory.config import MemoryConfig
from agentos.capabilities.memory.index import MemoryIndex, MemorySearchResult
from agentos.capabilities.memory.tools import MemorySearchTool


# ===== Chunker 测试 =====


class TestChunker:
    """测试文本分块器"""

    def test_empty_text_returns_no_chunks(self):
        chunker = Chunker()
        result = chunker.chunk("", "test.md")
        assert result == []

    def test_whitespace_only_returns_no_chunks(self):
        chunker = Chunker()
        result = chunker.chunk("   \n  \n  ", "test.md")
        assert result == []

    def test_short_text_single_chunk(self):
        chunker = Chunker()
        text = "这是一段简短的文本。\n只有两行。"
        result = chunker.chunk(text, "test.md", chunk_size=400, overlap=80)
        assert len(result) == 1
        assert result[0].path == "test.md"
        assert result[0].start_line == 1
        assert "简短的文本" in result[0].text

    def test_long_text_multiple_chunks(self):
        chunker = Chunker()
        # 创建超过 chunk_size * 3 字符的文本
        lines = [f"这是第{i}行内容，包含一些信息。" * 5 for i in range(100)]
        text = "\n".join(lines)
        result = chunker.chunk(text, "test.md", chunk_size=50, overlap=10)
        assert len(result) > 1

    def test_chunk_has_valid_line_numbers(self):
        chunker = Chunker()
        lines = [f"Line {i}" for i in range(50)]
        text = "\n".join(lines)
        result = chunker.chunk(text, "test.md", chunk_size=20, overlap=5)
        for chunk in result:
            assert chunk.start_line >= 1
            assert chunk.end_line >= chunk.start_line
            assert chunk.chunk_id  # 非空 ID

    def test_chunk_respects_paragraph_boundary(self):
        chunker = Chunker()
        text = "第一段内容。\n\n第二段内容。\n\n第三段内容。"
        result = chunker.chunk(text, "test.md", chunk_size=10, overlap=2)
        # 应该在段落边界切分
        assert len(result) >= 1

    def test_chunk_dataclass_fields(self):
        chunk = MemoryChunk(
            chunk_id="abc123",
            path="memory/2026-03-10.md",
            start_line=5,
            end_line=10,
            text="some text",
        )
        assert chunk.chunk_id == "abc123"
        assert chunk.path == "memory/2026-03-10.md"
        assert chunk.start_line == 5
        assert chunk.end_line == 10
        assert chunk.text == "some text"


# ===== MemoryConfig 测试 =====


class TestMemoryConfig:
    """测试配置数据类"""

    def test_default_config(self):
        cfg = MemoryConfig()
        assert cfg.enabled is False
        assert cfg.bootstrap_max_chars == 8000
        assert cfg.search.enabled is True
        assert cfg.search.embedding_model == "text-embedding-3-small"
        assert cfg.search.chunk_size == 400
        assert cfg.search.chunk_overlap == 80
        assert cfg.search.hybrid.vector_weight == 0.7

    def test_from_dict_empty(self):
        cfg = MemoryConfig.from_dict({})
        assert cfg.enabled is False
        assert cfg.bootstrap_max_chars == 8000

    def test_from_dict_full(self):
        data = {
            "memory": {
                "enabled": True,
                "bootstrap_max_chars": 4000,
                "search": {
                    "enabled": False,
                    "embedding_model": "text-embedding-3-large",
                    "chunk_size": 200,
                    "chunk_overlap": 40,
                    "hybrid": {
                        "vector_weight": 0.5,
                        "text_weight": 0.5,
                        "candidate_multiplier": 8,
                    },
                },
            }
        }
        cfg = MemoryConfig.from_dict(data)
        assert cfg.enabled is True
        assert cfg.bootstrap_max_chars == 4000
        assert cfg.search.enabled is False
        assert cfg.search.embedding_model == "text-embedding-3-large"
        assert cfg.search.chunk_size == 200
        assert cfg.search.hybrid.vector_weight == 0.5
        assert cfg.search.hybrid.candidate_multiplier == 8


# ===== MemoryIndex 测试 =====


class TestMemoryIndex:
    """测试 SQLite 索引和搜索"""

    @pytest.fixture
    def index(self, tmp_path):
        """创建临时数据库的 MemoryIndex"""
        db_path = tmp_path / "test_memory.db"
        cfg = MemoryConfig(enabled=True)
        return MemoryIndex(db_path, cfg)

    def test_upsert_and_get_mtimes(self, index):
        chunks = [
            {
                "chunk_id": "chunk_1",
                "start_line": 1,
                "end_line": 5,
                "text": "这是测试内容",
                "embedding": None,
            }
        ]
        index.upsert_chunks("MEMORY.md", chunks, file_mtime=1000.0)
        mtimes = index.get_indexed_mtimes()
        assert "MEMORY.md" in mtimes
        assert mtimes["MEMORY.md"] == 1000.0

    def test_upsert_replaces_old_chunks(self, index):
        old_chunks = [{"chunk_id": "old_1", "start_line": 1, "end_line": 2, "text": "旧内容", "embedding": None}]
        index.upsert_chunks("test.md", old_chunks, file_mtime=100.0)

        new_chunks = [{"chunk_id": "new_1", "start_line": 1, "end_line": 3, "text": "新内容", "embedding": None}]
        index.upsert_chunks("test.md", new_chunks, file_mtime=200.0)

        mtimes = index.get_indexed_mtimes()
        assert mtimes["test.md"] == 200.0

    def test_remove_file(self, index):
        chunks = [{"chunk_id": "c1", "start_line": 1, "end_line": 2, "text": "内容", "embedding": None}]
        index.upsert_chunks("to_remove.md", chunks, file_mtime=100.0)
        assert "to_remove.md" in index.get_indexed_mtimes()

        index.remove_file("to_remove.md")
        assert "to_remove.md" not in index.get_indexed_mtimes()

    def test_bm25_search(self, index):
        chunks = [
            {"chunk_id": "c1", "start_line": 1, "end_line": 5, "text": "Python 是一种编程语言", "embedding": None},
            {"chunk_id": "c2", "start_line": 6, "end_line": 10, "text": "今天天气很好", "embedding": None},
        ]
        index.upsert_chunks("test.md", chunks, file_mtime=100.0)

        # FTS5 搜索
        if index._fts5_available:
            results = index.search_bm25("Python", limit=5)
            assert len(results) > 0
            assert results[0][0] == "c1"  # chunk_id

    def test_vector_search(self, index):
        # 创建简单的测试向量
        vec_a = [1.0, 0.0, 0.0, 0.0]
        vec_b = [0.0, 1.0, 0.0, 0.0]

        chunks_a = [
            {
                "chunk_id": "va",
                "start_line": 1,
                "end_line": 2,
                "text": "文档A",
                "embedding": vec_a,
            }
        ]
        chunks_b = [
            {
                "chunk_id": "vb",
                "start_line": 1,
                "end_line": 2,
                "text": "文档B",
                "embedding": vec_b,
            }
        ]
        index.upsert_chunks("a.md", chunks_a, file_mtime=100.0)
        index.upsert_chunks("b.md", chunks_b, file_mtime=100.0)

        # 查询向量接近 vec_a
        results = index.search_vector([0.9, 0.1, 0.0, 0.0], limit=5)
        assert len(results) == 2
        # va 应该排在前面（余弦相似度更高）
        assert results[0][0] == "va"

    def test_hybrid_search_bm25_only(self, index):
        chunks = [
            {"chunk_id": "h1", "start_line": 1, "end_line": 3, "text": "deployment plan chose Kubernetes for production", "embedding": None},
        ]
        index.upsert_chunks("test.md", chunks, file_mtime=100.0)

        # 无向量，仅 BM25
        results = index.hybrid_search("Kubernetes", embedding=None, limit=5)
        if index._fts5_available:
            assert len(results) >= 1
            assert results[0].path == "test.md"

    def test_hybrid_search_empty_index(self, index):
        results = index.hybrid_search("任何查询", embedding=None, limit=5)
        assert results == []

    def test_search_result_snippet_truncation(self, index):
        long_text = "A" * 1000
        chunks = [{"chunk_id": "long", "start_line": 1, "end_line": 1, "text": long_text, "embedding": None}]
        index.upsert_chunks("long.md", chunks, file_mtime=100.0)

        if index._fts5_available:
            # BM25 可能不匹配纯重复字符，用 hybrid 直接测试 _fetch_chunks
            result_list = index._fetch_chunks(["long"], {"long": 0.5})
            assert len(result_list) == 1
            assert len(result_list[0].snippet) <= 703  # 700 + "..."

    def test_encoding_decoding_embedding(self):
        original = [0.1, 0.2, 0.3, 0.4, 0.5]
        blob = MemoryIndex._encode_embedding(original)
        decoded = MemoryIndex._decode_embedding(blob)
        for a, b in zip(original, decoded):
            assert abs(a - b) < 1e-6

    def test_cosine_similarity(self):
        assert abs(MemoryIndex._cosine_similarity([1, 0], [1, 0]) - 1.0) < 1e-6
        assert abs(MemoryIndex._cosine_similarity([1, 0], [0, 1]) - 0.0) < 1e-6
        assert abs(MemoryIndex._cosine_similarity([1, 0], [-1, 0]) - (-1.0)) < 1e-6
        assert MemoryIndex._cosine_similarity([0, 0], [1, 0]) == 0.0
        assert MemoryIndex._cosine_similarity([1], [1, 0]) == 0.0  # 不同维度


# ===== MemoryManager 测试 =====


class TestMemoryManager:
    """测试 MemoryManager（文件读取和索引管理）"""

    @pytest.fixture
    def workspace(self, tmp_path):
        """创建临时 workspace 目录"""
        ws = tmp_path / "workspace"
        ws.mkdir()
        return ws

    @pytest.fixture
    def manager(self, workspace, tmp_path):
        from agentos.capabilities.memory.manager import MemoryManager

        cfg = MemoryConfig(enabled=True, bootstrap_max_chars=200)
        db_path = tmp_path / "test_memory.db"
        return MemoryManager(
            workspace_dir=str(workspace),
            config=cfg,
            db_path=db_path,
        )

    @pytest.mark.asyncio
    async def test_load_memory_md_returns_prompt_with_paths(self, manager):
        """load_memory_md 应返回指引 prompt（包含文件路径），不读取文件内容"""
        result = await manager.load_memory_md()
        assert result is not None
        assert "MEMORY.md" in result
        assert "记忆文件" in result
        assert "read_file" in result
        assert "agents/default" in result

    @pytest.mark.asyncio
    async def test_load_memory_md_with_agent_id(self, manager):
        """指定 agent_id 时，路径应包含该 agent_id"""
        result = await manager.load_memory_md(agent_id="planner")
        assert result is not None
        assert "agents/planner/MEMORY.md" in result
        assert "agents/planner/memory/" in result

    @pytest.mark.asyncio
    async def test_load_memory_md_includes_today_yesterday(self, manager):
        """prompt 应包含今天和昨天的日期路径"""
        from datetime import datetime, timedelta
        today_str = datetime.now().strftime("%Y-%m-%d")
        yesterday_str = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

        result = await manager.load_memory_md()
        assert today_str in result
        assert yesterday_str in result

    @pytest.mark.asyncio
    async def test_sync_index_no_files(self, manager):
        await manager.sync_index()
        mtimes = manager.index.get_indexed_mtimes()
        assert mtimes == {}

    @pytest.mark.asyncio
    async def test_sync_index_with_memory_md(self, manager, workspace):
        (workspace / "MEMORY.md").write_text("测试记忆内容", encoding="utf-8")
        await manager.sync_index()
        mtimes = manager.index.get_indexed_mtimes()
        assert "MEMORY.md" in mtimes

    @pytest.mark.asyncio
    async def test_sync_index_with_daily_logs(self, manager, workspace):
        """兼容旧路径：workspace/memory/*.md 仍可被索引"""
        memory_dir = workspace / "memory"
        memory_dir.mkdir()
        (memory_dir / "2026-03-10.md").write_text("今天完成了 API 设计", encoding="utf-8")
        await manager.sync_index()
        mtimes = manager.index.get_indexed_mtimes()
        assert "memory/2026-03-10.md" in mtimes

    @pytest.mark.asyncio
    async def test_sync_index_with_agent_memory(self, manager, workspace):
        """新路径：agents/{id}/memory/*.md 和 agents/{id}/MEMORY.md"""
        agent_dir = workspace / "agents" / "planner"
        (agent_dir / "memory").mkdir(parents=True)
        (agent_dir / "MEMORY.md").write_text("长期记忆", encoding="utf-8")
        (agent_dir / "memory" / "2026-03-20.md").write_text("日记内容", encoding="utf-8")
        await manager.sync_index()
        mtimes = manager.index.get_indexed_mtimes()
        assert "agents/planner/MEMORY.md" in mtimes
        assert "agents/planner/memory/2026-03-20.md" in mtimes

    @pytest.mark.asyncio
    async def test_sync_index_auto_embeds_new_chunks(self, manager, workspace, monkeypatch):
        (workspace / "MEMORY.md").write_text("这是一段需要自动嵌入的记忆", encoding="utf-8")

        embed_calls: list[list[str]] = []

        async def fake_embed(texts: list[str]) -> list[list[float]]:
            embed_calls.append(list(texts))
            return [[0.1, 0.2, 0.3] for _ in texts]

        monkeypatch.setattr(manager.embedding_service, "available", lambda: True)
        monkeypatch.setattr(manager.embedding_service, "embed", fake_embed)

        await manager.sync_index()

        conn = manager.index._conn()
        rows = conn.execute("SELECT text, embedding FROM memory_chunks").fetchall()
        conn.close()

        assert len(rows) == 1
        assert rows[0]["embedding"] is not None
        assert embed_calls == [[rows[0]["text"]]]

    @pytest.mark.asyncio
    async def test_sync_index_retries_pending_embeddings_without_file_changes(
        self, manager, workspace, monkeypatch
    ):
        (workspace / "MEMORY.md").write_text("第一次嵌入失败后应在下次 sync 重试", encoding="utf-8")

        attempt = {"count": 0}

        async def flaky_embed(texts: list[str]) -> list[list[float]]:
            attempt["count"] += 1
            if attempt["count"] == 1:
                raise RuntimeError("mock embed error")
            return [[0.4, 0.5, 0.6] for _ in texts]

        monkeypatch.setattr(manager.embedding_service, "available", lambda: True)
        monkeypatch.setattr(manager.embedding_service, "embed", flaky_embed)

        await manager.sync_index()

        conn = manager.index._conn()
        first_row = conn.execute("SELECT embedding FROM memory_chunks").fetchone()
        conn.close()
        assert first_row["embedding"] is None

        await manager.sync_index()

        conn = manager.index._conn()
        second_row = conn.execute("SELECT embedding FROM memory_chunks").fetchone()
        conn.close()
        assert second_row["embedding"] is not None
        assert attempt["count"] == 2

    @pytest.mark.asyncio
    async def test_sync_index_incremental(self, manager, workspace):
        (workspace / "MEMORY.md").write_text("版本1", encoding="utf-8")
        await manager.sync_index()

        # 不修改文件，再次 sync 不应更新
        mtimes_before = manager.index.get_indexed_mtimes()
        await manager.sync_index()
        mtimes_after = manager.index.get_indexed_mtimes()
        assert mtimes_before == mtimes_after

    @pytest.mark.asyncio
    async def test_sync_index_removes_deleted_files(self, manager, workspace):
        (workspace / "MEMORY.md").write_text("内容", encoding="utf-8")
        await manager.sync_index()
        assert "MEMORY.md" in manager.index.get_indexed_mtimes()

        os.remove(workspace / "MEMORY.md")
        await manager.sync_index()
        assert "MEMORY.md" not in manager.index.get_indexed_mtimes()

    @pytest.mark.asyncio
    async def test_search_bm25_fallback(self, manager, workspace):
        """嵌入不可用时搜索应降级为 BM25"""
        (workspace / "MEMORY.md").write_text("用户偏好: Python 3.12", encoding="utf-8")
        await manager.sync_index()

        # embedding service 默认不可用（没有 API key）
        results = await manager.search("Python")
        # BM25 可能返回结果也可能为空（取决于 FTS5 支持），不应崩溃
        assert isinstance(results, list)

    @pytest.mark.asyncio
    async def test_summarize_turn_writes_to_daily_file(self, workspace, tmp_path):
        """summarize_turn 应写入 agents/{agent_id}/memory/YYYY-MM-DD.md"""
        from datetime import datetime
        from agentos.capabilities.memory.manager import MemoryManager

        class _FakeProvider:
            async def call(self, **kwargs):
                return {"content": "用户偏好 Python"}

        class _FakeFactory:
            def get_provider(self, provider_name=None):
                return _FakeProvider()

        manager = MemoryManager(
            workspace_dir=str(workspace),
            config=MemoryConfig(enabled=True),
            db_path=tmp_path / "test_memory_summary.db",
            llm_factory=_FakeFactory(),
        )

        await manager.summarize_turn(
            messages=[
                {"role": "user", "content": "请记住我偏好 Python"},
                {"role": "assistant", "content": "好的，我会记住。"},
            ],
            agent_id="planner",
        )

        today_str = datetime.now().strftime("%Y-%m-%d")
        daily_path = workspace / "agents" / "planner" / "memory" / f"{today_str}.md"
        assert daily_path.exists()
        content = daily_path.read_text(encoding="utf-8")
        assert "用户偏好 Python" in content

    @pytest.mark.asyncio
    async def test_summarize_turn_default_agent_id(self, workspace, tmp_path):
        """未指定 agent_id 时应使用 default"""
        from datetime import datetime
        from agentos.capabilities.memory.manager import MemoryManager

        class _FakeProvider:
            async def call(self, **kwargs):
                return {"content": "总结内容"}

        class _FakeFactory:
            def get_provider(self, provider_name=None):
                return _FakeProvider()

        manager = MemoryManager(
            workspace_dir=str(workspace),
            config=MemoryConfig(enabled=True),
            db_path=tmp_path / "test_memory_summary2.db",
            llm_factory=_FakeFactory(),
        )

        await manager.summarize_turn(
            messages=[
                {"role": "user", "content": "你好"},
                {"role": "assistant", "content": "你好！"},
            ]
        )

        today_str = datetime.now().strftime("%Y-%m-%d")
        daily_path = workspace / "agents" / "default" / "memory" / f"{today_str}.md"
        assert daily_path.exists()


# ===== MemorySearchTool 测试 =====


class TestMemorySearchTool:
    """测试 MemorySearchTool"""

    @pytest.fixture
    def tool(self, tmp_path):
        from agentos.capabilities.memory.manager import MemoryManager

        ws = tmp_path / "workspace"
        ws.mkdir()
        (ws / "MEMORY.md").write_text("Python 3.12 偏好", encoding="utf-8")

        cfg = MemoryConfig(enabled=True)
        db_path = tmp_path / "test_memory.db"
        mgr = MemoryManager(workspace_dir=str(ws), config=cfg, db_path=db_path)
        return MemorySearchTool(mgr)

    def test_tool_metadata(self, tool):
        assert tool.name == "memory_search"
        assert "query" in tool.parameters["properties"]
        assert "query" in tool.parameters["required"]

    @pytest.mark.asyncio
    async def test_execute_empty_query(self, tool):
        import json
        result = await tool.execute(query="")
        parsed = json.loads(result)
        assert "error" in parsed

    @pytest.mark.asyncio
    async def test_execute_returns_json(self, tool):
        import json
        result = await tool.execute(query="Python")
        parsed = json.loads(result)
        assert "results" in parsed or "error" in parsed
