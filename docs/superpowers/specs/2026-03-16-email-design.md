# AgentOS 邮件收发功能设计文档

**日期**: 2026-03-16
**版本**: 1.0
**状态**: 设计阶段

## 1. 背景与目标

### 1.1 背景

用户希望在 AgentOS 框架中实现邮件收发功能，使 AI Agent 能够：
- 自动发送通知邮件（任务完成、定时报告等）
- 处理收到的邮件（读取客户邮件并自动回复、处理工单等）
- 通过对话让 Agent 收发邮件（用户说"帮我发封邮件给张三"）

### 1.2 目标

实现完整的邮件自动化能力，支持：
- ✅ 发送邮件（纯文本/HTML、附件、抄送）
- ✅ 接收邮件（列出、读取、搜索）
- ✅ 附件管理（上传、下载）
- ✅ 邮件操作（标记已读/未读、删除）
- ✅ 通用邮箱支持（Gmail、Outlook、QQ 等）

### 1.3 技术选型

**选择方案：Python 标准库（SMTP/IMAP）**

理由：
- 零额外依赖（`smtplib`、`imaplib`、`email` 都是标准库）
- 通用性强（支持所有邮件服务商）
- 配置简单（仅需账号密码）
- 符合 AgentOS 最小化原则

---

## 2. 架构设计

### 2.1 整体架构

```
用户/Agent 请求
    ↓
AgentRuntime (决策调用哪个工具)
    ↓
ToolRuntime (发布事件: tool.call_requested)
    ↓
ToolSessionWorker (执行工具)
    ↓
EmailTool (使用 smtplib/imaplib)
    ↓
邮件服务器 (SMTP/IMAP)
```

### 2.2 事件流

```
用户输入: "帮我发邮件给 test@example.com"
  ↓
ui.user_input
  ↓
agent.step_started
  ↓
llm.call_requested → llm.call_completed (决策调用 send_email)
  ↓
tool.call_requested (send_email)
  ↓
tool.call_started
  ↓
[执行 SMTP 发送]
  ↓
tool.call_result
  ↓
tool.call_completed
  ↓
llm.call_requested → llm.call_completed (生成回复)
  ↓
agent.step_completed
```

---

## 3. 工具设计

### 3.1 工具列表

| 工具名 | 风险等级 | 功能 |
|--------|---------|------|
| `send_email` | MEDIUM | 发送邮件（支持附件、HTML、抄送） |
| `list_emails` | LOW | 列出邮件（支持过滤：未读、发件人、主题、日期） |
| `read_email` | LOW | 读取邮件完整内容 |
| `download_attachment` | MEDIUM | 下载邮件附件到本地 |
| `mark_email` | MEDIUM | 标记邮件（已读/未读/删除） |
| `search_emails` | LOW | 搜索邮件（关键词、日期范围） |

### 3.2 SendEmailTool（发送邮件）

**参数：**
```python
{
    "type": "object",
    "properties": {
        "to": {
            "type": "array",
            "items": {"type": "string"},
            "description": "收件人邮箱列表"
        },
        "subject": {
            "type": "string",
            "description": "邮件主题"
        },
        "body": {
            "type": "string",
            "description": "邮件正文"
        },
        "cc": {
            "type": "array",
            "items": {"type": "string"},
            "description": "抄送列表（可选）"
        },
        "attachments": {
            "type": "array",
            "items": {"type": "string"},
            "description": "附件文件路径列表（可选）"
        },
        "html": {
            "type": "boolean",
            "default": false,
            "description": "是否为 HTML 格式"
        }
    },
    "required": ["to", "subject", "body"]
}
```

**核心逻辑：**
1. 从 config 读取 SMTP 配置（smtp_host, smtp_port, username, password）
2. 构建 MIME 邮件对象（MIMEMultipart）
3. 附件路径通过 `_path_policy` 检查（仅允许 workspace/已授权目录）
4. 附件大小限制（默认 10MB）
5. 使用 `asyncio.to_thread()` 异步执行 SMTP 发送

**返回：**
```python
{
    "success": true,
    "to": ["test@example.com"],
    "subject": "测试邮件",
    "message": "邮件发送成功"
}
```

**风险等级：** MEDIUM（发送邮件有副作用，但不修改本地文件）

---

### 3.3 ListEmailsTool（列出邮件）

**参数：**
```python
{
    "type": "object",
    "properties": {
        "folder": {
            "type": "string",
            "default": "INBOX",
            "description": "邮箱文件夹（INBOX/Sent/Drafts）"
        },
        "limit": {
            "type": "integer",
            "default": 10,
            "description": "返回邮件数量"
        },
        "unread_only": {
            "type": "boolean",
            "default": false,
            "description": "仅显示未读邮件"
        },
        "from_email": {
            "type": "string",
            "description": "按发件人过滤"
        },
        "subject_contains": {
            "type": "string",
            "description": "主题包含关键词"
        },
        "since_date": {
            "type": "string",
            "description": "起始日期（YYYY-MM-DD）"
        }
    },
    "required": []
}
```

**返回：**
```python
{
    "success": true,
    "folder": "INBOX",
    "count": 5,
    "emails": [
        {
            "id": "123",
            "from": "sender@example.com",
            "subject": "测试邮件",
            "date": "2026-03-16 10:30:00",
            "preview": "邮件正文预览前200字..."
        }
    ]
}
```

**核心逻辑：**
1. 连接 IMAP 服务器（使用 `imaplib.IMAP4_SSL`）
2. 选择文件夹（默认 INBOX）
3. 构建搜索条件（UNSEEN、FROM、SUBJECT、SINCE）
4. 获取最新 N 封邮件
5. 解析邮件头（From、Subject、Date）
6. 提取正文预览（前 200 字符）

**风险等级：** LOW（只读操作）

---

### 3.4 ReadEmailTool（读取邮件详情）

**参数：**
```python
{
    "type": "object",
    "properties": {
        "email_id": {
            "type": "string",
            "description": "邮件 ID（从 list_emails 获取）"
        },
        "folder": {
            "type": "string",
            "default": "INBOX",
            "description": "邮箱文件夹"
        },
        "mark_as_read": {
            "type": "boolean",
            "default": true,
            "description": "是否标记为已读"
        }
    },
    "required": ["email_id"]
}
```

**返回：**
```python
{
    "success": true,
    "email": {
        "id": "123",
        "from": "sender@example.com",
        "to": ["me@example.com"],
        "subject": "测试邮件",
        "date": "2026-03-16 10:30:00",
        "body": "完整邮件正文内容...",
        "attachments": [
            {"filename": "file.pdf", "size_kb": 256}
        ]
    }
}
```

**风险等级：** LOW（只读操作）

---

### 3.5 DownloadAttachmentTool（下载附件）

**参数：**
```python
{
    "type": "object",
    "properties": {
        "email_id": {
            "type": "string",
            "description": "邮件 ID"
        },
        "attachment_filename": {
            "type": "string",
            "description": "附件文件名"
        },
        "save_path": {
            "type": "string",
            "description": "保存路径"
        },
        "folder": {
            "type": "string",
            "default": "INBOX"
        }
    },
    "required": ["email_id", "attachment_filename", "save_path"]
}
```

**安全机制：**
- `save_path` 通过 PathPolicy 检查
- 仅允许保存到 workspace 或已授权目录

**风险等级：** MEDIUM（写入文件）

---

### 3.6 MarkEmailTool（标记邮件）

**参数：**
```python
{
    "type": "object",
    "properties": {
        "email_id": {
            "type": "string",
            "description": "邮件 ID"
        },
        "action": {
            "type": "string",
            "enum": ["read", "unread", "delete"],
            "description": "操作类型"
        },
        "folder": {
            "type": "string",
            "default": "INBOX"
        }
    },
    "required": ["email_id", "action"]
}
```

**风险等级：** MEDIUM（修改邮件状态）

---

### 3.7 SearchEmailsTool（搜索邮件）

**参数：**
```python
{
    "type": "object",
    "properties": {
        "query": {
            "type": "string",
            "description": "搜索关键词"
        },
        "folder": {
            "type": "string",
            "default": "INBOX"
        },
        "since_date": {
            "type": "string",
            "description": "起始日期（YYYY-MM-DD）"
        },
        "limit": {
            "type": "integer",
            "default": 20
        }
    },
    "required": ["query"]
}
```

**风险等级：** LOW（只读操作）

---

## 4. 配置设计

### 4.1 config.yml 配置结构

```yaml
tools:
  email:
    enabled: true

    # SMTP 发送配置
    smtp_host: smtp.gmail.com
    smtp_port: 587

    # IMAP 接收配置
    imap_host: imap.gmail.com
    imap_port: 993

    # 认证信息（支持环境变量）
    username: ${EMAIL_USERNAME}
    password: ${EMAIL_PASSWORD}

    # 安全限制
    max_attachment_size_mb: 10
    timeout: 30
```

### 4.2 常见邮箱预设

| 服务商 | SMTP 服务器 | IMAP 服务器 |
|--------|------------|------------|
| Gmail | smtp.gmail.com:587 | imap.gmail.com:993 |
| Outlook | smtp-mail.outlook.com:587 | outlook.office365.com:993 |
| QQ 邮箱 | smtp.qq.com:587 | imap.qq.com:993 |
| 163 邮箱 | smtp.163.com:465 | imap.163.com:993 |

### 4.3 DEFAULT_CONFIG

```python
"email": {
    "enabled": False,  # 默认禁用，需用户配置后启用
    "smtp_host": "",
    "smtp_port": 587,
    "imap_host": "",
    "imap_port": 993,
    "username": "${EMAIL_USERNAME}",
    "password": "${EMAIL_PASSWORD}",
    "max_attachment_size_mb": 10,
    "timeout": 30,
}
```

---

## 5. 安全机制

### 5.1 密码保护

- 使用环境变量 `${EMAIL_PASSWORD}`，不直接写入 config.yml
- ToolRuntime 记录日志时自动过滤 `password` 字段
- 文档提醒用户使用应用专用密码（而非账号密码）

### 5.2 附件安全

**上传附件（send_email）：**
- 通过 `_path_policy` 检查附件路径
- 仅允许读取 workspace 或已授权目录的文件
- 大小限制：默认 10MB（可配置）

**下载附件（download_attachment）：**
- 通过 `_path_policy` 检查保存路径
- 仅允许保存到 workspace 或已授权目录

### 5.3 超时控制

- SMTP/IMAP 操作默认超时 30 秒
- 使用 `asyncio.wait_for()` 包装

### 5.4 风险等级

- **LOW**: list_emails, read_email, search_emails（只读操作）
- **MEDIUM**: send_email, download_attachment, mark_email（有副作用）

---

## 6. 错误处理

### 6.1 配置缺失

```python
if not all([smtp_host, username, password]):
    return {"success": False, "error": "邮件配置不完整，请检查 config.yml"}
```

### 6.2 认证失败

```python
except smtplib.SMTPAuthenticationError:
    return {"success": False, "error": "邮箱认证失败，请检查用户名和密码"}
```

### 6.3 网络超时

```python
except asyncio.TimeoutError:
    return {"success": False, "error": "连接邮件服务器超时"}
```

### 6.4 附件过大

```python
if file_size > max_size:
    return {"success": False, "error": f"附件超过 {max_size_mb}MB 限制"}
```

### 6.5 路径未授权

```python
if verdict != PathVerdict.ALLOW:
    return {"success": False, "error": f"路径未授权: {file_path}"}
```

---

## 7. 测试策略

### 7.1 单元测试（tests/unit/test_email_tools.py）

- 工具注册验证
- 参数 schema 验证
- 配置缺失时的错误处理
- 附件大小限制逻辑

### 7.2 集成测试（tests/integration/test_email_integration.py）

- 工具与 PathPolicy 集成
- 附件路径安全检查
- 超时控制

### 7.3 E2E 测试（tests/e2e/test_email_e2e.py）

- 使用真实邮箱账号
- 完整流程：发送 → 列出 → 读取 → 下载附件
- 需要环境变量：`EMAIL_USERNAME`, `EMAIL_PASSWORD`

**测试命令：**
```bash
# 单元测试
python3 -m pytest tests/unit/test_email_tools.py -v

# 集成测试
python3 -m pytest tests/integration/test_email_integration.py -v

# E2E 测试（需真实邮箱）
export EMAIL_USERNAME=test@gmail.com
export EMAIL_PASSWORD=your-app-password
python3 -m pytest tests/e2e/test_email_e2e.py -v
```

---

## 8. 文件结构

### 8.1 新增文件

```
agentos/capabilities/tools/email.py          # 6 个工具类实现
tests/unit/test_email_tools.py              # 单元测试
tests/integration/test_email_integration.py # 集成测试
tests/e2e/test_email_e2e.py                 # E2E 测试
docs/superpowers/specs/2026-03-16-email-design.md  # 本设计文档
```

### 8.2 修改文件

```
agentos/capabilities/tools/registry.py       # 注册 6 个工具
agentos/platform/config/config.py            # 添加 email 配置到 DEFAULT_CONFIG
CLAUDE.md                                    # 添加邮件工具使用说明
```

---

## 9. 使用示例

### 9.1 发送邮件

```
用户: 帮我发一封邮件给 test@example.com，主题是"测试邮件"，内容是"这是一封测试邮件"
Agent: [调用 send_email 工具]
      参数: {
        "to": ["test@example.com"],
        "subject": "测试邮件",
        "body": "这是一封测试邮件"
      }
      返回: {"success": true, "message": "邮件发送成功"}
Agent: 邮件已成功发送给 test@example.com
```

### 9.2 列出邮件

```
用户: 列出我的收件箱最新 5 封邮件
Agent: [调用 list_emails 工具]
      参数: {"limit": 5}
      返回: {
        "success": true,
        "emails": [
          {"id": "123", "from": "sender@example.com", "subject": "测试", ...}
        ]
      }
Agent: 您的收件箱有 5 封邮件：
      1. 来自 sender@example.com - 测试
      2. ...
```

### 9.3 读取邮件

```
用户: 读取第一封邮件的详细内容
Agent: [调用 read_email 工具]
      参数: {"email_id": "123"}
      返回: {
        "success": true,
        "email": {
          "from": "sender@example.com",
          "subject": "测试",
          "body": "完整正文...",
          "attachments": [{"filename": "file.pdf", "size_kb": 256}]
        }
      }
Agent: 邮件详情：
      发件人: sender@example.com
      主题: 测试
      正文: 完整正文...
      附件: file.pdf (256 KB)
```

### 9.4 下载附件

```
用户: 下载第一封邮件的附件到 workspace
Agent: [调用 download_attachment 工具]
      参数: {
        "email_id": "123",
        "attachment_filename": "file.pdf",
        "save_path": "/workspace/downloads/file.pdf"
      }
      返回: {"success": true, "saved_path": "/workspace/downloads/file.pdf"}
Agent: 附件已保存到 /workspace/downloads/file.pdf
```

---

## 10. 实现优先级

### 10.1 第一阶段（核心功能）

- ✅ SendEmailTool（发送纯文本邮件）
- ✅ ListEmailsTool（列出收件箱）
- ✅ ReadEmailTool（读取邮件详情）

### 10.2 第二阶段（增强功能）

- ✅ DownloadAttachmentTool（下载附件）
- ✅ MarkEmailTool（标记邮件）
- ✅ SearchEmailsTool（搜索邮件）

### 10.3 后续增强（可选）

- 邮件模板支持
- HTML 邮件富文本编辑
- 邮件草稿管理
- 邮件转发/回复

---

## 11. 预估工作量

- 工具实现: 4-5 小时
- 测试编写: 2-3 小时
- 文档更新: 1 小时
- **总计**: 7-9 小时

---

## 12. 风险与限制

### 12.1 风险

- **应用专用密码**：现代邮箱服务商（Gmail、Outlook）需要生成应用专用密码，用户可能不熟悉
- **IMAP 限制**：部分邮箱服务商对 IMAP 连接频率有限制
- **附件大小**：大附件可能导致内存占用过高

### 12.2 限制

- 不支持 OAuth 认证（仅支持用户名密码）
- 不支持邮件实时推送（需要主动调用 list_emails）
- 不支持邮件加密（PGP/S/MIME）

---

## 13. 后续优化方向

- 支持 OAuth 认证（Gmail API）
- 支持邮件实时推送（IMAP IDLE）
- 支持邮件模板系统
- 支持邮件批量操作
