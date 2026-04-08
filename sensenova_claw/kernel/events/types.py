# 事件类型常量，统一放在这里便于维护和检索。

# 用户事件（原 ui.* → user.*）
USER_INPUT = "user.input"
USER_TURN_CANCEL_REQUESTED = "user.turn_cancel_requested"
USER_QUESTION_ASKED = "user.question_asked"
USER_QUESTION_ANSWERED = "user.question_answered"

# Agent 编排事件（两阶段）
AGENT_STEP_STARTED = "agent.step_started"
AGENT_STEP_COMPLETED = "agent.step_completed"
AGENT_UPDATE_TITLE_COMPLETED = "agent.update_title_completed"

# LLM 执行事件（五阶段：requested → started → [delta...] → result → completed）
LLM_CALL_REQUESTED = "llm.call_requested"
LLM_CALL_STARTED = "llm.call_started"
LLM_CALL_DELTA = "llm.call_delta"
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
TOOL_CONFIRMATION_RESOLVED = "tool.confirmation_resolved"

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

# 通知事件
NOTIFICATION_PUSH = "notification.push"
NOTIFICATION_SESSION = "notification.session"

# v1.1: Agent 消息通信事件
AGENT_MESSAGE_REQUESTED = "agent.message_requested"
AGENT_MESSAGE_COMPLETED = "agent.message_completed"
AGENT_MESSAGE_FAILED = "agent.message_failed"

# Proactive 事件
PROACTIVE_JOB_TRIGGERED = "proactive.job_triggered"
PROACTIVE_JOB_STARTED = "proactive.job_started"
PROACTIVE_JOB_COMPLETED = "proactive.job_completed"
PROACTIVE_JOB_FAILED = "proactive.job_failed"
PROACTIVE_JOB_SKIPPED = "proactive.job_skipped"
PROACTIVE_RESULT = "proactive.result"

# 会话生命周期事件
SESSION_CREATED = "session.created"

# Todolist 变更事件
TODOLIST_UPDATED = "todolist.updated"

# 配置变更事件
CONFIG_UPDATED = "config.updated"

# Deep Research 深度研究事件
RESEARCH_STARTED = "research.started"
RESEARCH_PLAN_COMPLETED = "research.plan_completed"
RESEARCH_PLAN_CONFIRMED = "research.plan_confirmed"
RESEARCH_WAVE_STARTED = "research.wave_started"
RESEARCH_DIMENSION_COMPLETED = "research.dimension_completed"
RESEARCH_WAVE_COMPLETED = "research.wave_completed"
RESEARCH_REPORT_GENERATED = "research.report_generated"
RESEARCH_COMPLETED = "research.completed"
RESEARCH_FAILED = "research.failed"

# 系统级事件的 session_id（广播哨兵，不属于任何用户会话）
SYSTEM_SESSION_ID = "__system__"
