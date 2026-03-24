# 安装后配置引导 + SystemAdmin 运维 Agent 设计

## 概述

用户安装 Sensenova-Claw 后，如果未配置任何 LLM API，系统应在所有入口（终端、Web、CLI）提示用户完成配置。配置完成后引导用户使用 SystemAdmin Agent 进行更多系统管理操作。

## 模块一：LLM 配置状态检测

### 后端 API

新增 `GET /api/config/llm-status` 端点：

```json
// Response
{
  "configured": true,
  "providers": ["openai", "anthropic"]
}
```

**检测逻辑**：遍历 `config.yml` 中 `llm.providers`，检查是否有至少一个 provider 的 `api_key` 非空且 provider 不是 `mock`。

**文件**：`sensenova_claw/interfaces/http/config_api.py`

### CLI 端检测

CLI 直接读取本地 config.yml 判断，不走 API。复用 `Config` 类的解析逻辑。

## 模块二：终端启动提示

### sensenova-claw run 启动后提示

**文件**：`sensenova_claw/app/main.py`（`run` 命令入口）

服务启动后，检测 config.yml 中 LLM 配置状态。如果未配置，打印：

```
⚠️  未检测到可用的 LLM API 配置，当前使用 Mock 模式
   → 访问 http://localhost:3000/?token=xxx 进行配置
   → 或使用 sensenova-claw cli 进行配置
```

检测逻辑与 API 端点一致，直接读 config 判断。

## 模块三：CLI 交互式 LLM 配置引导

### 触发条件

`sensenova-claw cli` 连接成功后，检测到未配置 LLM API。

### 交互流程

```
⚠️  未检测到 LLM API 配置，请先完成初始设置

请选择 LLM 提供商:
  1. OpenAI 兼容
  2. Anthropic (Claude)
  3. Google Gemini
  4. 跳过配置
> 1

请选择具体服务商:
  1. OpenAI
  2. 通义千问 (Qwen)
  3. 智谱 GLM (Zhipu)
  4. MiniMax
  5. DeepSeek
  6. 零一万物 (Yi)
  7. 其他 (手动输入 Base URL)
> 2

请输入 Base URL (回车使用默认值 https://dashscope.aliyuncs.com/compatible-mode/v1):
请输入 API Key: sk-xxxx

可用模型:
  1. qwen-plus
  2. qwen-turbo
  3. qwen-max
> 1

✅ LLM 配置完成！已写入 config.yml
💡 输入 /agent switch system-admin 可切换到运维助手，完成更多系统配置
```

### 实现细节

- **文件**：`sensenova_claw/app/cli/app.py` 中新增 `_run_llm_setup()` 方法
- 直接读写本地 config.yml 文件
- 选择 provider 大类后，再选择具体服务商，预设对应的 base_url 和模型列表：
  - **OpenAI 兼容**：OpenAI / 通义千问 / 智谱GLM / MiniMax / DeepSeek / 零一万物 / 其他
  - **Anthropic**：直接进入配置
  - **Gemini**：直接进入配置
- 各服务商预设默认 base_url：
  - OpenAI: `https://api.openai.com/v1`
  - 通义千问: `https://dashscope.aliyuncs.com/compatible-mode/v1`
  - 智谱GLM: `https://open.bigmodel.cn/api/paas/v4`
  - MiniMax: `https://api.minimax.chat/v1`
  - DeepSeek: `https://api.deepseek.com/v1`
  - 零一万物: `https://api.lingyiwanwu.com/v1`
  - Anthropic: `https://api.anthropic.com`
  - Gemini: `https://generativelanguage.googleapis.com`
- 交互顺序：选 provider → 选服务商 → 输入 base_url（预填默认值）→ 输入 API key → 选模型
- 各服务商预设推荐模型列表
- 配置写入后通知服务端热重载（通过 WebSocket 消息或重连）

## 模块四：Web 端 LLM 配置引导页

### 页面 `/setup`

风格仿照 `/login` 页面（居中白色卡片，Sensenova-Claw 品牌标识）。

**步骤流程**：
1. 选择 Provider 大类（按钮式选择：OpenAI 兼容 / Anthropic / Gemini）
2. 如果是 OpenAI 兼容，选择具体服务商（自动填充 Base URL）
3. 输入 Base URL（预填默认值，可修改）+ API Key
4. 选择默认模型（下拉框，根据服务商过滤）
4. 底部：「完成配置」按钮 + 「跳过」链接
5. 完成后调用 `PUT /api/config/sections` 写入配置
6. 配置完成 → 跳转 `/chat?agent=system-admin`
7. Skip → 跳转 `/chat`

### 路由拦截逻辑

在 `ProtectedRoute` 组件中：
1. 已认证 → 调用 `GET /api/config/llm-status`
2. `configured: false` → 重定向到 `/setup`
3. `/setup` 和 `/login` 页面本身不做拦截

**文件**：
- 新增 `sensenova_claw/app/web/app/setup/page.tsx`
- 修改 `sensenova_claw/app/web/components/ProtectedRoute.tsx`

## 模块五：SystemAdmin Agent

### Agent 配置

```yaml
# 预注册在代码中，不需要用户手动创建
id: system-admin
name: SystemAdmin
description: 系统运维管理员，负责 Sensenova-Claw 平台的配置管理、Agent 管理、工具管理、Skill/Plugin 安装等运维操作
provider: (继承当前默认 provider)
model: (继承当前默认 model)
temperature: 0.2
system_prompt: |
  你是 Sensenova-Claw 的系统管理员（SystemAdmin）。你的职责是帮助用户管理和配置 Sensenova-Claw 平台。

  你可以通过读写配置文件和执行系统命令来完成管理任务。操作前请先告知用户你将要执行的操作，等用户确认后再执行。

  修改配置文件后，请提醒用户某些配置可能需要重启服务才能生效。
tools:
  - read_file
  - write_file
  - bash_command
skills:
  - system-admin-skill
can_delegate_to: []
enabled: true
```

### 注册方式

在 `AgentRegistry.load_from_config()` 中，确保 `system-admin` Agent 始终存在（类似 `default` Agent 的处理方式）。

**文件**：`sensenova_claw/capabilities/agents/registry.py`

## 模块六：system-admin-skill

### Skill 文件

`sensenova_claw/capabilities/skills/builtin/system-admin-skill/SKILL.md`

### Skill 内容覆盖

#### 1. 环境感知

- 通过 `read_file` 读取项目根目录的 `config.yml` 获取当前配置
- 配置目录路径：读取 config.yml 中 `system.sensenova_claw_home` 字段，或检查环境变量 `SENSENOVA_CLAW_HOME`，默认为 `~/.sensenova-claw/`
- 通过 `bash_command` 执行 `echo $SENSENOVA_CLAW_HOME` 确定实际配置目录

#### 2. LLM 配置管理

- **查看配置**：`read_file` 读取 config.yml，解析 `llm.providers` 和 `llm.models`
- **添加/修改 Provider**：`read_file` 读取 → 修改 YAML → `write_file` 写回
- **添加/修改模型**：同上，修改 `llm.models` 部分
- **切换默认模型**：修改 `llm.default_model`

#### 3. Agent 管理

- **查看 Agent 列表**：`bash_command` 执行 `ls {sensenova_claw_home}/agents/`
- **创建 Agent**：在 `{sensenova_claw_home}/agents/{id}/` 目录下创建 `config.json`、`AGENTS.md`、`USER.md`
- **修改 Agent**：读取并修改 `config.json`
- **删除 Agent**：`bash_command` 删除对应目录

#### 4. 工具配置

- **搜索工具**：修改 config.yml 中 `tools.serper_search.api_key` 等字段
- **邮件工具**：修改 config.yml 中 `tools.email` 部分（SMTP/IMAP 配置）
- **启用/禁用工具**：修改 `{sensenova_claw_home}/.agent_preferences.json`

#### 5. Skill 管理

- **查看已安装 Skill**：`bash_command` 执行 `ls {sensenova_claw_home}/skills/`
- **安装 Skill**：`bash_command` 将 skill 目录复制到 `{sensenova_claw_home}/skills/`
- **卸载 Skill**：`bash_command` 删除对应 skill 目录
- **启用/禁用 Skill**：读写 `{sensenova_claw_home}/skills_state.json`

#### 6. Plugin 管理

- **查看已安装 Plugin**：`bash_command` 查看 plugin 目录
- **安装 Plugin**：`bash_command` 复制 plugin 目录到对应位置
- **卸载 Plugin**：`bash_command` 删除对应目录

#### 7. Cron 管理

- **查看 Cron 任务**：读取 config.yml 中 `cron` 部分
- **添加/修改/删除 Cron**：修改 config.yml 的 `cron` 配置

#### 8. 系统状态

- **查看配置概览**：读取 config.yml 输出关键配置项
- **查看目录结构**：`bash_command` 执行 `tree` 或 `ls -la`
- **查看日志**：`bash_command` 读取日志文件
- **查看数据库大小**：`bash_command` 检查 `{sensenova_claw_home}/data/` 目录

#### 9. 安全规范

- 修改前先备份原文件（`cp config.yml config.yml.bak`）
- 操作前告知用户将要做什么
- 不直接操作数据库文件
- API Key 等敏感信息写入后提醒用户不要分享 config.yml

## 文件变更清单

| 文件 | 操作 | 说明 |
|------|------|------|
| `sensenova_claw/interfaces/http/config_api.py` | 修改 | 新增 `GET /api/config/llm-status` |
| `sensenova_claw/app/main.py` | 修改 | `run` 命令启动后检测并打印提示 |
| `sensenova_claw/app/cli/app.py` | 修改 | 新增 `_run_llm_setup()` 交互式引导 |
| `sensenova_claw/app/web/app/setup/page.tsx` | 新增 | LLM 配置引导页 |
| `sensenova_claw/app/web/components/ProtectedRoute.tsx` | 修改 | 添加 LLM 状态检测和重定向 |
| `sensenova_claw/capabilities/agents/registry.py` | 修改 | 确保 system-admin Agent 始终注册 |
| `sensenova_claw/capabilities/skills/builtin/system-admin-skill/SKILL.md` | 新增 | 运维 Skill |
| `sensenova_claw/app/gateway/main.py` | 修改 | 启动时注册 system-admin Agent |
