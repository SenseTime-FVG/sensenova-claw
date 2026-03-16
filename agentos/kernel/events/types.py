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

# Cron 定时任务事件
CRON_JOB_ADDED = "cron.job_added"
CRON_JOB_UPDATED = "cron.job_updated"
CRON_JOB_REMOVED = "cron.job_removed"
CRON_JOB_STARTED = "cron.job_started"
CRON_JOB_FINISHED = "cron.job_finished"
CRON_SYSTEM_EVENT = "cron.system_event"
CRON_DELIVERY_REQUESTED = "cron.delivery_requested"

# 主动出站消息事件
MESSAGE_OUTBOUND_SENT = "message.outbound_sent"

# Heartbeat 心跳巡检事件
HEARTBEAT_WAKE_REQUESTED = "heartbeat.wake_requested"
HEARTBEAT_CHECK_STARTED = "heartbeat.check_started"
HEARTBEAT_COMPLETED = "heartbeat.completed"

# v1.1: Agent 消息通信事件
AGENT_MESSAGE_REQUESTED = "agent.message_requested"
AGENT_MESSAGE_COMPLETED = "agent.message_completed"
AGENT_MESSAGE_FAILED = "agent.message_failed"
