# 启动与关闭流程

## 启动流程

AgentOS 的启动入口位于 `app/gateway/main.py`，按照以下顺序初始化和启动各组件。

### 第一阶段：初始化核心服务

```
1. Repository(SQLite)      ← 数据库连接和表结构初始化
2. PublicEventBus           ← 全局事件总线
3. EventPublisher           ← 事件发布辅助工具
4. BusRouter                ← 事件路由器（连接 Public 和 Private 总线）
5. EventPersister           ← 事件持久化订阅者
```

这些是系统最基础的组件，其他所有模块都依赖它们。

### 第二阶段：初始化注册表

```
6. ToolRegistry             ← 注册内置工具（bash_command, serper_search, brave_search, baidu_search, tavily_search, fetch_url, read_file, write_file）
7. SkillRegistry            ← 加载 workspace/ 和内置 skills
8. AgentRegistry            ← 加载 config.yml 中的 agent 配置 + workspace/agents/ 目录
```

注册表负责管理可用的工具、Skills 和 Agent 配置。

### 第三阶段：初始化上下文与状态

```
9.  ContextBuilder          ← 构建 LLM 调用的上下文（系统提示 + 工具 + 记忆 + 历史）
10. MemoryManager           ← 管理 MEMORY.md 的读写
11. SessionStateStore       ← 内存状态管理
```

### 第四阶段：启动 Runtime（按顺序）

启动顺序有严格要求，因为后启动的 Runtime 可能依赖先启动的 Runtime 所创建的基础设施。

```
12. EventPersister.start()    ← 开始持久化事件（最先启动，确保不丢事件）
13. BusRouter.start()         ← 开始路由事件
14. AgentRuntime.start()      ← 注册 AgentSessionWorker factory
15. LLMRuntime.start()        ← 注册 LLMSessionWorker factory
16. ToolRuntime.start()       ← 注册 ToolSessionWorker factory
17. TitleRuntime.start()      ← 订阅 agent.step_completed，生成标题
18. Gateway.start()           ← 启动 WebSocket 网关
19. CronRuntime.start()       ← 启动定时任务调度
20. HeartbeatRuntime.start()  ← 启动心跳检测
```

### 第五阶段：注册 Channel 和加载插件

```
21. 注册 WebSocketChannel     ← 内置 WebSocket 接入
22. 注册 FeishuChannel        ← 如果飞书插件可用
23. PluginRegistry.load_plugins()  ← 加载所有已注册插件
```

### 启动时序图

```
时间 ──────────────────────────────────────────────────────►

[核心服务]
  Repository ─────┐
  PublicEventBus ─┤
  EventPublisher ─┤
  BusRouter ──────┤
  EventPersister ─┘
                    [注册表]
                    ToolRegistry ───┐
                    SkillRegistry ──┤
                    AgentRegistry ──┘
                                     [上下文/状态]
                                     ContextBuilder ─────┐
                                     MemoryManager ──────┤
                                     SessionStateStore ──┘
                                                          [Runtime 启动]
                                                          EventPersister.start()
                                                          BusRouter.start()
                                                          AgentRuntime.start()
                                                          LLMRuntime.start()
                                                          ToolRuntime.start()
                                                          TitleRuntime.start()
                                                          Gateway.start()
                                                          CronRuntime.start()
                                                          HeartbeatRuntime.start()
                                                                                  [Channel/插件]
                                                                                  WebSocketChannel
                                                                                  FeishuChannel
                                                                                  Plugins
```

---

## 关闭流程

关闭流程与启动顺序**相反**，确保依赖关系正确释放。

```
1. 停止插件和 Channel
   ├── PluginRegistry.unload()
   ├── FeishuChannel.close()
   └── WebSocketChannel.close()

2. 停止 Runtime（反向顺序）
   ├── HeartbeatRuntime.stop()
   ├── CronRuntime.stop()
   ├── Gateway.stop()
   ├── TitleRuntime.stop()
   ├── ToolRuntime.stop()
   ├── LLMRuntime.stop()
   ├── AgentRuntime.stop()
   ├── BusRouter.stop()
   └── EventPersister.stop()    ← 最后停止，确保所有事件都已持久化

3. 清理资源
   ├── SessionStateStore.clear()
   ├── PublicEventBus.close()
   └── Repository.close()       ← 关闭数据库连接
```

### 优雅关闭的关键点

- **EventPersister 最后停止**：确保关闭过程中产生的事件也能被持久化
- **BusRouter 在 Runtime 之后停止**：确保 Runtime 的停止事件能被正确路由
- **Gateway 在 Runtime 之前停止**：阻止新的用户请求进入，但允许正在处理的请求完成
- **PrivateEventBus 由 BusRouter 统一回收**：不需要单独关闭每个 session 的总线
