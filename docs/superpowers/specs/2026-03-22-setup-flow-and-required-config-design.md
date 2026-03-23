# Setup 流程优化 + 必配清单设计

## 概述

优化首次配置体验：Setup 完成后直接跳转到 system-admin 对话；system-admin 默认中文名称；进入 system-admin 时自动检查必配项并发送提醒。

## 需求

1. **system-admin 名称** — 默认 Name 改为"系统运维管理员"
2. **Setup 后跳转** — 完成 LLM 配置后跳转到 `/chat?agent=system-admin`（而非首页）
3. **必配清单检查** — 进入 system-admin 对话时，前端检查必配项，缺失则自动作为用户消息发送

## 详细设计

### 1. system-admin 名称

修改 `config_example.yml` 中 `agents.system-admin.name` 为 `系统运维管理员`。

### 2. Setup 后跳转

**文件**: `agentos/app/web/app/setup/page.tsx`

将 `router.push('/')` 改为 `router.push('/chat?agent=system-admin')`（两处：完成配置按钮和跳过按钮）。

**文件**: `agentos/app/web/app/chat/page.tsx`

当前 chat 页面不读取 `?agent=` query param。需要添加：
- 读取 `searchParams.get('agent')`
- 如果有值，初始化 `selectedAgentId` 为该值

### 3. 必配清单

#### 3.1 后端 API

**新增端点**: `GET /api/config/required-check`

**文件**: `agentos/interfaces/http/config_api.py`

返回各必配项状态：

```json
{
  "search_tool": {
    "configured": false,
    "message": "搜索工具未配置（serper/brave/baidu/tavily 至少需要配置一个）"
  },
  "email": {
    "configured": false,
    "message": "邮箱未配置（需要配置 SMTP/IMAP 信息）"
  }
}
```

检查逻辑：
- **搜索工具**: 检查 `tools.serper_search.api_key`、`tools.brave_search.api_key`、`tools.baidu_search.api_key`、`tools.tavily_search.api_key` 至少一个有值
- **邮箱**: 检查 `tools.email.enabled == true` 且 `smtp_host`、`username` 有值

#### 3.2 前端自动消息

**文件**: `agentos/app/web/app/chat/page.tsx`

当 `selectedAgentId === 'system-admin'` 且创建新 session 时：
1. 调用 `GET /api/config/required-check`
2. 收集所有 `configured === false` 的项
3. 如果有缺失，拼接消息文本并自动作为用户输入发送：

```
以下系统配置尚未完成，请帮我配置：
1. 搜索工具未配置（serper/brave/baidu/tavily 至少需要配置一个）
2. 邮箱未配置（需要配置 SMTP/IMAP 信息）
```

4. 如果全部已配置，不发送任何自动消息

**触发时机**: 仅在进入 system-admin 且是新 session（无历史消息）时检查一次。切换回已有 session 不重复触发。

## 文件变更清单

| 操作 | 文件 |
|------|------|
| 修改 | `config_example.yml` — system-admin name |
| 修改 | `agentos/app/web/app/setup/page.tsx` — 跳转目标 |
| 修改 | `agentos/app/web/app/chat/page.tsx` — 读取 agent query param + 必配清单检查 |
| 修改 | `agentos/interfaces/http/config_api.py` — 新增 required-check 端点 |
