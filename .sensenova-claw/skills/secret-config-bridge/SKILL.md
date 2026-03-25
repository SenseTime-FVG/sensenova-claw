---
name: secret-config-bridge
description: 当其他 skill 或 tool 需要读取或写入 API key / secret 时使用。通过本目录下的 `scripts/secret_bridge.py` 直连项目配置与 secret store，同时维护目标 skill 目录下的 `secret.yml` 映射文件。
---

# Secret Config Bridge

这是一个给其他 skill / tool 复用的密钥桥接 skill。它不通过 HTTP 请求后端接口，而是直接调用本目录下的脚本：

```bash
python .sensenova-claw/skills/secret-config-bridge/scripts/secret_bridge.py
```

脚本会：

- 直接复用项目内的 `Config`、`ConfigManager`、`SecretStore`
- 写入真实 secret store
- 更新 `config.yml` 中对应的敏感字段引用
- 在目标 skill 目录下创建或更新 `secret.yml`

## 读取 secret

读取输入固定为：

```json
{"action": "read", "path": "secret:openai-whisper-api:OPENAI_API_KEY"}
```

或：

```json
{"action": "read", "path": "tools.brave_search.api_key"}
```

执行方式示例：

```bash
printf '%s' '{"action": "read", "path": "tools.brave_search.api_key"}' \
  | python .sensenova-claw/skills/secret-config-bridge/scripts/secret_bridge.py
```

处理规则：

1. 如果 `path` 是 `secret:<skill>:<ENV>`，优先读取对应 skill 目录下的 `secret.yml`
2. 例如：

```yaml
OPENAI_API_KEY: secret:openai-whisper-api:OPENAI_API_KEY
```

3. 若 `secret.yml` 中有对应映射，则用该映射从真实 secret store 取值
4. 若 `path` 是普通 dotted path，例如 `tools.brave_search.api_key`，则直接读取项目配置解析后的真实值
5. 仅把 secret 用于后续 API 调用，不要在最终回复中泄露 secret 明文

## 写入 secret

写入输入固定为：

```json
{
  "action": "write",
  "json": {
    "__meta__": {
      "skill": "openai-whisper-api",
      "env": "OPENAI_API_KEY"
    },
    "llm": {
      "providers": {
        "openai": {
          "api_key": "sk-xxx"
        }
      }
    }
  }
}
```

执行方式示例：

```bash
printf '%s' '{
  "action": "write",
  "json": {
    "__meta__": {
      "skill": "openai-whisper-api",
      "env": "OPENAI_API_KEY"
    },
    "llm": {
      "providers": {
        "openai": {
          "api_key": "sk-xxx"
        }
      }
    }
  }
}' | python .sensenova-claw/skills/secret-config-bridge/scripts/secret_bridge.py
```

处理规则：

1. `json.__meta__.skill` 指定要维护哪个 skill 目录下的 `secret.yml`
2. `json.__meta__.env` 指定 `secret.yml` 中的环境变量键名
3. 业务 payload 中必须恰好包含一个非空敏感字段，例如 `llm.providers.openai.api_key` 或 `tools.brave_search.api_key`
4. 脚本会调用项目内 `ConfigManager` 写回配置，并把真实值写入 secret store
5. 写入成功后，会在目标 skill 目录下创建或更新：

```yaml
OPENAI_API_KEY: secret:openai-whisper-api:OPENAI_API_KEY
```

6. `secret.yml` 只保存映射，不保存明文

## 返回结果

读取成功示例：

```json
{
  "ok": true,
  "path": "secret:openai-whisper-api:OPENAI_API_KEY",
  "value": "sk-xxx",
  "source": "skill_secret_mapping"
}
```

写入成功示例：

```json
{
  "ok": true,
  "path": "llm.providers.openai.api_key",
  "secret_ref": "secret:openai-whisper-api:OPENAI_API_KEY"
}
```

失败示例：

```json
{
  "ok": false,
  "error": "..."
}
```

## 禁止事项

- 不要通过 HTTP `GET` / `PUT` 配置接口调用本能力
- 不要在最终回复中泄露 secret 明文
- 不要把 secret 明文写进 skill 目录下的 `secret.yml`
- 不要把 secret 写入普通 Markdown、日志、临时文件或代码仓库
- 不要读取未注册的任意 path
- 不要因为 secret 为空就自行生成占位 key
