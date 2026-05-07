"""记忆管理器：统一管理记忆文件读取、向量索引和对话总结

存储结构（v1.3）：
  ~/.sensenova-claw/agents/{agent_id}/MEMORY.md            — 长期累积记忆
  ~/.sensenova-claw/agents/{agent_id}/memory/YYYY-MM-DD.md  — 按日记忆
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any

from sensenova_claw.capabilities.memory.chunker import Chunker
from sensenova_claw.capabilities.memory.config import MemoryConfig
from sensenova_claw.capabilities.memory.embedding import EmbeddingService
from sensenova_claw.capabilities.memory.index import MemoryIndex, MemorySearchResult

if TYPE_CHECKING:
    from sensenova_claw.adapters.llm.factory import LLMFactory
    from sensenova_claw.kernel.events.bus import PublicEventBus

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


def _normalize_summary_llm_error(provider_name: str, model: str, error_message: str) -> dict[str, Any]:
    """复制 llm_worker 的错误归一化逻辑，供对话总结重试使用。"""
    context: dict[str, Any] = {"model": model, "provider": provider_name}
    normalized = {
        "error_type": None,
        "error_code": "llm_call_failed",
        "error_message": error_message,
        "user_message": f"LLM调用失败: {error_message}",
        "context": context,
    }

    unsupported_params = _extract_summary_unsupported_parameters(error_message)
    if unsupported_params:
        context["unsupported_params"] = unsupported_params
        normalized["error_code"] = "unsupported_parameters"
        normalized["user_message"] = (
            "当前模型或网关不支持以下请求参数："
            f"{', '.join(unsupported_params)}。"
            "系统会尝试自动移除后重试。"
        )

    conflicting_params = _extract_summary_conflicting_parameters(error_message)
    if conflicting_params:
        context["conflicting_params"] = conflicting_params
        normalized["error_code"] = "conflicting_parameters"
        normalized["user_message"] = (
            "当前模型或网关不允许同时指定以下参数："
            f"{', '.join(conflicting_params)}。"
            "系统会尝试仅保留第一个参数后重试。"
        )

    return normalized


def _extract_summary_unsupported_parameters(error_message: str) -> list[str]:
    """复制 llm_worker 的 unsupported parameter 提取逻辑。"""
    normalized_message = error_message.replace("\\'", "'").replace('\\"', '"')
    candidates: list[str] = []

    single_patterns = [
        r"Unknown parameter:\s*['\"]([^'\"]+)['\"]",
        r"Unsupported parameter:\s*['\"]([^'\"]+)['\"]",
    ]
    for pattern in single_patterns:
        candidates.extend(re.findall(pattern, normalized_message, flags=re.IGNORECASE))

    list_patterns = [
        r"Unknown parameters:\s*\[([^\]]+)\]",
        r"Unsupported parameters:\s*\[([^\]]+)\]",
    ]
    for pattern in list_patterns:
        for raw_group in re.findall(pattern, normalized_message, flags=re.IGNORECASE):
            candidates.extend(re.findall(r"['\"]([^'\"]+)['\"]", raw_group))

    if re.search(r'"code"\s*:\s*"unknown_parameter"', normalized_message, flags=re.IGNORECASE):
        candidates.extend(re.findall(r'"param"\s*:\s*"([^"]+)"', normalized_message, flags=re.IGNORECASE))

    unique_params: list[str] = []
    for name in candidates:
        param = str(name).strip()
        if param and param not in unique_params:
            unique_params.append(param)
    return unique_params


def _extract_summary_conflicting_parameters(error_message: str) -> list[str]:
    """复制 llm_worker 的 conflicting parameter 提取逻辑。"""
    normalized_message = error_message.replace("\\'", "'").replace('\\"', '"')
    match = re.search(
        r"[`'\"]?([a-zA-Z_][a-zA-Z0-9_]*)[`'\"]?\s+and\s+[`'\"]?([a-zA-Z_][a-zA-Z0-9_]*)[`'\"]?\s+cannot both be specified",
        normalized_message,
        flags=re.IGNORECASE,
    )
    if not match:
        return []
    return [match.group(1), match.group(2)]


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
        from sensenova_claw.kernel.events.types import CONFIG_UPDATED
        async for event in bus.subscribe():
            if event.type == CONFIG_UPDATED and event.payload.get("section") == "memory":
                new_config = MemoryConfig.from_dict(config_data_getter())
                self.config = new_config
                logger.info("MemoryManager: config reloaded due to config change")

    async def load_memory_md(self, agent_id: str | None = None) -> str | None:
        """生成记忆指引 prompt，告诉 Agent 应该读取哪些记忆文件。

        不再把文件内容注入 system prompt，而是列出文件路径，
        由 Agent 在需要时通过 read_file 工具主动读取。
        """
        effective_id = agent_id or "default"
        return self._format_memory_prompt(effective_id)

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

        # 扫描所有 agent 的记忆文件
        memory_files: dict[str, Path] = {}

        # 新路径：agents/*/MEMORY.md + agents/*/memory/*.md
        agents_dir = workspace / "agents"
        if agents_dir.exists():
            for agent_dir in agents_dir.iterdir():
                if not agent_dir.is_dir():
                    continue
                agent_mem_md = agent_dir / "MEMORY.md"
                if agent_mem_md.exists():
                    rel = str(agent_mem_md.relative_to(workspace)).replace("\\", "/")
                    memory_files[rel] = agent_mem_md
                mem_sub = agent_dir / "memory"
                if mem_sub.exists():
                    for md_file in mem_sub.glob("*.md"):
                        rel = str(md_file.relative_to(workspace)).replace("\\", "/")
                        memory_files[rel] = md_file

        # 兼容旧路径：workspace/MEMORY.md
        for legacy in self._global_memory_candidates():
            if legacy.exists():
                rel = str(legacy.relative_to(workspace)).replace("\\", "/")
                memory_files[rel] = legacy
                break

        # 兼容旧路径：workspace/memory/*.md
        old_memory_dir = workspace / "memory"
        if old_memory_dir.exists():
            for md_file in old_memory_dir.glob("**/*.md"):
                rel = str(md_file.relative_to(workspace)).replace("\\", "/")
                memory_files[rel] = md_file

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
        from sensenova_claw.platform.config.config import config

        if provider_name and model:
            resolved_provider, resolved_model = provider_name, model
        else:
            model_key = model or config.get("llm.default_model")
            resolved_provider, resolved_model = config.resolve_model(model_key)

        provider_name = provider_name or resolved_provider
        model = resolved_model

        provider = self.llm_factory.get_provider(provider_name)
        attempt_temperature: float | None = 1.0
        attempt_extra_body = dict(config.get("agent.extra_body", {})) or None
        unsupported_retry_count = 0
        conflicting_retry_count = 0
        messages = [
            {"role": "system", "content": _SUMMARIZE_SYSTEM_PROMPT},
            {"role": "user", "content": f"请总结以下对话：\n\n{conversation}"},
        ]

        while True:
            try:
                response = await provider.call(
                    model=model,
                    messages=messages,
                    tools=None,
                    temperature=attempt_temperature,
                    max_tokens=500,
                    extra_body=attempt_extra_body,
                )
                return str(response.get("content", "") or "")
            except Exception as exc:
                normalized_error = _normalize_summary_llm_error(provider_name, model, str(exc))

                unsupported_params = normalized_error["context"].get("unsupported_params") or []
                removable_params = [
                    param for param in unsupported_params
                    if isinstance(attempt_extra_body, dict) and param in attempt_extra_body
                ]
                if (
                    normalized_error["error_code"] == "unsupported_parameters"
                    and removable_params
                    and unsupported_retry_count < 3
                ):
                    unsupported_retry_count += 1
                    logger.warning(
                        "summary llm call has unsupported parameters, retry without params provider=%s model=%s params=%s attempt=%s",
                        provider_name,
                        model,
                        removable_params,
                        unsupported_retry_count,
                    )
                    next_extra_body = dict(attempt_extra_body)
                    for param in removable_params:
                        next_extra_body[param] = None
                    attempt_extra_body = next_extra_body
                    continue

                conflicting_params = normalized_error["context"].get("conflicting_params") or []
                removable_conflicting_params = list(conflicting_params[1:]) if len(conflicting_params) > 1 else []
                if (
                    normalized_error["error_code"] == "conflicting_parameters"
                    and removable_conflicting_params
                    and conflicting_retry_count < 3
                ):
                    conflicting_retry_count += 1
                    removed_params: list[str] = []
                    next_extra_body = dict(attempt_extra_body) if attempt_extra_body else {}
                    for param in removable_conflicting_params:
                        if param == "temperature":
                            attempt_temperature = None
                            removed_params.append(param)
                            continue
                        if param in next_extra_body:
                            next_extra_body[param] = None
                            removed_params.append(param)

                    if removed_params:
                        logger.warning(
                            "summary llm call has conflicting parameters, retry keeping first param provider=%s model=%s params=%s kept=%s attempt=%s",
                            provider_name,
                            model,
                            removed_params,
                            conflicting_params[0],
                            conflicting_retry_count,
                        )
                        attempt_extra_body = next_extra_body or None
                        continue

                raise

    async def _append_to_memory_md(self, summary: str, agent_id: str | None = None) -> None:
        """将总结内容追加到当日记忆文件 agents/{agent_id}/memory/YYYY-MM-DD.md"""
        effective_id = agent_id or "default"
        today_str = datetime.now().strftime("%Y-%m-%d")
        daily_path = self._daily_memory_path(effective_id, today_str)

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        entry = f"\n\n---\n[{timestamp}]\n{summary}\n"

        try:
            await asyncio.to_thread(self._append_file_blocking, daily_path, entry)
            logger.info("对话总结已追加到 %s", daily_path)
        except Exception:
            logger.warning("写入记忆文件失败", exc_info=True)

    @staticmethod
    def _append_file_blocking(path: Path, content: str) -> None:
        """阻塞式追加文件内容。"""
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as file:
            file.write(content)

    def _agent_memory_dir(self, agent_id: str) -> Path:
        """返回 agents/{agent_id}/memory/ 目录路径"""
        return Path(self.workspace_dir) / "agents" / agent_id / "memory"

    def _agent_memory_md(self, agent_id: str) -> Path:
        """返回 agents/{agent_id}/MEMORY.md 路径"""
        return Path(self.workspace_dir) / "agents" / agent_id / "MEMORY.md"

    def _daily_memory_path(self, agent_id: str, date_str: str) -> Path:
        """返回 agents/{agent_id}/memory/YYYY-MM-DD.md 路径"""
        return self._agent_memory_dir(agent_id) / f"{date_str}.md"

    def _global_memory_candidates(self) -> list[Path]:
        """兼容旧路径：workspace/MEMORY.md, workspace/memory.md"""
        workspace = Path(self.workspace_dir)
        return [workspace / "MEMORY.md", workspace / "memory.md"]

    def _collect_memory_paths(self, agent_id: str) -> dict[str, Path]:
        """收集该 agent 的所有记忆文件（用于索引扫描）。

        包含：agents/{agent_id}/MEMORY.md + agents/{agent_id}/memory/*.md
        兼容旧路径：workspace/MEMORY.md, workspace/memory/{agent_id}.md
        """
        files: dict[str, Path] = {}
        workspace = Path(self.workspace_dir)

        # 新路径
        agent_mem_md = self._agent_memory_md(agent_id)
        if agent_mem_md.exists():
            rel = str(agent_mem_md.relative_to(workspace)).replace("\\", "/")
            files[rel] = agent_mem_md

        mem_dir = self._agent_memory_dir(agent_id)
        if mem_dir.exists():
            for md_file in mem_dir.glob("*.md"):
                rel = str(md_file.relative_to(workspace)).replace("\\", "/")
                files[rel] = md_file

        # 兼容旧路径
        for legacy in self._global_memory_candidates():
            if legacy.exists():
                rel = str(legacy.relative_to(workspace)).replace("\\", "/")
                files[rel] = legacy
                break

        old_agent_mem = workspace / "memory" / f"{agent_id}.md"
        if old_agent_mem.exists():
            rel = str(old_agent_mem.relative_to(workspace)).replace("\\", "/")
            files[rel] = old_agent_mem

        return files

    def _format_memory_prompt(self, agent_id: str) -> str:
        """生成记忆指引 prompt（不含文件内容，由 Agent 按需 read_file）。

        prompt_builder._build_memory 会自动添加 '## Memory' 标题。
        """
        today = datetime.now()
        yesterday = today - timedelta(days=1)
        today_str = today.strftime("%Y-%m-%d")
        yesterday_str = yesterday.strftime("%Y-%m-%d")

        # 基础路径（使用 ~ 简写）
        base = f"~/.sensenova-claw/agents/{agent_id}"
        memory_md = f"{base}/MEMORY.md"
        today_file = f"{base}/memory/{today_str}.md"
        yesterday_file = f"{base}/memory/{yesterday_str}.md"

        return (
            "你拥有长期记忆能力。以下是你的记忆文件，请在需要时用 read_file 读取。\n\n"
            "### 记忆文件\n"
            f"- **长期记忆**: `{memory_md}` — 用户偏好、重要决策、长期有效的信息\n"
            f"- **今日记忆**: `{today_file}` — 今天的对话摘要和上下文\n"
            f"- **昨日记忆**: `{yesterday_file}` — 昨天的对话摘要\n\n"
            "### 记忆读取规则\n"
            "- 每次会话开始时，先用 read_file 读取上述三个文件（不存在则跳过）\n"
            "- 回答涉及过往工作、决策、日期、人物、偏好的问题前，先读记忆文件或调用 memory_search\n\n"
            "### 记忆写入规则\n"
            f"- 用户提到偏好、个人信息、重要决策时，用 write_file 追加到 `{memory_md}`\n"
            f"- 日常笔记和运行上下文追加到 `{today_file}`\n"
            "- 已有文件时追加内容，不要覆盖\n"
        )
