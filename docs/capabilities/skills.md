# Skills 系统

Skills 是 Sensenova-Claw 的声明式任务编排机制。与工具（Tool）不同，Skills 不是直接可调用的函数，而是以 Markdown 文档形式定义的结构化指令，在构建系统提示时注入给 Agent 作为参考。

## 核心概念

- **Skill**：一个包含名称、描述和详细步骤的 Markdown 文档
- **SkillRegistry**：管理 Skill 的注册、加载、启用/禁用
- **SKILL.md**：Skill 的定义文件，使用 YAML frontmatter + Markdown body 格式
- **skills_state.json**：Skill 启用/禁用状态的持久化文件

## Skill 数据结构

Skill 类定义位于 `sensenova_claw/capabilities/skills/registry.py`：

```python
class Skill:
    name: str          # 技能名称（唯一标识）
    description: str   # 描述（用于展示和 LLM 选择）
    body: str          # YAML/Markdown 技能定义内容
    path: Path         # SKILL.md 所在目录

    @property
    def source(self) -> str
        """来源：读取 .install.json 获取，默认 'local'"""

    @property
    def version(self) -> str | None
        """版本号：读取 .install.json 获取"""

    @property
    def install_info(self) -> dict | None
        """安装信息：从 .install.json 读取"""
```

## SKILL.md 文件格式

每个 Skill 以 `SKILL.md` 文件定义，使用 YAML frontmatter 声明元信息：

```markdown
---
name: pdf_to_markdown
description: 将 PDF 文件转换为 Markdown 格式
metadata:
  sensenova-claw:
    requires:
      bins: ["pdftotext"]    # 依赖的系统二进制文件
---

## 步骤

1. 使用 bash_command 调用 pdftotext 转换 PDF
2. 读取转换后的文本文件
3. 格式化为 Markdown 输出

## 注意事项

- 支持中英文 PDF
- 表格内容可能需要手动调整格式
```

**解析规则**：
- 文件必须以 `---` 开头
- YAML frontmatter 中 `name` 和 `description` 为必填字段
- `---` 之后的内容为 `body`，即 Skill 的详细指令

## SkillRegistry

SkillRegistry 位于 `sensenova_claw/capabilities/skills/registry.py`，管理所有 Skill 的生命周期：

```python
class SkillRegistry:
    def __init__(
        self,
        workspace_dir: Path | None,     # 工作区 skills 目录
        user_dir: Path | None,          # 用户级目录（~/.sensenova-claw/skills）
        state_file: Path | None,        # skills_state.json 路径
        builtin_dir: Path | None,       # 内置 skills 目录
    )

    # CRUD 操作
    def register(skill: Skill) -> None           # 注册 Skill 到内存
    def unregister(name: str) -> bool             # 从内存移除
    def get(name: str) -> Skill | None            # 按名称获取
    def get_all() -> list[Skill]                  # 获取所有已加载 Skill

    # 状态管理
    def set_enabled(name: str, enabled: bool)     # 设置启用/禁用，持久化到 skills_state.json
    def is_enabled(name: str) -> bool             # 检查是否启用

    # 加载
    def load_skills(config: dict) -> None         # 从所有目录加载
    def reload_skill(name: str, config: dict)     # 热重载指定 Skill
    def parse_skill(skill_path: Path) -> Skill    # 解析 SKILL.md 文件
```

### 加载优先级

`load_skills()` 按以下顺序加载，后加载的同名 Skill 覆盖先加载的：

```
builtin_dir（内置 skills，最低优先级）
  ↓
user_dir（用户级，~/.sensenova-claw/skills）
  ↓
workspace_dir（工作区 skills）
  ↓
extra_dirs（config.yml 中配置的额外目录，最高优先级）
```

### 门控机制（_should_load）

Skill 是否加载取决于三层检查：

1. **skills_state.json**（最高优先级）：如果文件中存在该 Skill 的 `enabled` 字段，以此为准
2. **config.yml 配置**：检查 `skills.entries.{skill_name}.enabled`
3. **二进制依赖检查**：检查 `metadata.sensenova-claw.requires.bins` 中列出的二进制文件是否在系统 PATH 中（通过 `shutil.which` 检查）

## 内置 Skills

Sensenova-Claw 包含以下内置 Skills，位于 `workspace/skills/` 目录：

### 文档处理

| Skill | 描述 |
|-------|------|
| `pdf` | PDF 文件转换与处理 |
| `docx` | Word 文档转 Markdown |
| `xlsx` | Excel 文件转 Markdown |
| `pptx` | PowerPoint 文件处理 |

### 前端开发

| Skill | 描述 |
|-------|------|
| `frontend-design` | 前端界面设计 |
| `webapp-testing` | Web 应用测试 |
| `web-artifacts-builder` | Web 构建产物管理 |

### 创意设计

| Skill | 描述 |
|-------|------|
| `canvas-design` | 画布设计 |
| `algorithmic-art` | 算法艺术生成 |
| `brand-guidelines` | 品牌指南制作 |
| `theme-factory` | 主题工厂 |

### 沟通协作

| Skill | 描述 |
|-------|------|
| `doc-coauthoring` | 文档协作编写 |
| `internal-comms` | 内部沟通文案 |
| `slack-gif-creator` | Slack GIF 创建 |

### 工具管理

| Skill | 描述 |
|-------|------|
| `skill-creator` | 创建新 Skill |
| `mcp-builder` | MCP 协议构建器 |

### 飞书集成

| Skill | 描述 |
|-------|------|
| `feishu-doc` | 飞书文档操作 |
| `feishu-wiki` | 飞书知识库操作 |
| `feishu-drive` | 飞书云盘操作 |
| `feishu-perm` | 飞书权限管理 |

## Skill 在 Agent 中的集成方式

### 系统提示注入

在 ContextBuilder 构建系统提示时，将启用的 Skills 列表注入：

```python
# 伪代码
enabled_skills = skill_registry.get_all()
for skill in enabled_skills:
    system_prompt += f"\n## Skill: {skill.name}\n"
    system_prompt += f"{skill.description}\n"
    system_prompt += f"{skill.body}\n"
```

### Agent 级别过滤

可以在 `AgentConfig.skills` 中指定特定 Agent 可用的 Skill 列表：

```yaml
agents:
  research-agent:
    skills: ["pdf", "fetch_url"]  # 仅允许这两个 Skill
  design-agent:
    skills: []                     # 空列表 = 允许全部 Skill
```

### Skills 不是工具

**重要区别**：Skills 与 Tools 的本质不同：

| 维度 | Tool | Skill |
|------|------|-------|
| 调用方式 | LLM function calling 直接调用 | 作为上下文注入系统提示 |
| 执行方式 | 由 ToolRuntime 自动执行 | Agent 参考后自行编排 Tool 调用 |
| 参数格式 | JSON Schema 严格定义 | 自然语言描述 |
| 返回值 | 结构化数据 | 无直接返回 |

Skills 本质上是"教 Agent 如何完成复杂任务的说明书"，Agent 阅读后自行决定调用哪些工具、以什么顺序执行。

## 配置参考

```yaml
skills:
  entries:
    pdf:
      enabled: true
    xlsx:
      enabled: false        # 禁用特定 Skill

  extra_dirs:               # 额外的 Skill 加载目录
    - /path/to/custom/skills
```

## Skill 市场

Sensenova-Claw 支持通过 Skill 市场安装和管理 Skills，相关数据模型位于 `sensenova_claw/capabilities/skills/models.py`：

- **SkillSearchItem**：市场搜索结果项
- **SkillDetail**：Skill 详情（含文件列表、预览）
- **InstallRequest**：安装请求
- **UpdateInfo**：更新信息

安装的 Skill 会在其目录下生成 `.install.json` 文件，记录来源（source）、版本（version）等安装信息。
