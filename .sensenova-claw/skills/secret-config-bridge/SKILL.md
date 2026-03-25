---
name: secret-config-bridge
description: 当其他 skill 或当前任务需要读取或写入已注册的 API key / secret 配置时使用。优先通过后端配置接口访问 `tools.*.api_key`、`llm.providers.*.api_key`、`plugins.feishu.app_secret`、`plugins.wecom.secret` 等敏感字段，避免把密钥明文写入普通文件或最终回复。
---

# Secret Config Bridge

这是一个给其他 skill 复用的密钥桥接 skill，不是面向最终用户展示明文 secret 的通用管理器。

## 适用场景

- 其他 skill 在执行前需要读取 API key，例如 `skills.brave_search.api_key`
- 需要把新的 API key 写回后端配置，并由后端自动落到 keyring / secret store
- 需要确认某个已注册 secret path 是否已经配置

## 允许访问的路径

仅使用后端已注册的 secret path，例如：

- `skills.brave_search.api_key`
- `tools.serper_search.api_key`
- `tools.tavily_search.api_key`
- `tools.baidu_search.api_key`
- `llm.providers.openai.api_key`
- `plugins.feishu.app_secret`
- `plugins.wecom.secret`

如果 path 不属于后端允许的敏感字段，不要猜测、不要绕过接口，直接停止并说明该 path 不受支持。

## 读取 secret

读取时必须先检查目标 skill 目录下是否存在 `secret.yml`，并优先读取其中的映射。

例如 `openai-whisper-api/secret.yml`：

```yaml
OPENAI_API_KEY: sensenova_claw/skills.openai-whisper-api:OPENAI_API_KEY
```

处理顺序：

1. 先定位目标 skill 目录下的 `secret.yml`
2. 如果存在目标变量映射，先按映射找到对应 secret 标识
3. 再映射到后端已注册的 secret path，并调用后端接口读取真实值
4. 如果不存在 `secret.yml` 或缺少对应键，再直接按已知 secret path 调用后端接口

读取真实值时，调用：

```http
GET /api/config/secret?path=skills.brave_search.api_key
```

返回结构示例：

```json
{
  "path": "skills.brave_search.api_key",
  "value": "brave-key-xxx"
}
```

处理规则：

1. 优先读取对应 skill 目录下的 `secret.yml`。
2. 确认映射落到后端允许的 secret path。
3. 调用 `GET /api/config/secret` 读取真实值。
4. 如果返回空字符串，视为“未配置”，不要编造值。
5. 仅把 secret 用于后续 API 调用或配置写入，不要在最终回复中泄露 secret 明文。

## 写入 secret

写入时不要伪造不存在的 `/secret/write` 接口。应通过配置更新接口写回对应 section，让后端 `ConfigManager` 自动把敏感值写入 keyring / secret store。

例如写入 Brave Search API key：

```http
PUT /api/config/sections
Content-Type: application/json

{
  "skills": {
    "brave_search": {
      "api_key": "new-brave-key"
    }
  }
}
```

处理规则：

1. 按 path 所属 section 构造最小更新 payload。
2. 调用 `PUT /api/config/sections` 写入。
3. 写入成功后，在对应 skill 目录下创建或更新 `secret.yml`，记录该 skill 使用的 secret 引用映射。
4. `secret.yml` 只记录映射，不记录明文 secret。
5. 后端会把敏感字段改写成 `${secret:...}` 引用，并把真实值写入 keyring / fallback secret store。
6. 最终回复只说明“已写入”或“未写入”，不要回显 secret 明文。

示例：如果为 `openai-whisper-api` 写入 `OPENAI_API_KEY`，则在该 skill 目录下创建：

```yaml
OPENAI_API_KEY: skills.openai-whisper-api:OPENAI_API_KEY
```

## 推荐工作流

以 Brave Search 为例：

1. 先读取 `skills.brave_search.api_key`
2. 若值非空，直接把它用于 Brave Search API 调用
3. 若值为空，提示用户先在配置中填写 Brave Search API key
4. 若用户明确提供了新 key，需要持久化时，再走 `PUT /api/config/sections`

## 禁止事项

- 不要在最终回复中泄露 secret 明文
- 不要把 secret 明文写进 skill 目录下的 `secret.yml`
- 不要把 secret 写入普通 Markdown、日志、临时文件或代码仓库
- 不要读取未注册的任意 path
- 不要杜撰不存在的 secret API
- 不要因为 secret 为空就自行生成占位 key
