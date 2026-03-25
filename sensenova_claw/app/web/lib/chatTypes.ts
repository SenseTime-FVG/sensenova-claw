// 共享类型定义和工具函数
import { extractThinkContentFromReasoningDetails } from './assistantThink';

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
  turnId?: string;
  thinkingContent?: string;
  thinkingState?: 'streaming' | 'collapsed';
  /** 工具消息在无 toolInfo 时展示的工具名（如会话历史回放） */
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

// --- 工具函数 ---

export function makeId(): string {
  return `${Date.now()}_${Math.random().toString(16).slice(2)}`;
}

export function getTitle(meta: string): string {
  try { return JSON.parse(meta).title || '未命名会话'; } catch { return '未命名会话'; }
}

export function getAgentId(meta: string): string {
  try { return JSON.parse(meta).agent_id || 'default'; } catch { return 'default'; }
}

export function getParentSessionId(meta: string): string | null {
  try { return JSON.parse(meta).parent_session_id || null; } catch { return null; }
}

export function getTaskId(meta: string): string | null {
  try { return JSON.parse(meta).task_id || null; } catch { return null; }
}

export function timeLabel(ts: number): string {
  const diff = Date.now() / 1000 - ts;
  if (diff < 60) return '刚刚';
  if (diff < 3600) return `${Math.floor(diff / 60)}分钟前`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}小时前`;
  return `${Math.floor(diff / 86400)}天前`;
}

export function truncateResult(result: unknown, max = 50000): unknown {
  if (!result) return result;
  const s = JSON.stringify(result);
  if (s.length <= max) return result;
  if (typeof result === 'object' && result !== null && 'content' in result) {
    return { ...(result as Record<string, unknown>), content: String((result as Record<string, unknown>).content).slice(0, max) + '\n... (截断)' };
  }
  return s.slice(0, max) + '... (截断)';
}

export function formatArgs(args: unknown): string {
  if (!args) return '';
  if (typeof args === 'string') { try { return JSON.stringify(JSON.parse(args), null, 2); } catch { return args; } }
  if (typeof args === 'object') return JSON.stringify(args, null, 2);
  return String(args);
}

export function parseEventPayload(event: Record<string, unknown>): Record<string, unknown> {
  const rawPayload = event.payload_json;
  if (typeof rawPayload === 'string') {
    try { return JSON.parse(rawPayload) as Record<string, unknown>; } catch { return {}; }
  }
  return (event.payload || {}) as Record<string, unknown>;
}

export function rebuildMessagesFromEvents(events: Record<string, unknown>[]): ChatMessage[] {
  const rebuilt: ChatMessage[] = [];
  const toolMessageMap = new Map<string, string>();

  for (const event of events) {
    const payload = parseEventPayload(event);
    const eventType = String(event.event_type || '');

    if (eventType === 'user.input') {
      rebuilt.push({ id: makeId(), role: 'user', content: String(payload.content || ''), timestamp: Date.now() });
      continue;
    }
    if (eventType === 'llm.call_result') {
      const response = (payload.response || {}) as Record<string, unknown>;
      const content = String(response.content || '');
      const reasoningDetails = response.reasoning_details;
      const thinkingContent = extractThinkContentFromReasoningDetails(reasoningDetails);
      // 历史重建时只为有实际内容或思考内容的 llm_result 创建 assistant 消息
      // 仅含 tool_calls 的空结果不需要创建（工具调用已由 tool.call_requested 展示）
      if (content || thinkingContent) {
        rebuilt.push({
          id: makeId(),
          role: 'assistant',
          content,
          timestamp: Date.now(),
          thinkingContent: thinkingContent || undefined,
          thinkingState: thinkingContent ? 'collapsed' : undefined,
        });
      }
      continue;
    }
    if (eventType === 'tool.call_requested') {
      const toolInfo: ToolInfo = {
        name: String(payload.tool_name || ''),
        arguments: (payload.arguments || {}) as Record<string, unknown>,
        status: 'running',
      };
      const message: ChatMessage = { id: makeId(), role: 'tool', content: `Executing tool: ${payload.tool_name || ''}`, timestamp: Date.now(), toolInfo };
      rebuilt.push(message);
      toolMessageMap.set(String(payload.tool_call_id || ''), message.id);
      continue;
    }
    if (eventType === 'tool.call_result') {
      const messageId = toolMessageMap.get(String(payload.tool_call_id || ''));
      if (!messageId) continue;
      const messageIndex = rebuilt.findIndex((m) => m.id === messageId);
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
        // 查找最后一条 assistant 消息，避免与 llm.call_result 重复
        let lastAssistantIdx = -1;
        for (let i = rebuilt.length - 1; i >= 0; i--) {
          if (rebuilt[i].role === 'assistant') { lastAssistantIdx = i; break; }
        }
        if (lastAssistantIdx !== -1 && rebuilt[lastAssistantIdx].content === response) {
          // 内容相同，只折叠思考状态
          rebuilt[lastAssistantIdx] = { ...rebuilt[lastAssistantIdx], thinkingState: rebuilt[lastAssistantIdx].thinkingContent ? 'collapsed' : undefined };
        } else if (lastAssistantIdx !== -1 && !rebuilt[lastAssistantIdx].content) {
          // 最后一条 assistant 消息内容为空（可能是中间轮次），更新它
          rebuilt[lastAssistantIdx] = { ...rebuilt[lastAssistantIdx], content: response };
        } else {
          rebuilt.push({ id: makeId(), role: 'assistant', content: response, timestamp: Date.now() });
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

// --- 消息分组（将连续工具调用收拢到一个折叠组） ---

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

/** 从 session 事件中重建右侧面板的步骤和任务进度 */
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
      const progressIdx = taskProgress.findIndex(t => t.task === toolName && t.status === 'running');
      if (progressIdx !== -1) {
        taskProgress[progressIdx] = { ...taskProgress[progressIdx], step: 1, status: 'completed' };
      }
    }
  }

  return { steps, taskProgress, toolStepMap };
}

/** 将 session 列表按 task_id 分组为 TaskGroup[] */
export function groupSessionsToTasks(sessions: SessionItem[]): TaskGroup[] {
  const taskMap = new Map<string, TaskGroup>();
  const childSessions: SessionItem[] = [];

  // 第一轮：收集独立任务（无 task_id 的 session）
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

  // 第二轮：将子 session 归入父任务
  for (const child of childSessions) {
    const taskId = getTaskId(child.meta)!;
    const group = taskMap.get(taskId);
    if (group) {
      group.sessions.push(child);
      group.lastActive = Math.max(group.lastActive, child.last_active);
    } else {
      // 父 session 不存在，作为独立任务
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
