# Knowledge Base Skill - 详细参考

本文档提供知识库技能的详细规范和示例。

## 存储结构详解

### 目录结构

```
{vault}/Knowledge/
├── user-profile.md             # 用户画像（单文件，持续追加）
├── qa-history/                 # 问答历史
│   ├── 2026-03/
│   │   ├── 2026-03-26-event-driven-debug.md
│   │   └── 2026-03-27-api-design.md
│   └── 2026-04/
│       └── ...
├── facts/                      # 事实/知识点
│   ├── 2026-03/
│   │   ├── 2026-03-26-api-endpoints.md
│   │   └── 2026-03-27-db-credentials.md
│   └── 2026-04/
│       └── ...
└── _index.md                   # 可选：知识库索引
```

### 文件命名规范

- **qa-history**: `YYYY-MM-DD-<简短标题>.md`
  - 示例: `2026-03-26-event-driven-debug.md`

- **facts**: `YYYY-MM-DD-<简短标题>.md`
  - 示例: `2026-03-26-api-endpoints.md`

- **user-profile**: 固定为 `user-profile.md`

---

## 模板详解

### user-profile.md 模板

```markdown
---
updated: YYYY-MM-DD
tags: [kb/profile]
---

# 用户画像

## 基本信息
- 称呼:
- 角色/职业:
- 时区/语言偏好:

## 工作上下文
- 当前项目:
- 技术栈:
- 团队情况:

## 偏好设置
- 回答风格:
- 常用工具:
- 特殊要求:

## 重要备忘

### YYYY-MM-DD
- 备忘内容

```

### qa-entry.md 模板

```markdown
---
date: YYYY-MM-DD
tags: [kb/qa, topic/xxx, source/conversation]
related: [[user-profile]]
---

# 标题（问题简述）

## 问题
用户的原始问题描述

## 解答
解答的核心内容

## 关键点
- 要点 1
- 要点 2

## 上下文
对话发生的背景（可选）
```

### fact-entry.md 模板

```markdown
---
date: YYYY-MM-DD
tags: [kb/fact, topic/xxx, source/user-input]
related: [[user-profile]]
---

# 标题

## 内容
事实/知识点的具体内容

## 上下文
用户提供此信息的背景
```

---

## 标签体系详解

### 命名空间

| 前缀 | 用途 | 示例 |
|------|------|------|
| `kb/` | 知识库类型 | `kb/profile`, `kb/qa`, `kb/fact` |
| `topic/` | 主题分类 | `topic/python`, `topic/api` |
| `source/` | 来源类型 | `source/conversation`, `source/user-input` |

### 类型标签（必选）

| 存储位置 | 标签 |
|----------|------|
| user-profile.md | `kb/profile` |
| qa-history/ | `kb/qa` |
| facts/ | `kb/fact` |

### 主题标签（自动生成）

从内容中提取关键技术词汇，映射到 `topic/` 命名空间。

常见主题标签：
- `topic/python`, `topic/javascript`, `topic/rust`
- `topic/fastapi`, `topic/react`, `topic/vue`
- `topic/api`, `topic/database`, `topic/devops`
- `topic/event-driven`, `topic/microservices`
- `topic/debugging`, `topic/testing`, `topic/deployment`

规则：
- 每篇笔记最多 5 个主题标签
- 优先选择具体的技术词汇
- 避免过于宽泛的标签

### 来源标签

| 场景 | 标签 |
|------|------|
| 对话中自动提取 | `source/conversation` |
| 用户主动提供（/remember） | `source/user-input` |
| agent 推断的信息 | `source/agent-infer` |

---

## 双向链接详解

### 链接类型

1. **内联链接**: 在正文中使用 `[[笔记名]]`
2. **related 字段**: 在 frontmatter 中列出相关笔记

### 生成规则

| 场景 | 链接方式 |
|------|----------|
| 新笔记涉及用户偏好 | `related: [[user-profile]]` |
| 新笔记与已有 QA 主题相同 | `related: [[已有QA笔记]]` |
| 正文提到已存在的概念 | 正文中添加 `[[概念笔记]]` |

### 示例

```markdown
---
date: 2026-03-26
tags: [kb/qa, topic/event-driven, topic/debugging]
related: [[user-profile]], [[2026-03-20-architecture-decision]]
---

# 事件驱动架构调试

在调试 [[EventBus]] 时，发现事件丢失问题...
```

---

## 完整示例

### 示例 1: 用户画像

```markdown
---
updated: 2026-03-26
tags: [kb/profile]
---

# 用户画像

## 基本信息
- 称呼: Jerry
- 角色/职业: 后端开发工程师
- 时区/语言偏好: UTC+8，中文

## 工作上下文
- 当前项目: Sensenova-Claw (AI Agent 平台)
- 技术栈: Python 3.12, FastAPI, SQLite, Next.js
- 团队情况: 个人项目

## 偏好设置
- 回答风格: 简洁，代码优先
- 常用工具: VS Code, Claude Code
- 特殊要求: 使用中文注释

## 重要备忘

### 2026-03-26
- 正在开发知识库 skill，基于 Obsidian 存储

### 2026-03-25
- 项目采用事件驱动架构
```

### 示例 2: QA 记录

```markdown
---
date: 2026-03-26
tags: [kb/qa, topic/event-driven, topic/debugging, source/conversation]
related: [[user-profile]], [[2026-03-25-architecture-overview]]
---

# EventBus 事件丢失调试

## 问题
在使用 PublicEventBus 时，部分事件似乎丢失了，下游 Runtime 没有收到。

## 解答
事件丢失通常由以下原因导致：

1. **session_id 不匹配**
   - 检查发布事件时的 session_id
   - 确认订阅者的 session_id 过滤逻辑

2. **订阅时机问题**
   - 确保在事件发布前完成订阅
   - 检查 Runtime 初始化顺序

3. **调试方法**
   ```python
   # 在 EventBus 中添加日志
   logger.debug(f"Publishing event: {envelope.type} to session {envelope.session_id}")
   ```

## 关键点
- 使用 trace_id 追踪完整链路
- 事件发布是异步的，注意顺序问题
```

### 示例 3: Fact 记录

```markdown
---
date: 2026-03-26
tags: [kb/fact, topic/api, topic/deployment, source/user-input]
related: [[user-profile]]
---

# 项目 API 端点

## 内容
- 生产环境: https://api.example.com/v1
- 测试环境: https://staging-api.example.com/v1
- 本地开发: http://localhost:8000

## 上下文
用户在讨论部署配置时提供，用于后续参考。
```

---

## 错误处理

### Vault 未配置

如果 `obsidian_list_vaults` 返回空或报错：

```
知识库功能需要配置 Obsidian vault。
请在 config.yml 中配置：

tools:
  obsidian:
    vaults:
      - ~/Documents/MyVault
```

### 文件不存在

如果读取 user-profile.md 时文件不存在：
- 静默跳过，不报错
- 等待第一次写入时自动创建

### 搜索无结果

如果 `obsidian_search` 返回空：
- 直接回答用户问题
- 不强制从知识库获取信息
