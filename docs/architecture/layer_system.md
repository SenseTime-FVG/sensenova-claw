# System Support Layer 技术架构设计

## 层目标
System Support Layer 是全局治理层，负责安全策略、预算治理、日志审计、可观测与密钥托管。该层不直接承载业务流程，但对所有层实施强制约束。

目标：
- 建立统一策略判断入口，阻断违规调用
- 对 token、并发、工具资源进行预算控制
- 保证事件与产物可追溯、可重建
- 提供统一错误模型与审计链

## 模块清单
- `ObservabilityService`：事件、指标、Tracing 采集
- `CostGovernor`：预算检查与预留释放
- `PolicyEngine`：权限、域名、文件、风险动作策略评估
- `SecretsVault`：本地密钥安全存储
- `AuditStore`：审计日志追加、查询、重建

## 核心接口

### 1) ObservabilityService

`ObservabilityService.record_event(event: EventEnvelope) -> RecordAck`
- Caller: `EventBus.publish`（统一入口）
- Callee: `MetricsSink.write`, `TraceStore.append`
- 前置条件: event schema 有效
- 返回值: `RecordAck { accepted, indexed }`
- 错误码: `OBS_SCHEMA_INVALID`, `OBS_BACKEND_DOWN`
- 重试策略: `OBS_BACKEND_DOWN` 重试 3 次
- 幂等键: `event.event_id`

`ObservabilityService.record_metric(metric: MetricPoint) -> RecordAck`
- Caller: `ToolRuntime.execute`, `CostGovernor.reserve/release`, `SessionManager.run_turn`
- Callee: `MetricsSink.write`
- 前置条件: metric 名称在白名单
- 返回值: `RecordAck`
- 错误码: `METRIC_INVALID`
- 重试策略: 非阻塞补偿上报
- 幂等键: `metric.metric_id`

`ObservabilityService.start_span(input: StartSpanInput) -> TraceSpan`
- Caller: `SessionManager.run_turn`, `ToolRuntime.execute`
- Callee: `TraceStore.create`
- 前置条件: parent_span 存在或为根 span
- 返回值: `TraceSpan`
- 错误码: `TRACE_PARENT_INVALID`
- 重试策略: 不重试
- 幂等键: `trace_id + span_name + seq`

`ObservabilityService.end_span(input: EndSpanInput) -> TraceSpan`
- Caller: `SessionManager.run_turn`, `ToolRuntime.execute.finally`
- Callee: `TraceStore.close`
- 前置条件: span 处于 running
- 返回值: 闭合后的 `TraceSpan`
- 错误码: `TRACE_SPAN_NOT_RUNNING`
- 重试策略: 不重试
- 幂等键: `span_id + end_seq`

### 2) CostGovernor

`CostGovernor.check_budget(input: BudgetCheckInput) -> BudgetDecision`
- Caller: `AgentKernel.plan_next_step`, `SessionManager.run_turn`
- Callee: `QuotaStore.get_current`
- 前置条件: session/user/org 预算配置已加载
- 返回值: `BudgetDecision { allowed, remaining, reason? }`
- 错误码: `BUDGET_PROFILE_NOT_FOUND`
- 重试策略: 不重试
- 幂等键: `session_id + span_id + budget_scope`

`CostGovernor.reserve(input: BudgetReserveInput) -> BudgetReservation`
- Caller: `ToolRuntime.execute`
- Callee: `QuotaStore.reserve`
- 前置条件: `check_budget` 已通过
- 返回值: `BudgetReservation { reservation_id, amount, expires_at }`
- 错误码: `BUDGET_EXCEEDED`, `BUDGET_RESERVE_CONFLICT`
- 重试策略: `BUDGET_RESERVE_CONFLICT` 重试 1 次
- 幂等键: `idempotency_key`

`CostGovernor.release(input: BudgetReleaseInput) -> BudgetReleaseAck`
- Caller: `ToolRuntime.post_check`, `SessionManager.fail/complete`
- Callee: `QuotaStore.release`
- 前置条件: reservation_id 存在
- 返回值: `BudgetReleaseAck { released_amount, remaining }`
- 错误码: `BUDGET_RESERVATION_NOT_FOUND`
- 重试策略: 重试 1 次
- 幂等键: `reservation_id + release_seq`

### 3) PolicyEngine

`PolicyEngine.evaluate(action_context: SecurityContext) -> PolicyDecision`
- Caller: `ToolRuntime.execute`, `ToolRuntime.post_check`, `AppGateway.export_pptx`
- Callee: `PolicyRuleSet.match`, `RiskScorer.score`
- 前置条件: `SecurityContext` 包含 actor、资源、动作
- 返回值: `PolicyDecision { decision, reason, require_confirmation, policy_id }`
- 错误码: `POLICY_CONTEXT_INVALID`, `POLICY_ENGINE_UNAVAILABLE`
- 重试策略: 引擎不可用时 fail-close（默认拒绝）
- 幂等键: `context_hash`

`PolicyEngine.pre_check(input: SecurityContext) -> PolicyDecision`
- Caller: `ToolRuntime.execute`
- Callee: `PolicyEngine.evaluate`
- 前置条件: action_context 完整
- 返回值: `PolicyDecision`
- 错误码: 同 `PolicyEngine.evaluate`
- 重试策略: 不重试（fail-close）
- 幂等键: `context_hash`

`PolicyEngine.post_check(input: SecurityContext) -> PolicyDecision`
- Caller: `ToolRuntime.post_check`
- Callee: `PolicyEngine.evaluate`
- 前置条件: 输出资源引用存在
- 返回值: `PolicyDecision`
- 错误码: 同 `PolicyEngine.evaluate`
- 重试策略: 不重试（fail-close）
- 幂等键: `context_hash + output_ref`

### 4) SecretsVault

`SecretsVault.put(input: SecretPutInput) -> SecretRef`
- Caller: `ChannelGateway.bind_oauth`, `AdminSettings.save_credential`
- Callee: OS 安全存储（keychain/credential manager）
- 前置条件: 调用者具备管理员权限
- 返回值: `SecretRef { secret_id, scope, masked_hint }`
- 错误码: `SECRET_STORE_DENIED`, `SECRET_STORE_FAILED`
- 重试策略: 重试 1 次
- 幂等键: `scope + key_name`

`SecretsVault.get(input: SecretGetInput) -> SecretMaterialRef`
- Caller: `ToolRuntime.execute`（访问第三方服务前）
- Callee: OS 安全存储
- 前置条件: scope、key_name 存在且调用者授权
- 返回值: `SecretMaterialRef`（仅内存引用，不落盘）
- 错误码: `SECRET_NOT_FOUND`, `SECRET_ACCESS_DENIED`
- 重试策略: 不重试
- 幂等键: `secret_id + access_seq`

`SecretsVault.revoke(secret_id: string) -> RevokeAck`
- Caller: `AdminSettings.revoke_credential`
- Callee: OS 安全存储
- 前置条件: secret 存在
- 返回值: `RevokeAck { revoked: bool }`
- 错误码: `SECRET_NOT_FOUND`
- 重试策略: 重试 1 次
- 幂等键: `secret_id`

### 5) AuditStore

`AuditStore.append(record: AuditRecord) -> AppendAck`
- Caller: `EventBus.publish`, `PolicyEngine.evaluate`
- Callee: `AuditLogWriter.write`
- 前置条件: record 可序列化，包含链路字段
- 返回值: `AppendAck { offset, checksum }`
- 错误码: `AUDIT_WRITE_FAILED`
- 重试策略: 写失败重试 3 次
- 幂等键: `record.record_id`

`AuditStore.query(input: AuditQuery) -> AuditRecordSet`
- Caller: `SessionInspector.get_timeline`, `EventBus.replay`
- Callee: `AuditIndex.search`
- 前置条件: query 至少包含 session_id 或 trace_id
- 返回值: `AuditRecordSet`
- 错误码: `AUDIT_QUERY_INVALID`
- 重试策略: 不重试
- 幂等键: `query_hash`

`AuditStore.reconstruct(session_id: string, checkpoint: string) -> RuntimeStateSnapshot`
- Caller: `SessionRecoveryService.recover`, `SessionManager.recover`
- Callee: `ReplayEngine.rebuild`
- 前置条件: checkpoint 存在且可读
- 返回值: `RuntimeStateSnapshot`
- 错误码: `RECONSTRUCT_FAILED`, `CHECKPOINT_NOT_FOUND`
- 重试策略: 重试 1 次
- 幂等键: `session_id + checkpoint`

## 数据结构

### PolicyDecision
```text
PolicyDecision {
  id: string,
  session_id: string,
  trace_id: string,
  span_id: string,
  status: "allow" | "deny" | "require_confirmation",
  policy_id: string,
  reason: string,
  risk_level: "low" | "medium" | "high",
  require_confirmation: bool,
  created_at: string,
  updated_at: string
}
```

### BudgetQuota
```text
BudgetQuota {
  id: string,
  session_id: string,
  trace_id: string,
  span_id: string,
  status: "active" | "exhausted" | "suspended",
  scope: "session" | "user" | "org",
  token_limit: int,
  token_used: int,
  tool_call_limit: int,
  tool_call_used: int,
  created_at: string,
  updated_at: string
}
```

### TraceSpan
```text
TraceSpan {
  id: string,
  session_id: string,
  trace_id: string,
  span_id: string,
  status: "running" | "succeeded" | "failed",
  parent_span_id: string?,
  name: string,
  started_at: string,
  ended_at: string?,
  created_at: string,
  updated_at: string
}
```

### AuditRecord
```text
AuditRecord {
  id: string,
  record_id: string,
  session_id: string,
  trace_id: string,
  span_id: string,
  status: "accepted" | "rejected",
  event_type: string,
  actor: string,
  payload_ref: string,
  checksum: string,
  created_at: string,
  updated_at: string
}
```

### SecurityContext
```text
SecurityContext {
  id: string,
  session_id: string,
  trace_id: string,
  span_id: string,
  status: "pending" | "evaluated",
  actor: "ui" | "agent" | "tool" | "system",
  action: string,
  resource_type: string,
  resource_ref: string,
  network_target: string?,
  file_path: string?,
  risk_hint: string?,
  created_at: string,
  updated_at: string
}
```

### 跨层公共契约（System 视角）
```text
EventEnvelope { event_id, session_id, trace_id, span_id, type, status, actor, payload, created_at, updated_at }
ErrorModel { code, message, retriable, suggested_action, span_id }
ToolCallRequest/ToolCallResult（统一模型，禁止私有字段直传）
ArtifactRef { artifact_id, version, path, mime, checksum }
```

## 调用关系

### 主时序（E2E）
1. `AgentKernel.plan_next_step` -> `CostGovernor.check_budget`
2. `ToolRuntime.execute` -> `PolicyEngine.pre_check`
3. `ToolRuntime.execute` -> `CostGovernor.reserve`
4. `EventBus.publish` -> `ObservabilityService.record_event` + `AuditStore.append`
5. `ToolRuntime.post_check` -> `PolicyEngine.post_check`
6. `SessionManager.complete/fail` -> `CostGovernor.release`
7. 恢复链路：`SessionManager.recover` -> `AuditStore.reconstruct`

### 模块调用矩阵（Caller -> Callee）
- `ToolRuntime.execute` -> `PolicyEngine.evaluate`
- `ToolRuntime.execute` -> `CostGovernor.reserve`
- `AgentKernel.plan_next_step` -> `CostGovernor.check_budget`
- `EventBus.publish` -> `ObservabilityService.record_event`
- `EventBus.publish` -> `AuditStore.append`
- `SessionRecoveryService.recover` -> `AuditStore.reconstruct`
- `ToolRuntime.execute` -> `SecretsVault.get`

## 异常与恢复
- `POLICY_ENGINE_UNAVAILABLE`：fail-close，默认拒绝并触发 `policy.denied`
- `BUDGET_EXCEEDED`：停止当前 step，返回 `suggested_action=reduce_scope_or_confirm_extra_budget`
- `AUDIT_WRITE_FAILED`：进入本地缓冲并持续补偿写入
- `OBS_BACKEND_DOWN`：不阻塞主流程，异步补报
- `SecretsVault` 访问失败：中断外部调用，提示重新授权

## 验收标准
- 所有高风险调用路径均有 `PolicyEngine` 明确校验点
- 预算检查、预留、释放形成闭环且可追溯
- 审计记录可重建 `RuntimeStateSnapshot`
- 事件、指标、trace 三类观测数据均可关联 `trace_id/span_id`
- 系统错误统一映射到 `ErrorModel`
