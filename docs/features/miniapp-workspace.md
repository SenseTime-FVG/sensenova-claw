# Mini-App Workspace

## 概述

`custom_pages` 现已升级为可运行的 mini-app workspace：

- 创建入口仍然是前端 `/create-feature`
- 存储仍然是 `{AGENTOS_HOME}/custom_pages.json`
- 每个页面现在可以拥有：
  - 独立工作区目录
  - 专属 Agent 或复用现有 Agent
  - 可运行的前端入口文件
  - 构建任务记录
  - 页面内交互回传能力
  - 可选 ACP coding agent 构建通道

## 目录结构

```python
class MiniAppWorkspace:
    agentos_home: str
    custom_pages_json: str  # {agentos_home}/custom_pages.json
    runs_json: str          # {agentos_home}/custom_pages_runs/{slug}.json

    # 页面工作区目录
    workspace_root: str     # {agentos_home}/workdir/{agent_id}/miniapps/{slug}
    app_dir: str            # {workspace_root}/app
    manifest: str           # {workspace_root}/miniapp.json
    interaction_log: str    # {workspace_root}/interaction_log.jsonl

    # 页面入口
    entry_file_path: str    # 相对于 {agentos_home}/workdir 的路径
    bridge_script_path: str # 相对于 {agentos_home}/workdir 的路径
```

## 页面内交互桥接

内置页面和接入后的复用页面都可以通过 `window.AgentOSMiniApp.emit(action, payload)` 把事件回传给宿主页面。

这里的 mini-app 是通用 workspace 能力，不预设某个垂直业务。页面壳体、组件和大部分前端逻辑可以长期复用；只有用户真正需要变化的内容、配置或下一步任务，才由 Agent 决定是否更新。

```javascript
window.AgentOSMiniApp.configureActionRouting({
  defaultTarget: "agent",
  routes: {
    task_card_selected: "local",
    save_workspace_snapshot: "server",
    request_page_refine: "agent"
  }
})

window.AgentOSMiniApp.emit("workspace_result_submitted", {
  completed_cards: 3,
  summary: "用户完成了本轮任务并请求下一步建议"
})
```

宿主页面会按动作目标分流：

- `local`: 只在宿主页记录事件，不访问后端，也不占用 Agent
- `server`: 调用 `POST /api/custom-pages/{slug}/actions`，由服务端接收并记录
- `agent`: 调用 `POST /api/custom-pages/{slug}/actions`，再转到当前页面绑定的 Agent

这样页面里的高频 UI 动作可以继续像普通应用一样本地运行，只有真正需要服务端处理或 Agent 判断的动作才会离开页面。

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
  "action": "workspace_result_submitted",
  "payload": {
    "completed_cards": 3,
    "summary": "用户完成了本轮任务并请求下一步建议"
  },
  "session_id": "sess_xxx"
}
```

## Builder

### builtin

内置构建器会直接写出可运行的 HTML/CSS/JS：

- 从零生成场景：生成通用 workspace 壳体，页面结构和组件可长期复用
- 复用场景：复制源目录，保留 LICENSE/NOTICE，并注入 bridge 脚本
- Agent 主要负责在用户需要时生成或更新内容、逻辑和工作流，而不是每次交互都重做整页

### acp

ACP 模式目前实现最小通道：

- `initialize`
- `session/new`
- `session/prompt`

通过 stdio JSON-RPC 与外部 coding agent 通信，并把通知事件落入 run logs。

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
- 当前本机通过 `npx -y -p @zed-industries/codex-acp -p @zed-industries/codex-acp-linux-x64 codex-acp --help` 可以正常启动
- 如果你已经把 `codex-acp` 安装到 `PATH`，也可以改成更直接的配置：

```yaml
miniapps:
  acp:
    command: "codex-acp"
    args: []
```

如果你不想依赖 `npx` 或官方 adapter 仍有环境兼容问题，仓库里也保留了备用 bridge：

```yaml
miniapps:
  acp:
    command: "/home/haodong/agentos/.venv/bin/python"
    args:
      - "-m"
      - "agentos.capabilities.miniapps.codex_acp_bridge"
```

## 专属 Agent

若页面启用 `create_dedicated_agent=true`：

- 会基于所选 `base_agent_id` 复制模型、工具、技能配置
- 会把 `workdir` 指向当前页面的 `app` 目录
- 会在启动阶段由 `MiniAppService.restore_dedicated_agents()` 重新注册

这样页面聊天和页面事件都能直接驱动同一个工作区 Agent。
