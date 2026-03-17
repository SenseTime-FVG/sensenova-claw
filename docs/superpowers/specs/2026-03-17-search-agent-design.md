# Search Agent 设计文档

## 1. 概述

为办公 Agent Team 添加 `search-agent`（搜索调研助手），专注于深度调研特定主题，生成结构化 Markdown 报告。

### 设计目标

- 支持多轮搜索和内容抓取
- 利用 OCR 处理图片和文档
- 可委托给 doc-organizer 和 data-analyst
- 输出结构化 Markdown 报告

## 2. 整体架构

### Agent 层级结构

```
office-main (办公主助手)
    ├─> ppt-agent (PPT 生成)
    ├─> data-analyst (数据分析)
    ├─> doc-organizer (文档整理)
    ├─> email-agent (邮件助手)
    └─> search-agent (搜索调研) ← 新增
```

### 委托关系

```
office-main
    └─> search-agent
            ├─> doc-organizer (整理复杂文档)
            └─> data-analyst (分析数据)
```

## 3. Search Agent 配置

### 3.1 基本信息

- **ID**: `search-agent`
- **名称**: 搜索调研助手
- **职责**: 深度调研特定主题，生成结构化报告

### 3.2 配置详情

```yaml
search-agent:
  name: 搜索调研助手
  description: 深度调研特定主题，多轮搜索+内容抓取+OCR处理+生成报告
  provider: gemini
  model: MaaS_Ge_3.1_pro_preview_20260219
  temperature: 0.2
  system_prompt: |
    你是搜索调研专家，负责深度调研特定主题并生成结构化报告。

    核心能力：
    1. 多轮搜索：使用 serper_search 进行多角度搜索
    2. 内容抓取：使用 fetch_url 获取网页内容
    3. 图片处理：使用 image_search 搜索图片，使用 paddleocr-doc-parsing 提取图片文字
    4. 文档处理：委托 doc-organizer 整理复杂文档
    5. 数据分析：委托 data-analyst 分析数据
    6. 报告生成：输出结构化 Markdown 报告

    工作流程：
    1. 理解调研主题和目标
    2. 制定搜索策略（关键词、搜索轮次）
    3. 执行多轮搜索并抓取内容
    4. 处理图片和文档（OCR、格式转换）
    5. 整理和分析信息
    6. 生成结构化报告（包含摘要、详细内容、引用来源）

    报告格式：
    # {主题}调研报告

    ## 摘要
    {核心发现和结论，3-5句话}

    ## 详细内容
    ### {子主题1}
    {详细内容，包含关键信息和数据}

    ### {子主题2}
    {详细内容}

    ## 数据分析
    {如有数据，展示图表和分析结果}

    ## 引用来源
    - [标题1](链接1)
    - [标题2](链接2)

    报告输出规则：
    - 默认保存在 workspace/ 目录（由 PathPolicy 管理）
    - 文件名格式：{主题关键词}_{时间戳}.md（如：ai_trends_20260317_100530.md）
    - 如果文件已存在，自动添加序号后缀（如：ai_trends_20260317_100530_1.md）
    - 报告路径会在完成后返回给用户
  tools:
    - serper_search
    - fetch_url
    - read_file
    - write_file
    - image_search
    - delegate
  skills:
    - paddleocr-doc-parsing
  can_delegate_to:
    - doc-organizer
    - data-analyst
  max_delegation_depth: 1
```

## 4. 工具和 Skills

### 4.1 复用现有工具

| 工具名 | 用途 |
|--------|------|
| `serper_search` | 网络搜索 |
| `fetch_url` | 获取网页内容 |
| `image_search` | 搜索图片 |
| `read_file` | 读取文件 |
| `write_file` | 写入报告 |
| `delegate` | 委托其他 agent |

### 4.2 复用现有 Skills

| Skill 名 | 用途 |
|----------|------|
| `paddleocr-doc-parsing` | OCR 处理图片和文档 |

**说明**：
- paddleocr-doc-parsing 已安装在 `var/skills/paddleocr-doc-parsing/`
- 通过 `python scripts/vl_caller.py` 调用
- 支持 PDF 和图片格式
- 需要配置环境变量：`PADDLEOCR_DOC_PARSING_API_URL`、`PADDLEOCR_ACCESS_TOKEN`

## 5. 调研流程

### 5.1 典型调研流程

```
用户输入主题
    ↓
理解主题和目标
    ↓
制定搜索策略（关键词、角度）
    ↓
第1轮搜索（serper_search）
    ↓
抓取关键网页（fetch_url）
    ↓
第2-3轮搜索（不同角度）
    ↓
搜索相关图片（image_search）
    ↓
OCR 处理图片（paddleocr-doc-parsing）
    ↓
委托整理文档（doc-organizer，如需要）
    ↓
委托分析数据（data-analyst，如需要）
    ↓
整理信息
    ↓
生成 Markdown 报告（write_file）
    ↓
返回报告路径
```

### 5.2 OCR 处理流程

**Skill 调用方式**：
- paddleocr-doc-parsing 是已安装的 skill（位于 `var/skills/paddleocr-doc-parsing/`）
- Agent 通过在 system_prompt 中引导 LLM 使用该 skill
- LLM 会根据需要自主决定何时调用 paddleocr-doc-parsing
- Skill 内部通过 `scripts/vl_caller.py` 执行 OCR 处理

**场景 1：处理搜索结果中的图片**
```
image_search 返回图片 URL
    ↓
LLM 决定需要 OCR 处理
    ↓
调用 paddleocr-doc-parsing skill（传入图片 URL）
    ↓
Skill 内部执行：python scripts/vl_caller.py --file-url "图片URL"
    ↓
返回提取的文字内容
    ↓
整合到报告
```

**场景 2：处理用户上传的文档**
```
用户提供文档路径
    ↓
LLM 决定需要 OCR 处理
    ↓
调用 paddleocr-doc-parsing skill（传入文档路径）
    ↓
Skill 内部执行：python scripts/vl_caller.py --file-path "文档路径"
    ↓
返回提取的文字内容
    ↓
作为调研输入材料
```

## 6. 配置变更

### 6.1 需要修改的文件

**文件**: `config.yml`

**变更 1**: 添加 search-agent 配置
```yaml
agents:
  # ... 现有 agent 配置 ...

  search-agent:
    name: 搜索调研助手
    description: 深度调研特定主题，多轮搜索+内容抓取+OCR处理+生成报告
    provider: gemini
    model: MaaS_Ge_3.1_pro_preview_20260219
    temperature: 0.2
    system_prompt: |
      # ... 见上文 3.2 节 ...
    tools:
      - serper_search
      - fetch_url
      - read_file
      - write_file
      - image_search
      - delegate
    skills:
      - paddleocr-doc-parsing
    can_delegate_to:
      - doc-organizer
      - data-analyst
    max_delegation_depth: 1
```

**变更 2**: 更新 office-main 的委托关系
```yaml
agents:
  office-main:
    # ... 现有配置 ...
    can_delegate_to:
      - ppt-agent
      - data-analyst
      - doc-organizer
      - email-agent
      - search-agent  # 新增
```

### 6.2 无需新增文件

- 所有工具已存在
- paddleocr-doc-parsing skill 已安装
- 无需新增代码文件

## 7. 使用示例

### 示例 1：简单调研

```
用户: 帮我调研一下 2024 年 AI 大模型的发展趋势
office-main → search-agent
结果: 已生成调研报告，保存在 workspace/ai_trends_20260317_100530.md
```

### 示例 2：包含图片 OCR

```
用户: 调研量子计算的最新进展，包括相关图表
office-main → search-agent
  → image_search（搜索量子计算图表）
  → paddleocr-doc-parsing（提取图表文字）
结果: 已生成包含图表分析的报告
```

### 示例 3：委托其他 agent

```
用户: 调研 2024 年全球 GDP 数据并分析
office-main → search-agent
  → serper_search（搜索 GDP 数据）
  → fetch_url（获取数据文件）
  → delegate to data-analyst（分析数据）
结果: 已生成包含数据分析的报告
```

### 示例 4：处理用户文档

```
用户: 这是一份扫描的财报 PDF，帮我调研相关行业信息
office-main → search-agent
  → paddleocr-doc-parsing（提取 PDF 文字）
  → serper_search（搜索行业信息）
结果: 已生成行业调研报告
```

## 8. 测试计划

### 8.1 单 Agent 测试

**测试用例 1：简单调研**
```python
# 测试文件：tests/e2e/test_search_agent.py
async def test_simple_research():
    """测试 search-agent 独立完成简单调研"""
    user_input = "调研 Python 3.13 的新特性"
    # 预期：执行 2-3 轮搜索，生成包含摘要和引用的报告
    # 验证：报告文件存在，包含标题、摘要、详细内容、引用来源
```

### 8.2 OCR 功能测试

**测试用例 2：图片 OCR**
```python
async def test_image_ocr():
    """测试处理搜索结果中的图片"""
    user_input = "调研量子计算架构图"
    # 预期：搜索图片 → OCR 提取文字 → 整合到报告
    # 验证：报告中包含图片描述和提取的文字内容
```

### 8.3 委托链路测试

**测试用例 3：委托 data-analyst**
```python
async def test_delegation_to_analyst():
    """测试委托 data-analyst 分析数据"""
    user_input = "调研 2024 年全球 AI 投资数据并分析趋势"
    # 预期：搜索数据 → 委托 data-analyst → 生成包含分析的报告
    # 验证：报告中包含数据分析章节
```

### 8.4 报告质量测试

- 报告结构完整性：包含摘要、详细内容、引用来源
- 引用来源准确性：所有链接可访问
- 内容覆盖度：覆盖主题的多个角度
- Markdown 格式正确性：标题层级、列表格式正确

## 9. 依赖和前置条件

### 9.1 环境依赖

- Python 3.12+
- paddleocr-doc-parsing skill 已安装
- SERPER_API_KEY 已配置（用于搜索）

### 9.2 OCR 配置

paddleocr-doc-parsing skill 需要配置 API 访问信息。

**配置方式 1：在 config.yml 中配置**（推荐）
```yaml
tools:
  paddleocr:
    api_url: https://xxx.paddleocr.com/layout-parsing
    access_token: ${PADDLEOCR_ACCESS_TOKEN}  # 支持环境变量引用
    timeout: 120
```

**配置方式 2：系统环境变量**
```bash
export PADDLEOCR_DOC_PARSING_API_URL="https://xxx.paddleocr.com/layout-parsing"
export PADDLEOCR_ACCESS_TOKEN="your_token_here"
export PADDLEOCR_DOC_PARSING_TIMEOUT="120"
```

**说明**：
- 优先使用 config.yml 配置，便于统一管理
- 支持 `${ENV_VAR}` 语法引用环境变量
- 如果 config.yml 未配置，会回退到系统环境变量

### 9.3 现有组件

- `serper_search` 工具已实现
- `fetch_url` 工具已实现
- `image_search` 工具已实现
- `read_file`、`write_file` 工具已实现
- `delegate` 工具已实现
- `doc-organizer` agent 已配置
- `data-analyst` agent 已配置

## 10. 实现清单

### 10.1 配置变更

| 文件 | 变更内容 | 优先级 |
|------|----------|--------|
| `config.yml` | 添加 search-agent 配置 | 高 |
| `config.yml` | 更新 office-main 的 can_delegate_to | 高 |

### 10.2 无需新增

- ✅ 所有工具已存在
- ✅ paddleocr-doc-parsing skill 已安装
- ✅ 委托机制已实现
- ✅ 无需新增代码文件

## 11. 后续优化方向

1. **智能搜索策略**：根据主题自动生成多角度搜索关键词
2. **内容去重**：避免重复抓取相同内容
3. **质量评估**：评估搜索结果和报告质量
4. **增量调研**：支持在已有报告基础上补充调研
5. **多语言支持**：支持中英文混合调研
