# 实现计划：办公 Agent Team

**日期**: 2026-03-16
**设计文档**: docs/design/office-agent-team.md

## 目标

实现办公 Agent Team，包括 1 个 main agent 和 4 个 subagent，支持 PPT 生成、数据分析、文档整理和邮件管理。

## 实现阶段

### 阶段 1：核心框架（本次实现）

#### 1.1 创建 Agent 配置
- [ ] 在 `config.yml` 中添加 5 个 agent 配置
- [ ] 验证 agent 可以正确加载

#### 1.2 实现文档来源插件化架构
- [ ] 创建 `agentos/adapters/doc_sources/base.py`（基类）
- [ ] 创建 `agentos/adapters/doc_sources/registry.py`（注册表）
- [ ] 创建 `agentos/adapters/doc_sources/local.py`（本地文件适配器）
- [ ] 创建 `agentos/adapters/doc_sources/feishu.py`（飞书适配器，预留接口）
- [ ] 创建 `agentos/adapters/doc_sources/__init__.py`（自动注册）

#### 1.3 实现 doc_source_tool
- [ ] 创建 `agentos/capabilities/tools/doc_source.py`
- [ ] 注册到 ToolRegistry
- [ ] 测试本地文件读取

#### 1.4 实现基础 Skills
- [ ] 创建 `workspace/skills/generate_ppt.yml`（预留扩展接口）
- [ ] 创建 `workspace/skills/gmail_skill.yml`（基于 himalaya CLI）

#### 1.5 测试委托链路
- [ ] 测试 office-main → ppt-agent
- [ ] 测试 ppt-agent → data-analyst
- [ ] 测试 doc_source_tool 自动识别文件来源

### 阶段 2：数据分析能力（后续）
- 实现 `analyze_data` skill
- 实现 `visualize_data` skill

### 阶段 3：扩展支持（后续）
- 添加 Notion、钉钉文档适配器
- 添加 Outlook skill
- 实现 PPT 生成的多种方式

## 关键文件

**新增文件**：
- `agentos/adapters/doc_sources/base.py`
- `agentos/adapters/doc_sources/registry.py`
- `agentos/adapters/doc_sources/local.py`
- `agentos/adapters/doc_sources/feishu.py`
- `agentos/adapters/doc_sources/__init__.py`
- `agentos/capabilities/tools/doc_source.py`
- `workspace/skills/generate_ppt.yml`
- `workspace/skills/gmail_skill.yml`

**修改文件**：
- `config.yml`（添加 agents 配置）

## 实现细节

### doc_source_tool 实现要点
- 调用 DocSourceRegistry.get_adapter(url) 自动识别来源
- 返回格式：`{"content": str, "source": str}` 或 `{"error": str}`

### Agent 配置要点
- office-main: can_delegate_to 包含所有 4 个 subagent
- ppt-agent: can_delegate_to = ["data-analyst"]
- data-analyst: can_delegate_to = ["doc-organizer"]
- doc-organizer: can_delegate_to = ["ppt-agent", "data-analyst", "email-agent"]
- email-agent: can_delegate_to = ["doc-organizer"]

### Skills 实现要点
- generate_ppt: 预留 generator 配置，初期返回占位符
- gmail_skill: 调用 himalaya CLI，需要用户预先配置

## 验收标准

1. 5 个 agent 配置正确加载
2. doc_source_tool 可以读取本地文件
3. office-main 可以成功委托给 ppt-agent
4. ppt-agent 可以成功委托给 data-analyst

## 风险与依赖

- himalaya CLI 需要用户手动安装和配置
- 飞书文档访问需要 API token（本次仅预留接口）
- PPT 生成需要后续实现具体生成器
