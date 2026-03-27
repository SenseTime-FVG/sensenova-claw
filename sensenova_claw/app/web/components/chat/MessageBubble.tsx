'use client';

import { useEffect, useMemo, useState, memo } from 'react';
import { Bot, User, Wrench, ChevronRight, ChevronDown, Brain } from 'lucide-react';
import { Markdown } from '@/components/ui/Markdown';
import { isJsonLike, stringifyContent } from '@/lib/utils';
import { type ChatMessage, formatArgs, groupMessages } from '@/lib/chatTypes';
import { resolveAssistantDisplayContent } from '@/lib/assistantThink';
import { useChatSession } from '@/contexts/ChatSessionContext';
import { AskUserResponseForm } from '@/components/chat/AskUserResponseForm';

const MAX_TOOL_CONTENT_HEIGHT = 240;

function ToolContent({ value }: { value: unknown }) {
  if (!value) return <span className="text-muted-foreground italic">empty</span>;
  if (isJsonLike(value)) {
    return (
      <pre className="whitespace-pre-wrap break-words text-xs font-mono leading-relaxed">
        <code>{formatArgs(value)}</code>
      </pre>
    );
  }
  return <Markdown variant="detail" content={stringifyContent(value)} />;
}

const ToolCallItem = memo(function ToolCallItem({ msg }: { msg: ChatMessage }) {
  const [expanded, setExpanded] = useState(false);
  const ti = msg.toolInfo;
  const { submitQuestionResponse } = useChatSession();

  if (!ti) {
    return (
      <div className="py-0.5 tool-info">
        <button
          onClick={() => setExpanded(!expanded)}
          className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded text-xs hover:bg-muted/80 transition-colors cursor-pointer select-none"
        >
          <ChevronRight size={12} className={`shrink-0 text-muted-foreground transition-transform duration-150 ${expanded ? 'rotate-90' : ''}`} />
          <Wrench size={11} className="shrink-0 text-green-500" />
          <span className="font-mono text-foreground/80 tool-name">{msg.name || 'tool'}</span>
          <span className="px-1.5 py-0.5 rounded-full text-[10px] font-medium leading-none bg-green-500/10 text-green-600 dark:text-green-400 tool-status completed">成功</span>
        </button>
        {expanded && (
          <div className="ml-5 mt-1 border-l-2 border-border/30 pl-3 pb-1 section-content">
            <div className="overflow-y-auto rounded-md border border-border/50 bg-muted/30 px-3 py-2" style={{ maxHeight: MAX_TOOL_CONTENT_HEIGHT }}>
              <ToolContent value={msg.content} />
            </div>
          </div>
        )}
      </div>
    );
  }

  const inlineAskUser = ti.askUser;

  return (
    <div className="py-0.5 tool-info">
      <button
        onClick={() => setExpanded(!expanded)}
        className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded text-xs hover:bg-muted/80 transition-colors cursor-pointer select-none"
      >
        <ChevronRight size={12} className={`shrink-0 text-muted-foreground transition-transform duration-150 ${expanded ? 'rotate-90' : ''}`} />
        <Wrench size={11} className={`shrink-0 ${ti.status === 'completed' ? (ti.success !== false ? 'text-green-500' : 'text-red-500') : 'text-amber-500'}`} />
        <span className="font-mono text-foreground/80 tool-name">{ti.name}</span>
        <span className={`px-1.5 py-0.5 rounded-full text-[10px] font-medium leading-none tool-status ${
          ti.status === 'running'
            ? 'bg-amber-500/10 text-amber-600 dark:text-amber-400 running'
            : ti.success !== false
              ? 'bg-green-500/10 text-green-600 dark:text-green-400 completed'
              : 'bg-red-500/10 text-red-600 dark:text-red-400 failed'
        }`}>
          {ti.status === 'running' ? '执行中...' : ti.success !== false ? '成功' : '失败'}
        </span>
      </button>
      {inlineAskUser && (
        <div
          data-testid={`inline-ask-user-${inlineAskUser.questionId}`}
          className="ml-5 mt-2 rounded-xl border border-sky-200/60 bg-sky-50/50 px-3 py-3"
        >
          <AskUserResponseForm
            value={{
              question: inlineAskUser.question,
              options: inlineAskUser.options,
              multiSelect: inlineAskUser.multiSelect,
            }}
            pending={inlineAskUser.pending}
            resolved={inlineAskUser.resolved}
            testIdPrefix="ask-user-shared"
            onSubmit={(answer) => submitQuestionResponse({
              questionId: inlineAskUser.questionId,
              sourceSessionId: inlineAskUser.sourceSessionId,
              answer,
              cancelled: false,
            })}
            onCancel={() => submitQuestionResponse({
              questionId: inlineAskUser.questionId,
              sourceSessionId: inlineAskUser.sourceSessionId,
              answer: null,
              cancelled: true,
            })}
          />
        </div>
      )}
      {expanded && (
        <div className="ml-5 mt-1 border-l-2 border-border/30 pl-3 space-y-2 pb-1">
          <div>
            <div className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider mb-1 section-toggle">参数</div>
            <div className="overflow-y-auto rounded-md border border-border/50 bg-muted/30 px-3 py-2 section-content" style={{ maxHeight: MAX_TOOL_CONTENT_HEIGHT }}>
              <ToolContent value={ti.arguments} />
            </div>
          </div>
          {ti.status === 'completed' && (
            <div>
              <div className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider mb-1 section-toggle">结果</div>
              <div className={`overflow-y-auto rounded-md border px-3 py-2 section-content ${ti.error ? 'border-red-500/20 bg-red-500/5' : 'border-border/50 bg-muted/30'}`} style={{ maxHeight: MAX_TOOL_CONTENT_HEIGHT }}>
                {ti.error ? (
                  <span className="text-xs text-red-600 dark:text-red-400">{ti.error}</span>
                ) : (
                  <ToolContent value={ti.result} />
                )}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
});

export const ToolCallGroup = memo(function ToolCallGroup({ tools }: { tools: ChatMessage[] }) {
  return (
    <div className="flex gap-4 max-w-4xl mx-auto my-2 bubble tool">
      <div className="w-10 shrink-0" />
      <div className="flex-1 min-w-0 space-y-1">
        {tools.map(tool => <ToolCallItem key={tool.id} msg={tool} />)}
      </div>
    </div>
  );
});

export const MessageBubble = memo(function MessageBubble({ msg }: { msg: ChatMessage }) {
  const parsedAssistantContent = useMemo(
    () => msg.role === 'assistant'
      ? resolveAssistantDisplayContent(msg.content || '', msg.thinkingContent)
      : { answerContent: '', thinkContent: '' },
    [msg.content, msg.role, msg.thinkingContent],
  );
  // 思考过程默认展开显示。每条 assistant 消息独立持有 thinkingContent，
  // 同一 turn 中工具调用前后的多条 assistant 会各自显示自己的思考过程。
  const [showThink, setShowThink] = useState(true);

  useEffect(() => {
    if (msg.role !== 'assistant') return;
    setShowThink(true);
  }, [msg.id, msg.role, msg.thinkingState]);

  if (msg.role === 'system') {
    return (
      <div className="flex justify-center my-3 bubble system">
        <div className="max-w-3xl rounded-2xl border border-border bg-muted/50 px-4 py-2 text-[10px] text-muted-foreground">
          <Markdown variant="system" content={msg.content} />
        </div>
      </div>
    );
  }

  if (msg.role === 'user') {
    return (
      <div className="flex gap-4 max-w-4xl mx-auto flex-row-reverse my-6 bubble user">
        <div className="w-10 h-10 rounded-full bg-secondary flex items-center justify-center shrink-0 border-2 border-border shadow-md">
          <User size={20} className="text-secondary-foreground" />
        </div>
        <div className="flex-1 flex flex-col items-end pt-1">
          <div className="bg-primary text-primary-foreground text-sm p-4 rounded-3xl rounded-tr-sm max-w-[85%] leading-relaxed shadow-lg">
            <Markdown variant="user" content={msg.content} />
          </div>
        </div>
      </div>
    );
  }

  // assistant
  return (
    <div className="flex gap-4 max-w-4xl mx-auto my-8 group overflow-hidden bubble assistant">
      <div className="w-10 h-10 rounded-full bg-primary flex items-center justify-center shrink-0 shadow-lg mt-1 group-hover:scale-105 transition-transform">
        <Bot size={20} className="text-primary-foreground" />
      </div>
      <div className="flex-1 min-w-0">
        <div className="space-y-3">
          {parsedAssistantContent.thinkContent ? (
            <div className="rounded-2xl border border-amber-500/25 bg-amber-500/8 overflow-hidden">
              <button
                type="button"
                data-testid="assistant-think-toggle"
                onClick={() => setShowThink((prev) => !prev)}
                className="flex w-full items-center gap-2 px-4 py-3 text-left text-sm font-medium text-amber-900/80 dark:text-amber-200/90"
              >
                <Brain size={14} className="shrink-0 text-amber-600 dark:text-amber-400" />
                <span>思考过程</span>
                <ChevronDown size={14} className={`shrink-0 transition-transform duration-200 ${showThink ? 'rotate-180' : ''}`} />
              </button>
              <div
                data-testid="assistant-think-content"
                hidden={!showThink}
                className="border-t border-amber-500/15 px-4 py-3 text-sm"
              >
                <Markdown content={parsedAssistantContent.thinkContent} />
              </div>
            </div>
          ) : null}
          {parsedAssistantContent.answerContent ? (
            <div className="text-base md:text-lg text-foreground leading-relaxed">
              <Markdown content={parsedAssistantContent.answerContent} />
            </div>
          ) : null}
        </div>
      </div>
    </div>
  );
});

export const MessageList = memo(function MessageList({ messages }: { messages: ChatMessage[] }) {
  const groups = groupMessages(messages);
  return (
    <>
      {groups.map(group => {
        if (group.type === 'tool_group') {
          return <ToolCallGroup key={group.id} tools={group.messages} />;
        }
        return <MessageBubble key={group.id} msg={group.msg} />;
      })}
    </>
  );
});
