---
name: system-admin-skill
description: Sensenova-Claw 系统运维管理技能，涵盖 LLM 配置、Agent 管理、工具配置、Skill/Plugin 安装、Cron 管理和系统状态查看
---

# Sensenova-Claw 系统运维管理技能

## 1. 环境感知

### SENSENOVA_CLAW_HOME

统一由环境变量 `$SENSENOVA_CLAW_HOME` 控制，未设置时默认 `~/.sensenova-claw/`。

```
{SENSENOVA_CLAW_HOME}/
├── config.yml                  # 主配置文件
├── agents/{id}/
│   └── AGENTS.md               # Agent role prompt
├── workdir/{id}/               # 运行时工作区
├── skills/{skill-name}/        # 用户 skill
│   └── SKILL.md
├── skills_state.json           # Skill 启用/禁用状态
└── .agent_preferences.json     # Agent 工具/技能偏好
```

项目根目录：

```
{PROJECT_ROOT}/
└─.sensenova-claw/                  # 运行时工作区
      ├── skills/{skill-name}/      # 内置 skill
      │      └── SKILL.md
      └── agents/{id}/              # 内置 Agent 
             ├── AGENTS.md         
             └── SYSTEM_PROMPT.md   # Agent 系统提示词（必须放此文件）
```

---

## 2. LLM 配置管理

### 配置结构

```yaml
llm:
  providers:
    openai:
      source_type: openai          # 必填，决定调用哪个 SDK
      api_key: ${OPENAI_API_KEY}
      base_url: ${OPENAI_BASE_URL}
      timeout: 60
      max_retries: 3
    my-custom-llm:                 # provider_id 可自定义
      source_type: openai-compatible  # 使用 OpenAI 兼容协议
      api_key: ${MY_LLM_API_KEY}
      base_url: https://my-llm.example.com/v1
  models:
    gpt_4o_mini:
      provider: openai             # 引用上面的 provider_id
      model_id: gpt-4o-mini
      timeout: 60
      max_output_tokens: 8192
  default_model: gpt_4o_mini      # 引用 llm.models 中的 key
```

**source_type 可选值：**

| 类别 | source_type | 说明 |
|:---|:---|:---|
| 原生 | `openai`, `anthropic`, `gemini` | 官方 API |
| 国产 | `qwen`, `deepseek`, `minimax`, `glm`, `kimi`, `step` | 各厂商 API（OpenAI 兼容） |
| 通用兼容 | `openai-compatible`, `anthropic-compatible`, `gemini-compatible` | 自定义端点 |

旧配置（无 source_type）会自动兼容：provider_id 与已知名称匹配时自动推断，否则回退 `openai-compatible`。

### 热更新

修改 `config.yml` 后 ConfigFileWatcher 自动检测变更，LLMFactory 自动刷新，**无需重启**。

### 常用 API

```bash
# 测试连通性
curl -s -X POST http://localhost:8000/api/config/test-llm \
  -H "Content-Type: application/json" \
  -d '{"provider":"openai","api_key":"sk-...","base_url":"","model_id":"gpt-4o-mini"}'

# 列出可用模型
curl -s -X POST http://localhost:8000/api/config/list-models \
  -H "Content-Type: application/json" \
  -d '{"api_key":"sk-...","base_url":"","provider":"openai"}'

# Secret 迁移（明文 → keyring）
curl -s -X POST http://localhost:8000/api/config/migrate-secrets
```

---

## 3. Agent 管理

### 配置结构

**`config.yml` 的 `agents` 段**（行为参数）：

```yaml
agents:
  my-agent:
    name: My Agent
    description: Agent 描述
    model: gpt_4o_mini          # 引用 llm.models 中的 key
    temperature: 0.2
    tools: []                   # 允许使用的工具列表（空 = 全部）
    skills: []                  # 允许使用的 Skills 列表（空 = 全部）
    workdir: ""
    can_send_message_to: []     # [] = 所有, ["a","b"] = 指定, null = 禁止
    max_delegation_depth: 3
    max_pingpong_turns: 10
    enabled: true
```

**system_prompt 必须放在 `{SENSENOVA_CLAW_HOME}/agents/{id}/SYSTEM_PROMPT.md`，不允许写在 config.yml 中。**

### can_send_message_to（别名 can_delegate_to）

| 值 | 含义 |
|:---|:---|
| `[]`（默认） | 可向所有已启用 Agent 发消息 |
| `["a", "b"]` | 仅向指定 Agent 发消息 |
| `null` | 禁止发消息，`send_message` 工具不暴露给该 Agent |

### Agent 工具偏好

偏好存储在 `{SENSENOVA_CLAW_HOME}/.agent_preferences.json`，支持全局和 Agent 级覆盖：

```json
{
  "tools": { "bash_command": true, "serper_search": false },
  "agent_tools": {
    "my-agent": { "bash_command": false }
  },
  "skills": { "ppt-superpower": true }
}
```

**优先级**：全局 `tools` 禁用优先 → Agent 级 `agent_tools` 覆盖 → 默认启用。

当 Agent 配置了 `tools` 列表时，不在列表中的工具不会展示；当 `can_send_message_to` 为 `null` 时，`send_message` 不会展示。

### 常用 API

```bash
# 列出所有 Agent
curl -s http://localhost:8000/api/agents | python3 -m json.tool

# 创建 Agent
curl -s -X POST http://localhost:8000/api/agents \
  -H "Content-Type: application/json" \
  -d '{"id":"my-agent","name":"My Agent","system_prompt":"你是..."}'

# 更新 Agent 配置
curl -s -X PUT http://localhost:8000/api/agents/{id}/config \
  -H "Content-Type: application/json" \
  -d '{"name":"新名称","temperature":0.3}'

# 更新偏好
curl -s -X PUT http://localhost:8000/api/agents/{id}/preferences \
  -H "Content-Type: application/json" \
  -d '{"tools":{"bash_command":false}}'

# 删除 Agent（不能删除 default）
curl -s -X DELETE http://localhost:8000/api/agents/{id}
```

---

## 4. 工具配置

### 搜索工具

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
```

未配置 API key 的搜索工具不会暴露给 LLM。

### 工具审批

```yaml
tools:
  permission:
    enabled: false
    auto_approve_levels: ["low"]
    confirmation_timeout: 60
    timeout_action: reject       # reject | approve | block
```

启用后，高风险工具执行前需用户确认。审批结果通过 `tool_confirmation_resolved` 事件下发，前端 UI 在收到服务端裁决后关闭。

### 邮件工具

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
```

### Obsidian 工具

```yaml
tools:
  obsidian:
    enabled: true                          # 启用后注册 obsidian 相关工具
    vaults:                                # 本地 vault 路径列表
      - ~/Documents/MyVault
    remote:                                # 远程 vault（需 Local REST API 插件）
      - name: remote-vault
        url: http://192.168.1.100:27123
        api_key: your-api-key
```

**注意**：`vaults` 是列表格式。未配置时会自动检测常见位置（`~/Documents/Obsidian`、`~/Obsidian` 等）。

### 检查配置状态

```bash
curl -s http://localhost:8000/api/config/required-check | python3 -m json.tool
```

---

## 5. Skill 管理

### 加载优先级（后覆盖前）

1. 内置（`{PROJECT_ROOT}/.sensenova-claw/skills`）
2. 用户（`{SENSENOVA_CLAW_HOME}/skills`）
3. 工作区（`{workspace_dir}/skills`）
4. 配置额外目录（`skills.extra_dirs`）

### 启用状态优先级

1. `{SENSENOVA_CLAW_HOME}/skills_state.json`（最高）
2. `config.yml` 中 `skills.entries.{name}.enabled`
3. 二进制依赖检查（SKILL.md 中 `metadata.sensenova-claw.requires.bins`）

### 常用 API

```bash
# 列出 Skill
curl -s http://localhost:8000/api/skills | python3 -m json.tool

# 启用/禁用
curl -s -X PUT http://localhost:8000/api/skills/{name}/enable
curl -s -X PUT http://localhost:8000/api/skills/{name}/disable

# 热重载
curl -s -X POST http://localhost:8000/api/skills/{name}/reload
```

### 安装新 Skill

```bash
mkdir -p {SENSENOVA_CLAW_HOME}/skills/{skill-name}
```

写入 `SKILL.md`（需包含 YAML frontmatter `name` + `description`）。

### Skill 环境配置检测

检测 Skills 所需的环境配置

**你必须严格按照以下流程进行，不要自己猜**
#### 执行流程:
1. 列出所有的skill，写一个检测的todolist，必须包括所有的skill 

```todolist
- 检测 <skill1_name> [未检测]
- 检测 <skill2_name> [未检测]
...
```  

2. 按`todolist`串行(不要并发读取多个SKILL，一个一个检测)依次对每一个`[未检测]`skill执行以下操作(不要自己猜测哪些可能需要检查，检查所有的skill):  
   - (1) 使用`read_file` tool 读取`SKILL.md`，列出使用该skill所需的所有环境变量，例如:`MINERU_TOKEN`,`OPENAI_API_KEY`  
   - (2) 判断该环境变量是否已配置，严格按以下顺序执行判断: (i)使用`get_secret`获取对应key；(ii)检查当前环境是否配置该变量；(iii)检查SKILL.md是否有其他路径存储该变量  
   - (3) 记录未配置的环境变量  
   - (4) 将 该skill 状态改为 `[finish]`
类似
```todolist
- 检测 <skill1_name> [finish] - [未配置环境变量: None]
- 检测 <skill1_name> [finish] - [未配置环境变量: <API_KEY1>, <API_KEY2>, ...]
- 检测 <skill2_name> [未检测]
...
``` 
3. 汇总所有未配置的环境变量(空字符串视为未配置)
4. 如果用户给出一些环境变量的配置，使用`write_secret`写入，若写入失败，尝试写入当前环境

> 当前环境常用的路径`{SENSENOVA_CLAW_HOME}/.env` or `{PROJECT_ROOT}/.env`。`{SENSENOVA_CLAW_HOME}/.env`优先
---

## 6. Plugin 管理

配置在 `config.yml` 的 `plugins` 段，修改后需**重启服务**。

内置 Plugin：`feishu`、`wecom`、`telegram`、`discord`、`whatsapp`

---

## 7. Cron 管理

Cron 任务存储在 SQLite `cron_jobs` 表，通过 REST API 管理。

```bash
# 列出任务
curl -s http://localhost:8000/api/cron/jobs | python3 -m json.tool

# 创建任务
curl -s -X POST http://localhost:8000/api/cron/jobs \
  -H "Content-Type: application/json" \
  -d '{"name":"每日报告","schedule_type":"cron","schedule_value":"0 9 * * *","timezone":"Asia/Shanghai","text":"请生成今日报告","session_target":"main","enabled":true}'

# 手动触发
curl -s -X POST http://localhost:8000/api/cron/jobs/{job_id}/trigger

# 执行历史
curl -s http://localhost:8000/api/cron/runs | python3 -m json.tool
```

**调度类型**：`cron`（标准表达式）、`every`（毫秒间隔）、`at`（ISO 8601 一次性）

---

## 8. 系统状态

```bash
# 配置概览
curl -s http://localhost:8000/api/config/sections | python3 -m json.tool

# LLM 状态
curl -s http://localhost:8000/api/config/llm-status | python3 -m json.tool

# 可用工具
curl -s http://localhost:8000/api/tools | python3 -m json.tool
```

---

## 9. REST API 速查

| 模块 | 端点 | 功能 |
|:---|:---|:---|
| Config | `/api/config` | 配置读写、LLM 管理、连通性测试、Secret 迁移 |
| Agents | `/api/agents` | Agent CRUD、偏好管理 |
| Skills | `/api/skills` | 列表、启用/禁用、热重载 |
| Cron | `/api/cron` | 定时任务 CRUD、手动触发、执行历史 |
| Tools | `/api/tools` | 列出可用工具 |
| Sessions | `/api/sessions` | 会话管理 |
| Files | `/api/files` | 文件上传/下载 |

---

## 10. 安全规范

1. **告知后再操作**：修改前向用户说明，等确认后执行
2. **修改前备份**：`cp config.yml config.yml.bak.$(date +%Y%m%d_%H%M%S)`
3. **删除需二次确认**：Agent、Skill 删除不可逆
4. **禁止直接操作 .db 文件**
5. **敏感数据**：建议用 Secret 迁移将明文密钥存入 keyring
6. **热更新 vs 重启**：
   - 无需重启：LLM、Agent、Skill 配置
   - 需要重启：Plugin 配置、全局 Cron 开关
