import { extractThinkContentFromReasoningDetails } from './assistantThink';
import { detectLocale, formatRelativeTime, translate, type Locale } from './i18n';

export interface ToolInfo {
  name: string;
  arguments: Record<string, unknown>;
  result?: unknown;
  success?: boolean;
  error?: string;
  status: 'running' | 'completed';
}

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant' | 'tool' | 'system';
  content: string;
  timestamp: number;
  /**
   * 同一 turn 中可能产生多条 assistant 消息（LLM 回复 → 工具调用 → LLM 再次回复），
   * 它们共享相同的 turnId，但每条消息各自持有独立的 content 和 thinkingContent。
   * **重要**：更新同 turnId 消息时，只能修改最后一条，不得合并或删除前面的消息，
   * 否则会丢失早期的思考过程和回复内容。
   */
  turnId?: string;
  /** LLM 的思考过程文本，每条 assistant 消息独立持有 */
  thinkingContent?: string;
  /**
   * 思考过程的展示状态：
   * - 'streaming': 展开显示（默认状态，包括流式输出中和输出完成后）
   * - 'collapsed': 折叠隐藏
   * 当前策略：思考过程默认展开，不在 turn 完成时自动折叠。
   */
  thinkingState?: 'streaming' | 'collapsed';
  /** 工具消息在没有 toolInfo 时展示的工具名。 */
  name?: string;
  toolInfo?: ToolInfo;
}

export interface SessionItem {
  session_id: string;
  created_at: number;
  last_active: number;
  meta: string;
  status: string;
  last_turn_status?: 'started' | 'completed' | 'cancelled' | 'error' | null;
  last_turn_ended_at?: number | null;
  last_agent_response?: string | null;
}

export interface TaskGroup {
  taskId: string;
  title: string;
  lastActive: number;
  sessions: SessionItem[];
}

export interface AgentOption {
  id: string;
  name: string;
  description: string;
}

export interface ContextFileRef {
  name: string;
  path: string;
}

export interface StepItem {
  label: string;
  status: 'done' | 'running' | 'pending';
}

export interface TaskProgressItem {
  task: string;
  step: number;
  total: number;
  status: 'running' | 'completed';
}

export interface NotificationItem {
  id: string;
  text: string;
  timestamp: number;
}

export interface PendingInteraction {
  type: 'question' | 'confirmation';
  sessionId: string;
  turnId: string;
  traceId: string;
  question?: string;
  options?: string[];
  multiSelect?: boolean;
  toolName?: string;
  toolArguments?: Record<string, unknown>;
}

export interface FileItem {
  name: string;
  type: 'file' | 'folder';
  path: string;
  size?: number;
}

export function makeId(): string {
  return `${Date.now()}_${Math.random().toString(16).slice(2)}`;
}

export function getTitle(meta: string, locale: Locale = detectLocale()): string {
  try {
    const title = JSON.parse(meta).title;
    return typeof title === 'string' && title.trim() ? title : translate(locale, 'chat.untitledSession');
  } catch {
    return translate(locale, 'chat.untitledSession');
  }
}

export function getAgentId(meta: string): string {
  try {
    return JSON.parse(meta).agent_id || 'default';
  } catch {
    return 'default';
  }
}

export function getParentSessionId(meta: string): string | null {
  try {
    return JSON.parse(meta).parent_session_id || null;
  } catch {
    return null;
  }
}

export function getTaskId(meta: string): string | null {
  try {
    return JSON.parse(meta).task_id || null;
  } catch {
    return null;
  }
}

export function timeLabel(ts: number | null | undefined, locale: Locale = detectLocale()): string {
  if (typeof ts !== 'number' || !Number.isFinite(ts)) return '';
  return formatRelativeTime(locale, ts);
}

export function truncateResult(result: unknown, max = 50000): unknown {
  if (!result) return result;
  const serialized = JSON.stringify(result);
  if (serialized.length <= max) return result;
  if (typeof result === 'object' && result !== null && 'content' in result) {
    return {
      ...(result as Record<string, unknown>),
      content: String((result as Record<string, unknown>).content).slice(0, max) + '\n... (截断)',
    };
  }
  return serialized.slice(0, max) + '... (截断)';
}

export function formatArgs(args: unknown): string {
  if (!args) return '';
  if (typeof args === 'string') {
    try {
      return JSON.stringify(JSON.parse(args), null, 2);
    } catch {
      return args;
    }
  }
  if (typeof args === 'object') return JSON.stringify(args, null, 2);
  return String(args);
}

export function parseEventPayload(event: Record<string, unknown>): Record<string, unknown> {
  const rawPayload = event.payload_json;
  if (typeof rawPayload === 'string') {
    try {
      return JSON.parse(rawPayload) as Record<string, unknown>;
    } catch {
      return {};
    }
  }
  return (event.payload || {}) as Record<string, unknown>;
}

export function findLatestAssistantTurnMessage(messages: ChatMessage[], turnId: string): ChatMessage | null {
  for (let i = messages.length - 1; i >= 0; i--) {
    const message = messages[i];
    if (message.role === 'assistant' && message.turnId === turnId) {
      return message;
    }
  }
  return null;
}

/**
 * 更新同一 turn 中最后一条 assistant 消息，或在工具调用后追加新气泡。
 *
 * 【核心规则】同一 turnId 可能对应多条 assistant 消息（每次工具调用后 LLM 会产生新回复），
 * 每条消息各自持有独立的 thinkingContent。本函数只操作最后一条：
 *   - 最后一条之后没有 tool 消息 → 原地更新（流式追加内容）
 *   - 最后一条之后有 tool 消息 → 追加新气泡（工具调用后的新一轮回复）
 *
 * **禁止**合并或删除同 turnId 的早期 assistant 消息，否则会丢失前面的思考过程。
 */
export function upsertAssistantTurnMessage(
  messages: ChatMessage[],
  turnId: string,
  patch: {
    content?: string;
    thinkingContent?: string;
    thinkingState?: 'streaming' | 'collapsed';
    keepExistingContentWhenEmpty?: boolean;
  },
): ChatMessage[] {
  const matchingIndices: number[] = [];
  for (let i = 0; i < messages.length; i++) {
    const message = messages[i];
    if (message.role === 'assistant' && message.turnId === turnId) {
      matchingIndices.push(i);
    }
  }

  const existing = matchingIndices.length > 0 ? messages[matchingIndices[matchingIndices.length - 1]] : null;
  const nextContent = patch.content && patch.content.length > 0
    ? patch.content
    : patch.keepExistingContentWhenEmpty
      ? (existing?.content || '')
      : (patch.content ?? existing?.content ?? '');
  const nextThinkingContent = patch.thinkingContent !== undefined
    ? patch.thinkingContent
    : existing?.thinkingContent;
  const nextThinkingState = patch.thinkingState !== undefined
    ? patch.thinkingState
    : existing?.thinkingState;

  if (!existing && !nextContent && !nextThinkingContent) {
    return messages;
  }

  const nextMessage: ChatMessage = {
    id: existing?.id || makeId(),
    role: 'assistant',
    content: nextContent,
    timestamp: existing?.timestamp || Date.now(),
    turnId,
    thinkingContent: nextThinkingContent || undefined,
    thinkingState: nextThinkingState,
  };

  if (!existing) {
    return [...messages, nextMessage];
  }

  const lastIndex = matchingIndices[matchingIndices.length - 1];
  const hasToolAfter = messages.slice(lastIndex + 1).some((message) => message.role === 'tool');

  if (!hasToolAfter) {
    // 最后一条 assistant 之后没有 tool → 原地更新最后一条，保留之前的不动
    const next = [...messages];
    next[lastIndex] = nextMessage;
    return next;
  }

  // 最后一条 assistant 之后有 tool → 追加新气泡（工具调用后的新一轮回复）
  // 保留之前所有 assistant 消息不变（它们的 thinking content 各自独立）
  return [...messages, { ...nextMessage, id: makeId() }];
}

export function rebuildMessagesFromEvents(events: Record<string, unknown>[]): ChatMessage[] {
  let rebuilt: ChatMessage[] = [];
  const toolMessageMap = new Map<string, string>();

  for (const event of events) {
    const payload = parseEventPayload(event);
    const eventType = String(event.event_type || '');
    const turnId = typeof event.turn_id === 'string' ? event.turn_id : undefined;

    if (eventType === 'user.input') {
      rebuilt.push({
        id: makeId(),
        role: 'user',
        content: String(payload.content || ''),
        timestamp: Date.now(),
      });
      continue;
    }

    if (eventType === 'llm.call_result') {
      const response = (payload.response || {}) as Record<string, unknown>;
      const content = String(response.content || '');
      const reasoningDetails = response.reasoning_details;
      const thinkingContent = extractThinkContentFromReasoningDetails(reasoningDetails);

      // 仅为有展示内容的 llm_result 建立 assistant 消息，避免工具前草稿常驻。
      if (content || thinkingContent) {
        if (turnId) {
          rebuilt = upsertAssistantTurnMessage(rebuilt, turnId, {
            content,
            thinkingContent,
            thinkingState: thinkingContent ? 'streaming' : undefined,
          });
        } else {
          rebuilt.push({
            id: makeId(),
            role: 'assistant',
            content,
            timestamp: Date.now(),
            thinkingContent: thinkingContent || undefined,
            thinkingState: thinkingContent ? 'streaming' : undefined,
          });
        }
      }
      continue;
    }

    if (eventType === 'tool.call_requested') {
      const toolInfo: ToolInfo = {
        name: String(payload.tool_name || ''),
        arguments: (payload.arguments || {}) as Record<string, unknown>,
        status: 'running',
      };
      const message: ChatMessage = {
        id: makeId(),
        role: 'tool',
        content: `Executing tool: ${payload.tool_name || ''}`,
        timestamp: Date.now(),
        toolInfo,
      };
      rebuilt.push(message);
      toolMessageMap.set(String(payload.tool_call_id || ''), message.id);
      continue;
    }

    if (eventType === 'tool.call_result') {
      const messageId = toolMessageMap.get(String(payload.tool_call_id || ''));
      if (!messageId) continue;
      const messageIndex = rebuilt.findIndex((message) => message.id === messageId);
      if (messageIndex === -1) continue;
      rebuilt[messageIndex] = {
        ...rebuilt[messageIndex],
        content: `Tool Finished: ${payload.tool_name || ''}`,
        toolInfo: {
          name: String(payload.tool_name || ''),
          arguments: rebuilt[messageIndex].toolInfo?.arguments || {},
          result: truncateResult(payload.result),
          success: Boolean(payload.success),
          error: String(payload.error || ''),
          status: 'completed',
        },
      };
      continue;
    }

    if (eventType === 'agent.step_completed') {
      const response = String(payload.final_response || '') || String(((payload.result as Record<string, unknown> | undefined)?.content) || '');
      if (response) {
        if (turnId) {
          rebuilt = upsertAssistantTurnMessage(rebuilt, turnId, {
            content: response,
            keepExistingContentWhenEmpty: true,
          });
        } else {
          let lastAssistantIdx = -1;
          for (let i = rebuilt.length - 1; i >= 0; i--) {
            if (rebuilt[i].role === 'assistant') {
              lastAssistantIdx = i;
              break;
            }
          }

          if (lastAssistantIdx !== -1 && rebuilt[lastAssistantIdx].content === response) {
            // 内容相同，保持不变（thinking 默认展开）
          } else if (lastAssistantIdx !== -1 && !rebuilt[lastAssistantIdx].content) {
            rebuilt[lastAssistantIdx] = { ...rebuilt[lastAssistantIdx], content: response };
          } else {
            rebuilt.push({ id: makeId(), role: 'assistant', content: response, timestamp: Date.now() });
          }
        }
      }
      continue;
    }

    if (eventType === 'notification.session') {
      const metadata = (payload.metadata || {}) as Record<string, unknown>;
      const body = String(payload.body || payload.text || '');
      if (body && metadata.append_to_chat !== false) {
        rebuilt.push({ id: makeId(), role: 'system', content: body, timestamp: Date.now() });
      }
    }
  }

  return rebuilt;
}

export type MessageGroupItem =
  | { type: 'message'; id: string; msg: ChatMessage }
  | { type: 'tool_group'; id: string; messages: ChatMessage[] };

export function groupMessages(messages: ChatMessage[]): MessageGroupItem[] {
  const groups: MessageGroupItem[] = [];
  let toolBuf: ChatMessage[] = [];

  const flush = () => {
    if (toolBuf.length > 0) {
      groups.push({ type: 'tool_group', id: `tg_${toolBuf[0].id}`, messages: [...toolBuf] });
      toolBuf = [];
    }
  };

  for (const msg of messages) {
    if (msg.role === 'tool') {
      toolBuf.push(msg);
    } else {
      flush();
      groups.push({ type: 'message', id: msg.id, msg });
    }
  }
  flush();
  return groups;
}

export function rebuildStepsFromEvents(events: Record<string, unknown>[]): {
  steps: StepItem[];
  taskProgress: TaskProgressItem[];
  toolStepMap: Map<string, number>;
} {
  const steps: StepItem[] = [];
  const taskProgress: TaskProgressItem[] = [];
  const toolStepMap = new Map<string, number>();

  for (const event of events) {
    const payload = parseEventPayload(event);
    const eventType = String(event.event_type || '');

    if (eventType === 'tool.call_requested') {
      const toolName = String(payload.tool_name || '');
      const toolCallId = String(payload.tool_call_id || '');
      const idx = steps.length;
      toolStepMap.set(toolCallId, idx);
      steps.push({ label: `执行 ${toolName}`, status: 'running' });
      taskProgress.push({ task: toolName, step: 0, total: 1, status: 'running' });
    } else if (eventType === 'tool.call_result') {
      const toolCallId = String(payload.tool_call_id || '');
      const toolName = String(payload.tool_name || '');
      const stepIdx = toolStepMap.get(toolCallId);
      if (stepIdx !== undefined && stepIdx < steps.length) {
        steps[stepIdx] = { ...steps[stepIdx], status: 'done' };
      }
      const progressIdx = taskProgress.findIndex((item) => item.task === toolName && item.status === 'running');
      if (progressIdx !== -1) {
        taskProgress[progressIdx] = { ...taskProgress[progressIdx], step: 1, status: 'completed' };
      }
    }
  }

  return { steps, taskProgress, toolStepMap };
}

export function groupSessionsToTasks(sessions: SessionItem[]): TaskGroup[] {
  const taskMap = new Map<string, TaskGroup>();
  const childSessions: SessionItem[] = [];

  for (const session of sessions) {
    const taskId = getTaskId(session.meta);
    if (taskId) {
      childSessions.push(session);
    } else {
      taskMap.set(session.session_id, {
        taskId: session.session_id,
        title: getTitle(session.meta),
        lastActive: session.last_active,
        sessions: [session],
      });
    }
  }

  for (const child of childSessions) {
    const taskId = getTaskId(child.meta)!;
    const group = taskMap.get(taskId);
    if (group) {
      group.sessions.push(child);
      group.lastActive = Math.max(group.lastActive, child.last_active);
    } else {
      taskMap.set(child.session_id, {
        taskId: child.session_id,
        title: getTitle(child.meta),
        lastActive: child.last_active,
        sessions: [child],
      });
    }
  }

  return Array.from(taskMap.values()).sort((a, b) => b.lastActive - a.lastActive);
}
