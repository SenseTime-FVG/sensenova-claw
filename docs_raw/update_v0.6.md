# PRD: AgentOS 长期记忆系统

> 版本: update_v0.6
> 日期: 2026-03-10
> 项目: AgentOS
> 参考: OpenClaw memory 系统, xhx_agent_v3/memory
> 技术设计: [docs/18_memory_system.md](../docs/18_memory_system.md)

---

## 1. 概述

为 AgentOS 引入跨会话长期记忆——**文件即记忆**。

以 Workspace 中的 Markdown 文件为唯一事实来源，通过 `memory_search` 工具实现语义检索，通过现有 `write_file` / `read_file` 工具实现记忆读写。

### 1.1 解决的问题

- Agent 没有跨会话记忆，每次对话从零开始
- 无法记住用户偏好（称呼、语言、技术栈等）
- 历史对话上下文无法复用

### 1.2 核心取舍

| 做 | 不做 |
|---|---|
| Markdown 文件存储（可读、可编辑、可 git 管理） | 不引入 mem0 / Qdrant 等外部向量库 |
| `memory_search` 语义搜索（BM25 + 向量混合） | 不做隐式自动注入全部记忆 |
| `MEMORY.md` 自动注入 system prompt | 不做自动摘要 / 自动事实提取 |
| 复用现有 `write_file` 写入记忆 | 不新增 memory_store / memory_forget 工具 |
| SQLite 本地向量索引 | 不依赖云端向量服务 |

### 1.3 设计原则

| 原则 | 说明 |
|------|------|
| **文件即记忆** | Markdown 文件是唯一事实来源 |
| **显式优于隐式** | 读写都通过显式工具调用 |
| **两层记忆** | 长期事实 (`MEMORY.md`) 和每日日志 (`memory/YYYY-MM-DD.md`) 分离 |
| **渐进降级** | 向量不可用降 BM25，BM25 不可用降空结果 |
| **不阻塞事件循环** | 嵌入和搜索通过 `asyncio.to_thread()` |

---

## 2. 记忆存储

```
{workspace}/
├── MEMORY.md                    ← 长期记忆（偏好、决策、持久事实）
└── memory/
    ├── 2026-03-08.md           ← 每日日志（append-only）
    └── 2026-03-10.md
```

| 文件 | 用途 | 写入 | 读取 |
|------|------|------|------|
| `MEMORY.md` | 长期事实 | Agent 用 `write_file` | 每次 turn 注入 system prompt |
| `memory/YYYY-MM-DD.md` | 每日日志 | Agent 用 `write_file` 追加 | `memory_search` 按需检索 |

---

## 3. 新增工具

仅新增 **1 个** 工具：

### memory_search

语义搜索 `MEMORY.md` + `memory/**/*.md`，返回匹配片段。

- 混合搜索：BM25 + 向量加权合并（0.7/0.3）
- 嵌入不可用时降级为纯 BM25
- 搜索前 lazy 检查文件变更，按需增量重索引

写入和删除复用现有 `write_file`，精确读取复用 `read_file`。

---

## 4. MEMORY.md 注入

每次 turn 开始时：

1. `AgentSessionWorker` 读取 `MEMORY.md`（如果存在）
2. 格式化为 Memory 指令段落（含读写指引 + 文件内容）
3. 作为 `memory_context` 参数传入 `ContextBuilder`
4. `ContextBuilder` 纯字符串拼接，无 I/O

截断保护：超过 `bootstrap_max_chars`（默认 8000）时截断。

---

## 5. 向量搜索索引

- **存储**: 复用 SQLite，新增 `memory_chunks` 表 + FTS5 全文搜索表
- **分块**: ~400 token，80 token 重叠，段落/句子边界
- **嵌入**: OpenAI `text-embedding-3-small`（复用已有 API key）
- **刷新**: lazy 策略——search 时检查 mtime + 启动时全量扫描

---

## 6. 配置

```yaml
memory:
  enabled: true
  bootstrap_max_chars: 8000

  search:
    enabled: true
    embedding_model: "text-embedding-3-small"
    chunk_size: 400
    chunk_overlap: 80
    hybrid:
      vector_weight: 0.7
      text_weight: 0.3
      candidate_multiplier: 4
```

`memory.enabled: false` 时系统行为与 v0.4 完全一致。

---

## 7. 新增文件

```
backend/app/memory/
├── __init__.py
├── config.py          # MemoryConfig
├── manager.py         # MemoryManager（文件读取 + 索引协调）
├── index.py           # MemoryIndex（SQLite + 混合搜索）
├── chunker.py         # 文本分块
├── embedding.py       # EmbeddingService（OpenAI）
└── tools.py           # MemorySearchTool
```

## 8. 修改文件

| 文件 | 修改 |
|------|------|
| `main.py` | 初始化 MemoryManager，注入 AgentRuntime + ToolRegistry |
| `agent_runtime.py` | 新增 `memory_manager` 属性 |
| `agent_worker.py` | `_handle_user_input` 读取 MEMORY.md 传入 ContextBuilder |
| `context_builder.py` | `build_messages()` 新增 `memory_context` 参数 |
| `config.py` | DEFAULT_CONFIG 添加 memory 段 |
| `repository.py` | 新增 memory_chunks 表 |

---

## 9. 验收标准

1. MEMORY.md 内容出现在 system prompt 中
2. `memory_search("部署方案")` 能匹配 memory/ 下相关片段
3. 嵌入 API 不可用时 BM25 降级仍能搜索
4. Agent 通过 `write_file` 写入 MEMORY.md 后，新会话 system prompt 包含该内容
5. `memory.enabled: false` 时无任何记忆行为
6. 嵌入和搜索不阻塞 asyncio 事件循环

---

## 10. 交付计划

| 步骤 | 内容 | 工期 |
|------|------|------|
| 1 | MemoryConfig + MemoryManager（load_memory_md） | 0.5 天 |
| 2 | ContextBuilder memory_context + AgentWorker 集成 | 0.5 天 |
| 3 | Chunker + EmbeddingService | 0.5 天 |
| 4 | MemoryIndex（SQLite + FTS5 + 向量搜索） | 1 天 |
| 5 | 混合搜索 + MemorySearchTool | 0.5 天 |
| 6 | 配置 + main.py 集成 + DB schema | 0.5 天 |
| 7 | E2E 测试 | 0.5 天 |

**总计：4 天**

---

## 11. 后续扩展

| 特性 | 优先级 |
|------|--------|
| Memory Flush（压缩前静默提醒保存记忆） | P1 |
| Session Memory（/new 时自动保存对话摘要） | P1 |
| 本地嵌入（GGUF，零 API 成本） | P2 |
| 时间衰减 / MMR 去重 | P3 |
| File Watcher 替代 lazy sync | P3 |
