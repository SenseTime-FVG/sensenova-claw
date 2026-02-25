# Application Layer 技术架构设计

## 层目标
Application Layer 面向最终用户，承载任务创建、大纲确认、逐页编辑、导出与版本回滚。应用层只通过 `AppGateway` 与 Runtime/Kernel 交互，不直接调用 Driver。

目标：
- 提供“生成-编辑-再生成-导出”闭环体验
- 保证用户操作与系统状态强一致可追溯
- 在交互中暴露策略拦截、预算提示与恢复能力

## 模块清单
- `TaskCreationUI`：任务创建与输入材料选择
- `OutlineEditor`：大纲查看、增删改、确认
- `PageHtmlEditor`：逐页 HTML 所见即所得编辑
- `ExportPanel`：导出配置、导出执行与结果展示
- `VersionTimeline`：版本对比与回滚
- `AppGateway`：应用层统一后端入口
- `RealtimeEventClient`：会话级事件订阅与推送

## 核心接口

### 1) AppGateway

`AppGateway.submit_task(input: UserTaskRequest) -> SessionView`
- Caller: `TaskCreationUI.onSubmit`
- Callee: `AppTaskController.submit_task`, `SessionManager.create/start`
- 前置条件: 输入源最少一个（URL/PDF/Word/对话/文件夹）
- 返回值: `SessionView { session_id, status, initial_outline_ref }`
- 错误码: `TASK_INPUT_INVALID`, `SESSION_START_FAILED`
- 重试策略: 表单级重试 1 次
- 幂等键: `client_request_id`

`AppGateway.update_outline(input: OutlineUpdateInput) -> OutlineUpdateResult`
- Caller: `OutlineEditor.onConfirm`
- Callee: `Planner.replan`, `WorkspaceManager.checkpoint`
- 前置条件: outline 树结构合法
- 返回值: 新 plan/version 引用
- 错误码: `OUTLINE_INVALID`, `REPLAN_FAILED`
- 重试策略: `REPLAN_FAILED` 可重试 1 次
- 幂等键: `session_id + outline_revision`

`AppGateway.save_page_html(input: SavePageHtmlInput) -> SavePageHtmlResult`
- Caller: `PageHtmlEditor.onSave`
- Callee: `WorkspaceManager.create_artifact`, `WorkspaceManager.checkpoint`, `QualityGuard.validate_page`
- 前置条件: HTML 语法检查通过
- 返回值: `ArtifactRef + quality_status`
- 错误码: `HTML_INVALID`, `CHECKPOINT_FAILED`
- 重试策略: 存储失败重试 1 次
- 幂等键: `page_id + editor_revision`

`AppGateway.export_pptx(input: ExportJob) -> ExportJobResult`
- Caller: `ExportPanel.onExport`
- Callee: `PolicyEngine.evaluate`, `LocalDriverOffice.export_pptx`, `EventBus.publish`
- 前置条件: 会话状态可导出，必需资源齐全
- 返回值: `ExportJobResult { job_id, artifact_ref, status }`
- 错误码: `EXPORT_BLOCKED_POLICY`, `EXPORT_FAILED`
- 重试策略: 导出失败重试 1 次
- 幂等键: `session_id + export_revision`

### 2) RealtimeEventClient

`RealtimeEventClient.subscribe_session(session_id: string) -> Subscription`
- Caller: `TaskDetailPage.onMount`
- Callee: `EventBus.subscribe`
- 前置条件: session_id 存在且用户有访问权限
- 返回值: `Subscription { id, topic, status }`
- 错误码: `SESSION_NOT_FOUND`, `SUBSCRIBE_DENIED`
- 重试策略: 连接失败指数退避重试 3 次
- 幂等键: `session_id + client_id`

`RealtimeEventClient.push_user_action(action: UIActionEvent) -> Ack`
- Caller: `TaskCreationUI`, `OutlineEditor`, `PageHtmlEditor`, `ExportPanel`
- Callee: `EventBus.publish(ui.*)`
- 前置条件: action schema 校验通过
- 返回值: `Ack { accepted: bool, event_id }`
- 错误码: `UI_ACTION_INVALID`, `EVENTBUS_UNAVAILABLE`
- 重试策略: `EVENTBUS_UNAVAILABLE` 重试 2 次
- 幂等键: `action.id`

### 3) VersionTimeline

`VersionTimeline.compare(input: VersionCompareInput) -> VersionDiff`
- Caller: `VersionTimeline.onCompare`
- Callee: `WorkspaceManager.list_versions`
- 前置条件: 两个版本存在
- 返回值: `VersionDiff`
- 错误码: `VERSION_NOT_FOUND`
- 重试策略: 不重试
- 幂等键: `session_id + base_version + target_version`

`VersionTimeline.rollback(input: VersionRollbackInput) -> RollbackResult`
- Caller: `VersionTimeline.onRollback`
- Callee: `WorkspaceManager.restore_checkpoint`, `SessionManager.resume`
- 前置条件: 目标版本可恢复
- 返回值: `RollbackResult { restored_version, session_status }`
- 错误码: `ROLLBACK_FAILED`, `CHECKPOINT_CORRUPTED`
- 重试策略: 回滚失败重试 1 次
- 幂等键: `session_id + target_version + rollback_request_id`

## 数据结构

### UserTaskRequest
```text
UserTaskRequest {
  id: string,
  session_id: string,
  trace_id: string,
  span_id: string,
  status: "draft" | "submitted",
  user_id: string,
  input_sources: [InputSource],
  prompt: string,
  expected_pages: int,
  style_profile: string?,
  created_at: string,
  updated_at: string
}
```

### OutlineNode
```text
OutlineNode {
  id: string,
  session_id: string,
  trace_id: string,
  span_id: string,
  status: "draft" | "confirmed" | "deprecated",
  node_id: string,
  parent_id: string?,
  title: string,
  summary: string,
  order_index: int,
  created_at: string,
  updated_at: string
}
```

### PageHtmlDoc
```text
PageHtmlDoc {
  id: string,
  session_id: string,
  trace_id: string,
  span_id: string,
  status: "generated" | "edited" | "validated" | "invalid",
  page_id: string,
  html_ref: string,
  assets: [ArtifactRef],
  quality_score: float,
  created_at: string,
  updated_at: string
}
```

### ExportJob
```text
ExportJob {
  id: string,
  session_id: string,
  trace_id: string,
  span_id: string,
  status: "pending" | "running" | "succeeded" | "failed",
  export_job_id: string,
  input_version: int,
  output_format: "pptx",
  options_ref: string,
  created_at: string,
  updated_at: string
}
```

### UIActionEvent
```text
UIActionEvent {
  id: string,
  session_id: string,
  trace_id: string,
  span_id: string,
  status: "accepted" | "rejected",
  action_type: string,
  source_component: string,
  payload_ref: string,
  created_at: string,
  updated_at: string
}
```

### ViewModelState
```text
ViewModelState {
  id: string,
  session_id: string,
  trace_id: string,
  span_id: string,
  status: "loading" | "ready" | "error" | "stale",
  current_step: string,
  progress_percent: int,
  blocking_reason: string?,
  latest_event_ref: string,
  created_at: string,
  updated_at: string
}
```

### 跨层公共契约（App 视角）
```text
AppGateway.* 是 UI 唯一后端入口
EventEnvelope 用于实时事件同步
ErrorModel 用于 UI 统一错误展现
ArtifactRef 用于资源预览/下载
ToolCallRequest/Result 不直接暴露给 UI，仅透传引用
```

## 调用关系

### 主时序（E2E）
1. `TaskCreationUI.onSubmit` -> `AppGateway.submit_task` -> `SessionManager.start`
2. `RealtimeEventClient.subscribe_session` 接收 `agent/tool/artifact` 事件流更新页面
3. `OutlineEditor.onConfirm` -> `AppGateway.update_outline` -> `Planner.replan`
4. `PageHtmlEditor.onSave` -> `AppGateway.save_page_html` -> `WorkspaceManager.checkpoint`
5. `ExportPanel.onExport` -> `AppGateway.export_pptx` -> `LocalDriverOffice.export_pptx`
6. `VersionTimeline.onRollback` -> `WorkspaceManager.restore_checkpoint` -> `SessionManager.resume`

### 模块调用矩阵（Caller -> Callee）
- `TaskCreationUI.onSubmit` -> `AppGateway.submit_task`
- `OutlineEditor.onConfirm` -> `AppGateway.update_outline`
- `PageHtmlEditor.onSave` -> `AppGateway.save_page_html`
- `ExportPanel.onExport` -> `AppGateway.export_pptx`
- `AppGateway.submit_task` -> `SessionManager.start`
- `AppGateway.update_outline` -> `Planner.replan`
- `AppGateway.save_page_html` -> `WorkspaceManager.checkpoint`
- `AppGateway.export_pptx` -> `LocalDriverOffice.export_pptx`
- `RealtimeEventClient.subscribe_session` -> `EventBus.subscribe`
- `VersionTimeline.rollback` -> `WorkspaceManager.restore_checkpoint`

## 异常与恢复
- 表单校验失败：前端阻断，不进入 Runtime
- `blocked_policy`：UI 展示二次确认，确认后重发请求
- `REPLAN_FAILED`：保持原版本，提示用户继续编辑或重试
- `EXPORT_FAILED`：保留 `ExportJob` 失败快照，支持一键重试
- 回滚失败：自动回退到最近稳定 checkpoint，状态置 `error` 并给出修复建议

## 验收标准
- UI 组件不直接调用 Driver，全部通过 `AppGateway.*`
- 每个交互动作可映射到事件流与审计记录
- 编辑、回滚、导出都具备幂等键
- 导出链路含策略校验和结构化错误反馈
- ViewModel 可实时反映 session 状态与阻塞原因
