---
name: system-admin-skill
description: Sensenova-Claw 系统运维管理技能，涵盖 LLM 配置、Agent 管理、工具配置、Skill/Plugin 安装、Cron 管理和系统状态查看
---

# Sensenova-Claw 系统运维管理技能

本技能指导 SystemAdmin Agent 完成 Sensenova-Claw 平台的各类运维操作。

---

## 1. 环境感知

### 确定 SENSENOVA_CLAW_HOME

按以下优先级确定 Sensenova-Claw 主目录：

1. 检查环境变量 `$SENSENOVA_CLAW_HOME`
2. 读取 `config.yml` 中的 `system.sensenova_claw_home` 字段
3. 默认值：`~/.sensenova-claw/`

**操作步骤：**

```bash
# 用 bash_command 获取实际路径
bash_command: echo "${SENSENOVA_CLAW_HOME:-$HOME/.sensenova-claw}"
```

确定 `{SENSENOVA_CLAW_HOME}` 后，查看目录结构：

```bash
bash_command: ls -la {SENSENOVA_CLAW_HOME}/
```

**标准目录结构：**

```
{SENSENOVA_CLAW_HOME}/
├── agents/          # Agent 配置目录
│   └── {id}/
│       ├── SYSTEM_PROMPT.md   # Agent 系统提示词（必须放在此文件）
│       └── ...
├── skills/          # 用户级 Skill 目录
│   └── {skill-name}/
│       └── SKILL.md
├── skills_state.json  # Skill 启用/禁用状态
└── .agent_preferences.json  # Agent 工具/技能偏好设置
```

项目根目录（通常是运行 `sensenova-claw run` 的目录）包含：

```
{PROJECT_ROOT}/
├── config.yml       # 主配置文件
├── var/             # 运行时数据（数据库等）
└── workspace/       # 运行时工作区
```

---

## 2. LLM 配置管理

### 读取当前 LLM 配置

```
read_file: config.yml
```

关注 `llm.providers` 和 `llm.models` 段：

```yaml
llm:
  providers:
    openai:
      api_key: ${OPENAI_API_KEY}
      base_url: https://api.openai.com/v1  # 可省略，使用默认值
      timeout: 60
      max_retries: 3
    deepseek:
      api_key: ${DEEPSEEK_API_KEY}
      base_url: https://api.deepseek.com/v1
  models:
    gpt_4o_mini:
      provider: openai
      model_id: gpt-4o-mini
      timeout: 60
      max_output_tokens: 8192
    deepseek_chat:
      provider: deepseek
      model_id: deepseek-chat
  default_model: gpt_4o_mini  # 引用 llm.models 中的 key

agent:
  temperature: 0.2
  system_prompt: "全局默认系统提示词（当 Agent 无独立 SYSTEM_PROMPT.md 时使用）"
```

### 添加新 LLM Provider

**注意：OpenAI 兼容的第三方接口（DeepSeek、通义千问、Moonshot 等）均使用 `provider: openai`，通过 `base_url` 区分。**

修改 `config.yml` 时使用 `write_file` 工具。修改前先用 `read_file` 读取完整内容，再写回完整修改后的内容。

**v1.2 热更新**：LLM 配置支持通过 ConfigManager 热更新。修改 `config.yml` 后，ConfigFileWatcher 会自动检测变更并触发 `CONFIG_UPDATED` 事件，下游模块（LLMFactory）自动刷新，**无需重启服务**。

### 测试 LLM 连通性

配置完成后可测试连通性：

```bash
# 通过 REST API 测试（需要服务已启动）
bash_command: curl -s -X POST http://localhost:8000/api/config/test-llm \
  -H "Content-Type: application/json" \
  -d '{"provider":"openai","api_key":"sk-...","base_url":"","model_id":"gpt-4o-mini"}'
```

### 查询可用模型

```bash
# 列出某个 provider 的所有可用模型
bash_command: curl -s -X POST http://localhost:8000/api/config/list-models \
  -H "Content-Type: application/json" \
  -d '{"api_key":"sk-...","base_url":"","provider":"openai"}'
```

### Secret 管理

API key 等敏感信息可通过系统密钥环（keyring）安全存储，避免明文写入 `config.yml`：

```bash
# 将 config.yml 中的明文密钥迁移到密钥环
bash_command: curl -s -X POST http://localhost:8000/api/config/migrate-secrets
```

迁移后，`config.yml` 中的明文值会被替换为 `$secret_ref:...` 引用。

---

## 3. Agent 管理

### 列出所有 Agent

```bash
# 通过 REST API 获取（推荐，包含完整详情）
bash_command: curl -s http://localhost:8000/api/agents | python3 -m json.tool
```

或通过文件系统：

```bash
bash_command: ls {SENSENOVA_CLAW_HOME}/agents/
```

### 查看 Agent 配置

```bash
# 通过 REST API
bash_command: curl -s http://localhost:8000/api/agents/{id} | python3 -m json.tool
```

### Agent 配置结构

Agent 配置分布在两个位置：

**1. `config.yml` 的 `agents` 段**（行为参数）：

```yaml
agents:
  my-agent:
    name: My Agent
    description: Agent 描述
    model: gpt_4o_mini          # 引用 llm.models 中的 key
    temperature: 0.2
    max_tokens: null
    extra_body: {}              # 透传给 LLM API 的额外参数
    tools: []                   # 允许使用的工具列表（空 = 全部）
    skills: []                  # 允许使用的 Skills 列表（空 = 全部）
    workdir: ""                 # 工作目录（空=自动解析为 workspace/workdir/{id}）
    can_send_message_to: []     # Agent 间消息权限（见下方说明）
    max_delegation_depth: 3     # 最大委托深度
    max_pingpong_turns: 10      # 单个子会话最大往返轮数
    enabled: true
```

**2. `{SENSENOVA_CLAW_HOME}/agents/{id}/SYSTEM_PROMPT.md`**（系统提示词）：

```markdown
你是一个专业的 AI 助手...
```

**重要：`system_prompt` 不允许写在 `config.yml` 中，必须放在 `SYSTEM_PROMPT.md` 文件中，否则启动会报错。**

### Agent 间消息权限（can_send_message_to）

`can_send_message_to`（别名 `can_delegate_to`）控制该 Agent 是否可以通过 `send_message` 工具向其他 Agent 发送消息：

| 值 | 含义 |
|:---|:---|
| `[]`（空列表，默认） | 可以向**所有**已启用 Agent 发消息 |
| `["agent-a", "agent-b"]` | 仅可向指定 Agent 发消息 |
| `null` | **禁止**向任何 Agent 发消息（`send_message` 工具不会暴露给该 Agent） |

配置示例：

```yaml
agents:
  default:
    can_send_message_to: null       # 禁止 default agent 发消息
  research-agent:
    can_send_message_to:            # 仅允许向 default 发消息
      - default
  coordinator:
    can_send_message_to: []         # 可以向所有 agent 发消息
```

**注意：** 当设为 `null` 时，该 Agent 的 system prompt 中也不会注入可用 Agent 列表信息。

### 创建新 Agent

**方式一：通过 REST API（推荐）**

```bash
bash_command: curl -s -X POST http://localhost:8000/api/agents \
  -H "Content-Type: application/json" \
  -d '{
    "id": "my-agent",
    "name": "My Agent",
    "description": "Agent 描述",
    "model": "gpt_4o_mini",
    "system_prompt": "你是一个专业的 AI 助手",
    "tools": [],
    "skills": [],
    "can_send_message_to": [],
    "max_delegation_depth": 3
  }'
```

**方式二：通过文件系统**

1. 在 `config.yml` 的 `agents` 段添加配置
2. 创建 system prompt 文件：

```bash
bash_command: mkdir -p {SENSENOVA_CLAW_HOME}/agents/{new-id}
```

```
write_file: {SENSENOVA_CLAW_HOME}/agents/{new-id}/SYSTEM_PROMPT.md
内容: 系统提示词...
```

### 更新 Agent 配置

```bash
# 通过 REST API
bash_command: curl -s -X PUT http://localhost:8000/api/agents/{id}/config \
  -H "Content-Type: application/json" \
  -d '{"name":"新名称","temperature":0.3}'
```

### 删除 Agent

**注意：不能删除 `default` Agent。**

```bash
# 通过 REST API（推荐）
bash_command: curl -s -X DELETE http://localhost:8000/api/agents/{id}
```

### Agent 工具/技能偏好

通过 `{SENSENOVA_CLAW_HOME}/.agent_preferences.json` 控制工具和技能的启用/禁用：

```json
{
  "tools": {
    "bash_command": true,
    "serper_search": false
  },
  "skills": {
    "ppt-superpower": true
  }
}
```

也可通过 REST API 更新：

```bash
bash_command: curl -s -X PUT http://localhost:8000/api/agents/{id}/preferences \
  -H "Content-Type: application/json" \
  -d '{"tools":{"bash_command":false},"skills":{"some-skill":true}}'
```

---

## 4. 工具配置

### 搜索工具 API Key 配置

在 `config.yml` 的 `tools` 段配置：

```yaml
tools:
  serper_search:
    api_key: ${SERPER_API_KEY}
    timeout: 15
    max_results: 10
  brave_search:
    api_key: ${BRAVE_API_KEY}
  tavily_search:
    api_key: ${TAVILY_API_KEY}
  baidu_search:
    api_key: ${BAIDU_APPBUILDER_API_KEY}
```

未配置 API key 的搜索工具不会暴露给 LLM。

### 检查工具配置状态

```bash
# 检查搜索工具和邮件配置是否已完成
bash_command: curl -s http://localhost:8000/api/config/required-check | python3 -m json.tool
```

### 邮件工具配置

```yaml
tools:
  email:
    enabled: true
    smtp_host: smtp.gmail.com
    smtp_port: 587
    imap_host: imap.gmail.com
    imap_port: 993
    username: ${EMAIL_USERNAME}
    password: ${EMAIL_PASSWORD}
    max_attachment_size_mb: 10
    timeout: 30
```

常见邮箱配置：
- **Gmail**: SMTP `smtp.gmail.com:587`，IMAP `imap.gmail.com:993`，需使用应用专用密码
- **Outlook**: SMTP `smtp-mail.outlook.com:587`，IMAP `outlook.office365.com:993`
- **QQ邮箱**: SMTP `smtp.qq.com:587`，IMAP `imap.qq.com:993`，需开启 IMAP/SMTP 并获取授权码

### 启用/禁用工具（Agent 级别）

通过 Agent 偏好设置控制（见 Agent 管理 > Agent 工具/技能偏好）。

---

## 5. Skill 管理

### 列出已安装的 Skill

**通过 REST API（推荐）：**

```bash
bash_command: curl -s http://localhost:8000/api/skills | python3 -m json.tool
```

**用户级 Skill（持久化）：**

```bash
bash_command: ls {SENSENOVA_CLAW_HOME}/skills/
```

**内置 Skill（随项目分发）：**

```bash
bash_command: ls {PROJECT_ROOT}/.sensenova-claw/skills/
```

### Skill 加载优先级

Skill 按以下优先级加载（后加载的覆盖先加载的同名 Skill）：
1. 内置 Skill（`{PROJECT_ROOT}/.sensenova-claw/skills`）
2. 用户 Skill（`~/.sensenova-claw/skills`）
3. 工作区 Skill（`{workspace_dir}/skills`）
4. 配置额外目录（`config.yml` 中的 `skills.extra_dirs`）

### 查看 Skill 内容

```
read_file: {SENSENOVA_CLAW_HOME}/skills/{skill-name}/SKILL.md
```

### Skill 启用/禁用

启用状态按以下优先级判断：
1. `{SENSENOVA_CLAW_HOME}/skills_state.json`（最高优先级）
2. `config.yml` 中的 `skills.entries.{name}.enabled`
3. 二进制依赖检查（SKILL.md 中声明的 `metadata.sensenova-claw.requires.bins`）

**修改启用状态：**

```bash
# 通过 REST API（推荐）
bash_command: curl -s -X PUT http://localhost:8000/api/skills/{skill-name}/enable
bash_command: curl -s -X PUT http://localhost:8000/api/skills/{skill-name}/disable
```

或手动修改 `{SENSENOVA_CLAW_HOME}/skills_state.json`：

```json
{
  "skill-name": {
    "enabled": true
  }
}
```

### 安装新 Skill

1. 创建 Skill 目录

```bash
bash_command: mkdir -p {SENSENOVA_CLAW_HOME}/skills/{skill-name}
```

2. 写入 `SKILL.md`（必须包含 YAML frontmatter）

```
write_file: {SENSENOVA_CLAW_HOME}/skills/{skill-name}/SKILL.md
```

SKILL.md 格式：

```markdown
---
name: skill-name
description: Skill 描述
metadata:
  sensenova-claw:
    requires:
      bins: [binary1, binary2]  # 可选：声明二进制依赖
---

# Skill 内容

...
```

### 卸载 Skill

```bash
bash_command: rm -rf {SENSENOVA_CLAW_HOME}/skills/{skill-name}
```

### 热重载 Skill

单个 Skill 可以在不重启服务的情况下重载：

```bash
# 通过 REST API
bash_command: curl -s -X POST http://localhost:8000/api/skills/{skill-name}/reload
```

---

## 6. Plugin 管理

Plugin 通过 PluginRegistry 动态发现和加载，配置在 `config.yml` 的 `plugins` 段：

```yaml
plugins:
  feishu:
    enabled: true
    app_id: ${FEISHU_APP_ID}
    app_secret: ${FEISHU_APP_SECRET}
    verification_token: ${FEISHU_VERIFICATION_TOKEN}
    encrypt_key: ${FEISHU_ENCRYPT_KEY}
    tools:
      doc: true
      wiki: true
      drive: true
  wecom:
    enabled: false
    corp_id: ${WECOM_CORP_ID}
    agent_id: ${WECOM_AGENT_ID}
    secret: ${WECOM_SECRET}
  whatsapp:
    enabled: false
```

**内置 Plugin：** feishu（飞书）、wecom（企业微信）、whatsapp

每个 Plugin 可注册 Channel、Tool 或 Hook。修改 Plugin 配置后需重启服务。

---

## 7. Cron 管理

**v1.2 重要变更：Cron 任务已改为数据库驱动（SQLite `cron_jobs` 表），不再存储在 `config.yml` 中。**

### 通过 REST API 管理 Cron

**列出所有任务：**

```bash
bash_command: curl -s http://localhost:8000/api/cron/jobs | python3 -m json.tool
```

**创建新任务：**

```bash
bash_command: curl -s -X POST http://localhost:8000/api/cron/jobs \
  -H "Content-Type: application/json" \
  -d '{
    "name": "每日报告",
    "schedule_type": "cron",
    "schedule_value": "0 9 * * *",
    "timezone": "Asia/Shanghai",
    "text": "请生成今日工作报告",
    "session_target": "main",
    "enabled": true
  }'
```

**调度类型：**

| schedule_type | schedule_value 格式 | 说明 |
|:---|:---|:---|
| `cron` | `分 时 日 月 周` | 标准 cron 表达式 |
| `every` | 毫秒数（如 `1800000`） | 每隔指定毫秒触发 |
| `at` | ISO 8601 时间（如 `2026-03-25T09:00:00`） | 一次性定时触发 |

**常用 cron 表达式：**
- `0 9 * * *` — 每天 09:00
- `0 9 * * 1` — 每周一 09:00
- `*/30 * * * *` — 每 30 分钟

**查看单个任务：**

```bash
bash_command: curl -s http://localhost:8000/api/cron/jobs/{job_id} | python3 -m json.tool
```

**更新任务：**

```bash
bash_command: curl -s -X PUT http://localhost:8000/api/cron/jobs/{job_id} \
  -H "Content-Type: application/json" \
  -d '{"name":"新名称","enabled":false}'
```

**删除任务：**

```bash
bash_command: curl -s -X DELETE http://localhost:8000/api/cron/jobs/{job_id}
```

**手动触发：**

```bash
bash_command: curl -s -X POST http://localhost:8000/api/cron/jobs/{job_id}/trigger
```

**查看执行历史：**

```bash
# 单个任务的执行记录
bash_command: curl -s http://localhost:8000/api/cron/jobs/{job_id}/runs | python3 -m json.tool

# 所有任务的执行记录
bash_command: curl -s http://localhost:8000/api/cron/runs | python3 -m json.tool
```

### Cron 全局配置

`config.yml` 中的 `cron` 段控制全局行为（非具体任务）：

```yaml
cron:
  enabled: true
  max_concurrent_runs: 3
```

### Heartbeat 心跳

Heartbeat 是内置周期性检查机制，配置在 `config.yml`：

```yaml
heartbeat:
  enabled: true
  every: 300000          # 毫秒
  target: main
  prompt: "系统心跳检查"
  active_hours:
    start: 9
    end: 18
```

---

## 8. 系统状态查看

### 查看配置概览

```
read_file: config.yml
```

### 通过 REST API 查看配置

```bash
# 查看 llm / agent / plugins 配置
bash_command: curl -s http://localhost:8000/api/config/sections | python3 -m json.tool

# 检查 LLM 是否已配置
bash_command: curl -s http://localhost:8000/api/config/llm-status | python3 -m json.tool

# 查看 LLM 提供商预设列表
bash_command: curl -s http://localhost:8000/api/config/llm-presets | python3 -m json.tool
```

### 查看数据库大小

```bash
bash_command: du -sh {PROJECT_ROOT}/var/*.db 2>/dev/null || echo "未找到数据库文件"
```

### 查看运行时日志

```bash
bash_command: tail -n 50 {PROJECT_ROOT}/var/sensenova-claw.log 2>/dev/null || echo "未找到日志文件"
```

### 查看工作区目录

```bash
bash_command: ls -la {PROJECT_ROOT}/workspace/
```

### 查看可用工具

```bash
bash_command: curl -s http://localhost:8000/api/tools | python3 -m json.tool
```

---

## 9. REST API 速查

| 模块 | 端点前缀 | 主要功能 |
|:---|:---|:---|
| Config | `/api/config` | 配置读写、LLM provider/model 管理、连通性测试、Secret 迁移 |
| Agents | `/api/agents` | Agent CRUD、偏好管理 |
| Skills | `/api/skills` | 列表、安装、卸载、启用/禁用、热重载 |
| Cron | `/api/cron` | 定时任务 CRUD、手动触发、执行历史 |
| Tools | `/api/tools` | 列出可用工具 |
| Sessions | `/api/sessions` | 会话管理 |
| Files | `/api/files` | 文件上传/下载 |
| Notifications | `/api/notifications` | 通知状态和渠道 |

---

## 10. 安全规范

**操作前必须遵循以下规范：**

1. **告知后再操作**：执行任何修改操作前，先向用户说明将要执行的操作内容，等用户确认后再执行。

2. **修改前备份**：修改重要配置文件前，先备份原文件：
   ```bash
   bash_command: cp config.yml config.yml.bak.$(date +%Y%m%d_%H%M%S)
   ```

3. **删除操作需二次确认**：删除 Agent、Skill 等操作不可逆，必须明确得到用户确认。

4. **禁止操作数据库文件**：不要直接读写 `.db` 文件，数据库由系统内部管理。

5. **敏感数据提醒**：配置文件中可能包含 API key 等敏感信息，提醒用户不要将配置分享给他人。建议使用 Secret 迁移功能将明文密钥存入系统密钥环。

6. **热更新与重启**：
   - **无需重启**：LLM 配置（provider/model）、Agent 配置、Skill 启用/禁用 — 通过 ConfigManager 热更新
   - **需要重启**：Plugin（渠道）配置变更、全局 Cron 开关

   重启命令：
   ```bash
   # 查看进程
   bash_command: ps aux | grep sensenova-claw
   # 停止后重新启动
   bash_command: sensenova-claw run
   ```
