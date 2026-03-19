'use client';

import { useState } from 'react';
import { Bot, User, Wrench, ChevronDown } from 'lucide-react';
import { MarkdownRenderer } from '@/components/chat/MarkdownRenderer';
import { isJsonLike, stringifyContent } from '@/components/chat/messageContent';
import { type ChatMessage, formatArgs } from '@/lib/chatTypes';

export function MessageBubble({ msg }: { msg: ChatMessage }) {
  const [showArgs, setShowArgs] = useState(false);
  const [showResult, setShowResult] = useState(false);

  if (msg.role === 'system') {
    return (
      <div className="flex justify-center my-3">
        <div className="max-w-3xl rounded-2xl border border-border bg-muted/50 px-4 py-2 text-[10px] text-muted-foreground">
          <MarkdownRenderer className="chat-markdown chat-markdown--system" content={msg.content} />
        </div>
      </div>
    );
  }

  if (msg.role === 'user') {
    return (
      <div className="flex gap-4 max-w-4xl mx-auto flex-row-reverse my-6">
        <div className="w-10 h-10 rounded-full bg-secondary flex items-center justify-center shrink-0 border-2 border-border shadow-md">
          <User size={20} className="text-secondary-foreground" />
        </div>
        <div className="flex-1 flex flex-col items-end pt-1">
          <div className="bg-primary text-primary-foreground text-base md:text-lg p-5 rounded-3xl rounded-tr-sm max-w-[85%] leading-relaxed shadow-lg">
            <MarkdownRenderer className="chat-markdown chat-markdown--user" content={msg.content} />
          </div>
        </div>
      </div>
    );
  }

  if (msg.role === 'tool' && msg.toolInfo) {
    const ti = msg.toolInfo;
    return (
      <div className="flex gap-3 max-w-3xl mx-auto my-2 overflow-hidden">
        <div className="w-8 h-8 shrink-0" />
        <div className="flex-1 min-w-0">
          <div className="bg-card border border-border rounded-lg overflow-hidden shadow-sm">
            <div className="bg-muted px-4 py-2 flex items-center justify-between text-xs border-b">
              <div className="flex items-center gap-2">
                <Wrench size={14} className={ti.status === 'completed' ? 'text-green-500' : 'text-amber-500'} />
                <span className="text-foreground font-mono font-medium">{ti.name}</span>
              </div>
              <span className={`text-[10px] px-2 py-0.5 rounded-full font-medium ${ti.status === 'running' ? 'bg-amber-500/10 text-amber-600 dark:text-amber-400 border border-amber-500/20' : ti.success !== false ? 'bg-green-500/10 text-green-600 dark:text-green-400 border border-green-500/20' : 'bg-red-500/10 text-red-600 dark:text-red-400 border border-red-500/20'}`}>
                {ti.status === 'running' ? 'Executing...' : ti.success !== false ? 'Success' : 'Failed'}
              </span>
            </div>
            <div className="px-4 py-3 space-y-2">
              <button onClick={() => setShowArgs(!showArgs)} className="text-[11px] font-medium text-muted-foreground hover:text-foreground flex items-center gap-1.5 transition-colors">
                <ChevronDown size={14} className={`transition-transform duration-200 ${showArgs ? 'rotate-180' : ''}`} /> Payload
              </button>
              {showArgs && (
                isJsonLike(ti.arguments) ? (
                  <pre className="json-viewer">
                    <code>{formatArgs(ti.arguments)}</code>
                  </pre>
                ) : (
                  <div className="rounded-md border bg-muted/50 p-3">
                    <MarkdownRenderer className="chat-markdown chat-markdown--detail" content={stringifyContent(ti.arguments)} />
                  </div>
                )
              )}
              {ti.status === 'completed' && (
                <>
                  <button onClick={() => setShowResult(!showResult)} className="text-[11px] font-medium text-muted-foreground hover:text-foreground flex items-center gap-1.5 transition-colors mt-2">
                    <ChevronDown size={14} className={`transition-transform duration-200 ${showResult ? 'rotate-180' : ''}`} /> Output
                  </button>
                  {showResult && (
                    ti.error ? (
                      <div className="rounded-md border border-red-500/20 bg-red-500/10 p-3 text-red-600 dark:text-red-400">
                        <MarkdownRenderer className="chat-markdown chat-markdown--detail" content={ti.error} />
                      </div>
                    ) : isJsonLike(ti.result) ? (
                      <pre className="json-viewer">
                        <code>{formatArgs(ti.result)}</code>
                      </pre>
                    ) : (
                      <div className="rounded-md border bg-muted/50 p-3">
                        <MarkdownRenderer className="chat-markdown chat-markdown--detail" content={stringifyContent(ti.result)} />
                      </div>
                    )
                  )}
                </>
              )}
            </div>
          </div>
        </div>
      </div>
    );
  }

  // tool message without toolInfo (e.g. from websocket tool_result)
  if (msg.role === 'tool') {
    return (
      <div className="flex gap-3 max-w-3xl mx-auto my-2 overflow-hidden">
        <div className="w-8 h-8 shrink-0" />
        <div className="flex-1 min-w-0">
          <div className="bg-card border border-border rounded-lg overflow-hidden shadow-sm">
            <div className="bg-muted px-4 py-2 flex items-center gap-2 text-xs border-b">
              <Wrench size={14} className="text-green-500" />
              <span className="text-muted-foreground uppercase tracking-wider">Tool Result</span>
              {msg.name ? <span className="ml-auto font-mono text-foreground">{msg.name}</span> : null}
            </div>
            <div className="px-4 py-3">
              {isJsonLike(msg.content) ? (
                <pre className="json-viewer">
                  <code>{formatArgs(msg.content)}</code>
                </pre>
              ) : (
                <MarkdownRenderer className="chat-markdown chat-markdown--detail" content={msg.content} />
              )}
            </div>
          </div>
        </div>
      </div>
    );
  }

  // assistant
  return (
    <div className="flex gap-4 max-w-4xl mx-auto my-8 group overflow-hidden">
      <div className="w-10 h-10 rounded-full bg-primary flex items-center justify-center shrink-0 shadow-lg mt-1 group-hover:scale-105 transition-transform">
        <Bot size={20} className="text-primary-foreground" />
      </div>
      <div className="flex-1 min-w-0">
        <div className="text-base md:text-lg text-foreground break-words leading-relaxed font-medium">
          <MarkdownRenderer className="chat-markdown chat-markdown--assistant" content={msg.content} />
        </div>
      </div>
    </div>
  );
}
