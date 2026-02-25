# Driver Layer 技术架构设计

## 层目标
Driver Layer 负责把 AgentOS 的外部动作抽象为可控、可审计、可回放的执行能力。该层是 Runtime 与真实世界（文件系统、浏览器、Office、沙箱）的唯一桥梁。

目标：
- 提供统一工具执行契约，屏蔽不同驱动差异
- 强制执行前后策略校验与审计事件记录
- 支持本地直连与沙箱执行双路径
- 为崩溃恢复提供事件回放基础

## 模块清单
- `EventBus`：统一事件发布、订阅、回放
- `ToolRuntime`：工具注册、执行编排、生命周期管理
- `SandboxAdapter`：沙箱创建/执行/销毁、资源限制
- `LocalDrivers`：FS/Browser/Office 等具体驱动实现
- `AgentProcessManager`：Agent 工作者进程心跳、重启、隔离

## 核心接口

### 1) EventBus

`EventBus.publish(event: DriverEventEnvelope) -> PublishAck`
- Caller: `ToolRuntime.execute`, `ToolRuntime.post_check`, `SessionManager.run_turn`, `AppGateway`
- Callee: `ObservabilityService.record_event`, `AuditStore.append`, `RealtimeEventClient.push`
- 前置条件: `event.event_id` 全局唯一；`session_id/trace_id/span_id` 已填充
- 返回值: `PublishAck { accepted: bool, persisted: bool, offset: string }`
- 错误码: `EVENT_DUPLICATE`, `EVENT_SCHEMA_INVALID`, `BUS_UNAVAILABLE`
- 重试策略: `BUS_UNAVAILABLE` 指数退避重试 3 次
- 幂等键: `event.event_id`

`EventBus.subscribe(topic: string, handler_ref: string) -> Subscription`
- Caller: `RealtimeEventClient.subscribe_session`, `SessionRecoveryService.start_watch`
- Callee: `EventDispatcher.register_handler`
- 前置条件: topic 存在且 handler 已注册
- 返回值: `Subscription { id, topic, status }`
- 错误码: `TOPIC_NOT_FOUND`, `HANDLER_INVALID`
- 重试策略: 不自动重试（配置问题）
- 幂等键: `topic + handler_ref`

`EventBus.replay(session_id: string, from_checkpoint: string) -> ReplayStreamRef`
- Caller: `SessionManager.recover`
- Callee: `AuditStore.query`
- 前置条件: 会话存在，checkpoint 合法
- 返回值: `ReplayStreamRef { stream_id, total_events, checkpoint }`
- 错误码: `SESSION_NOT_FOUND`, `CHECKPOINT_INVALID`
- 重试策略: `BUS_UNAVAILABLE` 时重试 2 次
- 幂等键: `session_id + from_checkpoint`

### 2) ToolRuntime

`ToolRuntime.register(tool_schema: ToolSchema) -> RegisterAck`
- Caller: `ToolManager.bootstrap`, `DriverBootstrap.init`
- Callee: `ToolRegistry.upsert`
- 前置条件: schema 通过校验（权限、超时、风险级别）
- 返回值: `RegisterAck { tool_name, version, status }`
- 错误码: `TOOL_SCHEMA_INVALID`, `TOOL_CONFLICT`
- 重试策略: 不重试
- 幂等键: `tool_name + version`

`ToolRuntime.execute(call_request: ToolCallRequest) -> ToolCallResult`
- Caller: `ToolManager.execute_tool`, `SessionManager.run_turn`
- Callee: `PolicyEngine.evaluate`, `SandboxAdapter.exec` 或 `LocalDrivers.*`, `EventBus.publish`
- 前置条件: 工具已注册，预算已预留，权限通过
- 返回值: `ToolCallResult`
- 错误码: `POLICY_DENIED`, `TOOL_TIMEOUT`, `TOOL_RUNTIME_ERROR`, `SANDBOX_UNAVAILABLE`
- 重试策略: 
  - `TOOL_TIMEOUT`：最多 2 次，指数退避
  - `TOOL_RUNTIME_ERROR`：按 `ToolSchema.retry_policy`
  - `POLICY_DENIED`：不重试，转人工确认或重规划
- 幂等键: `call_id`

`ToolRuntime.post_check(call_result: ToolCallResult) -> PostCheckAck`
- Caller: `ToolRuntime.execute`
- Callee: `PolicyEngine.evaluate`(输出检查), `WorkspaceManager.persist_output`, `EventBus.publish`
- 前置条件: call_result 状态已落定（succeeded/failed/cancelled）
- 返回值: `PostCheckAck { status, artifact_ref? }`
- 错误码: `OUTPUT_POLICY_DENIED`, `ARTIFACT_PERSIST_FAILED`
- 重试策略: 仅对落盘失败重试 1 次
- 幂等键: `call_id + result_hash`

### 3) SandboxAdapter

`SandboxAdapter.create(profile: SandboxProfile) -> SandboxRef`
- Caller: `ToolRuntime.execute`, `SessionManager.prepare_isolated_step`
- Callee: `SandboxPool.allocate`
- 前置条件: profile 有资源上限与挂载目录白名单
- 返回值: `SandboxRef { sandbox_id, endpoint, ttl }`
- 错误码: `SANDBOX_RESOURCE_EXHAUSTED`, `SANDBOX_PROFILE_INVALID`
- 重试策略: 资源不足时排队重试 1 次
- 幂等键: `session_id + profile.profile_name + span_id`

`SandboxAdapter.exec(job: SandboxJob) -> SandboxExecResult`
- Caller: `ToolRuntime.execute`
- Callee: `SandboxRuntime.invoke`
- 前置条件: sandbox 存活、job 已签名
- 返回值: `SandboxExecResult { exit_code, stdout_ref, stderr_ref, output_ref }`
- 错误码: `SANDBOX_TIMEOUT`, `SANDBOX_CRASHED`
- 重试策略: `SANDBOX_CRASHED` 自动切换新沙箱重试 1 次
- 幂等键: `job.job_id`

`SandboxAdapter.destroy(sandbox_id: string) -> DestroyAck`
- Caller: `ToolRuntime.execute.finally`, `SessionManager.cleanup`
- Callee: `SandboxPool.release`
- 前置条件: sandbox_id 存在
- 返回值: `DestroyAck { released: bool }`
- 错误码: `SANDBOX_NOT_FOUND`
- 重试策略: 不重试
- 幂等键: `sandbox_id`

### 4) LocalDrivers

`LocalDriverFS.read(input: FSReadInput) -> FSReadOutput`
- Caller: `ToolRuntime.execute`
- Callee: OS 文件系统 API
- 前置条件: path 在白名单
- 返回值: 文件内容引用或摘要
- 错误码: `FS_PERMISSION_DENIED`, `FS_NOT_FOUND`
- 重试策略: 不重试
- 幂等键: `path + version_hint`

`LocalDriverFS.write(input: FSWriteInput) -> FSWriteOutput`
- Caller: `ToolRuntime.post_check`, `WorkspaceManager.persist_output`
- Callee: OS 文件系统 API
- 前置条件: path 可写，内容通过输出策略
- 返回值: `ArtifactRef`
- 错误码: `FS_PERMISSION_DENIED`, `FS_QUOTA_EXCEEDED`
- 重试策略: `FS_QUOTA_EXCEEDED` 不重试
- 幂等键: `path + content_hash`

`LocalDriverBrowser.fetch(input: BrowserFetchInput) -> BrowserFetchOutput`
- Caller: `ToolRuntime.execute`（网页抓取工具）
- Callee: 浏览器自动化后端（headless/headful）
- 前置条件: 域名策略允许
- 返回值: `html_ref`, `screenshot_ref`, `network_log_ref`
- 错误码: `DOMAIN_BLOCKED`, `NAVIGATION_TIMEOUT`
- 重试策略: `NAVIGATION_TIMEOUT` 最多 2 次
- 幂等键: `url + normalized_headers_hash`

`LocalDriverBrowser.screenshot(input: BrowserScreenshotInput) -> ScreenshotOutput`
- Caller: `ToolRuntime.execute`, `QualityGuard.capture_render`
- Callee: 浏览器自动化后端
- 前置条件: page 已加载
- 返回值: `ArtifactRef`
- 错误码: `PAGE_NOT_READY`
- 重试策略: 延迟 1 秒重试 2 次
- 幂等键: `page_ref + viewport_hash`

`LocalDriverOffice.export_pptx(input: ExportPptxInput) -> ExportPptxOutput`
- Caller: `AppGateway.export_pptx`, `ApplicationCommandService.export`
- Callee: Office 导出驱动
- 前置条件: HTML/素材齐全，字体检查通过
- 返回值: `ArtifactRef(pptx)`
- 错误码: `FONT_MISSING`, `LAYOUT_INVALID`, `OFFICE_UNAVAILABLE`
- 重试策略: `OFFICE_UNAVAILABLE` 重试 1 次
- 幂等键: `session_id + export_job_id + artifact_version`

### 5) AgentProcessManager

`AgentProcessManager.spawn(spec: AgentProcessSpec) -> AgentProcessRef`
- Caller: `SessionManager.start`, `MultiAgentOrchestrator.dispatch`
- Callee: OS 进程管理 API
- 前置条件: `spec` 包含镜像/命令/资源限制，且通过 `PolicyEngine` 进程级校验
- 返回值: `AgentProcessRef { process_id, pid, started_at }`
- 错误码: `PROCESS_SPAWN_FAILED`, `PROCESS_POLICY_DENIED`
- 重试策略: `PROCESS_SPAWN_FAILED` 最多重试 1 次
- 幂等键: `session_id + spec.worker_role + span_id`

`AgentProcessManager.heartbeat(process_id: string) -> HeartbeatAck`
- Caller: Agent worker
- Callee: `ProcessRegistry.update`
- 前置条件: process_id 已注册且处于 running
- 返回值: `HeartbeatAck { alive: bool, next_interval_ms }`
- 错误码: `PROCESS_NOT_FOUND`, `PROCESS_STALE`
- 重试策略: 网络抖动重试 2 次
- 幂等键: `process_id + heartbeat_seq`

`AgentProcessManager.restart(process_id: string, reason: string) -> AgentProcessRef`
- Caller: `SessionManager.recover`, `HealthMonitor`
- Callee: `AgentProcessManager.spawn`
- 前置条件: 旧进程状态为 crashed/unhealthy
- 返回值: 新 `AgentProcessRef`，并附旧进程映射关系
- 错误码: `PROCESS_RESTART_FAILED`
- 重试策略: 最多重试 1 次，失败转人工介入
- 幂等键: `process_id + restart_reason + restart_seq`

## 数据结构

### DriverEventEnvelope
```text
DriverEventEnvelope {
  id: string,
  event_id: string,
  session_id: string,
  trace_id: string,
  span_id: string,
  status: "running" | "succeeded" | "failed" | "cancelled",
  type: string,
  actor: "ui" | "agent" | "tool" | "system",
  payload: map,
  created_at: string,
  updated_at: string
}
```

### ToolSchema
```text
ToolSchema {
  id: string,
  session_id: string,
  trace_id: string,
  span_id: string,
  status: "active" | "deprecated",
  tool_name: string,
  version: string,
  input_schema_ref: string,
  output_schema_ref: string,
  risk_level: "low" | "medium" | "high",
  timeout_ms: int,
  retry_policy: { max_attempts: int, backoff_ms: int },
  idempotency_key_rule: string,
  created_at: string,
  updated_at: string
}
```

### ToolCallRequest
```text
ToolCallRequest {
  id: string,
  call_id: string,
  session_id: string,
  trace_id: string,
  span_id: string,
  status: "requested" | "running" | "completed",
  tool_name: string,
  tool_version: string,
  input_ref: string,
  timeout_ms: int,
  budget_token_reservation: int,
  idempotency_key: string,
  created_at: string,
  updated_at: string
}
```

### ToolCallResult
```text
ToolCallResult {
  id: string,
  call_id: string,
  session_id: string,
  trace_id: string,
  span_id: string,
  status: "succeeded" | "failed" | "cancelled",
  output_ref: string,
  metrics: { latency_ms: int, token_cost: int, retry_count: int },
  error: ErrorModel?,
  created_at: string,
  updated_at: string
}
```

### SandboxProfile
```text
SandboxProfile {
  id: string,
  session_id: string,
  trace_id: string,
  span_id: string,
  status: "ready" | "disabled",
  profile_name: string,
  cpu_limit: string,
  memory_limit_mb: int,
  network_policy: string,
  mount_whitelist: [string],
  ttl_seconds: int,
  created_at: string,
  updated_at: string
}
```

### 跨层公共契约（Driver 视角）
```text
EventEnvelope { event_id, session_id, trace_id, span_id, type, status, actor, payload, created_at, updated_at }
ErrorModel { code, message, retriable, suggested_action, span_id }
ArtifactRef { artifact_id, version, path, mime, checksum }
```

## 调用关系

### 主时序（E2E）
1. `SessionManager.run_turn` -> `ToolManager.execute_tool` -> `ToolRuntime.execute`
2. `ToolRuntime.execute` -> `PolicyEngine.evaluate(pre-check)` -> 通过后继续
3. 高风险工具：`ToolRuntime.execute` -> `SandboxAdapter.create/exec/destroy`
4. 低风险工具：`ToolRuntime.execute` -> `LocalDrivers.*`
5. `ToolRuntime.post_check` -> `PolicyEngine.evaluate(post-check)`
6. `ToolRuntime.post_check` -> `WorkspaceManager.persist_output`
7. `ToolRuntime` -> `EventBus.publish(tool.call_started/tool.call_result)`
8. 导出链路：`AppGateway.export_pptx` -> `LocalDriverOffice.export_pptx` -> `EventBus.publish(artifact.exported_pptx)`

### 模块调用矩阵（Caller -> Callee）
- `SessionManager.run_turn` -> `ToolRuntime.execute`
- `ToolRuntime.execute` -> `PolicyEngine.evaluate`
- `ToolRuntime.execute` -> `SandboxAdapter.exec`
- `ToolRuntime.execute` -> `LocalDriverFS.read/write`
- `ToolRuntime.execute` -> `LocalDriverBrowser.fetch/screenshot`
- `ToolRuntime.execute` -> `EventBus.publish`
- `EventBus.publish` -> `ObservabilityService.record_event`
- `EventBus.publish` -> `AuditStore.append`
- `AppGateway.export_pptx` -> `LocalDriverOffice.export_pptx`

## 异常与恢复
- `POLICY_DENIED`：发布 `policy.denied`，Runtime 转 `waiting_user` 或触发 `Planner.replan`
- `TOOL_TIMEOUT`：按工具策略重试；超阈值后写 `error.raised`，返回可重试失败
- `SANDBOX_CRASHED`：重建沙箱并单次重试；仍失败则中断当前 step
- 事件总线不可用：先写本地缓冲队列，后台补偿投递
- 导出失败（字体/版式）：返回结构化错误并附 `suggested_action`

## 验收标准
- Driver 层每个核心接口均标注 Caller/Callee、错误码、重试和幂等键
- `ToolCallRequest/Result` 与跨层统一契约一致
- 主链路与异常链路均可追溯到事件
- 导出链路与工具链路均经过 `PolicyEngine` 校验点
- 回放接口可从 checkpoint 生成稳定重放流
