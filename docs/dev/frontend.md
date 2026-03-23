# 前端架构

Sensenova-Claw 前端基于 Next.js 14 App Router 构建，采用 WebSocket 实时通信与后端事件系统对接。

## 技术栈

| 技术 | 用途 |
|------|------|
| Next.js 14 | App Router 框架 |
| TypeScript | 类型安全 |
| Tailwind CSS 3.4 | 样式 |
| Radix UI | 基础组件 |
| lucide-react | 图标 |
| 原生 WebSocket API | 实时通信 |
| React Context API | 状态管理 |
| Playwright | E2E 测试 |

## 目录结构

```
sensenova_claw/app/web/
├── app/                     # Next.js App Router 路由
│   ├── layout.tsx           # 根布局
│   ├── page.tsx             # 首页（重定向到 /agents）
│   ├── chat/page.tsx        # 聊天界面（核心页面）
│   ├── agents/              # Agent 管理
│   ├── sessions/            # 会话管理
│   ├── tools/               # 工具配置
│   ├── skills/              # Skills 市场
│   └── gateway/             # 网关配置
├── components/
│   ├── chat/                # 聊天组件
│   │   ├── ChatContainer.tsx
│   │   ├── InputArea.tsx
│   │   ├── MessageBubble.tsx
│   │   ├── MessageList.tsx
│   │   ├── TypingIndicator.tsx
│   │   └── SlashCommandMenu.tsx
│   ├── layout/              # 布局组件
│   │   ├── DashboardLayout.tsx
│   │   ├── DashboardNav.tsx
│   │   ├── Sidebar.tsx
│   │   └── StatusBar.tsx
│   └── ui/                  # 基础 UI 组件
├── contexts/                # React Context
│   ├── WebSocketContext.tsx  # WS 连接管理
│   ├── SessionContext.tsx   # 会话与消息状态
│   └── UIContext.tsx        # UI 状态
├── hooks/                   # 自定义 Hook
├── lib/                     # 工具函数
└── types/                   # TypeScript 类型定义
```

## 核心类型定义

### Message

```typescript
type MessageRole = 'user' | 'assistant' | 'tool' | 'system';

interface ToolInfo {
  name: string;
  arguments: Record<string, any>;
  result?: any;
  success?: boolean;
  error?: string;
  status: 'running' | 'completed';
}

interface Message {
  id: string;
  role: MessageRole;
  content: string;
  timestamp: number;
  toolInfo?: ToolInfo;      // 工具调用信息（仅 tool 角色）
}
```

### WebSocket 消息

```typescript
interface WsMessage {
  type: string;
  session_id?: string;
  payload: Record<string, unknown>;
  timestamp: number;
}
```

### Session

```typescript
interface Session {
  session_id: string;
  created_at: number;
  last_active: number;
  meta?: { title?: string; model?: string };
}
```

## 状态管理（三层 Context）

### WebSocketContext — 连接层

负责底层 WebSocket 连接：

- 自动重连（3 秒间隔，最多 10 次）
- 连接状态管理（`isConnected`）
- JSON 消息解析
- 清理（组件卸载时关闭连接）

```typescript
// 提供的接口
{
  isConnected: boolean;
  lastMessage: WsMessage | null;
  send: (message: object) => void;
}
```

### SessionContext — 业务层

管理会话和消息状态：

- 消息列表维护
- 工具调用 ID → 消息 ID 映射（`toolCallMapRef`）
- 会话历史重建（从后端事件流）
- 打字状态（`isTyping`）

```typescript
// 提供的接口
{
  sessionId: string | null;
  messages: Message[];
  isTyping: boolean;
  createSession: () => Promise<void>;
  sendUserInput: (content: string) => void;
  switchSession: (id: string) => void;
  startNewChat: () => void;
}
```

### UIContext — 展示层

管理 UI 状态（侧边栏视图切换等）。

## 事件处理流程

前端通过 WebSocket 接收后端推送的事件，根据 `type` 字段分发处理：

| 后端事件 | 前端处理 |
|----------|---------|
| `session_created` | 设置 sessionId，发送待输入内容 |
| `agent_thinking` | 显示加载动画（isTyping=true） |
| `llm_result` | 添加 assistant 消息 |
| `tool_execution` | 添加 tool 消息（status=running），记录映射 |
| `tool_result` | 更新 tool 消息（填入结果，status=completed） |
| `turn_completed` | 添加最终响应，停止加载（isTyping=false） |
| `title_updated` | 更新侧边栏会话标题 |
| `error` | 添加错误消息，停止加载 |
| `notification` | 添加系统通知消息 |

**工具调用追踪**：通过 `toolCallMapRef` 维护 `tool_call_id → message_id` 的映射。当收到 `tool_result` 时，根据 `tool_call_id` 找到对应消息并更新结果。

## 用户交互流程

```
用户输入消息
  │
  ├─ 无 sessionId → createSession() → 等待 session_created → 再发送
  └─ 有 sessionId → sendUserInput()
       │
       └─ WebSocket 发送:
          {type: "user_input", session_id: "xxx", payload: {content: "..."}}
              │
              └─ 等待后端事件推送 → 逐步更新 UI
```

## Slash Commands

输入 `/` 触发命令菜单，从 `/api/skills` 加载已启用的 Skills 列表：

- 输入 `/skill名称 参数` 调用指定 Skill
- 通过 `POST /api/sessions/{sessionId}/skill-invoke` 执行

## 调用的后端 API

| 端点 | 用途 |
|------|------|
| `GET /api/sessions` | 列出会话历史 |
| `POST /api/sessions` | 创建新会话 |
| `GET /api/sessions/{id}/events` | 获取事件流（重建历史） |
| `GET /api/agents` | 列出 Agent |
| `GET /api/tools` | 列出工具 |
| `PUT /api/tools/{name}/enabled` | 切换工具启用状态 |
| `GET /api/skills` | 列出 Skills |

## UI 主题

采用 VS Code 风格深色主题：

- 背景色：`#1e1e1e`
- 次级背景：`#2d2d30`
- 强调色：`#007acc`
- 文本色：`#cccccc`
- 状态指示：绿色/黄色/红色圆点

## 关键实现细节

- `MessageBubble` 对超过 500 字符的内容支持折叠/展开
- 工具结果截断上限 50KB
- 输入框支持 Enter 发送、Shift+Enter 换行，自动调整高度（最大 120px）
- 会话切换时通过 HTTP 拉取事件流重建消息历史（非 WebSocket 回放）
