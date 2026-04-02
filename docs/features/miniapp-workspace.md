# Mini-App Workspace

## 概述

`custom_pages` 现已升级为可运行的 mini-app workspace：

- 创建入口仍然是前端 `/create-feature`
- 存储仍然是 `{SENSENOVA_CLAW_HOME}/custom_pages.json`
- 每个页面现在可以拥有：
  - 独立工作区目录
  - 专属 Agent 或复用现有 Agent
  - 可运行的前端入口文件
  - 独立的 workspace Web server 入口
  - 构建任务记录
  - 页面内交互回传能力
  - 可选 ACP coding agent 构建通道

## 目录结构

```python
class MiniAppWorkspace:
    sensenova_claw_home: str
    custom_pages_json: str  # {sensenova_claw_home}/custom_pages.json
    runs_json: str          # {sensenova_claw_home}/custom_pages_runs/{slug}.json

    # 页面工作区目录
    workspace_root: str     # {sensenova_claw_home}/workdir/{agent_id}/miniapps/{slug}
    app_dir: str            # {workspace_root}/app
    server_entry: str       # {workspace_root}/server.py
    data_dir: str           # {workspace_root}/data
    manifest: str           # {workspace_root}/miniapp.json
    interaction_log: str    # {workspace_root}/interaction_log.jsonl

    # 页面入口
    entry_file_path: str    # 相对于 {sensenova_claw_home}/workdir 的路径
    server_entry_file_path: str
    bridge_script_path: str # 相对于 {sensenova_claw_home}/workdir 的路径
```

## 页面内交互桥接

内置页面和接入后的复用页面都可以通过 `window.Sensenova-ClawMiniApp.emit(action, payload, options)` 把事件回传给宿主页面。

这里的 mini-app 是通用 workspace 能力，不预设某个垂直业务。页面壳体、组件和大部分前端逻辑可以长期复用；只有用户真正需要变化的内容、配置或下一步任务，才由 Agent 决定是否更新。

推荐约定：

- `target`: `local | server | agent`
- `refreshMode`: `none | background | immediate`

含义：

- `none`：普通问答、记笔记、答题状态上报，不应触发即时 workspace 刷新
- `background`：代表已排入后台补货/夜间 refresh，但当前用户会话继续使用现有内容
- `immediate`：只有在页面结构或预生成内容必须立刻重算时才使用

```javascript
window.Sensenova-ClawMiniApp.configureActionRouting({
  defaultTarget: "server",
  routes: {
    task_card_selected: "local",
    save_workspace_snapshot: "server",
    workspace_agent_question: "agent"
  }
})

window.Sensenova-ClawMiniApp.emit("workspace_agent_question", {
  question: "这里为什么这样设计？",
  lesson_id: "lesson_3"
}, {
  target: "agent",
  refreshMode: "none"
})

window.Sensenova-ClawMiniApp.emit("workspace_refresh_requested", {
  reason: "prepared_units_exhausted"
}, {
  target: "server",
  refreshMode: "background"
})
```

宿主页面会按动作目标分流：

- `local`: 只在宿主页记录事件，不访问后端，也不占用 Agent
- `server`: 调用 `POST /api/custom-pages/{slug}/actions`，由服务端接收并记录
- `agent`: 调用 `POST /api/custom-pages/{slug}/actions`，再转到当前页面绑定的 Agent

这样页面里的高频 UI 动作可以继续像普通应用一样本地运行，状态持久化交给 workspace 自己的 server，只有真正需要 Agent 判断或后台补货编排时才会离开页面。

## API

### 创建页面

- `POST /api/custom-pages`

新增关键字段：

- `create_dedicated_agent`
- `workspace_mode`: `scratch | reuse`
- `source_project_path`
- `builder_type`: `builtin | acp`
- `generation_prompt`

### 查询构建记录

- `GET /api/custom-pages/{slug}/runs`

### 重新生成

- `POST /api/custom-pages/{slug}/generate`

### 页面交互回传

- `POST /api/custom-pages/{slug}/interactions`
- `POST /api/custom-pages/{slug}/actions`

请求体示例：

```json
{
  "target": "agent",
  "action": "workspace_agent_question",
  "payload": {
    "question": "这个步骤为什么会失败？"
  },
  "refresh_mode": "none",
  "session_id": "sess_xxx"
}
```

## Builder

### builtin

内置构建器现在会直接写出一个最小可运行的 client-server workspace：

- 从零生成场景：生成 `app/` 前端、`server.py` 服务端和 `data/` 状态目录
- 复用场景：复制源目录，保留 LICENSE/NOTICE，并注入 bridge 脚本
- Agent 主要负责在用户需要时生成或更新内容、逻辑和工作流，而不是每次交互都重做整页
- 默认设计原则是“自包含、少打扰、少刷新”：大多数交互走本地和服务端，Agent 只做最后兜底

### acp

ACP 模式目前实现最小通道：

- `initialize`
- `session/new`
- `session/prompt`

通过 stdio JSON-RPC 与外部 coding agent 通信，并把通知事件落入 run logs。

无论 builtin 还是 ACP，当前推荐生成目标都不再是“单个静态 HTML 页面”，而是：

- 一个自带 `server.py` 的独立 workspace Web server
- 一个位于 `app/` 的前端
- 一个位于 `data/` 的服务端状态区
- 一个“Agent 最后兜底”的交互模型
- 一个“尽量后台 refresh / 夜间补货”的更新策略

当前 ACP 运行时本身已经是通用的，真正决定“支持哪些 agent / 平台”的主要是：

- `miniapps.acp.command`
- `miniapps.acp.args`
- `miniapps.acp.env`
- 本机是否已经装好对应 agent / adapter

现在内置的 ACP Wizard 会自动检测当前平台（Linux / macOS / Windows）并给出推荐配置、安装命令与缺失项状态。内置预设包括：

- `Codex CLI` + `codex-acp`
- `Claude Agent / Claude Code` + `claude-agent-acp`
- `Gemini CLI` 原生 ACP（`--experimental-acp`）
- `Kimi CLI` 原生 ACP（`kimi acp`）
- `OpenCode` 原生 ACP（`opencode acp`）
- 仓库内置 `Codex ACP Bridge` 兜底方案

配置入口：

```yaml
miniapps:
  acp:
    enabled: false
    command: ""
    args: []
    env: {}
    startup_timeout_seconds: 20
    request_timeout_seconds: 180
```

也可以直接在前端设置页 `/acp` 中编辑 `miniapps.default_builder` 和 `miniapps.acp.*`，包括 `enabled`、`command`、`args`、`env` 与两类 timeout。
推荐优先使用设置页里的 ACP Wizard：

- 自动检测 PATH 中已有的 ACP agent / adapter
- 根据当前平台生成推荐 `command` / `args`
- 对缺失项执行安装
- 将推荐配置一键回填到表单，再由用户统一保存

如果要自动使用本机 `codex`，优先推荐使用官方 `codex-acp` 适配器：

```yaml
miniapps:
  default_builder: acp
  acp:
    enabled: true
    command: "npx"
    args:
      - "-y"
      - "-p"
      - "@zed-industries/codex-acp"
      - "-p"
      - "@zed-industries/codex-acp-linux-x64"
      - "codex-acp"
    env: {}
    startup_timeout_seconds: 20
    request_timeout_seconds: 180
```

说明：

- `codex-acp` 是 Zed 团队维护的 Codex 官方 ACP 适配器仓库：`zed-industries/codex-acp`
- 现在更推荐在 ACP Wizard 中直接安装 `@openai/codex` 与 `@zed-industries/codex-acp`，然后使用 `command: "codex-acp"`
- 如果你已经把 `codex-acp` 装到 `PATH`，也可以改成更直接的配置：

```yaml
miniapps:
  acp:
    command: "codex-acp"
    args: []
```

其他常见 agent 的命令示例：

```yaml
miniapps:
  acp:
    command: "claude-agent-acp"
    args: []
```

```yaml
miniapps:
  acp:
    command: "gemini"
    args:
      - "--experimental-acp"
```

```yaml
miniapps:
  acp:
    command: "kimi"
    args:
      - "acp"
```

```yaml
miniapps:
  acp:
    command: "opencode"
    args:
      - "acp"
```

如果你不想依赖外部 ACP adapter，或者某个平台上官方 adapter 仍有环境兼容问题，仓库里也保留了备用 bridge：

```yaml
miniapps:
  acp:
    command: "/home/haodong/sensenova_claw/.venv/bin/python"
    args:
      - "-m"
      - "sensenova-claw.capabilities.miniapps.codex_acp_bridge"
```

## 专属 Agent

若页面启用 `create_dedicated_agent=true`：

- 会基于所选 `base_agent_id` 复制模型、工具、技能配置
- 会把 `workdir` 指向当前页面的整个 `workspace` 根目录
- 会在启动阶段由 `MiniAppService.restore_dedicated_agents()` 重新注册

这样页面聊天和页面事件都能直接驱动同一个工作区 Agent。

## 工作区设计原则

创建 prompt 和 Agent prompt 现在都会明确强调以下原则：

- workspace 应优先是自包含的 client-server 应用，而不是只靠宿主页面驱动的静态壳
- 大部分用户交互应由本地逻辑或 workspace server 直接完成
- 发给 Agent 的消息默认只是问答、笔记沉淀或后台素材收集，不等于立刻刷新 workspace
- 用户再次打开 workspace 时，应尽量直接看到已准备好的内容
- 如果需要补充下一批内容，优先设计成后台 refresh、夜间 cron 或预生成流程，减少打断和等待
