'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { Bot } from 'lucide-react';
import { useChatSession } from '@/contexts/ChatSessionContext';
import { MessageBubble } from './MessageBubble';
import { TypingIndicator } from './TypingIndicator';
import { ChatInput, type ChatInputHandle } from './ChatInput';
import { InteractionDialog } from './QuestionDialog';
import { type ContextFileRef } from '@/lib/chatTypes';

interface ChatPanelProps {
  defaultAgentId: string;
  emptyState?: React.ReactNode | ((fillInput: (text: string) => void) => React.ReactNode);
  hideAgentSelector?: boolean;
  lockAgent?: boolean;
}

export function ChatPanel({ defaultAgentId, emptyState, hideAgentSelector, lockAgent }: ChatPanelProps) {
  const {
    wsConnected,
    currentSessionId,
    messages,
    isTyping,
    sendMessage,
    resetIfNeeded,
    activeInteraction,
    interactionSubmitting,
    sendQuestionAnswer,
    sendConfirmationResponse,
    handleInteractionTimeout,
    handleSkillInvoke,
    wsSend,
  } = useChatSession();

  const [selectedAgent, setSelectedAgent] = useState(defaultAgentId);
  const chatEndRef = useRef<HTMLDivElement>(null);
  const chatInputRef = useRef<ChatInputHandle>(null);

  // 页面挂载时：通过 switchSession 跳转过来则保留会话，否则重置为干净状态
  useEffect(() => {
    resetIfNeeded();
    setSelectedAgent(defaultAgentId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // 自动滚动到底部
  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isTyping]);

  const handleSend = useCallback((content: string, contextFiles?: ContextFileRef[]) => {
    sendMessage(content, contextFiles, selectedAgent);
  }, [sendMessage, selectedAgent]);

  // 斜杠命令处理（不在 ChatInput 层处理的额外逻辑）
  const handleSlashSubmit = useCallback((_content: string) => {
    return false; // ChatInput 内部已处理
  }, []);

  const fillInput = useCallback((text: string) => {
    chatInputRef.current?.setInput(text);
  }, []);

  const defaultEmptyState = (
    <div className="flex flex-col items-center justify-center h-full gap-5 text-muted-foreground max-w-md mx-auto text-center">
      <div className="w-16 h-16 rounded-2xl bg-primary/10 flex items-center justify-center text-primary mb-2 shadow-sm">
        <Bot size={32} />
      </div>
      <h3 className="text-xl font-semibold text-foreground">How can I help you today?</h3>
      <p className="text-sm">Type a message below to start a new conversation with AgentOS.</p>
    </div>
  );

  const resolvedEmptyState = typeof emptyState === 'function' ? emptyState(fillInput) : (emptyState || defaultEmptyState);

  return (
    <div className="flex flex-col h-full">
      {/* 消息区域 */}
      <div className="flex-1 overflow-y-auto p-4 md:p-8">
        {messages.length === 0 && !currentSessionId ? (
          resolvedEmptyState
        ) : (
          <>
            {messages.map(msg => <MessageBubble key={msg.id} msg={msg} />)}
            {isTyping && <TypingIndicator />}
            <div ref={chatEndRef} />
          </>
        )}
      </div>

      {/* 底部输入区 */}
      <ChatInput
        ref={chatInputRef}
        defaultAgentId={defaultAgentId}
        selectedAgent={selectedAgent}
        onSelectAgent={setSelectedAgent}
        onSend={handleSend}
        onSlashSubmit={handleSlashSubmit}
        disabled={isTyping || !!activeInteraction || interactionSubmitting}
        wsConnected={wsConnected}
        handleSkillInvoke={handleSkillInvoke}
        hideAgentSelector={hideAgentSelector}
        lockAgent={lockAgent}
      />

      {/* 交互对话框 */}
      <InteractionDialog
        open={!!activeInteraction}
        interaction={activeInteraction}
        submitting={interactionSubmitting}
        wsConnected={wsConnected}
        onQuestionSubmit={(answer) => sendQuestionAnswer(answer, false)}
        onQuestionCancel={() => sendQuestionAnswer(null, true)}
        onConfirmationSubmit={sendConfirmationResponse}
        onTimeout={handleInteractionTimeout}
      />
    </div>
  );
}
