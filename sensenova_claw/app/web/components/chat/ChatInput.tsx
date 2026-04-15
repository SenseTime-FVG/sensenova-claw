'use client';

import { useRef, useState, useCallback, forwardRef, useImperativeHandle, useEffect } from 'react';
import { Send, Square, Paperclip, File, FolderOpen } from 'lucide-react';
import { useDrop } from 'react-dnd';
import { TargetSelector } from './TargetSelector';
import { SlashCommandMenu, useSlashCommand } from './SlashCommandMenu';
import { type ContextFileRef } from '@/lib/chatTypes';
import { UploadProgress } from './UploadProgress';
import { useFileUpload } from '@/hooks/useFileUpload';
import { useChatSession, type RecommendationSendMeta } from '@/contexts/ChatSessionContext';
import { useI18n } from '@/contexts/I18nContext';

interface ChatInputProps {
  defaultAgentId: string;
  selectedAgent: string;
  onSelectAgent: (id: string) => void;
  onSend: (
    content: string,
    contextFiles?: ContextFileRef[],
    recommendation?: RecommendationSendMeta | null,
  ) => void;
  onSlashSubmit: (content: string) => boolean;
  onStop?: () => void;
  disabled: boolean;
  showStopButton?: boolean;
  stopPending?: boolean;
  wsConnected: boolean;
  handleSkillInvoke: (skillName: string, args: string) => void;
  hideAgentSelector?: boolean;
  lockAgent?: boolean;
  onReconnect?: () => void;
}

export interface ChatInputHandle {
  setInput: (text: string) => void;
}

export const ChatInput = forwardRef<ChatInputHandle, ChatInputProps>(function ChatInput({
  defaultAgentId,
  selectedAgent,
  onSelectAgent,
  onSend,
  onSlashSubmit,
  onStop,
  disabled,
  showStopButton,
  stopPending = false,
  wsConnected,
  handleSkillInvoke,
  hideAgentSelector,
  lockAgent,
  onReconnect,
}, ref) {
  const { t } = useI18n();
  const [inputValue, setInputValue] = useState('');
  const [draftRecommendation, setDraftRecommendation] = useState<RecommendationSendMeta | null>(null);
  const [showUploadMenu, setShowUploadMenu] = useState(false);
  const {
    currentSessionId,
    pendingPrefill,
    clearPendingPrefill,
    currentSessionQuestionInteraction,
    sendCurrentSessionQuestionAnswer,
  } = useChatSession();
  const [isSubmitting, setIsSubmitting] = useState(false);
  const isComposingRef = useRef(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const folderInputRef = useRef<HTMLInputElement>(null);
  const uploadMenuRef = useRef<HTMLDivElement>(null);

  // 当前轮次结束或 stop 按钮隐藏后，允许再次发送
  useEffect(() => {
    if (!showStopButton) setIsSubmitting(false);
  }, [showStopButton]);

  useEffect(() => {
    if (!showUploadMenu) return;
    const handler = (e: MouseEvent) => {
      if (uploadMenuRef.current && !uploadMenuRef.current.contains(e.target as Node)) {
        setShowUploadMenu(false);
      }
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [showUploadMenu]);

  useEffect(() => {
    if (!pendingPrefill) return;
    setInputValue(pendingPrefill.text);
    setDraftRecommendation(pendingPrefill.recommendation || null);
    clearPendingPrefill();
    setTimeout(() => {
      if (textareaRef.current) {
        textareaRef.current.style.height = 'auto';
        textareaRef.current.style.height = Math.min(textareaRef.current.scrollHeight, 96) + 'px';
        textareaRef.current.focus();
      }
    });
  }, [pendingPrefill, clearPendingPrefill]);

  useEffect(() => {
    if (draftRecommendation && currentSessionId && draftRecommendation.sourceSessionId !== currentSessionId) {
      setDraftRecommendation(null);
    }
  }, [currentSessionId, draftRecommendation]);

  const resizeTextarea = useCallback(() => {
    setTimeout(() => {
      if (textareaRef.current) {
        textareaRef.current.style.height = 'auto';
        textareaRef.current.style.height = Math.min(textareaRef.current.scrollHeight, 96) + 'px';
        textareaRef.current.focus();
      }
    });
  }, []);

  const insertAtRef = useCallback((path: string) => {
    setInputValue(prev => {
      const prefix = prev === '' || prev.endsWith(' ') || prev.endsWith('\n') ? prev : prev + ' ';
      return prefix + `@${path} `;
    });
    resizeTextarea();
  }, [resizeTextarea]);

  const [{ isOver }, dropRef] = useDrop(() => ({
    accept: 'FILE',
    drop: (item: { name: string; path: string }) => {
      insertAtRef(item.path);
    },
    collect: (monitor) => ({
      isOver: monitor.isOver(),
    }),
  }), [insertAtRef]);

  const { uploadItems, handleFileSelect } = useFileUpload({
    selectedAgent,
    onUploadSuccess: insertAtRef,
  });

  useImperativeHandle(ref, () => ({
    setInput: (text: string) => {
      setInputValue(text);
      resizeTextarea();
    },
  }), [resizeTextarea]);

  const { showMenu, skills, handleSelect: handleSlashSelect, handleSubmit: handleSlashSubmitHook } = useSlashCommand(
    inputValue, setInputValue, handleSkillInvoke,
  );

  const parseAtRefs = useCallback((content: string): ContextFileRef[] => {
    const refs: ContextFileRef[] = [];
    const regex = /@(\S+)/g;
    let m;
    while ((m = regex.exec(content)) !== null) {
      const p = m[1];
      const name = p.split(/[/\\]/).pop() || p;
      if (!refs.some(r => r.path === p)) {
        refs.push({ name, path: p });
      }
    }
    return refs;
  }, []);

  const handleSend = useCallback(() => {
    const content = inputValue.trim();
    const isQuestionReply = Boolean(currentSessionQuestionInteraction);
    if (!content || !wsConnected || disabled || isSubmitting || (!isQuestionReply && showStopButton)) return;

    if (handleSlashSubmitHook(content)) {
      setDraftRecommendation(null);
      setInputValue('');
      if (textareaRef.current) textareaRef.current.style.height = 'auto';
      return;
    }

    if (onSlashSubmit(content)) {
      setDraftRecommendation(null);
      setInputValue('');
      if (textareaRef.current) textareaRef.current.style.height = 'auto';
      return;
    }

    if (isQuestionReply) {
      sendCurrentSessionQuestionAnswer(content, false);
      setDraftRecommendation(null);
      setInputValue('');
      if (textareaRef.current) textareaRef.current.style.height = 'auto';
      return;
    }

    if (!isQuestionReply) {
      setIsSubmitting(true);
    }
    const contextFiles = parseAtRefs(content);
    onSend(content, contextFiles.length > 0 ? contextFiles : undefined, draftRecommendation);
    setDraftRecommendation(null);
    setInputValue('');
    if (textareaRef.current) textareaRef.current.style.height = 'auto';
  }, [
    inputValue,
    wsConnected,
    disabled,
    isSubmitting,
    showStopButton,
    handleSlashSubmitHook,
    onSlashSubmit,
    onSend,
    parseAtRefs,
    draftRecommendation,
    currentSessionQuestionInteraction,
    sendCurrentSessionQuestionAnswer,
  ]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.nativeEvent.isComposing || isComposingRef.current) return;
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend(); }
  };

  const handleInput = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setInputValue(e.target.value);
    if (!e.target.value.trim()) {
      setDraftRecommendation(null);
    }
    const ta = e.target;
    ta.style.height = 'auto';
    ta.style.height = Math.min(ta.scrollHeight, 96) + 'px';
  };

  const isQuestionReply = Boolean(currentSessionQuestionInteraction);
  const inputDisabled = !wsConnected || disabled || (showStopButton && !isQuestionReply);
  const showInlineSendButton = !showStopButton || isQuestionReply;
  const stopTitle = stopPending ? '终止中' : t('chat.stopGeneration');

  return (
    <div className="border-t bg-card/50 backdrop-blur-sm px-4 pt-2.5 pb-2 shrink-0 shadow-[0_-4px_16px_rgba(0,0,0,0.02)]">
      <div className="max-w-4xl mx-auto">
        <div className="flex items-center justify-between mb-2 pl-1">
          <div className="flex items-center gap-3">
            {!hideAgentSelector && (
              <TargetSelector selectedAgent={selectedAgent} onSelectAgent={onSelectAgent} locked={lockAgent} />
            )}
            <span className="flex items-center gap-1.5 text-[11px] font-medium text-muted-foreground bg-muted/50 px-2 py-0.5 rounded-full border">
              <span className={`w-1.5 h-1.5 rounded-full ${wsConnected ? 'bg-green-500 shadow-[0_0_4px_rgba(34,197,94,0.6)]' : 'bg-red-500'}`} />
              {wsConnected ? t('chat.connected') : t('chat.disconnected')}
            </span>
          </div>
          {!wsConnected && onReconnect && (
            <button
              onClick={onReconnect}
              className="text-[10px] text-primary hover:underline font-medium px-2"
            >
              {t('chat.reconnect')}
            </button>
          )}
        </div>

        <div
          ref={dropRef as unknown as React.Ref<HTMLDivElement>}
          className={`flex items-end gap-2 bg-background border rounded-[1.5rem] shadow-lg focus-within:ring-3 focus-within:ring-primary/10 focus-within:border-primary transition-all p-2 relative ${
            isOver ? 'border-primary bg-primary/5 ring-3 ring-primary/20' : 'border-border/80'
          }`}
        >
          {/* 附件上传 */}
          <input ref={fileInputRef} type="file" multiple className="hidden" onChange={handleFileSelect} />
          <input ref={folderInputRef} type="file" className="hidden" onChange={handleFileSelect}
            {...{ webkitdirectory: '', directory: '' } as React.InputHTMLAttributes<HTMLInputElement>}
          />
          <div className="relative mb-1 ml-0.5 shrink-0" ref={uploadMenuRef}>
            <button
              onClick={() => setShowUploadMenu(v => !v)}
              disabled={inputDisabled}
              className="w-8 h-8 rounded-lg flex items-center justify-center text-muted-foreground hover:text-foreground hover:bg-muted transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              title={t('chat.addFileReference')}
            >
              <Paperclip size={16} />
            </button>
            {showUploadMenu && (
              <div className="absolute bottom-full left-0 mb-1 bg-popover border border-border rounded-lg shadow-lg py-1 min-w-[120px] z-50">
                <button
                  className="flex items-center gap-2 w-full px-3 py-1.5 text-sm hover:bg-muted transition-colors text-left"
                  onClick={() => { fileInputRef.current?.click(); setShowUploadMenu(false); }}
                >
                  <File size={14} className="text-muted-foreground" />
                  <span>{t('chat.chooseFile')}</span>
                </button>
                <button
                  className="flex items-center gap-2 w-full px-3 py-1.5 text-sm hover:bg-muted transition-colors text-left"
                  onClick={() => { folderInputRef.current?.click(); setShowUploadMenu(false); }}
                >
                  <FolderOpen size={14} className="text-muted-foreground" />
                  <span>{t('chat.chooseFolder')}</span>
                </button>
              </div>
            )}
          </div>

          <div className="flex-1">
            <UploadProgress items={uploadItems} />
            <SlashCommandMenu inputValue={inputValue} skills={skills} onSelect={handleSlashSelect} visible={showMenu} />
            <textarea
              data-testid="chat-input"
              ref={textareaRef}
              value={inputValue}
              onChange={handleInput}
              onKeyDown={handleKeyDown}
              onCompositionStart={() => { isComposingRef.current = true; }}
              onCompositionEnd={() => { isComposingRef.current = false; }}
              placeholder={
                wsConnected
                  ? t('chat.inputPlaceholder')
                  : t('chat.waitingConnection')
              }
              disabled={inputDisabled}
              rows={1}
              className="w-full bg-transparent border-none px-4 py-2.5 text-[15px] text-foreground placeholder-muted-foreground/50 focus:outline-none focus:ring-0 resize-none disabled:opacity-50 disabled:cursor-not-allowed leading-relaxed"
              style={{ minHeight: '40px', maxHeight: '240px' }}
            />
          </div>
          {showStopButton && onStop && (
            <button
              data-testid="stop-button"
              onClick={onStop}
              disabled={stopPending}
              aria-label={stopTitle}
              className="w-11 h-11 mb-0.5 mr-0.5 rounded-xl bg-red-500 text-white hover:bg-red-600 flex items-center justify-center shrink-0 transition-all active:scale-90 shadow-md shadow-red-500/20 disabled:opacity-70 disabled:cursor-not-allowed disabled:active:scale-100"
              title={stopTitle}
            >
              <Square size={16} fill="currentColor" />
            </button>
          )}
          {showInlineSendButton && (
            <button
              data-testid="send-button"
              onClick={handleSend}
              disabled={!inputValue.trim() || inputDisabled || isSubmitting || stopPending}
              title={t('chat.sendMessage')}
              aria-label={t('chat.sendMessage')}
              className="w-11 h-11 mb-0.5 mr-0.5 rounded-xl bg-primary text-primary-foreground hover:bg-primary/90 flex items-center justify-center shrink-0 transition-all active:scale-90 disabled:opacity-50 disabled:active:scale-100 disabled:cursor-not-allowed shadow-md shadow-primary/20"
            >
              <Send size={20} className="ml-0.5" />
            </button>
          )}
        </div>
        <div className="text-center mt-2 text-[10px] text-muted-foreground/70">
          {t('chat.disclaimer')}
        </div>
      </div>
    </div>
  );
});
