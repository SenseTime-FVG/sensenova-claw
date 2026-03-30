# 接入 DingTalk 机器人

### 1. 安装依赖

```bash
conda activate base
uv sync --extra dev
```

确保环境中包含 `dingtalk-stream`。

### 2. 创建钉钉机器人应用

在钉钉开放平台创建机器人应用，拿到：

- `client_id`
- `client_secret`

当前插件基于官方 `dingtalk-stream-sdk-python`，使用 Stream 模式接收消息。

### 3. 配置 `config.yml`

```yaml
plugins:
  dingtalk:
    enabled: true
    client_id: "dingxxxx"
    client_secret: "xxxx"
    dm_policy: open
    group_policy: open
    require_mention: true
    allowlist: []
    group_allowlist: []
    reply_to_sender: false
    show_tool_progress: false
```

### 4. 目标 ID 规则

`message` 工具和 `Gateway.send_outbound()` 对钉钉支持两种目标格式：

- `user:<staff_id>`：主动发给指定用户
- `conversation:<open_conversation_id>`：主动发给指定群会话

### 5. 当前能力

- 私聊文本入站
- 群聊文本入站
- `mention` 控制
- `ask_user` 问答回传
- `message` 工具主动发文本

### 6. 当前限制

- 仅处理文本消息
- 目前未实现卡片消息、配对码和 richer onboarding
