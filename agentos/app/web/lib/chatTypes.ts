// 共享类型定义和工具函数

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
  toolInfo?: ToolInfo;
}

export interface SessionItem {
  session_id: string;
  created_at: number;
  last_active: number;
  meta: string;
  status: string;
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
        rebuilt.push({ id: makeId(), role: 'assistant', content: response, timestamp: Date.now() });
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
