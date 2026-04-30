'use client';

import { forwardRef, useCallback, useEffect, useImperativeHandle, useRef, useState } from 'react';
import { Bot, ChevronLeft } from 'lucide-react';
import { useChatSession, type RecommendationSendMeta } from '@/contexts/ChatSessionContext';
import { useFilePanel } from '@/contexts/FilePanelContext';
import { MessageArea } from './MessageArea';
import { ChatInput, type ChatInputHandle } from './ChatInput';
import { useSlideSet } from '@/components/ppt/PPTViewer';
import { type FilePreviewType } from '@/components/files/fileTypes';
import { type ChatAttachmentRef, type ContextFileRef, getAgentId } from '@/lib/chatTypes';
import { fetchWorkdirRoot } from '@/lib/utils';
import { useResizablePreview } from '@/hooks/useResizablePreview';
import { InlinePreview } from './InlinePreview';
import { useI18n } from '@/contexts/I18nContext';

interface ChatPanelProps {
  defaultAgentId: string;
  emptyState?: React.ReactNode | ((helpers: { fillInput: (text: string) => void; selectAgent: (agentId: string) => void }) => React.ReactNode);
  hideAgentSelector?: boolean;
  lockAgent?: boolean;
  /**
   * 工作台类页面：从左侧「最近对话」进入会话后，在对话区左上角显示返回按钮，
   * 点击后清空当前会话并恢复本页的 emptyState（主视图）。
   */
  returnToMainLabel?: string;
}

export interface ChatPanelHandle {
  fillInput: (text: string) => void;
}

export const ChatPanel = forwardRef<ChatPanelHandle, ChatPanelProps>(function ChatPanel({ defaultAgentId, emptyState, hideAgentSelector, lockAgent, returnToMainLabel }, ref) {
  const { t } = useI18n();
  const {
    wsConnected,
    currentSessionId,
    sessions,
    messages,
    isTyping,
    turnActive,
    activeInteraction,
    currentSessionQuestionInteraction,
    interactionSubmitting,
    sendMessage,
    sendQuestionAnswer,
    sendCurrentSessionQuestionAnswer,
    resetIfNeeded,
    startNewChat,
    handleSkillInvoke,
    cancelTurn,
    reconnect,
  } = useChatSession();

  const { openToPath } = useFilePanel();
  const [selectedAgent, setSelectedAgent] = useState(defaultAgentId);
  const [slidePreviewDir, setSlidePreviewDir] = useState<string | null>(null);
  const [filePreview, setFilePreview] = useState<{ path: string; type: FilePreviewType } | null>(null);
  
  const { previewHeight, onPreviewResize } = useResizablePreview();
  const chatInputRef = useRef<ChatInputHandle>(null);
  const slideSet = useSlideSet(slidePreviewDir);

  // 页面挂载时：通过 switchSession 跳转过来则保留会话，否则重置为干净状态
  useEffect(() => {
    resetIfNeeded();
    setSelectedAgent(defaultAgentId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // 当切换 session 时，从 session meta 中提取 agent_id 并设置为当前选中的 agent
  useEffect(() => {
    if (lockAgent) return;
    if (currentSessionId) {
      const currentSession = sessions.find(s => s.session_id === currentSessionId);
      if (currentSession) {
        const agentId = getAgentId(currentSession.meta);
        if (agentId) setSelectedAgent(agentId);
      }
    }
  }, [currentSessionId, sessions, lockAgent]);

  // 监听消息中目录/幻灯片链接点击 → 内联预览 + 文件面板定位
  useEffect(() => {
    const handler = (e: Event) => {
      const detail = (e as CustomEvent).detail as { dir: string; isAbsolute: boolean };
      let resolvedDir: string;

      if (detail.isAbsolute) {
        resolvedDir = detail.dir;
      } else {
        const curSession = sessions.find(s => s.session_id === currentSessionId);
        const agentId = (curSession ? getAgentId(curSession.meta) : null) || defaultAgentId || 'default';
        const firstSegment = detail.dir.split('/')[0];
        resolvedDir = firstSegment === agentId ? detail.dir : `${agentId}/${detail.dir}`;

        fetchWorkdirRoot().then(root => {
          if (root) {
            const sep = root.includes('\\') ? '\\' : '/';
            const fullPath = [root, resolvedDir.replace(/\//g, sep)].join(sep);
            openToPath(fullPath);
          }
        });
      }

      setSlidePreviewDir(resolvedDir);
      setFilePreview(null);
    };

    window.addEventListener('sensenova-claw:open-slide-preview', handler);
    return () => window.removeEventListener('sensenova-claw:open-slide-preview', handler);
  }, [defaultAgentId, currentSessionId, sessions, openToPath]);

  // 监听文件预览事件
  useEffect(() => {
    const handler = (e: Event) => {
      const detail = (e as CustomEvent).detail as { path: string; type: FilePreviewType };
      setFilePreview(detail);
      setSlidePreviewDir(null);
    };
    window.addEventListener('sensenova-claw:open-file-preview', handler);
    return () => window.removeEventListener('sensenova-claw:open-file-preview', handler);
  }, []);

  useEffect(() => {
    setSlidePreviewDir(null);
    setFilePreview(null);
  }, [currentSessionId]);

  const handleSend = useCallback((
    content: string,
    contextFiles?: ContextFileRef[],
    recommendation?: RecommendationSendMeta | null,
    attachments?: ChatAttachmentRef[],
  ) => {
    if (currentSessionQuestionInteraction) {
      sendCurrentSessionQuestionAnswer(content, false);
      return;
    }
    sendMessage(content, contextFiles, selectedAgent, recommendation, attachments);
  }, [currentSessionQuestionInteraction, sendCurrentSessionQuestionAnswer, sendMessage, selectedAgent]);

  const fillInput = useCallback((text: string) => {
    chatInputRef.current?.setInput(text);
  }, []);

  useImperativeHandle(ref, () => ({ fillInput }), [fillInput]);

  const defaultEmptyState = (
    <div className="flex flex-col items-center justify-center h-full gap-5 text-muted-foreground max-w-md mx-auto text-center">
      <div className="w-16 h-16 rounded-2xl bg-primary/10 flex items-center justify-center text-primary mb-2 shadow-sm">
        <Bot size={32} />
      </div>
      <h3 className="text-2xl font-bold text-foreground tracking-tight">{t('chat.emptyTitle')}</h3>
      <p className="text-sm leading-relaxed">{t('chat.emptyDescription')}</p>
    </div>
  );

  const resolvedEmptyState = typeof emptyState === 'function' ? emptyState({ fillInput, selectAgent: setSelectedAgent }) : (emptyState || defaultEmptyState);

  const showReturnToMain =
    Boolean(returnToMainLabel) && (Boolean(currentSessionId) || messages.length > 0);
  const isCurrentSessionQuestionInteraction = Boolean(currentSessionQuestionInteraction);

  return (
    <div className="flex flex-col h-full min-w-0">
      {showReturnToMain && (
        <div className="shrink-0 flex items-center gap-1 px-3 py-2 border-b border-border/60 bg-muted/30">
          <button
            type="button"
            onClick={() => startNewChat()}
            className="inline-flex items-center gap-1.5 rounded-lg px-2 py-1.5 text-sm font-medium text-muted-foreground hover:text-foreground hover:bg-muted/80 transition-colors"
          >
            <ChevronLeft className="w-4 h-4 shrink-0" />
            <span>{returnToMainLabel}</span>
          </button>
        </div>
      )}

      <MessageArea
        messages={messages}
        isTyping={isTyping}
        currentSessionId={currentSessionId}
        emptyState={currentSessionId ? defaultEmptyState : resolvedEmptyState}
      />

      <InlinePreview
        previewHeight={previewHeight}
        onPreviewResize={onPreviewResize}
        slideSet={slideSet}
        onCloseSlides={() => setSlidePreviewDir(null)}
        filePreview={filePreview}
        onCloseFile={() => setFilePreview(null)}
      />

      <ChatInput
        ref={chatInputRef}
        defaultAgentId={defaultAgentId}
        selectedAgent={selectedAgent}
        onSelectAgent={setSelectedAgent}
        onSend={handleSend}
        onSlashSubmit={() => false}
        onStop={cancelTurn}
        disabled={activeInteraction?.kind === 'confirmation'}
        showStopButton={turnActive && !isCurrentSessionQuestionInteraction}
        wsConnected={wsConnected}
        handleSkillInvoke={handleSkillInvoke}
        hideAgentSelector={hideAgentSelector}
        lockAgent={lockAgent || Boolean(currentSessionId)}
        onReconnect={reconnect}
      />
    </div>
  );
});
