# 记忆系统

记忆系统为 Agent 提供长期记忆能力，支持将重要信息持久化到 Markdown 文件，并通过混合搜索（BM25 + 向量相似度）在对话中检索相关记忆。

## 架构概览

```
MemoryManager（记忆管理器）
  ├── load_memory_md()       → 读取 MEMORY.md 注入系统提示
  ├── search()               → 混合搜索记忆内容
  ├── sync_index()           → 增量同步文件索引，并自动补齐待嵌入向量
  └── embed_pending_chunks() → 为 `embedding=NULL` 的 chunk 生成向量

MemoryIndex（索引引擎）
  ├── SQLite 存储（memory_chunks 表）
  ├── FTS5 全文搜索（BM25 排序）
  └── 向量搜索（cosine similarity）

Chunker（分块器）
  └── 按段落/句子边界智能分块，保留重叠

EmbeddingService（嵌入服务）
  └── OpenAI Embedding API 封装

MemorySearchTool（搜索工具）
  └── 注册为 memory_search 工具供 Agent 调用
```

## MemoryManager

核心管理器，位于 `agentos/capabilities/memory/manager.py`：

```python
class MemoryManager:
    def __init__(
        self,
        workspace_dir: str,      # 工作区目录路径
        config: MemoryConfig,    # 记忆配置
        db_path: Path,           # SQLite 数据库路径
    )

    async def load_memory_md() -> str | None
        """读取 MEMORY.md，格式化为系统提示片段"""

    async def search(query: str, max_results: int = 5) -> list[MemorySearchResult]
        """混合搜索记忆文件"""

    async def sync_index() -> None
        """增量同步索引"""

    async def embed_pending_chunks() -> None
        """为缺少嵌入的 chunks 生成向量"""
```

### load_memory_md()

读取工作区根目录的 `MEMORY.md` 文件，生成系统提示片段：

1. 读取 `{workspace}/MEMORY.md`
2. 文件不存在时返回 `None`
3. 超过 `bootstrap_max_chars`（默认 8000 字符）时截断，附加提示使用 `memory_search` 检索完整内容
4. 包装为记忆指令段落，包含记忆读取和写入指南

**生成的提示内容结构**：

```
你拥有长期记忆能力。

### 记忆读取
- 回答涉及过往工作、决策、日期、人物、偏好的问题前，先调用 memory_search 搜索记忆
- 搜索后可用 read_file 获取完整上下文

### 记忆写入
- 用户提到偏好、个人信息、重要决策时，用 write_file 写入 MEMORY.md
- 日常笔记和运行上下文追加到 memory/{今天日期}.md
- 已有文件时追加内容，不要覆盖

### 当前 MEMORY.md 内容
{MEMORY.md 的实际内容}
```

### search()

执行混合搜索的完整流程：

```python
async def search(query, max_results=5):
    # 1. 懒同步：确保索引是最新的
    # sync_index() 会自动补齐待嵌入 chunk，并重试历史 embedding=NULL 记录
    await self.sync_index()

    # 2. 获取查询向量（如果嵌入服务可用）
    embedding = await self.embedding_service.embed([query])
    # 嵌入失败时降级为纯 BM25 搜索

    # 3. 执行混合搜索（在线程池中，不阻塞事件循环）
    results = await asyncio.to_thread(
        self.index.hybrid_search, query, embedding, max_results
    )
    return results
```

### sync_index()

增量同步索引的流程：

```
1. 扫描记忆文件
   ├── {workspace}/MEMORY.md
   └── {workspace}/memory/**/*.md

2. 对比已索引的 mtime
   ├── 删除已不存在的文件索引
   └── 仅处理 mtime 有变更的文件

3. 对变更文件重新分块
   ├── Chunker.chunk(text, chunk_size=400, overlap=80)
   └── 生成 MemoryChunk 列表

4. 写入索引
   └── MemoryIndex.upsert_chunks(path, chunks, mtime)

5. 自动补齐待嵌入向量
   ├── sync_index() 完成后调用 embed_pending_chunks()
   └── 即使本次没有文件变化，也会重试历史遗留的 `embedding=NULL` chunks
```

## MemoryIndex

基于 SQLite 的索引引擎，位于 `agentos/capabilities/memory/index.py`：

### 数据库 Schema

```sql
CREATE TABLE memory_chunks (
    chunk_id TEXT PRIMARY KEY,    -- UUID 前 16 位
    path TEXT NOT NULL,           -- workspace 相对路径
    start_line INTEGER NOT NULL,  -- 起始行号
    end_line INTEGER NOT NULL,    -- 结束行号
    text TEXT NOT NULL,           -- 分块文本内容
    embedding BLOB,               -- 向量嵌入（float 数组的二进制编码）
    file_mtime REAL NOT NULL,     -- 源文件修改时间
    created_at REAL NOT NULL      -- 索引创建时间
);

-- FTS5 全文搜索虚拟表（如果 SQLite 编译支持）
CREATE VIRTUAL TABLE memory_chunks_fts
USING fts5(chunk_id, text, content=memory_chunks, content_rowid=rowid);
```

FTS5 表通过触发器与主表自动同步（INSERT/UPDATE/DELETE）。

### 混合搜索（hybrid_search）

```python
def hybrid_search(query, embedding, limit):
    candidate_limit = limit * candidate_multiplier  # 默认 4 倍

    # 1. 向量搜索：cosine similarity
    vector_results = search_vector(embedding, candidate_limit)

    # 2. BM25 全文搜索（归一化到 [0, 1]）
    bm25_results = search_bm25(query, candidate_limit)

    # 3. 加权合并
    for chunk_id in all_candidates:
        score = vector_weight * v_score + text_weight * t_score
        # 默认权重：向量 0.7 + 文本 0.3

    # 4. 按分数排序，返回 top-N
    return top_results  # MemorySearchResult 列表
```

**搜索结果**：

```python
@dataclass
class MemorySearchResult:
    snippet: str       # 文本片段（最多 700 字符）
    path: str          # workspace 相对路径
    start_line: int    # 起始行号
    end_line: int      # 结束行号
    score: float       # 综合评分
```

### 降级策略

- **嵌入服务不可用**：仅使用 BM25 全文搜索
- **FTS5 不支持**：仅使用向量搜索
- **两者都不可用**：返回空结果

## Chunker

智能分块器，位于 `agentos/capabilities/memory/chunker.py`：

```python
class Chunker:
    CHARS_PER_TOKEN = 3  # 字符/token 换算比（中英文平均值）

    def chunk(text, path, chunk_size=400, overlap=80) -> list[MemoryChunk]:
        """
        Args:
            text: 原始文本
            path: workspace 相对路径
            chunk_size: 目标 token 数（400 tokens ≈ 1200 字符）
            overlap: 重叠 token 数（80 tokens ≈ 240 字符）
        """
```

**分块策略**：

1. 按行遍历文本，累积到目标字符数
2. 在切分点选择上优先级：段落边界（双换行） > 句子边界（。！？.!?） > 当前位置
3. 保留 overlap 部分确保上下文连续性
4. 每个分块记录 `start_line` 和 `end_line`，便于定位原文

**MemoryChunk 结构**：

```python
@dataclass
class MemoryChunk:
    chunk_id: str      # UUID 前 16 位
    path: str          # workspace 相对路径
    start_line: int    # 起始行号（从 1 开始）
    end_line: int      # 结束行号
    text: str          # 分块文本
```

## EmbeddingService

嵌入服务封装，位于 `agentos/capabilities/memory/embedding.py`：

```python
class EmbeddingService:
    def __init__(self, mem_config: MemoryConfig)
        """初始化时尝试创建 OpenAI 客户端"""

    def available() -> bool
        """嵌入服务是否可用"""

    def dimensions() -> int
        """当前模型的向量维度"""

    async def embed(texts: list[str]) -> list[list[float]]
        """批量文本 → 向量"""
```

**支持的模型和维度**：

| 模型 | 维度 |
|------|------|
| text-embedding-3-small | 1536 |
| text-embedding-3-large | 3072 |
| text-embedding-ada-002 | 1536 |

**初始化逻辑**：
- 复用 `llm_providers.openai` 配置中的 `api_key` 和 `base_url`
- API key 未配置时不报错，标记为不可用，搜索降级为 BM25

## MemorySearchTool

注册为 `memory_search` 工具供 Agent 在对话中调用，位于 `agentos/capabilities/memory/tools.py`：

```python
class MemorySearchTool(Tool):
    name = "memory_search"
    description = "搜索长期记忆文件（MEMORY.md + memory/*.md），返回与查询最相关的片段"
```

**参数**：

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `query` | string | 是 | 搜索查询 |
| `max_results` | integer | 否 | 最大返回数，默认 5 |

**返回值**：

```json
{
  "results": [
    {
      "snippet": "相关文本片段...",
      "path": "MEMORY.md",
      "start_line": 10,
      "end_line": 25,
      "score": 0.8542
    }
  ]
}
```

**注册条件**：仅当 `memory.search.enabled = true` 时，MemorySearchTool 才会注册到 ToolRegistry。

## Agent 中的使用流程

完整的记忆使用链路：

```
1. 首轮对话
   ├── ContextBuilder 调用 load_workspace_files()
   │    └── 读取 AGENTS.md, USER.md 等工作区文件
   │
   ├── 如果 memory.enabled = true
   │    └── MemoryManager.load_memory_md()
   │         └── 将 MEMORY.md 内容注入系统提示
   │
   └── 系统提示包含记忆指令（读取/写入规则）

2. 对话过程中
   ├── Agent 遇到需要回忆的问题
   │    └── 调用 memory_search 工具搜索相关记忆
   │
   ├── Agent 需要记录信息
   │    ├── 用 write_file 写入 MEMORY.md（偏好、个人信息、重要决策）
   │    └── 用 write_file 追加到 memory/{日期}.md（日常笔记）
   │
   └── 索引自动更新
        └── 下次 search() 调用时 lazy sync 更新索引，并自动重试待嵌入 chunks
```

## 配置参考

```yaml
memory:
  enabled: true                      # 是否启用记忆系统
  bootstrap_max_chars: 8000          # MEMORY.md 注入系统提示的最大字符数

  search:
    enabled: true                    # 是否启用搜索（注册 memory_search 工具）
    embedding_model: text-embedding-3-small  # 嵌入模型
    chunk_size: 400                  # 分块大小（token 数）
    chunk_overlap: 80                # 分块重叠（token 数）

    hybrid:
      vector_weight: 0.7            # 向量搜索权重
      text_weight: 0.3              # BM25 搜索权重
      candidate_multiplier: 4       # 候选倍数（limit * 4 个候选参与排序）
```

## 文件结构

```
workspace/
  ├── MEMORY.md              # 长期记忆主文件（偏好、决策、人物信息）
  └── memory/
       ├── 2026-03-14.md     # 日常笔记（按日期组织）
       ├── 2026-03-13.md
       └── projects/
            └── agentos.md   # 项目相关记忆

var/
  └── memory.db              # SQLite 索引数据库（memory_chunks 表 + FTS5 虚拟表）
```
