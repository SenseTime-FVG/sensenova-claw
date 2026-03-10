# PRD: AgentOS Skills 系统

> 版本: update_v0.4
> 日期: 2026-03-09
> 项目: AgentOS

---

## 1. 概述

### 1.1 一句话描述

Skills 是声明式的 Markdown 指令文件（`SKILL.md`），教 Agent 如何使用工具或完成多步骤任务——与编程式 `Tool` 互补，不替代。

### 1.2 项目背景

AgentOS 是一个事件驱动的 Agent 系统，当前架构：
- **后端**: Python + FastAPI + WebSocket
- **前端**: React + TypeScript
- **核心流程**: `UI_USER_INPUT → LLM_CALL → TOOL_CALL → AGENT_STEP_COMPLETED`
- **已有 Tools**: `bash_command`, `serper_search`, `fetch_url`, `read_file`, `write_file`
- **占位 Tools**: `search_skill`, `load_skill`（v0.1 未实现）

### 1.3 Tool vs Skill

| | Tool（编程式） | Skill（声明式） |
|---|---|---|
| 形式 | Python 代码 | Markdown（`SKILL.md`） |
| 注册 | `ToolRegistry.register(tool)` | 放到目录，自动发现 |
| 运行时 | LLM function call → 执行代码 | 注入 system prompt → 指导 LLM 行为 |
| 热更新 | 重启生效 | 重启生效 |

典型例子：

- **Tool**: `bash_command`——执行 shell 命令并返回结果
- **Skill**: `deploy-staging`——告诉 Agent "当用户说部署时，依次调用 bash_command 执行 pull → build → push → rollout，每步检查退出码，失败回滚"

---

## 2. Skill 格式

### 2.1 目录结构

```
skills/
├── deploy-staging/
│   └── SKILL.md
└── code-review/
    └── SKILL.md
```

### 2.2 SKILL.md 示例

```markdown
---
name: deploy-staging
description: 部署应用到 staging 环境
metadata: {"agentos": {"requires": {"bins": ["docker", "kubectl"], "env": ["KUBECONFIG"]}}}
---

当用户要求部署到 staging 时：

1. 调用 `bash_command` 工具执行 `git pull origin main`
2. 调用 `bash_command` 工具执行 `docker build -t app:staging .`
3. 调用 `bash_command` 工具执行 `kubectl rollout restart deployment/app`

每步检查 return_code，非零停止并报告错误。
```

### 2.3 与现有 Tool 集成

Skill 通过指导 LLM 调用现有 Tool 来完成任务：

```markdown
---
name: research-topic
description: 深度研究某个主题
---

当用户要求研究某个主题时：

1. 调用 `serper_search` 搜索关键词，获取前 5 个结果
2. 对每个结果调用 `fetch_url` 获取完整内容
3. 调用 `write_file` 将研究结果保存到 `research_output.md`
4. 总结关键发现并回复用户
```

### 2.3 Frontmatter

| 字段 | 必需 | 说明 |
|------|------|------|
| `name` | 是 | 唯一标识（用于去重和覆盖） |
| `description` | 是 | 一句话描述 |
| `metadata` | 否 | 门控条件（见 §4） |

---

## 3. 检索与加载

### 3.1 两层来源

| 优先级 | 路径 | 说明 |
|--------|------|------|
| 低 | `~/.agentos/skills/` | 全局，所有 Agent 共享 |
| 高 | `<workspace>/skills/` | 项目级，仅当前 Agent |

同名 skill，workspace 覆盖全局。

**注意**: 项目使用 `.agentos/` 作为配置目录（见 `config.py` 第 92 行）。

### 3.2 发现规则

扫描来源目录的**直接子目录**，检查是否有 `SKILL.md`：

```python
def discover_skills(root_dir: str) -> list[Skill]:
    skills = []
    for name in os.listdir(root_dir):
        if name.startswith(".") or name == "node_modules":
            continue
        skill_md = os.path.join(root_dir, name, "SKILL.md")
        if os.path.isfile(skill_md):
            skills.append(load_skill(skill_md, source=root_dir))
    return skills
```

- 跳过 `.` 开头和 `node_modules`
- 不递归（只看一级子目录）
- 单个 SKILL.md 超过 256KB 跳过，记 warning

### 3.3 加载流程

```
Agent 启动 (main.py)
  → AgentRuntime 初始化
  → SkillRegistry.load() 扫描全局目录 + workspace 目录
  → 按名称合并（workspace 覆盖全局）
  → 解析 frontmatter
  → 门控过滤
  → 生成 prompt 片段，注入到 ContextBuilder 的 system prompt
```

**集成点**: 在 `app/runtime/context_builder.py` 的 `build_messages()` 中注入 skills 列表。

### 3.4 多 Agent

- **共享 skill**: 放 `~/.agentos/skills/`，所有 Agent 可见
- **专属 skill**: 放某 Agent 的 `<workspace>/skills/`，只有该 Agent 可见
- 不需要每个 Agent 存一份

**注意**: 当前项目是单 Agent 架构，未来如需多 Agent 支持，此设计已预留扩展空间。

---

## 4. 门控

通过 `metadata.agentos` 声明依赖，不满足则跳过：

```yaml
metadata: {"agentos": {"requires": {"bins": ["docker"], "env": ["DOCKER_HOST"]}}}
```

| 条件 | 说明 |
|------|------|
| `requires.bins` | 所有命令必须存在于 PATH |
| `requires.env` | 所有环境变量必须已设置 |

配置中可显式禁用：

```yaml
# .agentos/config.yaml
skills:
  entries:
    some-skill:
      enabled: false
```

过滤逻辑：

```python
def should_include(entry: SkillEntry, config: Config) -> bool:
    cfg = config.get(f"skills.entries.{entry.name}")
    if cfg and cfg.get("enabled") is False:
        return False
    req = entry.metadata.get("agentos", {}).get("requires", {})
    if req.get("bins") and not all(shutil.which(b) for b in req["bins"]):
        return False
    if req.get("env") and not all(os.environ.get(e) for e in req["env"]):
        return False
    return True
```

---

## 5. Prompt 注入

Eligible skills 以 XML 列表追加到 system prompt 末尾：

```xml
<available-skills>
<skill>
<name>deploy-staging</name>
<description>部署应用到 staging 环境</description>
<location>~/.agentos/skills/deploy-staging/SKILL.md</location>
</skill>
</available-skills>
```

Agent 在需要时用 `read_file` 工具读取完整 SKILL.md 获取详细指令。

超过 50 个 skills 时截取前 50 个（按名称排序），记 warning。

**实现位置**: 修改 `app/runtime/context_builder.py`，在 system prompt 中追加 skills 列表。

---

## 6. 配置

```yaml
# .agentos/config.yaml
skills:
  entries:
    deploy-staging:
      enabled: true
    some-unwanted:
      enabled: false
```

只需要 `enabled` 开关。环境变量在 `.agentos/config.yaml` 的全局配置或 `.env` 中设置，不做 per-skill 注入。

**注意**: 项目已有 `Config` 类支持多层配置合并（用户级 + 项目级 + 旧版 config.yml），Skills 配置复用此机制。

---

## 7. 数据模型

```python
@dataclass
class Skill:
    name: str
    description: str
    file_path: str       # SKILL.md 绝对路径
    base_dir: str        # skill 目录绝对路径
    source: str          # "global" | "workspace"
    content: str         # SKILL.md 完整内容

@dataclass
class SkillEntry:
    skill: Skill
    frontmatter: dict
    metadata: dict       # metadata.agentos（原始 dict，不单独建类型）


class SkillRegistry:
    def __init__(self, config: Config):
        self.config = config
        self._skills: dict[str, SkillEntry] = {}

    def load(self, workspace_dir: str) -> list[SkillEntry]:
        """扫描两层目录 → 合并 → 解析 frontmatter。"""

    def filter(self, entries: list[SkillEntry]) -> list[SkillEntry]:
        """门控过滤。"""

    def build_prompt(self, entries: list[SkillEntry]) -> str:
        """生成 XML 片段。"""
```

**集成到现有架构**:
- 在 `app/main.py` 初始化时创建 `SkillRegistry`
- 传递给 `ContextBuilder`，在构建 system prompt 时注入

---

## 8. 目录结构

```
backend/app/
└── skills/
    ├── __init__.py
    ├── types.py          # Skill, SkillEntry
    ├── registry.py       # SkillRegistry (load + filter + build_prompt)
    └── frontmatter.py    # parse_frontmatter()
```

一个模块 3 个文件，与现有 `tools/`, `llm/`, `runtime/` 模块结构保持一致。

---

## 9. 交付

| 步骤 | 内容 | 工期 |
|------|------|------|
| 1 | 目录发现 + frontmatter 解析 + 两层合并 | 1 天 |
| 2 | 门控过滤（enabled / bins / env） | 0.5 天 |
| 3 | Prompt 注入 + 接入 ContextBuilder | 0.5 天 |
| 4 | 移除占位 Tools（search_skill/load_skill） | 0.5 天 |
| 5 | 写 2-3 个示例 skills + e2e 测试 | 1 天 |

**总计：3.5 天。**

---

## 10. 验收标准

1. `~/.agentos/skills/test/SKILL.md` 放入后重启，Agent system prompt 中出现该 skill
2. `<workspace>/skills/test/SKILL.md` 覆盖同名全局 skill
3. `enabled: false` 能禁用 skill
4. `requires.bins: ["nonexistent"]` 的 skill 被自动跳过
5. Agent 对话中能读取 SKILL.md 并按指令执行
6. 占位 Tools（`search_skill`, `load_skill`）已从 `builtin.py` 和 `ToolRegistry` 中移除
7. e2e 测试验证：用户输入触发 skill → LLM 调用相关 Tools → 完成任务

---

## 11. 后续可加（现在不做）

| 特性 | 触发条件 | 成本 |
|------|----------|------|
| 文件监视（热重载） | 不想每次改完重启 | 加 watchfiles，~50 行 |
| `/skill-name` 用户命令 | 想要快捷入口 | 命令映射 + 名称消毒，~100 行 |
| 额外目录（extra_dirs） | 想要团队共享目录 | 配置加一个 list 字段，~10 行 |
| per-skill 环境变量注入 | skill 需要独立 API key | context manager save/restore，~40 行 |
| bundled skills | 准备发布/分发 | 加一层来源 + 打包逻辑 |

---

## 12. 与现有架构的集成点

### 12.1 修改文件清单

| 文件 | 修改内容 |
|------|----------|
| `backend/app/main.py` | 初始化 `SkillRegistry`，传递给 `ContextBuilder` |
| `backend/app/runtime/context_builder.py` | 接收 `SkillRegistry`，在 `build_messages()` 中注入 skills 到 system prompt |
| `backend/app/tools/builtin.py` | 删除 `SearchSkillTool` 和 `LoadSkillTool` |
| `backend/app/tools/registry.py` | 从 `_register_builtin()` 中移除占位 Tools |
| `backend/app/core/config.py` | 在 `DEFAULT_CONFIG` 中添加 `skills` 配置段 |

### 12.2 事件流不变

Skills 系统不改变现有事件驱动流程：
```
UI_USER_INPUT → LLM_CALL_REQUESTED → LLM_CALL_RESULT → TOOL_CALL_REQUESTED → TOOL_CALL_COMPLETED → AGENT_STEP_COMPLETED
```

Skills 只是通过 system prompt 指导 LLM 如何组合调用现有 Tools。

### 12.3 配置示例

```yaml
# .agentos/config.yaml
skills:
  entries:
    deploy-staging:
      enabled: true
    experimental-feature:
      enabled: false
```

---

## 13. 示例 Skills

### 13.1 deploy-staging

```markdown
---
name: deploy-staging
description: 部署应用到 staging 环境
metadata: {"agentos": {"requires": {"bins": ["docker", "kubectl"], "env": ["KUBECONFIG"]}}}
---

当用户要求部署到 staging 时：

1. 调用 `bash_command` 工具执行 `git pull origin main`，检查 return_code
2. 如果成功，调用 `bash_command` 工具执行 `docker build -t app:staging .`
3. 如果成功，调用 `bash_command` 工具执行 `kubectl rollout restart deployment/app`
4. 任何步骤失败（return_code != 0），立即停止并报告错误信息
```

### 13.2 research-topic

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

### 13.3 code-review

```markdown
---
name: code-review
description: 代码审查助手
---

当用户要求审查代码时：

1. 调用 `read_file` 读取指定文件
2. 检查以下方面：
   - 代码风格和可读性
   - 潜在的 bug 和边界情况
   - 性能问题
   - 安全漏洞（SQL 注入、XSS 等）
3. 生成审查报告，包含：
   - 发现的问题列表
   - 严重程度评级
   - 修复建议
4. 如果用户同意，可以调用 `write_file` 生成修复后的代码
```

---

## 14. 风险与限制

### 14.1 风险

1. **LLM 理解偏差**: Skill 是自然语言指令，LLM 可能误解或忽略
   - **缓解**: 使用清晰的结构化语言，提供具体示例

2. **Prompt 长度**: 50 个 skills 可能占用大量 token
   - **缓解**: 只注入 skill 列表，详细内容按需读取

3. **版本兼容**: Skill 格式变更可能破坏现有 skills
   - **缓解**: frontmatter 支持版本字段（未来扩展）

### 14.2 限制

1. **不支持动态参数**: Skill 不能像 Tool 那样定义结构化参数
2. **不支持返回值验证**: 无法强制 LLM 按特定格式返回
3. **依赖 LLM 能力**: 复杂逻辑可能需要更强的模型

---

## 15. 测试策略

### 15.1 单元测试

- `test_frontmatter_parsing()`: 测试 YAML frontmatter 解析
- `test_skill_discovery()`: 测试目录扫描和合并逻辑
- `test_gating()`: 测试门控过滤（bins/env/enabled）
- `test_prompt_generation()`: 测试 XML 生成

### 15.2 集成测试

- 创建临时 skill 目录，验证加载流程
- 测试 workspace 覆盖全局 skill
- 测试配置禁用 skill

### 15.3 E2E 测试

```python
async def test_skill_execution():
    # 1. 创建测试 skill
    skill_dir = Path("./test_workspace/skills/test-skill")
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text("""---
name: test-skill
description: 测试技能
---
当用户说"测试"时，调用 bash_command 执行 echo "success"
""")

    # 2. 启动 Agent
    # 3. 发送用户输入："测试"
    # 4. 验证 LLM 调用了 bash_command
    # 5. 验证返回结果包含 "success"
```

---

## 16. 总结

Skills 系统为 AgentOS 提供了声明式的任务编排能力，与现有编程式 Tools 形成互补：

- **Tools**: 原子能力（执行命令、搜索、读写文件）
- **Skills**: 组合能力（如何使用 Tools 完成复杂任务）

通过 Markdown + frontmatter 的简单格式，用户可以轻松扩展 Agent 能力，无需编写 Python 代码。系统设计遵循最小化原则，与现有架构无缝集成，预计 3.5 天完成开发和测试。
