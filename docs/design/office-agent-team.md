# 办公 Agent Team 设计文档

## 1. 概述

本文档描述办公 Agent Team 的设计方案，包括 1 个主 Agent 和 4 个专业 Subagent，支持 PPT 生成、数据分析、文档整理和邮件管理等办公场景。

### 设计目标

- 用户明确指定使用哪个 agent
- Main agent 负责任务编排，subagent 之间可以相互调用（如 PPT agent 调用数据分析 agent）
- 可扩展的文档来源和邮件来源支持
- 预留 PPT 生成的多种实现方式

## 2. 整体架构

### Agent 层级结构

```
office-main (办公主助手)
    ├─> ppt-agent (PPT 生成)
    ├─> data-analyst (数据分析)
    ├─> doc-organizer (文档整理)
    └─> email-agent (邮件助手)
```

### 用户交互流程

**场景 1：简单任务**
```
用户 → office-main → ppt-agent → 返回结果
```

**场景 2：Subagent 互相委托**
```
用户："生成包含数据分析的 PPT"
    ↓
office-main → ppt-agent
    ↓
ppt-agent → data-analyst（委托生成图表）
    ↓
data-analyst → 返回图表
    ↓
ppt-agent → 插入图表 → 返回 PPT
```

## 3. Agent 配置

### 3.1 Office-Main Agent

**职责**：理解用户需求，委托给专业 agent

**配置**：

```yaml
agents:
  office-main:
    name: 办公主助手
    description: 办公任务总调度，负责理解需求并委托给专业 agent
    provider: openai
    model: gpt-4o-mini
    temperature: 0.2
    system_prompt: |
      你是办公主助手，负责理解用户的办公需求并委托给专业 agent。
      可用的专业 agent：
      - ppt-agent: 生成 PPT 演示文稿
      - data-analyst: 数据分析和可视化
      - doc-organizer: 文档整理和处理
      - email-agent: 邮件收发和管理

      工作流程：
      1. 理解用户需求
      2. 判断需要哪个专业 agent
      3. 使用 delegate 工具委托任务
      4. 将结果返回给用户
    tools: ["delegate"]
    can_delegate_to: ["ppt-agent", "data-analyst", "doc-organizer", "email-agent"]
    max_delegation_depth: 2
```

### 3.2 PPT Agent

**职责**：生成 PPT 演示文稿，支持一句话生成和模板定制

**配置**：

```yaml
  ppt-agent:
    name: PPT 生成助手
    description: 生成 PPT 演示文稿，支持一句话生成和模板定制
    provider: openai
    model: gpt-4o-mini
    temperature: 0.3
    system_prompt: |
      你是 PPT 生成专家，负责创建演示文稿。

      工作流程：
      1. 收集需求（主题、页数、风格等）
      2. 如需数据分析图表，委托给 data-analyst
      3. 如需素材，使用 serper_search 搜索或 fetch_url 获取
      4. 调用 generate_ppt skill 生成 PPT 文件
      5. 返回文件路径给用户

      注意：generate_ppt skill 会根据配置调用不同的生成器（python-pptx/API/模板）
    tools: ["serper_search", "fetch_url", "read_file", "write_file", "bash_command", "delegate"]
    skills: ["generate_ppt"]
    can_delegate_to: ["data-analyst"]
    max_delegation_depth: 1
```

### 3.3 Data Analyst Agent

**职责**：数据分析、可视化和报告生成

**配置**：

```yaml
  data-analyst:
    name: 数据分析助手
    description: 数据分析、可视化和报告生成
    provider: openai
    model: gpt-4o-mini
    temperature: 0.1
    system_prompt: |
      你是数据分析专家，擅长数据处理和可视化。

      工作流程：
      1. 读取数据文件（支持 CSV、Excel、JSON）
      2. 使用 Python 进行数据分析（pandas、numpy）
      3. 生成可视化图表（matplotlib、seaborn）
      4. 输出分析报告和图表文件

      安全规则：
      - 只能执行数据分析相关的 Python 代码
      - 不能执行系统命令或网络请求
    tools: ["read_file", "write_file", "bash_command", "delegate"]
    skills: ["xlsx_to_markdown", "analyze_data", "visualize_data"]
    can_delegate_to: ["doc-organizer"]
    max_delegation_depth: 1
```

### 3.4 Doc Organizer Agent

**职责**：处理多种来源的文档，支持格式转换和整理

**配置**：

```yaml
  doc-organizer:
    name: 文档整理助手
    description: 处理多种来源的文档，支持格式转换和整理
    provider: openai
    model: gpt-4o-mini
    temperature: 0.2
    system_prompt: |
      你是文档整理专家，负责文档处理和整理。

      支持的文档来源（自动识别）：
      - 本地文件：直接提供文件路径
      - 飞书文档：feishu.cn 链接
      - Notion：notion.so 链接
      - 钉钉文档：dingtalk.com 链接

      工作流程：
      1. 使用 doc_source_tool 获取文档内容（自动识别来源）
      2. 使用对应的 skill 转换格式
      3. 根据用户需求整理内容
      4. 输出整理后的文档
    tools: ["doc_source_tool", "write_file", "bash_command", "delegate"]
    skills: ["pdf_to_markdown", "docx_to_markdown", "xlsx_to_markdown"]
    can_delegate_to: ["ppt-agent", "data-analyst", "email-agent"]
    max_delegation_depth: 1
```

### 3.5 Email Agent

**职责**：邮件收发、管理和定时提醒

**配置**：

```yaml
  email-agent:
    name: 邮件助手
    description: 邮件收发、管理和定时提醒
    provider: openai
    model: gpt-4o-mini
    temperature: 0.2
    system_prompt: |
      你是邮件管理专家，负责邮件处理和定时提醒。

      核心能力：
      1. 收发邮件：使用 gmail_skill/outlook_skill 等
      2. 定时检查：使用 bash_command 调用 cron 设置定时任务
      3. 智能提醒：分析邮件重要性并提醒用户

      工作流程示例：
      用户："每天早上 9 点检查 Gmail"
      → 使用 bash_command 创建 cron 任务
      → 任务触发时调用 gmail_skill 检查新邮件
      → 如有重要邮件，输出摘要
    tools: ["bash_command", "read_file", "write_file", "delegate"]
    skills: ["gmail_skill", "outlook_skill"]
    can_delegate_to: ["doc-organizer"]
    max_delegation_depth: 1
```

## 4. 委托关系图

```
office-main
    ├─> ppt-agent ──> data-analyst ──> doc-organizer
    ├─> data-analyst ──> doc-organizer
    ├─> doc-organizer ──> ppt-agent / data-analyst / email-agent
    └─> email-agent ──> doc-organizer
```

**说明**：
- office-main 可以委托给所有 4 个 subagent
- ppt-agent 可以委托给 data-analyst
- data-analyst 可以委托给 doc-organizer（读取文档数据）
- doc-organizer 可以委托给 ppt-agent、data-analyst、email-agent
- email-agent 可以委托给 doc-organizer（整理邮件附件）
- 最大委托深度：office-main (depth=2), 其他 subagent (depth=1)

## 5. 可扩展架构设计

### 5.1 文档来源插件化

**架构**：

```python
# agentos/adapters/doc_sources/base.py
class DocSourceAdapter:
    @staticmethod
    def can_handle(url: str) -> bool:
        raise NotImplementedError
    
    def fetch(self, url: str) -> str:
        raise NotImplementedError
```

**内置适配器**：

| 适配器 | 识别规则 | 优先级 |
|--------|----------|--------|
| LocalFileAdapter | `Path(url).exists()` | 高 |
| FeishuDocAdapter | `"feishu.cn" in url` | 高 |
| NotionAdapter | `"notion.so" in url` | 中 |
| DingTalkAdapter | `"dingtalk.com" in url` | 低 |


### 5.2 邮件来源 Skill 化

**架构**：通过 Skill + CLI 工具实现

```yaml
# workspace/skills/gmail_skill.yml
name: gmail_skill
description: Gmail 邮件操作（基于 himalaya CLI）
steps:
  - tool: bash_command
    command: "himalaya list --account gmail --max-results 10"
```

**扩展方式**：添加新的邮件 skill（如 `outlook_skill.yml`）

### 5.3 PPT 生成扩展接口

**配置**：

```yaml
# config.yml
ppt:
  generator: python-pptx  # 可选: python-pptx | api | template
```

**实现**：

```python
def generate_ppt(content: dict) -> str:
    generator_type = config.get("ppt.generator")
    if generator_type == "python-pptx":
        return PythonPptxGenerator().generate(content)
    elif generator_type == "api":
        return ApiPptGenerator().generate(content)
    elif generator_type == "template":
        return TemplatePptGenerator().generate(content)
```


## 6. 实现清单

### 6.1 需要新增的工具

| 工具名 | 功能 | 优先级 | 文件路径 |
|--------|------|--------|----------|
| `doc_source_tool` | 统一文档来源访问 | 高 | `agentos/capabilities/tools/doc_source.py` |

### 6.2 需要新增的 Skills

| Skill 名 | 功能 | 优先级 | 文件路径 |
|----------|------|--------|----------|
| `generate_ppt` | PPT 生成 | 高 | `workspace/skills/generate_ppt.yml` |
| `analyze_data` | 数据分析 | 中 | `workspace/skills/analyze_data.yml` |
| `visualize_data` | 数据可视化 | 中 | `workspace/skills/visualize_data.yml` |
| `gmail_skill` | Gmail 邮件操作 | 高 | `workspace/skills/gmail_skill.yml` |
| `outlook_skill` | Outlook 邮件操作 | 低 | `workspace/skills/outlook_skill.yml` |

### 6.3 需要新增的文档来源适配器

| 适配器 | 功能 | 优先级 | 文件路径 |
|--------|------|--------|----------|
| `DocSourceAdapter` | 基类 | 高 | `agentos/adapters/doc_sources/base.py` |
| `DocSourceRegistry` | 注册表 | 高 | `agentos/adapters/doc_sources/registry.py` |
| `LocalFileAdapter` | 本地文件 | 高 | `agentos/adapters/doc_sources/local.py` |
| `FeishuDocAdapter` | 飞书文档 | 高 | `agentos/adapters/doc_sources/feishu.py` |
| `NotionAdapter` | Notion | 中 | `agentos/adapters/doc_sources/notion.py` |
| `DingTalkAdapter` | 钉钉文档 | 低 | `agentos/adapters/doc_sources/dingtalk.py` |

### 6.4 需要新增的配置

在 `config.yml` 中添加：

```yaml
agents:
  office-main: {...}
  ppt-agent: {...}
  data-analyst: {...}
  doc-organizer: {...}
  email-agent: {...}

ppt:
  generator: python-pptx
```


## 7. 实现阶段划分

### 阶段 1：核心框架（高优先级）
1. 创建 5 个 agent 配置
2. 实现 `doc_source_tool` 和基础适配器（Local、Feishu）
3. 实现 `generate_ppt` skill（预留扩展接口）
4. 实现 `gmail_skill`

### 阶段 2：数据分析能力（中优先级）
1. 实现 `analyze_data` skill
2. 实现 `visualize_data` skill
3. 测试 subagent 互相委托流程

### 阶段 3：扩展支持（低优先级）
1. 添加更多文档来源适配器（Notion、钉钉）
2. 添加更多邮件 skill（Outlook）
3. 实现 PPT 生成的其他方式（API、模板）

## 8. 测试计划

### 8.1 单 Agent 测试
- office-main 正确识别需求并委托
- 每个 subagent 独立完成任务

### 8.2 委托链路测试
- office-main → ppt-agent
- ppt-agent → data-analyst → 返回图表
- data-analyst → doc-organizer → 读取文档数据

### 8.3 文档来源测试
- 本地文件读取
- 飞书文档访问
- 自动识别来源

### 8.4 邮件功能测试
- Gmail 收发邮件
- 定时检查邮件
- Cron 任务创建


## 9. 用户使用指南

### 9.1 创建会话

```bash
# Web 界面：选择 office-main agent
# CLI：指定 agent_id
python3 -m agentos.app.cli.cli_client --agent office-main
```

### 9.2 使用示例

**示例 1：生成 PPT**
```
用户: 帮我生成一份关于 2024 年销售数据的 PPT
office-main → ppt-agent
结果: 已生成 PPT，保存在 workspace/output/sales_2024.pptx
```

**示例 2：数据分析 + PPT**
```
用户: 分析 sales.csv 并生成包含图表的 PPT
office-main → ppt-agent → data-analyst（生成图表）
结果: 已生成包含图表的 PPT
```

**示例 3：文档整理**
```
用户: 整理这个飞书文档 https://feishu.cn/docs/xxx
office-main → doc-organizer
结果: 已整理文档，保存在 workspace/output/doc_summary.md
```

**示例 4：邮件定时检查**
```
用户: 每天早上 9 点检查 Gmail 并提醒我重要邮件
office-main → email-agent
结果: 已设置定时任务，每天 9:00 检查邮件
```

## 10. 后续优化方向

1. **智能路由**：office-main 自动判断是否需要多个 agent 协作
2. **上下文传递**：subagent 之间共享中间结果
3. **并行执行**：多个独立任务并行委托
4. **结果缓存**：避免重复执行相同任务
5. **用户反馈**：根据用户反馈调整委托策略
