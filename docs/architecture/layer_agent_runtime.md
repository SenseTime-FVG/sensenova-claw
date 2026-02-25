# Agent Runtime Layer 技术架构设计

## 层目标
Agent Runtime 是 Kernel 的运行底座，负责会话生命周期、工作区、任务并行编排、工具执行协调与恢复。它连接 Application、Kernel、Driver/System。

目标：
- 管理 Session/Turn 状态机并支持恢复
- 管理素材与产物版本，保证可回滚
- 承载多 Agent 并行执行并合并结果
- 统一工具调用入口与执行约束

## 模块清单
- `WorkspaceManager`：材料导入、产物版本、checkpoint
- `SessionManager`：会话控制、turn loop、恢复
- `StateMachine`：状态迁移规则
- `MultiAgentOrchestrator`：任务拆分、并行、合并
- `ToolManager`：工具注册编排、调用代理

## 核心接口

### 1) SessionManager

`SessionManager.create(input: SessionCreateInput) -> Session`
- Caller: `AppTaskController.submit_task`, `AppGateway.submit_task`
- Callee: `WorkspaceManager.initialize`, `StateMachine.transit`
- 前置条件: 用户输入合法，工作区可写
- 返回值: `Session`
- 错误码: `SESSION_CREATE_FAILED`, `WORKSPACE_INIT_FAILED`
- 重试策略: 可重试 1 次
- 幂等键: `user_id + client_request_id`

`SessionManager.start(session_id: string) -> Session`
- Caller: `AppTaskController.submit_task`
- Callee: `StateMachine.transit`, `AgentKernel.plan_next_step`, `EventBus.publish`
- 前置条件: session 在 `created/paused`
- 返回值: 更新后 `Session`
- 错误码: `INVALID_SESSION_STATE`
- 重试策略: 不重试
- 幂等键: `session_id + start_seq`

`SessionManager.run_turn(input: TurnInput) -> TurnResult`
- Caller: `SessionLoopScheduler.tick`
- Callee: `AgentKernel.plan_next_step`, `ToolManager.execute_tool`, `WorkspaceManager.checkpoint`
- 前置条件: session 处于 `running`
- 返回值: `TurnResult { decision, outputs, next_state }`
- 错误码: `KERNEL_UNAVAILABLE`, `TOOL_EXECUTION_FAILED`
- 重试策略: step 级重试，最多 2 次
- 幂等键: `turn_id + step_id`

`SessionManager.pause/resume/complete/fail(session_id: string) -> Session`
- Caller: `AppGateway`, `PolicyHandler`, `RecoveryService`
- Callee: `StateMachine.transit`, `EventBus.publish`, `CostGovernor.release`
- 前置条件: session_id 存在，目标状态迁移合法
- 返回值: 更新后 `Session`
- 错误码: `INVALID_SESSION_STATE`, `SESSION_NOT_FOUND`
- 重试策略: 不重试
- 幂等键: `session_id + target_state + action_seq`

`SessionManager.recover(input: RecoverInput) -> Session`
- Caller: `SessionRecoveryService.recover`
- Callee: `AuditStore.reconstruct`, `WorkspaceManager.restore_checkpoint`, `StateMachine.transit`
- 前置条件: 会话有可恢复 checkpoint
- 返回值: 恢复后 `Session`
- 错误码: `RECOVERY_FAILED`, `CHECKPOINT_NOT_FOUND`
- 重试策略: 重试 1 次
- 幂等键: `session_id + checkpoint + recover_seq`

### 2) StateMachine

`StateMachine.transit(current_state: string, event: RuntimeEvent) -> string(next_state)`
- Caller: `SessionManager.*`
- Callee: `TransitionRuleSet.evaluate`
- 前置条件: event 与当前状态匹配
- 返回值: 下一个合法状态
- 错误码: `STATE_TRANSITION_INVALID`
- 重试策略: 不重试
- 幂等键: `session_id + current_state + event.type + seq`

### 3) WorkspaceManager

`WorkspaceManager.import_material(input: MaterialImportInput) -> ArtifactRef`
- Caller: `SessionManager.create`, `AppGateway.upload_material`
- Callee: `LocalDriverFS.read`, `Indexer.enqueue`
- 前置条件: 文件在白名单路径内
- 返回值: `ArtifactRef(material)`
- 错误码: `MATERIAL_UNSUPPORTED`, `MATERIAL_IMPORT_FAILED`
- 重试策略: I/O 失败重试 1 次
- 幂等键: `file_checksum`

`WorkspaceManager.create_artifact(input: ArtifactCreateInput) -> ArtifactRef`
- Caller: `ToolRuntime.post_check`, `PageHtmlEditor.onSave`
- Callee: `LocalDriverFS.write`, `VersionStore.append`
- 前置条件: artifact 元数据完整，写路径可用
- 返回值: `ArtifactRef`
- 错误码: `ARTIFACT_CREATE_FAILED`
- 重试策略: I/O 失败重试 1 次
- 幂等键: `artifact_id + content_hash`

`WorkspaceManager.checkpoint(input: CheckpointInput) -> ArtifactVersion`
- Caller: `SessionManager.run_turn`, `PageHtmlEditor.onSave`
- Callee: `VersionStore.checkpoint`, `EventBus.publish(artifact.version_checkpointed)`
- 前置条件: 当前 artifact 存在可保存版本
- 返回值: `ArtifactVersion`
- 错误码: `CHECKPOINT_FAILED`
- 重试策略: 重试 1 次
- 幂等键: `session_id + artifact_id + checkpoint_seq`

`WorkspaceManager.list_versions(session_id: string) -> ArtifactVersionSet`
- Caller: `VersionTimeline.load`
- Callee: `VersionStore.query`
- 前置条件: session 存在
- 返回值: `ArtifactVersionSet`
- 错误码: `SESSION_NOT_FOUND`
- 重试策略: 不重试
- 幂等键: `session_id + list_seq`

`WorkspaceManager.restore_checkpoint(input: RestoreInput) -> RuntimeStateSnapshot`
- Caller: `SessionManager.recover`, `VersionTimeline.rollback`
- Callee: `VersionStore.restore`
- 前置条件: version 可用且完整
- 返回值: `RuntimeStateSnapshot`
- 错误码: `CHECKPOINT_CORRUPTED`, `RESTORE_FAILED`
- 重试策略: 失败重试 1 次
- 幂等键: `session_id + target_version + restore_seq`

### 4) MultiAgentOrchestrator

`MultiAgentOrchestrator.dispatch(plan: TaskPlan) -> WorkItemSet`
- Caller: `SessionManager.run_turn`, `AgentKernel.plan_next_step`
- Callee: `AgentProcessManager.spawn`
- 前置条件: plan 可并行化
- 返回值: `WorkItemSet`
- 错误码: `DISPATCH_FAILED`
- 重试策略: worker 启动失败重试 1 次
- 幂等键: `session_id + plan.plan_id + dispatch_seq`

`MultiAgentOrchestrator.merge(input: MergeInput) -> MergeResult`
- Caller: `SessionManager.run_turn`
- Callee: `ConflictResolver.resolve`, `QualityGuard.validate_page_set`
- 前置条件: 所有必要 work item 已完成或可用部分完成策略启用
- 返回值: `MergeResult { merged_output_ref, conflicts }`
- 错误码: `MERGE_CONFLICT_UNRESOLVED`
- 重试策略: 自动冲突降级重试 1 次
- 幂等键: `plan_id + merge_group_id`

`MultiAgentOrchestrator.cancel(work_item_id: string) -> CancelAck`
- Caller: `SessionManager.fail`, `AppGateway.cancel_task`
- Callee: `AgentProcessManager.kill`
- 前置条件: work_item 处于 queued/running
- 返回值: `CancelAck { cancelled: bool }`
- 错误码: `WORK_ITEM_NOT_FOUND`, `WORK_ITEM_ALREADY_FINISHED`
- 重试策略: 不重试
- 幂等键: `work_item_id`

### 5) ToolManager

`ToolManager.bootstrap(input: ToolBootstrapInput) -> ToolCatalog`
- Caller: `RuntimeBootstrap.init`
- Callee: `ToolRuntime.register`
- 前置条件: tool catalog 配置可读
- 返回值: `ToolCatalog`
- 错误码: `TOOL_BOOTSTRAP_FAILED`
- 重试策略: 重试 1 次
- 幂等键: `bootstrap_config_hash`

`ToolManager.execute_tool(request: ToolCallRequest) -> ToolCallResult`
- Caller: `SessionManager.run_turn`
- Callee: `ToolRuntime.execute`
- 前置条件: tool_name 存在于 catalog
- 返回值: `ToolCallResult`
- 错误码: `TOOL_NOT_REGISTERED`
- 重试策略: 委托 `ToolRuntime`
- 幂等键: `request.call_id`

## 数据结构

### Session
```text
Session {
  id: string,
  session_id: string,
  trace_id: string,
  span_id: string,
  status: "created" | "running" | "waiting_user" | "blocked_policy" | "failed" | "completed",
  user_id: string,
  workspace_ref: string,
  current_turn_id: string?,
  created_at: string,
  updated_at: string
}
```

### Turn
```text
Turn {
  id: string,
  session_id: string,
  trace_id: string,
  span_id: string,
  status: "running" | "succeeded" | "failed",
  turn_index: int,
  input_ref: string,
  decision_ref: string,
  output_ref: string,
  created_at: string,
  updated_at: string
}
```

### TaskPlan
```text
TaskPlan {
  id: string,
  session_id: string,
  trace_id: string,
  span_id: string,
  status: "draft" | "approved" | "running" | "failed" | "completed",
  plan_id: string,
  steps: [PlanStepRef],
  parallel_groups: [[string]],
  created_at: string,
  updated_at: string
}
```

### WorkItem
```text
WorkItem {
  id: string,
  session_id: string,
  trace_id: string,
  span_id: string,
  status: "queued" | "running" | "succeeded" | "failed" | "cancelled",
  work_item_id: string,
  assigned_agent_id: string,
  input_ref: string,
  output_ref: string,
  retry_count: int,
  created_at: string,
  updated_at: string
}
```

### ArtifactVersion
```text
ArtifactVersion {
  id: string,
  session_id: string,
  trace_id: string,
  span_id: string,
  status: "checkpointed" | "restored",
  artifact_id: string,
  version: int,
  path: string,
  parent_version: int?,
  checksum: string,
  created_at: string,
  updated_at: string
}
```

### RuntimeStateSnapshot
```text
RuntimeStateSnapshot {
  id: string,
  session_id: string,
  trace_id: string,
  span_id: string,
  status: "stable" | "partial",
  session_state: string,
  turn_state: string,
  last_checkpoint_version: int,
  replay_offset: string,
  created_at: string,
  updated_at: string
}
```

### 跨层公共契约（Runtime 视角）
```text
KernelDecision { step_id, action_type, tool_request?, user_confirmation_required, reason }
PlanStepExecutionResult { step_id, status, output_ref, error? }
EventEnvelope / ErrorModel / ToolCallRequest / ToolCallResult / ArtifactRef
```

## 调用关系

### 主时序（E2E）
1. `AppTaskController.submit_task` -> `SessionManager.create/start`
2. `SessionManager.run_turn` -> `AgentKernel.plan_next_step`
3. `SessionManager.run_turn` -> `MultiAgentOrchestrator.dispatch`（可选并行）
4. `SessionManager.run_turn` -> `ToolManager.execute_tool` -> `ToolRuntime.execute`
5. `SessionManager.run_turn` -> `WorkspaceManager.create_artifact/checkpoint`
6. `SessionManager` -> `StateMachine.transit`
7. 失败恢复：`SessionManager.recover` -> `AuditStore.reconstruct` + `WorkspaceManager.restore_checkpoint`

### 模块调用矩阵（Caller -> Callee）
- `AppTaskController.submit_task` -> `SessionManager.start`
- `SessionManager.run_turn` -> `AgentKernel.plan_next_step`
- `SessionManager.run_turn` -> `ToolManager.execute_tool`
- `ToolManager.execute_tool` -> `ToolRuntime.execute`
- `SessionManager.run_turn` -> `WorkspaceManager.checkpoint`
- `SessionManager.recover` -> `AuditStore.reconstruct`
- `SessionManager.recover` -> `WorkspaceManager.restore_checkpoint`
- `MultiAgentOrchestrator.dispatch` -> `AgentProcessManager.spawn`

## 异常与恢复
- `KERNEL_UNAVAILABLE`：turn 失败并进入 `waiting_user` 或自动降级单 Agent
- `TOOL_EXECUTION_FAILED`：按 step 重试策略执行；超过阈值触发 `Planner.replan`
- `STATE_TRANSITION_INVALID`：记审计并强制转 `failed`，等待人工介入
- `CHECKPOINT_CORRUPTED`：回滚至上一版本，触发完整一致性校验
- 恢复流程：`AuditStore.reconstruct` + `restore_checkpoint` + `StateMachine.transit(running)`

## 验收标准
- Session 生命周期覆盖 `create/start/pause/resume/complete/fail/recover`
- 每个 turn 的输入、决策、输出均可定位版本与事件
- 多 Agent 并行结果可合并，冲突有可解释结果
- 恢复可回到最近稳定 checkpoint 并继续运行
- Runtime 与 Kernel 边界通过 `KernelDecision/PlanStepExecutionResult` 固化
