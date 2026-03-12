# 18. 长期记忆系统

> 版本: v0.5
> 参考: OpenClaw memory 系统 + xhx_agent_v3/memory

---

## 1. 概述

为 AgentOS 引入跨会话长期记忆——**文件即记忆**，以 Workspace 中的 Markdown 文件为唯一事实来源，通过 `memory_search` 工具实现语义检索，通过现有 `write_file` / `read_file` 工具实现记忆读写。

### 1.1 核心取舍

| 做 | 不做 |
|---|---|
| Markdown 文件做记忆存储（可读、可编辑、可 git 管理） | 不引入 mem0 / Pinecone / Qdrant 等外部向量库 |
| `memory_search` 语义搜索工具 | 不做隐式自动注入全部记忆（仅 MEMORY.md 注入） |
| SQLite 本地向量索引 + BM25 混合搜索 | 不依赖云端向量服务 |
| `MEMORY.md` 自动注入 system prompt | 不做自动摘要 / 自动事实提取 |
| 复用现有 `write_file` 写入记忆 | 不新增 memory_store / memory_forget 工具 |

### 1.2 设计原则

| 原则 | 说明 |
|------|------|
| **文件即记忆** | Markdown 文件是唯一事实来源，Agent 只"记住"写入磁盘的内容 |
| **显式优于隐式** | 记忆的读写都通过显式工具调用（search / read_file / write_file） |
| **两层记忆** | 长期事实 (`MEMORY.md`) 和每日日志 (`memory/YYYY-MM-DD.md`) 分离 |
| **渐进降级** | 向量搜索不可用时降级为 BM25，嵌入服务不可用时返回空结果 |
| **不阻塞事件循环** | 嵌入和搜索通过 `asyncio.to_thread()` 推到线程池 |

---

## 2. 记忆存储

### 2.1 文件布局

```
{workspace}/
├── MEMORY.md                    ← 长期记忆（持久事实、偏好、决策）
└── memory/
    ├── 2026-03-08.md           ← 每日日志（append-only）
    ├── 2026-03-09.md
    └── 2026-03-10.md
```

### 2.2 两层记忆模型

| 文件 | 用途 | 写入方式 | 读取方式 |
|------|------|----------|----------|
| `MEMORY.md` | 长期记忆：偏好、决策、持久事实 | Agent 通过 `write_file` 写入 | 每次 turn 自动注入 system prompt |
| `memory/YYYY-MM-DD.md` | 每日日志：运行上下文、临时笔记 | Agent 通过 `write_file` 追加 | 通过 `memory_search` 按需检索 |

**写入约定**：
- `MEMORY.md` 由 Agent 全权管理内容结构，适合少量高价值信息（偏好、身份、关键决策）
- `memory/YYYY-MM-DD.md` 仅追加（append-only），不修改历史条目
- `memory/` 目录不存在时由 Agent 调用 `write_file` 时自动创建

---

## 3. 记忆工具

### 3.1 `memory_search` — 语义搜索（新增）

```python
class MemorySearchTool(Tool):
    name = "memory_search"
    description = "搜索长期记忆文件（MEMORY.md + memory/*.md），返回与查询最相关的片段"
    parameters = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "搜索查询"},
            "max_results": {"type": "integer", "description": "最大返回数，默认5"},
        },
        "required": ["query"],
    }
```

返回格式：

```python
@dataclass
class MemorySearchResult:
    snippet: str          # 匹配片段（~700 字符）
    path: str             # 文件路径（workspace 相对）
    start_line: int
    end_line: int
    score: float          # 相似度分数
```

关键行为：
- 搜索范围：`MEMORY.md` + `memory/**/*.md`
- 分块：~400 token 目标，80 token 重叠，按段落/句子边界切分
- 混合搜索：BM25 + 向量加权合并
- 嵌入服务不可用时降级为纯 BM25 关键词搜索
- 搜索前自动检查索引是否需要更新（dirty 标记）

### 3.2 现有工具复用

| 操作 | 使用的工具 | 说明 |
|------|-----------|------|
| 写入记忆 | `write_file` | Agent 写 MEMORY.md 或 memory/YYYY-MM-DD.md |
| 精确读取 | `read_file` | Agent 根据 memory_search 结果读取指定行 |
| 删除/编辑记忆 | `write_file` | Agent 重写 MEMORY.md 移除不需要的内容 |

**不新增** memory_store / memory_forget 工具，减少工具数量，降低 LLM 选择负担。

### 3.3 System Prompt 中的 Memory 指令

当 `memory_search` 可用且 `MEMORY.md` 存在时，在 system prompt 中注入：

```
## Memory

你拥有长期记忆能力。

### 记忆读取
- 回答涉及过往工作、决策、日期、人物、偏好的问题前，先调用 memory_search 搜索记忆
- 搜索后可用 read_file 获取完整上下文

### 记忆写入
- 用户提到偏好、个人信息、重要决策时，用 write_file 写入 MEMORY.md
- 日常笔记和运行上下文追加到 memory/{今天日期}.md
- 已有文件时追加内容，不要覆盖

### 当前 MEMORY.md 内容
{memory_md_content}
```

---

## 4. 向量搜索索引

### 4.1 架构

```
memory 文件变更
  → 搜索时检测 dirty → 增量重索引
  → 分块（~400 token, 80 token overlap）
  → Embedding（OpenAI text-embedding-3-small）
  → 存入 SQLite
  → 搜索时：BM25 + 向量混合 → 排序 → 返回
```

### 4.2 SQLite 存储

复用 AgentOS 已有的 SQLite 基础设施，新增 memory 相关表：

```sql
CREATE TABLE IF NOT EXISTS memory_chunks (
    chunk_id TEXT PRIMARY KEY,
    path TEXT NOT NULL,              -- workspace 相对路径
    start_line INTEGER NOT NULL,
    end_line INTEGER NOT NULL,
    text TEXT NOT NULL,
    embedding BLOB,                  -- float32 数组序列化
    file_mtime REAL NOT NULL,        -- 文件修改时间（用于增量索引）
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_chunks_path ON memory_chunks(path);

-- FTS5 全文搜索表
CREATE VIRTUAL TABLE IF NOT EXISTS memory_chunks_fts
USING fts5(chunk_id, text, content=memory_chunks, content_rowid=rowid);
```

### 4.3 混合搜索

```
Query
  ├── 向量搜索 → top K × 4 候选（cosine similarity）
  ├── BM25 搜索 → top K × 4 候选（FTS5 rank）
  └── 加权合并
       ├── final_score = 0.7 × vector_score + 0.3 × bm25_score
       └── Top K 结果
```

降级策略：
- 嵌入 API 不可用 → 仅 BM25 关键词搜索
- FTS5 不可用 → 仅向量搜索
- 都不可用 → 返回空结果

### 4.4 索引刷新

采用 lazy 策略（不用 file watcher）：

| 时机 | 方式 |
|------|------|
| `memory_search` 调用时 | 检查文件 mtime，有变更则增量重索引 |
| 后端启动时 | 全量扫描一次 |

增量逻辑：
1. 扫描 `MEMORY.md` + `memory/**/*.md`
2. 比较文件 mtime 与索引中的 `file_mtime`
3. 仅重新分块和嵌入变更的文件
4. 删除已不存在的文件的 chunks

---

## 5. MEMORY.md 注入

### 5.1 注入位置

在 `AgentSessionWorker._handle_user_input()` 中，调用 ContextBuilder 之前读取 `MEMORY.md`：

```python
async def _handle_user_input(self, event: EventEnvelope) -> None:
    content = str(event.payload.get("content", ""))
    # ...

    # 读取 MEMORY.md 内容（如果存在）
    memory_context = None
    if self.rt.memory_manager:
        memory_context = await self.rt.memory_manager.load_memory_md()

    history = self.rt.state_store.get_session_history(self.session_id)
    messages = self.rt.context_builder.build_messages(
        content, history,
        memory_context=memory_context,
    )
    # ...
```

### 5.2 ContextBuilder 修改

新增 `memory_context` 参数（纯字符串拼接，无 I/O）：

```python
def build_messages(
    self,
    user_input: str,
    history: list[dict] | None = None,
    memory_context: str | None = None,
) -> list[dict]:
    system_prompt = f"{base_prompt}\n\n系统类型: {system_type}\n当前时间: {current_time}"

    if self.skill_registry:
        system_prompt += self._build_skills_section()

    if memory_context:
        system_prompt += f"\n\n{memory_context}"

    # ...
```

### 5.3 截断保护

`MEMORY.md` 内容超过 `memory.bootstrap_max_chars`（默认 8000 字符）时截断，附加提示：

```
...(内容已截断，使用 memory_search 检索完整内容)
```

---

## 6. 核心模块

### 6.1 MemoryManager

统一管理记忆文件读取和向量索引：

```python
class MemoryManager:
    def __init__(self, workspace_dir: str, config: MemoryConfig, repo: Repository):
        self.workspace_dir = workspace_dir
        self.config = config
        self.index = MemoryIndex(repo, config)

    async def load_memory_md(self) -> str | None:
        """读取 MEMORY.md，格式化为 system prompt 片段
        
        1. 读取 {workspace}/MEMORY.md
        2. 文件不存在返回 None
        3. 超过 bootstrap_max_chars 截断
        4. 包装为 Memory Recall 指令段落
        """
        pass

    async def search(self, query: str, max_results: int = 5) -> list[MemorySearchResult]:
        """搜索记忆文件
        
        1. 确保索引已同步（lazy sync）
        2. 执行混合搜索
        3. 通过 asyncio.to_thread() 不阻塞事件循环
        """
        pass

    async def sync_index(self) -> None:
        """增量同步索引：扫描文件变更 → 重新分块 → 嵌入 → 存储"""
        pass
```

### 6.2 MemoryIndex

SQLite 存储和搜索引擎：

```python
class MemoryIndex:
    def __init__(self, repo: Repository, config: MemoryConfig):
        self.repo = repo
        self.config = config

    def upsert_chunks(self, path: str, chunks: list[MemoryChunk]) -> None:
        """写入/更新分块（删除旧 chunks + 插入新 chunks）"""
        pass

    def search_vector(self, embedding: list[float], limit: int) -> list[tuple[str, float]]:
        """向量相似度搜索"""
        pass

    def search_bm25(self, query: str, limit: int) -> list[tuple[str, float]]:
        """BM25 全文搜索"""
        pass

    def hybrid_search(self, query: str, embedding: list[float], limit: int) -> list[MemorySearchResult]:
        """混合搜索：向量 + BM25 加权合并"""
        pass

    def get_indexed_mtimes(self) -> dict[str, float]:
        """获取已索引文件的 mtime 映射"""
        pass

    def remove_file(self, path: str) -> None:
        """删除指定文件的所有 chunks"""
        pass
```

### 6.3 Chunker

文本分块器：

```python
class Chunker:
    def chunk(
        self,
        text: str,
        path: str,
        chunk_size: int = 400,    # 目标 token 数
        overlap: int = 80,         # 重叠 token 数
    ) -> list[MemoryChunk]:
        """按段落/句子边界智能分块，保留 overlap 确保上下文连续性"""
        pass
```

### 6.4 EmbeddingService

嵌入服务封装（Phase 1 仅 OpenAI）：

```python
class EmbeddingService:
    def __init__(self, config: MemoryConfig):
        self.config = config

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """批量文本 → 向量（通过 asyncio.to_thread 调用 OpenAI SDK）"""
        pass

    def dimensions(self) -> int:
        """当前模型的向量维度"""
        pass

    def available(self) -> bool:
        """嵌入服务是否可用（API key 已配置）"""
        pass
```

---

## 7. 配置

### 7.1 config.yaml

```yaml
memory:
  enabled: true
  bootstrap_max_chars: 8000          # MEMORY.md 注入 system prompt 的最大字符数

  search:
    enabled: true
    embedding_model: "text-embedding-3-small"
    # 嵌入 API 复用 llm_providers.openai 的 api_key 和 base_url
    chunk_size: 400                  # 分块目标 token 数
    chunk_overlap: 80                # 分块重叠 token 数
    hybrid:
      vector_weight: 0.7
      text_weight: 0.3
      candidate_multiplier: 4       # 候选数 = max_results × multiplier
```

### 7.2 DEFAULT_CONFIG 扩展

```python
DEFAULT_CONFIG = {
    # ... 现有配置 ...
    "memory": {
        "enabled": False,
        "bootstrap_max_chars": 8000,
        "search": {
            "enabled": True,
            "embedding_model": "text-embedding-3-small",
            "chunk_size": 400,
            "chunk_overlap": 80,
            "hybrid": {
                "vector_weight": 0.7,
                "text_weight": 0.3,
                "candidate_multiplier": 4,
            },
        },
    },
}
```

---

## 8. 目录结构

```
backend/app/
└── memory/
    ├── __init__.py
    ├── config.py              # MemoryConfig 数据类
    ├── manager.py             # MemoryManager（文件读取 + 索引管理）
    ├── index.py               # MemoryIndex（SQLite 存储 + 混合搜索）
    ├── chunker.py             # 文本分块
    ├── embedding.py           # EmbeddingService（OpenAI 嵌入封装）
    └── tools.py               # MemorySearchTool
```

---

## 9. 修改文件清单

| 文件 | 修改内容 |
|------|----------|
| `backend/app/main.py` | 初始化 MemoryManager，注入 AgentRuntime 和 ToolRegistry |
| `backend/app/runtime/agent_runtime.py` | 新增 `memory_manager` 属性 |
| `backend/app/runtime/workers/agent_worker.py` | `_handle_user_input` 中读取 MEMORY.md 并传入 ContextBuilder |
| `backend/app/runtime/context_builder.py` | `build_messages()` 新增 `memory_context` 参数 |
| `backend/app/core/config.py` | `DEFAULT_CONFIG` 添加 `memory` 配置段 |
| `backend/app/db/repository.py` | 新增 `memory_chunks` 表 schema 和 CRUD 方法 |

### 新增文件

| 文件 | 说明 |
|------|------|
| `backend/app/memory/__init__.py` | 模块入口 |
| `backend/app/memory/config.py` | MemoryConfig |
| `backend/app/memory/manager.py` | MemoryManager |
| `backend/app/memory/index.py` | MemoryIndex（SQLite 存储 + 搜索） |
| `backend/app/memory/chunker.py` | 文本分块 |
| `backend/app/memory/embedding.py` | EmbeddingService |
| `backend/app/memory/tools.py` | MemorySearchTool |

---

## 10. 初始化流程

```python
# main.py lifespan() 中

memory_manager = None
memory_enabled = config.get("memory.enabled", False)

if memory_enabled:
    from app.memory.config import MemoryConfig
    from app.memory.manager import MemoryManager
    from app.memory.tools import MemorySearchTool

    mem_config = MemoryConfig.from_dict(config.data)
    memory_manager = MemoryManager(
        workspace_dir=str(workspace_dir),
        config=mem_config,
        repo=repo,
    )
    await memory_manager.sync_index()

    if mem_config.search_enabled:
        tool_registry.register(MemorySearchTool(memory_manager))

    logger.info("Memory system enabled (workspace=%s)", workspace_dir)

agent_runtime = AgentRuntime(
    bus_router=bus_router,
    repo=repo,
    context_builder=context_builder,
    tool_registry=tool_registry,
    state_store=state_store,
    memory_manager=memory_manager,  # 新增，可能为 None
)
```

---

## 11. 运行时数据流

### 11.1 对话中的记忆读写

```
用户: "上周部署方案最终选了哪个？"
  │
  ├── AgentSessionWorker._handle_user_input()
  │   └── memory_manager.load_memory_md()
  │       → 读取 MEMORY.md，注入 system prompt
  │
  ├── Agent 判断：涉及过往决策 → 调用 memory_search
  │   └── memory_search(query="部署方案 决定")
  │       ├── 向量搜索 → memory/2026-03-03.md 第 15-22 行
  │       └── BM25 搜索 → MEMORY.md 第 8 行
  │
  ├── Agent 调用 read_file 获取详细内容
  │   └── read_file(file_path="memory/2026-03-03.md", start_line=15, num_lines=8)
  │
  └── Agent 综合信息回复用户
```

### 11.2 记忆写入

```
用户: "记住我喜欢用 Python 3.12"
  │
  ├── Agent 判断：用户偏好，应写入 MEMORY.md
  │   └── write_file(file_path="MEMORY.md", content="...", mode="append")
  │
  └── Agent 回复确认

用户: "今天完成了 API 设计"
  │
  ├── Agent 判断：日常笔记，写入每日日志
  │   └── write_file(file_path="memory/2026-03-10.md", content="...", mode="append")
  │
  └── Agent 回复确认
```

---

## 12. 交付计划

| 步骤 | 内容 | 工期 |
|------|------|------|
| 1 | MemoryConfig + MemoryManager（load_memory_md） | 0.5 天 |
| 2 | ContextBuilder 新增 memory_context + AgentWorker 集成 | 0.5 天 |
| 3 | Chunker + EmbeddingService（OpenAI） | 0.5 天 |
| 4 | MemoryIndex（SQLite 存储 + FTS5 + 向量搜索） | 1 天 |
| 5 | 混合搜索 + MemorySearchTool | 0.5 天 |
| 6 | 配置扩展 + main.py 集成 + DB schema | 0.5 天 |
| 7 | E2E 测试 | 0.5 天 |

**总计：4 天**

---

## 13. 验收标准

1. **MEMORY.md 注入**: system prompt 中包含 MEMORY.md 的内容
2. **语义搜索**: `memory_search("部署方案")` 能匹配到 memory/ 下包含 "deployment" 的片段
3. **BM25 降级**: 嵌入 API 不可用时，`memory_search("DOCKER_HOST")` 仍能通过关键词命中
4. **写入记忆**: Agent 能通过 `write_file` 写入 MEMORY.md 和 memory/YYYY-MM-DD.md
5. **跨会话**: 会话 1 写入 MEMORY.md 后，会话 2 的 system prompt 包含该内容
6. **增量索引**: 修改 memory 文件后，下次 search 能搜到新内容
7. **配置开关**: `memory.enabled: false` 时系统行为与 v0.4 完全一致
8. **优雅降级**: 嵌入 API 不可用时仅 BM25，不崩溃
9. **不阻塞**: 嵌入和搜索不阻塞 asyncio 事件循环

---

## 14. 测试策略

### 14.1 单元测试

```python
# test_chunker.py
def test_chunk_by_paragraph()
def test_chunk_overlap()
def test_chunk_respects_size_limit()

# test_memory_index.py
async def test_upsert_and_search_bm25()
async def test_upsert_and_search_vector()
async def test_hybrid_search_weighted()
async def test_incremental_sync()

# test_memory_manager.py
async def test_load_memory_md_missing_file()
async def test_load_memory_md_truncation()
async def test_search_delegates_to_index()
```

### 14.2 集成测试

```python
async def test_agent_worker_injects_memory_md()
async def test_context_builder_pure_function()
async def test_memory_search_tool_registered()
async def test_memory_disabled_no_side_effects()
```

### 14.3 E2E 测试

```python
async def test_write_and_search_cycle():
    """
    1. 启动后端（memory.enabled=True）
    2. 用户说 "记住我叫张三"，验证 Agent 调用 write_file 写入 MEMORY.md
    3. 新会话，验证 system prompt 包含 "张三"
    4. 用户说 "我叫什么？"，验证 Agent 回答 "张三"
    """

async def test_memory_search_finds_daily_log():
    """
    1. 写入 memory/2026-03-10.md
    2. 调用 memory_search
    3. 验证搜索结果包含写入的内容
    """
```

---

## 15. 风险与限制

| 风险 | 缓解措施 |
|------|----------|
| 嵌入 API 不可用 | 降级为 BM25 关键词搜索 |
| MEMORY.md 过大 | bootstrap_max_chars 截断保护 |
| 事件循环阻塞 | 所有 I/O 通过 asyncio.to_thread() |
| Agent 不主动写入记忆 | system prompt 明确指引写入时机和位置 |
| 索引与文件不同步 | 每次 search 前检查 mtime，lazy sync |

限制：
1. 嵌入仅支持 OpenAI（Phase 1），后续可扩展本地模型
2. 无自动摘要/事实提取，依赖 Agent 主动写入
3. 无 file watcher，索引在 search 时 lazy 更新
4. 无时间衰减和 MMR 去重（后续可加）

---

## 16. 后续扩展路径

| 特性 | 说明 | 优先级 |
|------|------|--------|
| Memory Flush | 上下文压缩前静默提醒 Agent 保存记忆 | P1（需先实现 compaction） |
| Session Memory | /new 或 /reset 时自动保存对话摘要 | P1 |
| 本地嵌入 | GGUF via llama-cpp-python，零 API 成本 | P2 |
| 时间衰减 | 旧记忆降权：score × e^(-λ × age_days) | P2 |
| MMR 去重 | 搜索结果多样性重排 | P3 |
| File Watcher | watchfiles 实时监测变更，替代 lazy sync | P3 |

---

## 17. 与 v0.5 初版方案（mem0）的对比

| 维度 | 初版（mem0） | 本版（文件记忆） |
|------|------------|----------------|
| 存储后端 | mem0 + Qdrant 向量库 | Markdown 文件 + SQLite |
| 外部依赖 | mem0ai, qdrant-client | 无新依赖（OpenAI SDK 已有） |
| 写入方式 | 专用 memory_store 工具 | 复用现有 write_file 工具 |
| 删除方式 | 专用 memory_forget 工具 | 复用 write_file 编辑文件 |
| 读取方式 | memory_search + 自动 recall | memory_search + MEMORY.md 注入 |
| 新增工具数 | 3 个 | 1 个 |
| 记忆可见性 | 存在向量库中，用户不可直接查看 | Markdown 文件，可直接查看/编辑 |
| 模块文件数 | 5 个 | 7 个（含搜索引擎） |
| 搜索能力 | 仅向量搜索 | BM25 + 向量混合搜索 |
| 可离线使用 | 否（依赖 mem0 + Qdrant） | 是（BM25 可离线，嵌入可选） |
