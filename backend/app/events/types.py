# 事件类型常量，统一放在这里便于维护和检索。

# 用户事件（原 ui.* → user.*）
USER_INPUT = "user.input"
USER_TURN_CANCEL_REQUESTED = "user.turn_cancel_requested"

# Agent 编排事件（两阶段）
AGENT_STEP_STARTED = "agent.step_started"
AGENT_STEP_COMPLETED = "agent.step_completed"

# LLM 执行事件（四阶段：requested → started → result → completed）
LLM_CALL_REQUESTED = "llm.call_requested"
LLM_CALL_STARTED = "llm.call_started"
LLM_CALL_RESULT = "llm.call_result"
LLM_CALL_COMPLETED = "llm.call_completed"

# Tool 执行事件（四阶段：requested → started → result → completed）
TOOL_CALL_REQUESTED = "tool.call_requested"
TOOL_CALL_STARTED = "tool.call_started"
TOOL_CALL_RESULT = "tool.call_result"
TOOL_CALL_COMPLETED = "tool.call_completed"

# Tool 权限确认事件
TOOL_CONFIRMATION_REQUESTED = "tool.confirmation_requested"
TOOL_CONFIRMATION_RESPONSE = "tool.confirmation_response"

# 错误事件
ERROR_RAISED = "error.raised"
