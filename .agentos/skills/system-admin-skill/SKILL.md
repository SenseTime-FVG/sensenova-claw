---
name: system-admin-skill
description: AgentOS 系统运维管理技能，涵盖 LLM 配置、Agent 管理、工具配置、Skill/Plugin 安装、Cron 管理和系统状态查看
---

# AgentOS 系统运维管理技能

本技能指导 SystemAdmin Agent 完成 AgentOS 平台的各类运维操作。

---

## 1. 环境感知

### 确定 AGENTOS_HOME

按以下优先级确定 AgentOS 主目录：

1. 检查环境变量 `$AGENTOS_HOME`
2. 读取 `config.yml` 中的 `system.agentos_home` 字段
3. 默认值：`~/.agentos/`

**操作步骤：**

```bash
# 用 bash_command 获取实际路径
bash_command: echo "${AGENTOS_HOME:-$HOME/.agentos}"
```

确定 `{AGENTOS_HOME}` 后，查看目录结构：

```bash
bash_command: ls -la {AGENTOS_HOME}/
```

**标准目录结构：**

```
{AGENTOS_HOME}/
├── agents/          # Agent 配置目录
│   └── {id}/
│       └── config.json
├── skills/          # 用户级 Skill 目录
│   └── {skill-name}/
│       └── SKILL.md
├── skills_state.json  # Skill 启用/禁用状态
└── .agent_preferences.json  # Agent 工具偏好设置
```

项目根目录（通常是运行 `agentos run` 的目录）包含：

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
    deepseek:
      api_key: ${DEEPSEEK_API_KEY}
      base_url: https://api.deepseek.com/v1
      provider: openai  # OpenAI 兼容接口统一用 openai
  models:
    gpt_4o_mini:
      provider: openai
      model: gpt-4o-mini
    deepseek_chat:
      provider: deepseek
      model: deepseek-chat
  default_model: gpt_4o_mini  # 引用 llm.models 中的 key

agent:
  model: gpt_4o_mini  # 引用 llm.models 中的 key
  temperature: 0.2
```

### 添加新 LLM Provider

**注意：OpenAI 兼容的第三方接口（DeepSeek、通义千问、Moonshot 等）均使用 `provider: openai`，通过 `base_url` 区分。**

修改 `config.yml` 时使用 `write_file` 工具。修改前先用 `read_file` 读取完整内容，再写回完整修改后的内容。

修改配置后，提醒用户：**需要重启 AgentOS 服务才能生效**。

---

## 3. Agent 管理

### 列出所有 Agent

```bash
bash_command: ls {AGENTOS_HOME}/agents/
```

### 查看 Agent 配置

```
read_file: {AGENTOS_HOME}/agents/{id}/config.json
```

### Agent 配置 JSON Schema

```json
{
  "id": "my-agent",
  "name": "My Agent",
  "description": "Agent 描述",
  "model": "gpt_4o_mini",
  "temperature": 0.2,
  "system_prompt": "系统提示词",
  "tools": ["bash_command", "read_file"],
  "skills": ["skill-name"],
  "enabled": true,
  "can_send_message_to": [],
  "max_send_depth": 3,
  "max_pingpong_turns": 10
}
```

### 创建新 Agent

1. 在 `{AGENTOS_HOME}/agents/{new-id}/` 目录下创建 `config.json`
2. 写入符合上述 schema 的配置

```bash
bash_command: mkdir -p {AGENTOS_HOME}/agents/{new-id}
```

```
write_file: {AGENTOS_HOME}/agents/{new-id}/config.json
内容: { ...配置 JSON... }
```

### 更新 Agent 配置

先读取现有配置，修改后写回：

```
read_file: {AGENTOS_HOME}/agents/{id}/config.json
write_file: {AGENTOS_HOME}/agents/{id}/config.json
```

### 删除 Agent

**注意：不能删除 `default` Agent。**

```bash
bash_command: rm -rf {AGENTOS_HOME}/agents/{id}
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

通过 `{AGENTOS_HOME}/.agent_preferences.json` 控制特定 Agent 的工具可用性：

```json
{
  "agent-id": {
    "disabled_tools": ["bash_command"]
  }
}
```

---

## 5. Skill 管理

### 列出已安装的 Skill

**用户级 Skill（持久化）：**

```bash
bash_command: ls {AGENTOS_HOME}/skills/
```

**内置 Skill（随项目分发）：**

```bash
bash_command: ls {PROJECT_ROOT}/.agentos/skills/
```

### 查看 Skill 内容

```
read_file: {AGENTOS_HOME}/skills/{skill-name}/SKILL.md
```

### Skill 启用/禁用状态

状态存储在 `{AGENTOS_HOME}/skills_state.json`：

```json
{
  "skill-name": {
    "enabled": true
  }
}
```

修改启用状态：

```
read_file: {AGENTOS_HOME}/skills_state.json
write_file: {AGENTOS_HOME}/skills_state.json
```

### 安装新 Skill

1. 创建 Skill 目录

```bash
bash_command: mkdir -p {AGENTOS_HOME}/skills/{skill-name}
```

2. 写入 `SKILL.md`（必须包含 YAML frontmatter）

```
write_file: {AGENTOS_HOME}/skills/{skill-name}/SKILL.md
```

SKILL.md 格式：

```markdown
---
name: skill-name
description: Skill 描述
---

# Skill 内容

...
```

### 卸载 Skill

```bash
bash_command: rm -rf {AGENTOS_HOME}/skills/{skill-name}
```

---

## 6. Plugin 管理

Plugin 配置在 `config.yml` 的 `channels` 段（如飞书、企微）：

```yaml
channels:
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
```

修改 Plugin 配置后需重启服务。

---

## 7. Cron 管理

Cron 任务配置在 `config.yml` 的 `cron` 段：

```yaml
cron:
  jobs:
    - id: daily-report
      name: 每日报告
      cron: "0 9 * * *"  # 标准 cron 表达式
      agent_id: default
      message: "请生成今日工作报告"
      enabled: true
```

Cron 表达式格式：`分 时 日 月 周`

常用示例：
- `0 9 * * *` — 每天 09:00
- `0 9 * * 1` — 每周一 09:00
- `*/30 * * * *` — 每 30 分钟

修改 Cron 配置后需重启服务生效。

---

## 8. 系统状态查看

### 查看配置概览

```
read_file: config.yml
```

### 查看数据库大小

```bash
bash_command: du -sh {PROJECT_ROOT}/var/*.db 2>/dev/null || echo "未找到数据库文件"
```

### 查看运行时日志

```bash
bash_command: tail -n 50 {PROJECT_ROOT}/var/agentos.log 2>/dev/null || echo "未找到日志文件"
```

### 查看工作区目录

```bash
bash_command: ls -la {PROJECT_ROOT}/workspace/
```

---

## 9. 安全规范

**操作前必须遵循以下规范：**

1. **告知后再操作**：执行任何修改操作前，先向用户说明将要执行的操作内容，等用户确认后再执行。

2. **修改前备份**：修改重要配置文件前，先备份原文件：
   ```bash
   bash_command: cp config.yml config.yml.bak.$(date +%Y%m%d_%H%M%S)
   ```

3. **删除操作需二次确认**：删除 Agent、Skill 等操作不可逆，必须明确得到用户确认。

4. **禁止操作数据库文件**：不要直接读写 `.db` 文件，数据库由系统内部管理。

5. **敏感数据提醒**：配置文件中可能包含 API key 等敏感信息，提醒用户不要将配置分享给他人。

6. **重启提醒**：以下修改需要重启 AgentOS 服务才能生效：
   - LLM provider/model 配置变更
   - Plugin（渠道）配置变更
   - Cron 任务配置变更
   - 工具配置变更

   重启命令：
   ```bash
   # 查看进程
   bash_command: ps aux | grep agentos
   # 停止后重新启动
   bash_command: agentos run
   ```
