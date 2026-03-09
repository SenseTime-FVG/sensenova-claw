# 前端架构设计

## 技术栈

- **框架**: Next.js 14+ (App Router)
- **语言**: TypeScript
- **状态管理**: React Context API
- **UI 组件**: shadcn/ui + Tailwind CSS
- **通信**: 原生 WebSocket
- **图标**: Lucide Icons

## 项目结构

```
frontend/
├── app/
│   ├── layout.tsx              # 根布局
│   ├── page.tsx                # 主页面
│   └── globals.css             # 全局样式
├── components/
│   ├── layout/
│   │   ├── TitleBar.tsx        # 标题栏
│   │   ├── ActivityBar.tsx     # 活动栏
│   │   ├── Sidebar.tsx         # 侧边栏
│   │   └── StatusBar.tsx       # 状态栏
│   ├── chat/
│   │   ├── ChatContainer.tsx   # 聊天容器
│   │   ├── MessageList.tsx     # 消息列表
│   │   ├── MessageBubble.tsx   # 消息气泡
│   │   ├── InputArea.tsx       # 输入区域
│   │   └── TypingIndicator.tsx # 输入提示
│   ├── explorer/
│   │   ├── FileTree.tsx        # 文件树
│   │   └── FileItem.tsx        # 文件项
│   └── history/
│       └── SessionList.tsx     # 会话列表
├── contexts/
│   ├── WebSocketContext.tsx    # WebSocket 上下文
│   ├── SessionContext.tsx      # 会话上下文
│   └── UIContext.tsx           # UI 状态上下文
├── hooks/
│   ├── useWebSocket.ts         # WebSocket Hook
│   ├── useSession.ts           # 会话管理 Hook
│   └── useChat.ts              # 聊天功能 Hook
├── types/
│   ├── message.ts              # 消息类型定义
│   ├── session.ts              # 会话类型定义
│   └── websocket.ts            # WebSocket 类型定义
└── lib/
    ├── websocket.ts            # WebSocket 客户端
    └── utils.ts                # 工具函数
```

## 核心组件设计

### 主布局 (MainLayout)

```typescript
export default function MainLayout() {
    return (
        <div className="flex flex-col h-screen bg-[#09090b]">
            <TitleBar />
            <div className="flex flex-1 overflow-hidden">
                <ActivityBar />
                <Sidebar />
                <ChatContainer />
            </div>
            <StatusBar />
        </div>
    );
}
```

### 聊天容器 (ChatContainer)

负责展示对话内容和处理用户输入。

**状态管理**:
- `messages`: 当前会话的消息列表
- `isTyping`: Agent 是否正在输入
- `toolExecutions`: 正在执行的工具列表

**功能**:
- 渲染消息列表
- 处理用户输入
- 显示工具执行状态
- 自动滚动到底部

### 消息气泡 (MessageBubble)

根据消息类型渲染不同样式。

**消息类型**:
- `user`: 用户消息（右侧，蓝色背景）
- `assistant`: AI 消息（左侧，灰色背景）
- `tool`: 工具执行结果（特殊样式）
- `system`: 系统提示（居中，小字）

**支持的内容格式**:
- 纯文本
- Markdown
- 代码块（带语法高亮）
- 工具调用卡片

## 状态管理

### WebSocketContext

管理 WebSocket 连接和消息收发。

```typescript
interface WebSocketContextType {
    isConnected: boolean;
    send: (message: any) => void;
    lastMessage: any;
}

export function WebSocketProvider({ children }) {
    const [isConnected, setIsConnected] = useState(false);
    const [lastMessage, setLastMessage] = useState(null);
    const wsRef = useRef<WebSocket | null>(null);

    useEffect(() => {
        const ws = new WebSocket('ws://localhost:8000/ws');

        ws.onopen = () => setIsConnected(true);
        ws.onmessage = (event) => {
            setLastMessage(JSON.parse(event.data));
        };
        ws.onclose = () => setIsConnected(false);

        wsRef.current = ws;

        return () => ws.close();
    }, []);

    const send = (message: any) => {
        if (wsRef.current?.readyState === WebSocket.OPEN) {
            wsRef.current.send(JSON.stringify(message));
        }
    };

    return (
        <WebSocketContext.Provider value={{ isConnected, send, lastMessage }}>
            {children}
        </WebSocketContext.Provider>
    );
}
```

### SessionContext

管理当前会话状态。

```typescript
interface SessionContextType {
    currentSession: Session | null;
    sessions: Session[];
    createSession: () => void;
    loadSession: (sessionId: string) => void;
    messages: Message[];
    addMessage: (message: Message) => void;
}
```

### UIContext

管理 UI 状态（侧边栏展开、主题等）。

```typescript
interface UIContextType {
    sidebarView: 'explorer' | 'history';
    setSidebarView: (view: string) => void;
    theme: 'dark' | 'light';
}
```

## 自定义 Hooks

### useWebSocket

封装 WebSocket 通信逻辑。

```typescript
export function useWebSocket() {
    const { send, lastMessage } = useContext(WebSocketContext);

    const sendUserInput = (content: string) => {
        send({
            type: 'user_input',
            session_id: currentSessionId,
            payload: { content },
            timestamp: Date.now()
        });
    };

    return { sendUserInput, lastMessage };
}
```

### useChat

管理聊天功能。

```typescript
export function useChat(sessionId: string) {
    const [messages, setMessages] = useState<Message[]>([]);
    const [isTyping, setIsTyping] = useState(false);
    const { lastMessage } = useWebSocket();

    useEffect(() => {
        if (!lastMessage) return;

        switch (lastMessage.type) {
            case 'agent_thinking':
                setIsTyping(true);
                break;
            case 'agent_response':
                addAssistantMessage(lastMessage.payload.content);
                if (lastMessage.payload.is_final) {
                    setIsTyping(false);
                }
                break;
            case 'turn_completed':
                setIsTyping(false);
                break;
        }
    }, [lastMessage]);

    return { messages, isTyping };
}
```

## 类型定义

### Message 类型

```typescript
interface Message {
    id: string;
    role: 'user' | 'assistant' | 'tool' | 'system';
    content: string;
    timestamp: number;
    toolCalls?: ToolCall[];
    toolResults?: ToolResult[];
}

interface ToolCall {
    id: string;
    name: string;
    arguments: Record<string, any>;
}

interface ToolResult {
    toolCallId: string;
    result: any;
    success: boolean;
}
```

### Session 类型

```typescript
interface Session {
    sessionId: string;
    createdAt: number;
    lastActive: number;
    meta: {
        title: string;
        tags?: string[];
        model?: string;
    };
}
```

## 样式设计

### VS Code 风格配色

```css
:root {
    --bg-primary: #09090b;
    --bg-secondary: #18181b;
    --bg-tertiary: #27272a;
    --border-color: #3f3f46;
    --text-primary: #e4e4e7;
    --text-secondary: #a1a1aa;
    --accent-blue: #3b82f6;
    --accent-hover: #2563eb;
}
```

### 自定义滚动条

```css
.custom-scrollbar::-webkit-scrollbar {
    width: 10px;
}

.custom-scrollbar::-webkit-scrollbar-track {
    background: transparent;
}

.custom-scrollbar::-webkit-scrollbar-thumb {
    background: var(--bg-tertiary);
    border-radius: 5px;
}
```
