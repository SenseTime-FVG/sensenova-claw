# Agent Kernel Layer 技术架构设计

## 层目标
Agent Kernel 负责任务理解、计划生成、技能选择、工具策略、质量检查与重规划，是系统智能决策核心。Kernel 不直接操作底层驱动，通过 Runtime/ToolManager 间接执行。

目标：
- 将用户意图转为可执行计划
- 在预算/安全约束下选择最优技能路径
- 在失败、策略拒绝或用户编辑后快速重规划
- 对产物执行质量门禁，保证输出稳定性

## 模块清单
- `IntentAnalyzer`：输入理解与约束抽取
- `Planner`：计划生成、步骤拆解、重规划
- `SkillRouter`：技能选择与参数绑定
- `MemoryService`：短期/长期记忆检索与压缩
- `ToolUsePolicy`：工具选择策略与回退策略
- `QualityGuard`：页面与整份文档质量校验

## 核心接口

### 1) IntentAnalyzer

`IntentAnalyzer.parse(user_input: UserTaskRequest, context: IntentContext) -> TaskIntent`
- Caller: `SessionManager.run_turn`
- Callee: `MemoryService.retrieve`（偏好补全）
- 前置条件: 输入文本或材料至少一项存在
- 返回值: `TaskIntent`
- 错误码: `INTENT_PARSE_FAILED`, `INPUT_EMPTY`
- 重试策略: 解析失败可降级规则模板重试 1 次
- 幂等键: `session_id + turn_id + input_hash`

### 2) Planner

`Planner.create_plan(intent: TaskIntent, constraints: PlanConstraints) -> TaskPlan`
- Caller: `SessionManager.run_turn`
- Callee: `CostGovernor.check_budget`, `SkillRouter.select`, `MemoryService.retrieve`
- 前置条件: intent 完整，constraints 包含预算和策略
- 返回值: `TaskPlan`
- 错误码: `PLAN_BUILD_FAILED`, `BUDGET_EXCEEDED`
- 重试策略: 预算不足时降级计划重试 1 次
- 幂等键: `session_id + intent.intent_id + plan_revision`

`Planner.plan_next_step(input: PlanStepInput) -> KernelDecision`
- Caller: `SessionManager.run_turn`
- Callee: `ToolUsePolicy.select_tool`, `SkillRouter.select`
- 前置条件: 当前 plan 有可执行 step
- 返回值: `KernelDecision`
- 错误码: `NO_EXECUTABLE_STEP`
- 重试策略: 不重试，转 replan
- 幂等键: `plan_id + step_id`

`Planner.replan(feedback: ReplanFeedback, failure: FailureContext) -> TaskPlan`
- Caller: `SessionManager.run_turn`, `OutlineEditor.onConfirm`
- Callee: `IntentAnalyzer.parse`, `SkillRouter.select`, `MemoryService.summarize`
- 触发条件: `tool.fail`、`policy.denied`、用户改大纲、质量校验失败
- 返回值: 新版本 `TaskPlan`
- 错误码: `REPLAN_FAILED`
- 重试策略: 最多 2 次，失败转人工确认
- 幂等键: `session_id + replan_trigger_event_id`

### 3) SkillRouter

`SkillRouter.select(plan_step: PlanStep, context: SkillContext) -> SkillInvocation`
- Caller: `Planner.create_plan`, `Planner.plan_next_step`
- Callee: `SkillCatalog.rank`
- 前置条件: step 类型已定义
- 返回值: `SkillInvocation`
- 错误码: `SKILL_NOT_FOUND`, `SKILL_VERSION_INCOMPATIBLE`
- 重试策略: 回退到默认技能版本
- 幂等键: `plan_id + step_id + skill_profile`

### 4) MemoryService

`MemoryService.retrieve(query: MemoryQuery) -> MemoryChunkSet`
- Caller: `IntentAnalyzer.parse`, `Planner.create_plan`, `QualityGuard.validate_page_set`
- Callee: `MemoryStore.search`
- 前置条件: query 至少包含 task/domain 约束
- 返回值: `MemoryChunkSet`
- 错误码: `MEMORY_QUERY_INVALID`, `MEMORY_BACKEND_DOWN`
- 重试策略: 后端失败重试 1 次
- 幂等键: `query_hash`

`MemoryService.update(input: MemoryUpdateInput) -> MemoryAck`
- Caller: `SessionManager.complete`, `Planner.replan`
- Callee: `MemoryStore.upsert`
- 前置条件: input 包含可追溯来源引用
- 返回值: `MemoryAck { updated: bool, chunk_ids }`
- 错误码: `MEMORY_UPDATE_FAILED`
- 重试策略: 重试 1 次
- 幂等键: `session_id + update_batch_id`

`MemoryService.summarize(input: MemorySummarizeInput) -> MemoryChunk`
- Caller: `Planner.replan`（压缩上下文降 token）
- Callee: `Compressor.run`
- 前置条件: 输入 chunk 数量超过阈值
- 返回值: 摘要 `MemoryChunk`
- 错误码: `MEMORY_SUMMARY_FAILED`
- 重试策略: 重试 1 次，失败则回退原始 chunk
- 幂等键: `summary_input_hash`

### 5) ToolUsePolicy

`ToolUsePolicy.select_tool(input: ToolSelectInput) -> ToolSelection`
- Caller: `Planner.plan_next_step`
- Callee: `PolicyEngine.evaluate`（可行性预判）
- 前置条件: 候选工具列表非空
- 返回值: `ToolSelection`
- 错误码: `TOOL_SELECTION_FAILED`
- 重试策略: 选择失败回退低风险工具集
- 幂等键: `step_id + candidate_hash`

`ToolUsePolicy.fallback(input: ToolFallbackInput) -> ToolSelection`
- Caller: `Planner.replan`
- Callee: `ToolCatalog.filter_by_risk`
- 前置条件: 原工具路径失败且存在候选回退工具
- 返回值: `ToolSelection`
- 错误码: `TOOL_FALLBACK_NOT_AVAILABLE`
- 重试策略: 不重试
- 幂等键: `step_id + fallback_level`

### 6) QualityGuard

`QualityGuard.validate_page(input: PageQualityInput) -> QualityReport`
- Caller: `SessionManager.run_turn`（单页完成后）
- Callee: `LocalDriverBrowser.screenshot`, `MemoryService.retrieve`
- 前置条件: 页面 HTML 已生成
- 返回值: `QualityReport`
- 错误码: `QUALITY_CHECK_FAILED`
- 重试策略: 失败重试 1 次并切换轻量规则
- 幂等键: `page_id + page_version`

`QualityGuard.validate_page_set(input: DeckQualityInput) -> DeckQualityReport`
- Caller: `SessionManager.complete`, `MultiAgentOrchestrator.merge`
- Callee: `QualityRuleSet.run`
- 前置条件: 所有页面有可读版本引用
- 返回值: `DeckQualityReport`
- 错误码: `DECK_QUALITY_CHECK_FAILED`
- 重试策略: 重试 1 次，失败降级关键规则集
- 幂等键: `deck_id + deck_version`

## 数据结构

### TaskIntent
```text
TaskIntent {
  id: string,
  session_id: string,
  trace_id: string,
  span_id: string,
  status: "parsed" | "ambiguous" | "invalid",
  intent_id: string,
  goal: string,
  constraints: [string],
  expected_pages: int,
  input_material_refs: [string],
  created_at: string,
  updated_at: string
}
```

### PlanStep
```text
PlanStep {
  id: string,
  session_id: string,
  trace_id: string,
  span_id: string,
  status: "pending" | "running" | "succeeded" | "failed" | "skipped",
  step_id: string,
  step_type: string,
  input_ref: string,
  output_ref: string,
  retry_budget: int,
  created_at: string,
  updated_at: string
}
```

### SkillInvocation
```text
SkillInvocation {
  id: string,
  session_id: string,
  trace_id: string,
  span_id: string,
  status: "selected" | "executed" | "failed",
  skill_name: string,
  skill_version: string,
  params_ref: string,
  tool_candidates: [string],
  created_at: string,
  updated_at: string
}
```

### MemoryChunk
```text
MemoryChunk {
  id: string,
  session_id: string,
  trace_id: string,
  span_id: string,
  status: "active" | "archived",
  memory_type: "short_term" | "long_term" | "summary",
  content_ref: string,
  tags: [string],
  score: float,
  created_at: string,
  updated_at: string
}
```

### QualityIssue
```text
QualityIssue {
  id: string,
  session_id: string,
  trace_id: string,
  span_id: string,
  status: "open" | "resolved" | "ignored",
  issue_code: string,
  severity: "low" | "medium" | "high",
  page_ref: string,
  description: string,
  suggested_fix: string,
  created_at: string,
  updated_at: string
}
```

### KernelDecision
```text
KernelDecision {
  id: string,
  session_id: string,
  trace_id: string,
  span_id: string,
  status: "ready" | "blocked" | "requires_user_confirmation",
  step_id: string,
  action_type: "call_tool" | "ask_user" | "replan" | "complete",
  tool_request_ref: string?,
  reason: string,
  created_at: string,
  updated_at: string
}
```

### 跨层公共契约（Kernel 视角）
```text
PlanStepExecutionResult { step_id, status, output_ref, error? }
ToolCallRequest/ToolCallResult
ErrorModel
EventEnvelope
```

## 调用关系

### 主时序（E2E）
1. `SessionManager.run_turn` -> `IntentAnalyzer.parse`（首轮或重大变更）
2. `SessionManager.run_turn` -> `Planner.create_plan`（计划初始化）
3. `SessionManager.run_turn` -> `Planner.plan_next_step` -> `ToolUsePolicy.select_tool`
4. `Planner.plan_next_step` -> `SkillRouter.select` 生成 `SkillInvocation`
5. Runtime 执行 `ToolCallRequest` 后返回 `PlanStepExecutionResult`
6. `QualityGuard.validate_page` -> 若失败触发 `Planner.replan`
7. `Planner.replan` 输出新 plan revision

### 模块调用矩阵（Caller -> Callee）
- `SessionManager.run_turn` -> `Planner.plan_next_step`
- `Planner.create_plan` -> `CostGovernor.check_budget`
- `Planner.create_plan` -> `SkillRouter.select`
- `Planner.plan_next_step` -> `ToolUsePolicy.select_tool`
- `Planner.replan` -> `MemoryService.summarize`
- `QualityGuard.validate_page` -> `LocalDriverBrowser.screenshot`
- `QualityGuard.validate_page_set` -> `MemoryService.retrieve`

## 异常与恢复
- `NO_EXECUTABLE_STEP`：立即触发 `Planner.replan`
- `SKILL_NOT_FOUND`：回退默认技能并记录 `error.raised`
- `BUDGET_EXCEEDED`：降级计划（减少页数/降低图像生成）
- `QUALITY_CHECK_FAILED`：页面标记为 `needs_regeneration`，回传 Runtime 重生成
- `policy.denied` 触发：`Planner.replan` 选择低风险工具路径

## 验收标准
- Kernel 接口覆盖“理解-规划-执行决策-质量闭环”
- `tool.fail`、`policy.denied`、用户改大纲三类场景均有 replan 路径
- `KernelDecision` 可被 Runtime 直接消费，无额外解释层
- 质量校验结果可映射到具体页面和修复建议
- 所有核心方法标注 Caller/Callee、错误码、重试与幂等键
