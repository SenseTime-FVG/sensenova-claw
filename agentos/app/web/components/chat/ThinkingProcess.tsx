'use client';

import { useState } from 'react';
import { ChevronDown, ChevronRight, Wrench, Brain } from 'lucide-react';
import { type ChatMessage, formatArgs } from '@/lib/chatTypes';
import { isJsonLike, stringifyContent } from '@/components/chat/messageContent';
import { MarkdownRenderer } from '@/components/chat/MarkdownRenderer';
import { MarkdownContent } from './MarkdownContent';
import { resolveAssistantDisplayContent } from '@/lib/assistantThink';

/**
 * 思考过程区块：将一个 turn 内的中间消息（thinking + tool calls）
 * 折叠显示在一个带最大高度的容器中。
 */
export function ThinkingProcess({ steps }: { steps: ChatMessage[] }) {
  const [expanded, setExpanded] = useState(false);

  if (steps.length === 0) return null;

  return (
    <div className="max-w-4xl mx-auto my-2">
      <div className="ml-14 rounded-xl border border-border/60 bg-muted/30 overflow-hidden">
        {/* 标题栏 */}
        <button
          type="button"
          onClick={() => setExpanded(prev => !prev)}
          className="flex w-full items-center gap-2 px-4 py-2.5 text-left text-xs font-medium text-muted-foreground hover:text-foreground transition-colors"
        >
          <ChevronDown
            size={14}
            className={`shrink-0 transition-transform duration-200 ${expanded ? 'rotate-0' : '-rotate-90'}`}
          />
          <Brain size={14} className="text-amber-500" />
          <span>思考过程</span>
          <span className="text-[10px] text-muted-foreground/60 ml-1">
            ({steps.filter(s => s.role === 'tool').length} 次工具调用)
          </span>
        </button>

        {/* 内容区 */}
        {expanded && (
          <div className="border-t border-border/40 max-h-[400px] overflow-y-auto">
            <div className="px-4 py-2 space-y-1">
              {steps.map(step => (
                step.role === 'tool'
                  ? <CompactToolCall key={step.id} msg={step} />
                  : <ThinkingText key={step.id} msg={step} />
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

/** 中间 assistant 思考文本（简洁显示） */
function ThinkingText({ msg }: { msg: ChatMessage }) {
  const { thinkContent, answerContent } = resolveAssistantDisplayContent(
    msg.content || '', msg.thinkingContent
  );
  const text = thinkContent || answerContent;
  if (!text) return null;

  return (
    <div className="text-xs text-muted-foreground py-1.5 pl-1 border-l-2 border-amber-500/30 ml-1">
      <div className="pl-3 max-h-[120px] overflow-y-auto">
        <MarkdownContent content={text} />
      </div>
    </div>
  );
}

/** 单行 tool call，点击展开 Payload/Output */
function CompactToolCall({ msg }: { msg: ChatMessage }) {
  const [expanded, setExpanded] = useState(false);
  const ti = msg.toolInfo;
  const toolName = ti?.name || msg.name || 'tool';
  const status = ti?.status || 'completed';
  const success = ti?.success !== false;

  return (
    <div className="py-0.5">
      {/* 单行摘要 */}
      <button
        type="button"
        onClick={() => setExpanded(prev => !prev)}
        className="flex items-center gap-2 w-full text-left text-xs py-1 px-1 rounded hover:bg-muted/50 transition-colors"
      >
        <ChevronRight
          size={12}
          className={`shrink-0 text-muted-foreground transition-transform duration-150 ${expanded ? 'rotate-90' : ''}`}
        />
        <Wrench size={12} className={status === 'running' ? 'text-amber-500' : success ? 'text-green-500' : 'text-red-500'} />
        <span className="font-mono text-foreground/80">{toolName}</span>
        <span className={`text-[10px] ml-auto ${status === 'running' ? 'text-amber-500' : success ? 'text-green-500/70' : 'text-red-500/70'}`}>
          {status === 'running' ? '执行中...' : success ? '✓' : '✗'}
        </span>
      </button>

      {/* 展开后：Payload 和 Output */}
      {expanded && ti && (
        <div className="ml-6 mt-1 mb-2 space-y-1">
          <CollapsibleSection title="Payload" content={ti.arguments} />
          {ti.status === 'completed' && (
            ti.error
              ? <CollapsibleSection title="Output" content={ti.error} isError />
              : <CollapsibleSection title="Output" content={ti.result} />
          )}
        </div>
      )}
    </div>
  );
}

/** 可折叠的 Payload/Output 子区块 */
function CollapsibleSection({
  title, content, isError = false,
}: {
  title: string;
  content: unknown;
  isError?: boolean;
}) {
  const [open, setOpen] = useState(false);

  return (
    <div>
      <button
        type="button"
        onClick={() => setOpen(prev => !prev)}
        className="flex items-center gap-1.5 text-[11px] font-medium text-muted-foreground hover:text-foreground transition-colors"
      >
        <ChevronRight
          size={11}
          className={`transition-transform duration-150 ${open ? 'rotate-90' : ''}`}
        />
        {title}
      </button>
      {open && (
        <div className={`mt-1 rounded-md border p-2 text-xs max-h-[200px] overflow-y-auto ${
          isError ? 'border-red-500/20 bg-red-500/5 text-red-600 dark:text-red-400' : 'border-border bg-muted/30'
        }`}>
          {isJsonLike(content) ? (
            <pre className="whitespace-pre-wrap break-all font-mono text-[11px]">
              <code>{formatArgs(content)}</code>
            </pre>
          ) : (
            <MarkdownRenderer
              className="chat-markdown chat-markdown--detail"
              content={stringifyContent(content)}
            />
          )}
        </div>
      )}
    </div>
  );
}
