# QQ Channel

## 概述

QQ 插件位于 `sensenova_claw.adapters.plugins.qq`，统一提供一个 `qq` channel，对外通过 `plugins.qq.mode` 切换协议实现：

- `official`：QQ 官方开放平台
- `onebot`：OneBot / NapCat / Lagrange

该插件复用现有 channel 模式：

- 入站消息统一转换为 `QQInboundMessage`
- 通过 `QQChannel` 维护会话与事件桥接
- 支持 `agent.step_completed`、`error_raised`、`user_question_asked`、`tool_call_started`、`cron_delivery_requested`

## 配置

```python
plugins = {
    "qq": {
        "enabled": True,
        "mode": "onebot",
        "dm_policy": "open",
        "group_policy": "open",
        "allowlist": [],
        "group_allowlist": [],
        "require_mention": True,
        "show_tool_progress": False,
        "reply_to_message": True,
        "official_app_id": "",
        "official_client_secret": "",
        "official_sandbox": False,
        "official_intents": [],
        "onebot_ws_url": "ws://127.0.0.1:3001",
        "onebot_access_token": "",
        "onebot_api_base_url": "http://127.0.0.1:3000",
        "onebot_self_id": "",
    }
}
```

## 测试

QQ 插件测试分三层：

- 单元测试：`tests/unit/test_qq_*.py`
- 进程内 e2e：`tests/e2e/test_qq_channel_onebot_e2e.py`
- 进程内 e2e：`tests/e2e/test_qq_channel_official_e2e.py`
