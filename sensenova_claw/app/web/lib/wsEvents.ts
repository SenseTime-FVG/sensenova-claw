// sensenova_claw/app/web/lib/wsEvents.ts

// ── Session 生命周期 ──

export interface SessionCreatedEvent {
  type: 'session_created';
  session_id: string;
  payload: { events?: Record<string, unknown>[] };
}

export interface SessionLoadedEvent {
  type: 'session_loaded';
  session_id: string;
  payload: { events: Record<string, unknown>[] };
}

export interface SessionListChangedEvent {
  type: 'session_list_changed';
  session_id?: string;
  payload: Record<string, never>;
}

export interface SessionDeletedEvent {
  type: 'session_deleted';
  session_id?: string;
  payload: { session_id: string };
}

export interface TitleUpdatedEvent {
  type: 'title_updated';
  session_id: string;
  payload: { title: string };
}

// ── LLM 流式 ──

export interface AgentThinkingEvent {
  type: 'agent_thinking';
  session_id: string;
  payload: Record<string, never>;
}

export interface LlmDeltaEvent {
  type: 'llm_delta';
  session_id: string;
  payload: {
    turn_id?: string;
    content_delta?: string;
    reasoning_delta?: string;
    content_snapshot?: string;
  };
}

export interface LlmResultEvent {
  type: 'llm_result';
  session_id: string;
  payload: {
    turn_id?: string;
    content?: string;
    reasoning_details?: unknown;
  };
}

// ── 工具 ──

export interface ToolExecutionEvent {
  type: 'tool_execution';
  session_id: string;
  payload: {
    tool_name: string;
    tool_call_id: string;
    arguments?: Record<string, unknown>;
  };
}

export interface ToolResultEvent {
  type: 'tool_result';
  session_id: string;
  payload: {
    tool_name: string;
    tool_call_id: string;
    result?: unknown;
    success?: boolean;
    error?: string;
  };
}

// ── 交互 ──

export interface ToolConfirmationRequestedEvent {
  type: 'tool_confirmation_requested';
  session_id: string;
  payload: {
    tool_call_id: string;
    tool_name: string;
    risk_level?: string;
    arguments?: Record<string, unknown>;
    timeout?: number;
  };
}

export interface ToolConfirmationResolvedEvent {
  type: 'tool_confirmation_resolved';
  session_id: string;
  payload: { tool_call_id: string; status: string };
}

export interface UserQuestionAskedEvent {
  type: 'user_question_asked';
  session_id: string;
  payload: {
    question_id: string;
    question: string;
    source_agent_id?: string;
    source_agent_name?: string;
    options?: string[];
    multi_select?: boolean;
    timeout?: number;
  };
}

export interface UserQuestionAnsweredEvent {
  type: 'user_question_answered_event';
  session_id: string;
  payload: { question_id: string };
}

// ── Turn 控制 ──

export interface TurnCompletedEvent {
  type: 'turn_completed';
  session_id: string;
  payload: { turn_id?: string; final_response?: string };
}

export interface TurnCancelledEvent {
  type: 'turn_cancelled';
  session_id: string;
  payload: { turn_id?: string };
}

export interface ErrorEvent {
  type: 'error';
  session_id?: string;
  payload: {
    user_message?: string;
    message?: string;
    error_type?: string;
  };
}

// ── 通知 ──

export interface NotificationEvent {
  type: 'notification';
  session_id?: string;
  payload: {
    title?: string;
    body?: string;
    text?: string;
    level?: 'info' | 'warning' | 'error' | 'success';
    source?: string;
    created_at_ms?: number;
    metadata?: {
      show_toast?: boolean;
      show_browser?: boolean;
      append_to_chat?: boolean;
    };
  };
}

export interface ProactiveResultEvent {
  type: 'proactive_result';
  session_id?: string;
  payload: {
    job_id: string;
    job_name: string;
    result: string;
    session_id?: string;
  };
}

export interface TodolistUpdatedEvent {
  type: 'todolist_updated';
  session_id?: string;
  payload: { date?: string };
}

// ── Union ──

export type WsInboundEvent =
  | SessionCreatedEvent | SessionLoadedEvent | SessionListChangedEvent
  | SessionDeletedEvent | TitleUpdatedEvent
  | AgentThinkingEvent | LlmDeltaEvent | LlmResultEvent
  | ToolExecutionEvent | ToolResultEvent
  | ToolConfirmationRequestedEvent | ToolConfirmationResolvedEvent
  | UserQuestionAskedEvent | UserQuestionAnsweredEvent
  | TurnCompletedEvent | TurnCancelledEvent | ErrorEvent
  | NotificationEvent | ProactiveResultEvent | TodolistUpdatedEvent;

// ── 已知事件类型集合 ──

const KNOWN_EVENT_TYPES = new Set<string>([
  'session_created', 'session_loaded', 'session_list_changed',
  'session_deleted', 'title_updated',
  'agent_thinking', 'llm_delta', 'llm_result',
  'tool_execution', 'tool_result',
  'tool_confirmation_requested', 'tool_confirmation_resolved',
  'user_question_asked', 'user_question_answered_event',
  'turn_completed', 'turn_cancelled', 'error',
  'notification', 'proactive_result', 'todolist_updated',
]);

// ── 解析函数 ──

/**
 * 将 raw WS JSON 转为类型化事件。
 * 不做深层字段校验，仅确认 type 字段存在且已知。
 * 未知 type 返回 null 并 warn。
 */
export function parseWsEvent(raw: Record<string, unknown>): WsInboundEvent | null {
  const type = raw.type;
  if (typeof type !== 'string') return null;
  if (!KNOWN_EVENT_TYPES.has(type)) {
    console.warn(`[WS] 未知事件类型: ${type}`);
    return null;
  }
  return {
    type,
    session_id: typeof raw.session_id === 'string' ? raw.session_id : undefined,
    payload: (raw.payload ?? {}) as Record<string, unknown>,
  } as WsInboundEvent;
}
