'use client';

import { AlertTriangle, CheckCircle2, Loader2, Wrench } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { MessageBubble } from '@/components/chat/MessageBubble';
import type { ChatMessage } from '@/lib/chatTypes';

interface BuildRunLog {
  ts: number;
  level: string;
  message: string;
}

interface BuildRun {
  id: string;
  builder_type: 'builtin' | 'acp';
  status: 'queued' | 'running' | 'completed' | 'failed';
  prompt: string;
  started_at_ms: number;
  ended_at_ms: number | null;
  logs: BuildRunLog[];
  error?: string;
}

interface MiniAppBuildFeedProps {
  agentName: string;
  latestRun: BuildRun;
}

interface AssistantDraft {
  content: string;
  thinkingContent: string;
  timestamp: number;
}

interface BuildToolCallItem {
  id: string;
  kind: 'tool';
  label: string;
  title: string;
  status: 'running' | 'completed' | 'failed';
  rawStatus: string;
  timestamp: number;
}

interface BuildChatItem {
  id: string;
  kind: 'chat';
  message: ChatMessage;
}

type BuildFeedItem = BuildToolCallItem | BuildChatItem;

const ACP_MESSAGE_PREFIX = 'ACP agent_message_chunk: ';
const ACP_THINK_PREFIX = 'ACP agent_thought_chunk: ';
const ACP_TOOL_PATTERN = /^ACP (tool_call(?:_update)?)(?: \[([^\]]+)\])?: (.+)$/;

export function MiniAppBuildFeed({ agentName, latestRun }: MiniAppBuildFeedProps) {
  const items = buildTranscriptMessages(latestRun);
  const statusLabel = formatRunStatus(latestRun.status);
  const builderLabel = latestRun.builder_type === 'acp' ? 'ACP Builder' : 'Builtin Builder';

  return (
    <div className="flex min-h-full flex-col">
      <div className="mb-6 rounded-2xl border border-border/70 bg-card/70 p-4 text-left shadow-sm">
        <div className="mb-3 flex flex-wrap items-center gap-2">
          <Badge variant={latestRun.status === 'failed' ? 'destructive' : latestRun.status === 'completed' ? 'default' : latestRun.status === 'running' ? 'secondary' : 'outline'}>
            {statusLabel}
          </Badge>
          <Badge variant="outline">{builderLabel}</Badge>
          <Badge variant="outline">{latestRun.id}</Badge>
        </div>
        <div className="text-sm font-medium text-foreground">{agentName} 构建消息流</div>
        <div className="mt-1 text-xs leading-6 text-muted-foreground">
          构建消息来自当前 build run，不会占用聊天 session。生成完成后，你仍可以继续在下方输入框里直接要求 Agent 改页面。
        </div>
      </div>

      {items.length > 0 ? (
        <div>
          {items.map((item) => (
            item.kind === 'chat'
              ? <MessageBubble key={item.id} msg={item.message} />
              : <BuildToolCallCard key={item.id} item={item} />
          ))}
        </div>
      ) : (
        <div className="rounded-2xl border border-dashed border-border/80 bg-muted/30 px-4 py-6 text-sm leading-6 text-muted-foreground">
          构建任务已提交，正在等待 builder 输出第一条消息。
        </div>
      )}
    </div>
  );
}

function BuildToolCallCard({ item }: { item: BuildToolCallItem }) {
  const statusLabel = item.status === 'completed' ? '已完成' : item.status === 'failed' ? '失败' : '运行中';
  const statusClassName = item.status === 'completed'
    ? 'bg-green-500/10 text-green-600 dark:text-green-400 border-green-500/20'
    : item.status === 'failed'
      ? 'bg-red-500/10 text-red-600 dark:text-red-400 border-red-500/20'
      : 'bg-amber-500/10 text-amber-600 dark:text-amber-400 border-amber-500/20';
  const Icon = item.status === 'completed' ? CheckCircle2 : item.status === 'failed' ? AlertTriangle : Loader2;

  return (
    <div
      data-testid="build-tool-card"
      className="my-4 ml-12 rounded-2xl border border-border/70 bg-card/80 p-4 shadow-sm"
    >
      <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <div className="flex h-8 w-8 items-center justify-center rounded-full bg-muted/70 text-muted-foreground">
            {item.status === 'running'
              ? <Icon className="h-4 w-4 animate-spin" />
              : <Icon className="h-4 w-4" />}
          </div>
          <div>
            <div className="text-sm font-medium text-foreground">{item.title}</div>
            <div className="text-xs uppercase tracking-wide text-muted-foreground">{item.label}</div>
          </div>
        </div>
        <div
          data-testid="build-tool-status"
          className={`rounded-full border px-2.5 py-1 text-xs font-medium ${statusClassName}`}
        >
          {statusLabel}
        </div>
      </div>
      <div className="flex items-center gap-2 text-xs text-muted-foreground">
        <Wrench className="h-3.5 w-3.5" />
        <span>{item.rawStatus || statusLabel}</span>
      </div>
    </div>
  );
}

function buildTranscriptMessages(run: BuildRun): BuildFeedItem[] {
  const items: BuildFeedItem[] = [];

  if (run.prompt.trim()) {
    items.push({
      id: `${run.id}-prompt`,
      kind: 'chat',
      message: {
        id: `${run.id}-prompt`,
        role: 'user',
        content: run.prompt,
        timestamp: run.started_at_ms,
      },
    });
  }

  let assistantDraft: AssistantDraft | null = null;

  const flushAssistantDraft = () => {
    if (!assistantDraft) return;
    if (!assistantDraft.content && !assistantDraft.thinkingContent) {
      assistantDraft = null;
      return;
    }
    const nextIndex = items.length;
    items.push({
      id: `${run.id}-assistant-${nextIndex}`,
      kind: 'chat',
      message: {
        id: `${run.id}-assistant-${nextIndex}`,
        role: 'assistant',
        content: assistantDraft.content,
        timestamp: assistantDraft.timestamp,
        thinkingContent: assistantDraft.thinkingContent || undefined,
        thinkingState: assistantDraft.thinkingContent ? 'collapsed' : undefined,
      },
    });
    assistantDraft = null;
  };

  const ensureAssistantDraft = (timestamp: number) => {
    if (assistantDraft) return assistantDraft;
    assistantDraft = {
      content: '',
      thinkingContent: '',
      timestamp,
    };
    return assistantDraft;
  };

  for (const log of run.logs || []) {
    const parsed = parseBuildLog(log.message);
    if (parsed.type === 'assistant_message') {
      const draft = ensureAssistantDraft(log.ts);
      draft.content = appendChunkText(draft.content, parsed.text);
      continue;
    }
    if (parsed.type === 'assistant_think') {
      const draft = ensureAssistantDraft(log.ts);
      draft.thinkingContent = appendChunkText(draft.thinkingContent, parsed.text);
      continue;
    }

    flushAssistantDraft();
    if (parsed.type === 'tool') {
      items.push({
        id: `${run.id}-tool-${items.length}`,
        kind: 'tool',
        label: parsed.label,
        title: parsed.title,
        status: parsed.status,
        rawStatus: parsed.rawStatus,
        timestamp: log.ts,
      });
      continue;
    }

    items.push({
      id: `${run.id}-system-${items.length}`,
      kind: 'chat',
      message: {
        id: `${run.id}-system-${items.length}`,
        role: 'system',
        content: parsed.text,
        timestamp: log.ts,
      },
    });
  }

  flushAssistantDraft();

  if (run.error) {
    items.push({
      id: `${run.id}-error`,
      kind: 'chat',
      message: {
        id: `${run.id}-error`,
        role: 'system',
        content: `构建失败：${run.error}`,
        timestamp: run.ended_at_ms || Date.now(),
      },
    });
  }

  return items;
}

function parseBuildLog(message: string):
  | { type: 'assistant_message'; text: string }
  | { type: 'assistant_think'; text: string }
  | { type: 'tool'; label: string; title: string; status: 'running' | 'completed' | 'failed'; rawStatus: string }
  | { type: 'system'; text: string } {
  if (message.startsWith(ACP_MESSAGE_PREFIX)) {
    return {
      type: 'assistant_message',
      text: message.slice(ACP_MESSAGE_PREFIX.length),
    };
  }

  if (message.startsWith(ACP_THINK_PREFIX)) {
    return {
      type: 'assistant_think',
      text: message.slice(ACP_THINK_PREFIX.length),
    };
  }

  const toolMatch = message.match(ACP_TOOL_PATTERN);
  if (toolMatch) {
    const [, label, rawStatus = '', title] = toolMatch;
    return {
      type: 'tool',
      label,
      title,
      status: normalizeToolStatus(rawStatus),
      rawStatus: rawStatus || 'in_progress',
    };
  }

  return {
    type: 'system',
    text: message,
  };
}

function appendChunkText(current: string, next: string): string {
  if (!next) return current;
  if (!current) return next;
  if (!shouldInsertChunkSpace(current, next)) {
    return `${current}${next}`;
  }
  return `${current} ${next}`;
}

function shouldInsertChunkSpace(current: string, next: string): boolean {
  const left = current.slice(-1);
  const right = next.slice(0, 1);
  if (!left || !right) return false;
  if (/\s/.test(left) || /\s/.test(right)) return false;
  if (/[\u4e00-\u9fff]/.test(left) || /[\u4e00-\u9fff]/.test(right)) return false;
  if (/[.,!?;:)\]}`]/.test(right)) return false;
  if (/[({[`]/.test(left)) return false;
  return /[A-Za-z0-9]/.test(left) && /[A-Za-z0-9]/.test(right);
}

function formatRunStatus(status: BuildRun['status']): string {
  if (status === 'running') return '生成中';
  if (status === 'completed') return '已完成';
  if (status === 'failed') return '失败';
  return '排队中';
}

function normalizeToolStatus(rawStatus: string): 'running' | 'completed' | 'failed' {
  const value = rawStatus.trim().toLowerCase();
  if (value === 'completed' || value === 'success' || value === 'succeeded' || value === 'done') {
    return 'completed';
  }
  if (value === 'failed' || value === 'error' || value === 'cancelled') {
    return 'failed';
  }
  return 'running';
}
