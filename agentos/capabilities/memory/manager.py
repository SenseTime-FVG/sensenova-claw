"""记忆管理器：统一管理记忆文件读取、向量索引和对话总结"""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from agentos.capabilities.memory.chunker import Chunker
from agentos.capabilities.memory.config import MemoryConfig
from agentos.capabilities.memory.embedding import EmbeddingService
from agentos.capabilities.memory.index import MemoryIndex, MemorySearchResult

if TYPE_CHECKING:
    from agentos.adapters.llm.factory import LLMFactory
    from agentos.kernel.events.bus import PublicEventBus

logger = logging.getLogger(__name__)


_SUMMARIZE_SYSTEM_PROMPT = (
    "你是一个对话总结助手。根据以下对话内容，提取并总结关键信息。\n\n"
    "要求：\n"
    "- 只保留【用户需求、目标、问题描述、已采取措施、最新解决状态、重要约定】\n"
    "- 删除寒暄、客套、重复推理过程、示例性代码细节\n"
    '- 如果用户在本轮会话中修正或推翻了之前的说法，以“最新结论”为准\n'
    "- 如果存在多个主题，请按主题分点描述\n"
    '- 使用第三人称、客观陈述，不要包含“用户说”“助手认为”等措辞\n'
    "- 不要加入任何新的推断或建议，只总结已出现的信息\n"
    "- 输出内容应适合直接作为 system / memory 注入使用\n"
    "- 输出格式简洁自然，不超过 200 字\n"
    "- 如果对话内容过于简单（如只是打招呼），输出空字符串即可"
)


class MemoryManager:
    def __init__(
        self,
        workspace_dir: str,
        config: MemoryConfig,
        db_path: Path,
        llm_factory: LLMFactory | None = None,
    ):
        self.workspace_dir = workspace_dir
        self.config = config
        self.index = MemoryIndex(db_path, config)
        self.chunker = Chunker()
        self.embedding_service = EmbeddingService(config)
        self.llm_factory = llm_factory
        self._index_lock = asyncio.Lock()

    async def start_config_listener(self, bus: PublicEventBus, config_data_getter) -> None:
        """订阅 config.updated 事件，memory section 变更时重建 MemoryConfig"""
        from agentos.kernel.events.types import CONFIG_UPDATED
        async for event in bus.subscribe():
            if event.type == CONFIG_UPDATED and event.payload.get("section") == "memory":
                new_config = MemoryConfig.from_dict(config_data_getter())
                self.config = new_config
                logger.info("MemoryManager: config reloaded due to config change")

    async def load_memory_md(self, agent_id: str | None = None) -> str | None:
        """读取 MEMORY.md 和 agent 专属记忆，格式化为 system prompt 片段

        1. 读取 {workspace}/MEMORY.md
        2. 如有 agent_id，额外读取 {workspace}/memory/{agent_id}.md
        3. 文件都不存在时返回 None
        4. 超过 bootstrap_max_chars 截断
        5. 包装为 Memory 指令段落
        """
        parts: list[str] = []

        for memory_path in self._global_memory_candidates():
            if not memory_path.exists():
                continue
            try:
                content = await asyncio.to_thread(memory_path.read_text, "utf-8")
                if content.strip():
                    parts.append(content.strip())
                    break
            except Exception:
                logger.warning("读取 MEMORY.md 失败", exc_info=True)

        if agent_id:
            agent_memory_path = Path(self.workspace_dir) / "memory" / f"{agent_id}.md"
            if agent_memory_path.exists():
                try:
                    agent_content = await asyncio.to_thread(agent_memory_path.read_text, "utf-8")
                    if agent_content.strip():
                        parts.append(f"### {agent_id} 的历史记忆\n{agent_content.strip()}")
                except Exception:
                    logger.warning("读取 agent 记忆失败: %s", agent_id, exc_info=True)

        if not parts:
            return None

        content = "\n\n".join(parts)
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
        """增量同步索引，并在同步后自动补齐待嵌入向量。"""
        async with self._index_lock:
            try:
                updated_count = await asyncio.to_thread(self._sync_index_blocking)
            except Exception:
                logger.warning("索引同步失败", exc_info=True)
                return

            if updated_count > 0:
                logger.debug("索引同步完成，准备补齐待嵌入 chunks（updated_files=%d）", updated_count)

            # 即使本次没有文件变化，也要重试历史遗留的 embedding=NULL chunks。
            await self._embed_pending_chunks_locked()

    def _sync_index_blocking(self) -> int:
        """阻塞式索引同步（在线程池中执行）"""
        workspace = Path(self.workspace_dir)

        # 扫描 memory 文件
        memory_files: dict[str, Path] = {}

        # MEMORY.md
        for memory_md in self._global_memory_candidates():
            if memory_md.exists():
                memory_files["MEMORY.md"] = memory_md
                break

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

        return updated_count

    async def embed_pending_chunks(self) -> None:
        """为没有嵌入向量的 chunks 生成嵌入（可选后台任务）"""
        async with self._index_lock:
            await self._embed_pending_chunks_locked()

    async def _embed_pending_chunks_locked(self) -> int:
        """在索引锁保护下，为待嵌入 chunks 生成向量。"""
        if not self.embedding_service.available():
            return 0

        conn = self.index._conn()
        rows = conn.execute(
            "SELECT chunk_id, text FROM memory_chunks WHERE embedding IS NULL"
        ).fetchall()
        conn.close()

        if not rows:
            return 0

        # 批量嵌入
        texts = [row["text"] for row in rows]
        chunk_ids = [row["chunk_id"] for row in rows]

        try:
            embeddings = await self.embedding_service.embed(texts)
        except Exception:
            logger.warning("批量嵌入失败", exc_info=True)
            return 0

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
        return len(chunk_ids)

    async def summarize_turn(
        self,
        messages: list[dict[str, Any]],
        provider: str | None = None,
        model: str | None = None,
        agent_id: str | None = None,
    ) -> None:
        """在每个 turn 结束后提取关键信息并追加写入记忆文件。"""
        if not self.llm_factory:
            logger.debug("summarize_turn 跳过: llm_factory 未配置")
            return

        conversation = self._extract_conversation(messages)
        if not conversation:
            return

        try:
            summary = await self._call_llm_for_summary(
                conversation,
                provider_name=provider,
                model=model,
            )
        except Exception:
            logger.warning("对话总结 LLM 调用失败", exc_info=True)
            return

        if not summary or not summary.strip():
            logger.debug("summarize_turn 跳过: LLM 返回空总结")
            return

        await self._append_to_memory_md(summary.strip(), agent_id=agent_id)

    def _extract_conversation(self, messages: list[dict[str, Any]]) -> str:
        """从消息列表中提取 user/assistant 对话内容。"""
        lines: list[str] = []
        for msg in messages:
            role = msg.get("role", "")
            content = msg.get("content", "")
            if role == "user" and content:
                lines.append(f"用户: {content}")
            elif role == "assistant" and content:
                lines.append(f"助手: {content}")
        return "\n".join(lines)

    async def _call_llm_for_summary(
        self,
        conversation: str,
        provider_name: str | None = None,
        model: str | None = None,
    ) -> str:
        """调用 LLM 对当前对话进行摘要。"""
        from agentos.platform.config.config import config

        if not model:
            model = config.get("llm.default_model")
        resolved_provider, resolved_model = config.resolve_model(model)
        provider_name = provider_name or resolved_provider
        model = resolved_model

        provider = self.llm_factory.get_provider(provider_name)
        response = await provider.call(
            model=model,
            messages=[
                {"role": "system", "content": _SUMMARIZE_SYSTEM_PROMPT},
                {"role": "user", "content": f"请总结以下对话：\n\n{conversation}"},
            ],
            tools=None,
            temperature=0.1,
            max_tokens=500,
        )
        return str(response.get("content", "") or "")

    async def _append_to_memory_md(self, summary: str, agent_id: str | None = None) -> None:
        """将总结内容追加到对应 agent 的记忆文件。"""
        if agent_id:
            memory_path = Path(self.workspace_dir) / "memory" / f"{agent_id}.md"
        else:
            memory_path = Path(self.workspace_dir) / "MEMORY.md"

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        entry = f"\n\n---\n[{timestamp}]\n{summary}\n"

        try:
            if not agent_id:
                await asyncio.to_thread(self._migrate_legacy_memory_file, memory_path)
            await asyncio.to_thread(self._append_file_blocking, memory_path, entry)
            logger.info("对话总结已追加到 %s", memory_path)
        except Exception:
            logger.warning("写入记忆文件失败", exc_info=True)

    @staticmethod
    def _append_file_blocking(path: Path, content: str) -> None:
        """阻塞式追加文件内容。"""
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as file:
            file.write(content)

    def _global_memory_candidates(self) -> list[Path]:
        workspace = Path(self.workspace_dir)
        return [workspace / "MEMORY.md", workspace / "memory.md"]

    @staticmethod
    def _migrate_legacy_memory_file(target: Path) -> None:
        legacy = target.parent / "memory.md"
        if legacy.exists() and not target.exists():
            legacy.rename(target)

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
