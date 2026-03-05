# 事件类型常量，统一放在这里便于维护和检索。
UI_USER_INPUT = "ui.user_input"
UI_TURN_CANCEL_REQUESTED = "ui.turn_cancel_requested"

AGENT_STEP_STARTED = "agent.step_started"
AGENT_STEP_COMPLETED = "agent.step_completed"
USER_INPUT = "user.input"

LLM_CALL_REQUESTED = "llm.call_requested"
LLM_CALL_STARTED = "llm.call_started"
LLM_CALL_COMPLETED = "llm.call_completed"

TOOL_CALL_REQUESTED = "tool.call_requested"
TOOL_CALL_STARTED = "tool.call_started"
TOOL_CALL_COMPLETED = "tool.call_completed"
TOOL_EXECUTION_START = "tool.execution_start"
TOOL_EXECUTION_END = "tool.execution_end"

ERROR_RAISED = "error.raised"
