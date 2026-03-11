# Skill 市场管理功能设计

> 支持从 ClawHub、Anthropic Plugin Marketplace、Git URL 搜索安装 skills，并在 AgentOS Web UI 中统一管理。

## 一、整体架构

```
┌─────────────────────────────────────────────────┐
│                   Frontend                       │
│  ┌──────────┐  ┌──────────┐  ┌───────────────┐  │
│  │ 市场浏览  │  │ 已安装管理│  │ Skill 详情页  │  │
│  └────┬─────┘  └────┬─────┘  └──────┬────────┘  │
│       │              │               │           │
│       ▼              ▼               ▼           │
│  ─────────── AgentOS REST API ───────────────    │
└──────────────────────┬──────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────┐
│                   Backend                        │
│                                                  │
│  ┌─────────────────────────────────────────────┐ │
│  │           SkillMarketService                │ │
│  │  - search(source, query)                    │ │
│  │  - install(source, skill_id)                │ │
│  │  - uninstall(skill_name)                    │ │
│  │  - check_updates()                          │ │
│  │  - update(skill_name)                       │ │
│  └──────┬──────────┬──────────┬────────────────┘ │
│         │          │          │                   │
│    ┌────▼───┐ ┌────▼───┐ ┌───▼────┐             │
│    │ClawHub │ │Anthropic│ │  Git   │             │
│    │Adapter │ │Adapter  │ │Adapter │             │
│    └────┬───┘ └────┬───┘ └───┬────┘             │
│         │          │         │                   │
│  ┌──────▼──────────▼─────────▼─────────────────┐ │
│  │         SkillRegistry (扩展)                 │ │
│  │  - 热重载 / 注册 / 卸载                      │ │
│  └─────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────┘
```

### 核心设计点

- **SkillMarketService** 是新增核心服务，统一处理搜索/安装/更新
- **Adapter 模式** 抽象不同来源（ClawHub、Anthropic Marketplace、Git），新增来源只需加一个 Adapter
- **SkillRegistry** 在现有基础上扩展，增加热重载和卸载能力

### Skill 存储路径

- **市场安装的 skill** → `{workspace_dir}/skills/`（系统级工作目录，默认 `./SenseAssistant/workspace/skills/`）
- **用户手动安装的 skill** → `~/.agentos/skills/`（用户级，跨项目共享）
- 加载优先级：工作区 > 用户级（同名 skill 工作区覆盖用户级）

> 注意：`{workspace_dir}` 是 AgentOS 系统级工作目录，整个系统的存储都在这下面，不是项目维度。

## 二、数据模型与 Adapter 接口

### 安装元数据

每个通过市场安装的 skill，在其目录下额外生成 `.install.json`：

```json
{
    "source": "clawhub",
    "source_id": "data-analyzer",
    "version": "1.2.0",
    "installed_at": "2026-03-12T10:00:00Z",
    "repo_url": null,
    "checksum": "sha256:abc..."
}
```

手动放到 `~/.agentos/skills/` 的 skill 没有此文件，标记为 `source: "local"`。

### Adapter 抽象接口

```python
class MarketAdapter(ABC):
    """统一的市场适配器接口"""

    @abstractmethod
    async def search(self, query: str, page: int = 1) -> SearchResult:
        """搜索 skill，返回分页结果"""

    @abstractmethod
    async def get_detail(self, skill_id: str) -> SkillDetail:
        """获取 skill 详情（描述、文件列表、版本历史）"""

    @abstractmethod
    async def download(self, skill_id: str, target_dir: Path) -> Path:
        """下载并解压 skill 到目标目录，返回 skill 路径"""

    @abstractmethod
    async def check_update(self, skill_id: str, current_version: str) -> UpdateInfo | None:
        """检查是否有新版本"""
```

三个实现：

| Adapter | 来源 | 搜索方式 | 下载方式 |
|---------|------|----------|----------|
| ClawHubAdapter | ClawHub | 调用 ClawHub 搜索 API | 下载 `.skill` zip 包 |
| AnthropicAdapter | Anthropic Plugin Marketplace | 调用 Anthropic marketplace API | 下载 plugin 包 |
| GitAdapter | Git 仓库 URL | 无搜索 | `git clone --depth 1`，提取 skill 目录 |

## 三、API 设计

### 市场搜索

```
GET /api/skills/market/search?source=clawhub&q=pdf&page=1

Response:
{
    "source": "clawhub",
    "total": 128,
    "page": 1,
    "items": [
        {
            "id": "pdf-to-markdown",
            "name": "pdf-to-markdown",
            "description": "Convert PDF files to markdown",
            "author": "someuser",
            "version": "1.2.0",
            "downloads": 3500,
            "source": "clawhub"
        }
    ]
}
```

### 市场 Skill 详情

```
GET /api/skills/market/detail?source=clawhub&id=pdf-to-markdown

Response:
{
    "id": "pdf-to-markdown",
    "name": "pdf-to-markdown",
    "description": "...",
    "version": "1.2.0",
    "author": "someuser",
    "skill_md_preview": "---\nname: pdf-to-markdown\n...",
    "files": ["SKILL.md", "scripts/convert.py", "references/api.md"],
    "installed": false
}
```

### 安装

```
POST /api/skills/install
Body: { "source": "clawhub", "id": "pdf-to-markdown" }
       或 { "source": "git", "repo_url": "https://github.com/user/skill-repo" }

Response: { "ok": true, "skill_name": "pdf-to-markdown" }
```

### 卸载

```
DELETE /api/skills/{skill_name}

Response: { "ok": true }
```

### 已安装 Skills（扩展现有接口）

```
GET /api/skills

Response:
[
    {
        "id": "skill-pdf-to-markdown",
        "name": "pdf-to-markdown",
        "description": "Convert PDF to markdown",
        "category": "installed",
        "enabled": true,
        "path": "/path/to/workspace/skills/pdf-to-markdown",
        "source": "clawhub",
        "version": "1.2.0",
        "has_update": true,
        "update_version": "1.3.0"
    }
]
```

### 启用 / 禁用

```
PATCH /api/skills/{skill_name}
Body: { "enabled": false }
```

### 更新

```
POST /api/skills/{skill_name}/update

Response: { "ok": true, "old_version": "1.2.0", "new_version": "1.3.0" }
```

### 用户显式调用 Skill（斜杠命令）

```
POST /api/sessions/{session_id}/skill-invoke
Body: { "skill_name": "pdf-to-markdown", "arguments": "convert report.pdf" }
```

将 skill 内容作为特殊用户消息注入当前会话事件流。

## 四、SkillRegistry 扩展

### 热重载

```python
class SkillRegistry:
    # 现有方法保持不变...

    def register(self, skill: Skill) -> None:
        """安装后立即注册，无需重启"""
        self._skills[skill.name] = skill

    def unregister(self, name: str) -> bool:
        """卸载时移除"""
        return self._skills.pop(name, None) is not None

    def reload_skill(self, name: str, config: dict) -> bool:
        """更新后重新解析并替换"""
        skill = self._skills.get(name)
        if not skill:
            return False
        new_skill = self._parse_skill(skill.path / "SKILL.md")
        if new_skill and self._should_load(new_skill, config):
            self._skills[name] = new_skill
            return True
        return False
```

### Skill 模型扩展

```python
class Skill:
    def __init__(self, name, description, body, path):
        self.name = name
        self.description = description
        self.body = body
        self.path = path

    @property
    def install_info(self) -> dict | None:
        """读取 .install.json，无则返回 None（本地 skill）"""
        info_path = self.path / ".install.json"
        if info_path.exists():
            return json.loads(info_path.read_text())
        return None

    @property
    def source(self) -> str:
        info = self.install_info
        return info["source"] if info else "local"

    @property
    def version(self) -> str | None:
        info = self.install_info
        return info.get("version") if info else None
```

## 五、斜杠命令与事件流集成

### 事件流

```
用户输入 "/pdf-to-markdown convert report.pdf"
    │
    ▼
前端 → POST /api/sessions/{sid}/skill-invoke
    │    { skill_name: "pdf-to-markdown", arguments: "convert report.pdf" }
    │
    ▼
后端 SkillInvokeHandler:
    1. 从 SkillRegistry 获取 skill
    2. 将 skill.body 中的 $ARGUMENTS 替换为实际参数
    3. 发布事件 ui.user_input，payload 为:
       {
           "text": "<渲染后的 skill 内容>",
           "type": "skill_invoke",
           "skill_name": "pdf-to-markdown",
           "original_input": "/pdf-to-markdown convert report.pdf"
       }
    │
    ▼
AgentRuntime 收到 ui.user_input → 正常进入 agent loop
    │
    ▼
前端聊天区显示:
    用户气泡: "/pdf-to-markdown convert report.pdf"
    Agent 响应: (按 skill 指令执行的结果)
```

### 关键点

- Skill 内容对用户不可见，只作为 prompt 注入 Agent
- `$ARGUMENTS`、`$0`、`$1` 等占位符按 Claude Code Agent Skills 标准替换
- 前端用户气泡展示原始输入（斜杠命令形式），不展示渲染后长文本

## 六、前端页面设计

### 页面结构

在现有 skills 页面基础上改造为两个 Tab：

**已安装 Tab**：
- 搜索过滤已安装 skills
- 每个 skill 卡片显示：名称、描述、来源标签、版本号
- 操作按钮：启用/禁用、更新（有新版本时）、卸载（非 local 来源）

**市场浏览 Tab**：
- 三个子 Tab：ClawHub / Anthropic / Git URL
- ClawHub 和 Anthropic：搜索框 + 分页结果列表，每项显示名称、描述、下载量、作者、安装按钮
- Git URL：输入框 + 安装按钮
- 已安装的 skill 显示"已安装"标记而非安装按钮

### Skill 详情弹窗

点击任意 skill 卡片弹出详情：
- 名称、描述、版本、作者、来源
- SKILL.md 内容预览（Markdown 渲染）
- 文件列表（目录结构）
- 操作按钮：安装/卸载/启用/禁用/更新

### 聊天框斜杠命令补全

- 输入框监听 `/` 前缀
- 弹出已安装且启用的 skill 列表
- 支持模糊搜索过滤
- 选择后自动填充 `/skill-name `，光标定位到参数位置

## 七、安全考虑

- 安装时显示来源、作者、描述信息，让用户自行判断
- `.install.json` 记录 checksum，后续可扩展完整性校验
- Git 来源使用 `--depth 1` 浅克隆，减少下载量
- Skill 内容本质是 prompt 注入，scripts/ 中的可执行脚本由 Agent 通过工具系统执行，受工具权限控制
