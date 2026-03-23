# 创建飞书应用

### 1. 打开飞书开放平台

访问 [飞书开放平台](https://open.feishu.cn/app)，使用飞书账号登录。

### 2. 创建应用

1. 点击 **创建企业自建应用**
2. 填写应用名称和描述
3. 选择应用图标

![创建企业自建应用](../images/feishu-step2-create-app.png)

### 3. 获取应用凭证

在应用的 **凭证与基础信息** 页面，复制：

- **App ID**（格式如 `cli_xxx`）
- **App Secret**

❗ **重要**：请妥善保管 App Secret，不要分享给他人。

![获取应用凭证](../images/feishu-step3-credentials.png)

### 4. 配置应用权限

在 **权限管理** 页面，点击 **批量导入** 按钮，粘贴以下 JSON 配置一键导入所需权限：

```json
{
  "scopes": {
    "tenant": [
      "aily:file:read",
      "aily:file:write",
      "application:application.app_message_stats.overview:readonly",
      "application:application:self_manage",
      "application:bot.menu:write",
      "cardkit:card:write",
      "contact:contact.base:readonly",
      "contact:user.employee_id:readonly",
      "corehr:file:download",
      "docs:document.content:read",
      "event:ip_list",
      "im:chat",
      "im:chat.access_event.bot_p2p_chat:read",
      "im:chat.members:bot_access",
      "im:message",
      "im:message.group_at_msg:readonly",
      "im:message.group_msg",
      "im:message.p2p_msg:readonly",
      "im:message:readonly",
      "im:message:send_as_bot",
      "im:resource",
      "sheets:spreadsheet",
      "wiki:wiki:readonly"
    ],
    "user": ["aily:file:read", "aily:file:write", "im:chat.access_event.bot_p2p_chat:read"]
  }
}
```

> **注意**：`im:message.group_msg` 权限（获取群组中所有消息，属于敏感权限）允许机器人接收群组中所有消息（不仅仅是 @机器人的）。如果您需要配置 `requireMention: false` 让机器人无需 @ 也能响应，则必须添加此权限。

![配置应用权限](../images/feishu-step4-permissions.png)

### 5. 启用机器人能力

在 **应用能力** > **机器人** 页面：

1. 开启机器人能力
2. 配置机器人名称

![启用机器人能力](../images/feishu-step5-bot-capability.png)

### 6. 配置事件订阅

⚠️ **重要提醒**：在配置事件订阅前，请务必确保已完成以下步骤：

1. 已在项目根目录的 `config.yml` 中启用飞书插件
2. 已正确填写 `plugins.feishu.app_id` 与 `plugins.feishu.app_secret`
3. Sensenova-Claw Gateway 已启动

在 **事件订阅** 页面：

1. 选择 **使用长连接接收事件**（WebSocket 模式）
2. 添加事件：`im.message.receive_v1`（接收消息）

对应的 Sensenova-Claw 配置示例：

```yaml
plugins:
  feishu:
    enabled: true
    app_id: "cli_xxx"
    app_secret: "xxx"
    dm_policy: "open"          # 私聊策略: open / allowlist
    group_policy: "mention"    # 群聊策略: mention / open / disabled
```

⚠️ **注意**：

- 当前项目的飞书接入使用 **长连接 WebSocket** 模式，不需要配置 HTTP 请求地址、加签校验 URL 或事件回调地址。
- 如果 `config.yml` 中未启用 `plugins.feishu`，或者 Gateway 尚未启动，飞书侧长连接不会真正建立。
- 当前仓库实现只需要消息接收事件 `im.message.receive_v1`；这一项配置完成后，插件会在启动时自动通过 SDK 建立连接。

![配置事件订阅](../images/feishu-step6-event-subscription.png)

### 7. 发布应用

1. 在 **版本管理与发布** 页面创建版本
2. 提交审核并发布
3. 等待管理员审批（企业自建应用通常自动通过）

---
