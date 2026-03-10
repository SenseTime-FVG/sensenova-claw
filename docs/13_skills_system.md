# AgentOS Skills 系统设计文档

## 概述

Skills 系统是 AgentOS 的声明式任务编排机制，通过 Markdown 文件（SKILL.md）教 Agent 如何使用工具完成复杂任务。Skills 与编程式 Tools 互补，不替代。

## 设计理念

### Tool vs Skill

| | Tool（编程式） | Skill（声明式） |
|---|---|---|
| 形式 | Python 代码 | Markdown（SKILL.md） |
| 注册 | `ToolRegistry.register(tool)` | 放到目录，自动发现 |
| 运行时 | LLM function call → 执行代码 | 注入 system prompt → 指导 LLM 行为 |
| 热更新 | 重启生效 | 重启生效 |

**典型例子**：
- **Tool**: `bash_command` - 执行 shell 命令并返回结果
- **Skill**: `deploy-staging` - 告诉 Agent "当用户说部署时，依次调用 bash_command 执行 pull → build → push → rollout，每步检查退出码，失败回滚"

## 架构设计

### 核心组件

#### SkillRegistry
位置：`backend/app/skills/registry.py`

职责：
- 从用户目录和工作区目录加载 SKILL.md
- 解析 YAML frontmatter
- 实现门控机制（enabled 配置、二进制依赖检查）
- 管理 skill 生命周期

#### ContextBuilder 集成
位置：`backend/app/runtime/context_builder.py`

职责：
- 接收 SkillRegistry 实例
- 在 `build_messages()` 中将 skills 注入到 system prompt
- 使用 `<available_skills>` XML 标签包裹

### 目录结构

```
~/.agentos/skills/          # 用户级 skills（所有项目共享）
  └── my-skill/
      └── SKILL.md

<workspace>/skills/         # 工作区 skills（项目专属，覆盖同名用户级 skill）
  └── deploy-staging/
      └── SKILL.md

backend/app/skills/         # 内置 skills（代码目录）
  ├── pdf/
  ├── docx/
  └── skill-creator/
```

## SKILL.md 格式

### 基本结构

```markdown
---
name: skill-name
description: 技能描述（用于触发判断）
metadata: {"agentos": {"requires": {"bins": ["docker"], "env": ["KUBECONFIG"]}}}
---

当用户要求 XXX 时：

1. 调用 `bash_command` 工具执行 ...
2. 调用 `serper_search` 搜索 ...
3. 检查结果并 ...
```

### Frontmatter 字段

- `name` (必需): skill 名称
- `description` (必需): 描述 skill 功能和触发条件
- `metadata` (可选): 元数据，包含依赖信息
  - `agentos.requires.bins`: 依赖的二进制文件列表
  - `agentos.requires.env`: 依赖的环境变量列表

### Body 内容

使用自然语言描述如何使用现有 Tools 完成任务。

## 配置管理

### 配置文件位置

```yaml
# .agentos/config.yaml
skills:
  entries:
    pdf:
      enabled: true
    experimental-skill:
      enabled: false
```

### 配置项说明

- `skills.entries.<skill-name>.enabled`: 是否启用该 skill（默认 true）

## 加载流程

### 初始化流程

```python
# 1. 在 main.py 的 lifespan 中初始化
workspace_dir = Path(config.get("system.workspace_dir", ".")) / "skills"
skill_registry = SkillRegistry(workspace_dir=workspace_dir)
skill_registry.load_skills(config.data)

# 2. 传递给 ContextBuilder
context_builder = ContextBuilder(skill_registry=skill_registry)

# 3. 构建消息时自动注入
messages = context_builder.build_messages(user_input)
```

### 加载顺序

1. 加载用户级 skills（`~/.agentos/skills/`）
2. 加载工作区 skills（`<workspace>/skills/`）
3. 工作区 skills 覆盖同名用户级 skills

### 门控机制

Skill 在以下情况下不会被加载：
- 配置中 `enabled: false`
- 依赖的二进制文件不存在（`requires.bins`）

## 运行机制

### System Prompt 注入

```
你是一个有工具能力的AI助手...

系统类型: Windows
当前时间: 2026-03-09 17:30:00

<available_skills>
- pdf: Comprehensive PDF manipulation toolkit...
- docx: Comprehensive document creation, editing...
- deploy-staging: 部署应用到 staging 环境
</available_skills>
```

### LLM 使用流程

1. LLM 读取 system prompt 中的 `<available_skills>`
2. 根据用户输入判断是否需要使用某个 skill
3. 按照 skill 的 body 指导，调用相应的 Tools
4. 完成任务并返回结果

## 内置 Skills

项目包含 16 个内置 skills：

1. **algorithmic-art** - 使用 p5.js 创建算法艺术
2. **brand-guidelines** - Anthropic 品牌规范
3. **canvas-design** - 创建视觉艺术（PNG/PDF）
4. **doc-coauthoring** - 文档协作工作流
5. **docx** - Word 文档处理
6. **frontend-design** - 前端设计
7. **internal-comms** - 内部沟通
8. **mcp-builder** - MCP 构建器
9. **pdf** - PDF 处理工具包
10. **pptx** - PowerPoint 处理
11. **skill-creator** - 创建新 skill
12. **slack-gif-creator** - Slack GIF 创建
13. **theme-factory** - 主题工厂
14. **web-artifacts-builder** - Web 组件构建
15. **webapp-testing** - Web 应用测试
16. **xlsx** - Excel 处理

## 示例 Skills

### 示例 1: deploy-staging

```markdown
---
name: deploy-staging
description: 部署应用到 staging 环境
metadata: {"agentos": {"requires": {"bins": ["docker", "kubectl"]}}}
---

当用户要求部署到 staging 时：

1. 调用 `bash_command` 工具执行 `git pull origin main`，检查 return_code
2. 如果成功，调用 `bash_command` 工具执行 `docker build -t app:staging .`
3. 如果成功，调用 `bash_command` 工具执行 `kubectl rollout restart deployment/app`
4. 任何步骤失败（return_code != 0），立即停止并报告错误信息
```

### 示例 2: research-topic

```markdown
---
name: research-topic
description: 深度研究某个主题并生成报告
---

当用户要求研究某个主题时：

1. 调用 `serper_search` 搜索关键词，获取搜索结果
2. 选择前 3-5 个最相关的链接
3. 对每个链接调用 `fetch_url` 获取完整内容
4. 分析和总结关键信息
5. 调用 `write_file` 将研究结果保存到 `research_output.md`
6. 向用户展示总结和保存路径
```

## 测试验证

### 单元测试

位置：`backend/tests/test_skill_registry.py`

测试内容：
- SKILL.md 解析
- Skills 加载
- 禁用 skill
- 工作区覆盖用户级 skill

### E2E 测试

位置：`backend/tests/test_skills_e2e.py`

测试内容：
- SkillRegistry 与 ContextBuilder 集成
- Skills 注入到 system prompt
- 验证加载的 skills 数量和内容

### 测试结果

```
Loaded 16 skills
Skills injected to system prompt
System prompt length: 5197 chars
  - algorithmic-art
  - brand-guidelines
  - canvas-design

All tests passed!
```

## 扩展指南

### 创建自定义 Skill

1. 在 `~/.agentos/skills/` 或 `<workspace>/skills/` 创建目录
2. 创建 `SKILL.md` 文件
3. 编写 frontmatter 和 body
4. 重启后端服务

### 禁用 Skill

在 `.agentos/config.yaml` 中添加：

```yaml
skills:
  entries:
    skill-name:
      enabled: false
```

## 技术决策

### 为什么不使用 Function Calling？

Skills 通过 system prompt 指导 LLM 行为，而不是作为 function 暴露给 LLM。原因：
- Skills 是多步骤流程，不适合单次 function call
- Skills 需要 LLM 理解上下文并灵活调整
- 避免 function 列表过长导致 token 浪费

### 为什么移除 search_skill 和 load_skill？

这两个 Tools 是 v0.1 的占位实现。在新的 Skills 系统中：
- Skills 通过 description 自动匹配，不需要 search
- Skills 通过 system prompt 注入，不需要 load

## 版本历史

### v0.4 (当前版本)
- ✅ 实现 SkillRegistry
- ✅ 集成 ContextBuilder
- ✅ 移除占位 Tools
- ✅ 添加配置支持
- ✅ 加载 16 个内置 skills

### 未来计划
- 文件监视（热重载）
- `/skill-name` 用户命令
- per-skill 环境变量注入
- bundled skills 打包分发

## 相关文档

- [12_builtin_tools.md](./12_builtin_tools.md) - 内置工具文档
- [07_configuration.md](./07_configuration.md) - 配置文件设计
- [03_core_modules.md](./03_core_modules.md) - 核心模块详解
