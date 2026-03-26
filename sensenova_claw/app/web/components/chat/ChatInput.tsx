'use client';

import { useRef, useState, useCallback, forwardRef, useImperativeHandle, useEffect } from 'react';
import { Send, Square, Paperclip, File, FolderOpen } from 'lucide-react';
import { useDrop } from 'react-dnd';
import { TargetSelector } from './TargetSelector';
import { SlashCommandMenu, useSlashCommand } from './SlashCommandMenu';
import { type ContextFileRef } from '@/lib/chatTypes';
import { singleFileFlow, dirUploadFlow, type ProgressCallback } from '@/lib/fileUpload';
import { UploadProgress, type UploadProgressItem } from './UploadProgress';
import { useChatSession, type RecommendationSendMeta } from '@/contexts/ChatSessionContext';

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
  wsConnected: boolean;
  handleSkillInvoke: (skillName: string, args: string) => void;
  hideAgentSelector?: boolean;
  lockAgent?: boolean;
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
  wsConnected,
  handleSkillInvoke,
  hideAgentSelector,
  lockAgent,
}, ref) {
  const [inputValue, setInputValue] = useState('');
  const [draftRecommendation, setDraftRecommendation] = useState<RecommendationSendMeta | null>(null);
  const [showUploadMenu, setShowUploadMenu] = useState(false);
  const [uploadItems, setUploadItems] = useState<UploadProgressItem[]>([]);
  const { currentSessionId, pendingPrefill, clearPendingPrefill } = useChatSession();
  const isComposingRef = useRef(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const folderInputRef = useRef<HTMLInputElement>(null);
  const uploadMenuRef = useRef<HTMLDivElement>(null);

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

  useImperativeHandle(ref, () => ({
    setInput: (text: string) => {
      setInputValue(text);
      setTimeout(() => {
        if (textareaRef.current) {
          textareaRef.current.style.height = 'auto';
          textareaRef.current.style.height = Math.min(textareaRef.current.scrollHeight, 96) + 'px';
          textareaRef.current.focus();
        }
      });
    },
  }), []);

  const { showMenu, handleSelect: handleSlashSelect, handleSubmit: handleSlashSubmitHook } = useSlashCommand(
    inputValue, setInputValue, handleSkillInvoke,
  );

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

  const handleFileSelect = useCallback(async (e: React.ChangeEvent<HTMLInputElement>) => {
    const selectedFiles = e.target.files;
    if (!selectedFiles || selectedFiles.length === 0) return;

    const fileList = Array.from(selectedFiles);
    const firstFile = fileList[0];
    const relPath = (firstFile as File & { webkitRelativePath?: string }).webkitRelativePath;
    const isFolder = Boolean(relPath);

    if (isFolder) {
      // 文件夹上传
      const topFolder = relPath!.split('/')[0];
      const itemId = `upload_${Date.now()}`;
      const totalSize = fileList.reduce((sum, f) => sum + f.size, 0);
      const showProgress = totalSize > 1024 * 1024;

      setUploadItems(prev => [...prev, {
        id: itemId, name: topFolder,
        percent: showProgress ? 0 : null,
        status: 'checking',
      }]);

      try {
        const onProgress: ProgressCallback | undefined = showProgress
          ? (loaded, total) => setUploadItems(prev =>
              prev.map(it => it.id === itemId ? { ...it, percent: Math.round(loaded / total * 100), status: 'uploading' } : it))
          : undefined;

        const result = await dirUploadFlow(topFolder, fileList, selectedAgent, onProgress);
        insertAtRef(result.path);
        setUploadItems(prev => prev.map(it => it.id === itemId ? { ...it, status: 'done', percent: 100 } : it));
      } catch (err) {
        setUploadItems(prev => prev.map(it => it.id === itemId
          ? { ...it, status: 'error', error: err instanceof Error ? err.message : '上传失败' } : it));
      }
    } else {
      // 单文件或多文件上传
      for (const file of fileList) {
        const itemId = `upload_${Date.now()}_${file.name}`;
        const showProgress = file.size > 1024 * 1024;

        setUploadItems(prev => [...prev, {
          id: itemId, name: file.name,
          percent: showProgress ? 0 : null,
          status: 'checking',
        }]);

        try {
          const onProgress: ProgressCallback | undefined = showProgress
            ? (loaded, total) => setUploadItems(prev =>
                prev.map(it => it.id === itemId ? { ...it, percent: Math.round(loaded / total * 100), status: 'uploading' } : it))
            : undefined;

          const result = await singleFileFlow(file, selectedAgent, onProgress);
          insertAtRef(result.path);
          setUploadItems(prev => prev.map(it => it.id === itemId ? { ...it, status: 'done', percent: 100 } : it));
        } catch (err) {
          setUploadItems(prev => prev.map(it => it.id === itemId
            ? { ...it, status: 'error', error: err instanceof Error ? err.message : '上传失败' } : it));
        }
      }
    }

    // 3秒后清除已完成的进度项
    setTimeout(() => {
      setUploadItems(prev => prev.filter(it => it.status !== 'done'));
    }, 3000);

    if (fileInputRef.current) fileInputRef.current.value = '';
    if (folderInputRef.current) folderInputRef.current.value = '';
  }, [selectedAgent, insertAtRef]);

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
    if (!content || !wsConnected || disabled) return;

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

    const contextFiles = parseAtRefs(content);
    onSend(content, contextFiles.length > 0 ? contextFiles : undefined, draftRecommendation);
    setDraftRecommendation(null);
    setInputValue('');
    if (textareaRef.current) textareaRef.current.style.height = 'auto';
  }, [inputValue, wsConnected, disabled, handleSlashSubmitHook, onSlashSubmit, onSend, parseAtRefs, draftRecommendation]);

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

  return (
    <div className="border-t bg-card/50 backdrop-blur-sm px-4 pt-2.5 pb-2 shrink-0 shadow-[0_-4px_16px_rgba(0,0,0,0.02)]">
      <div className="max-w-4xl mx-auto">
        <div className="flex items-center gap-3 mb-2 pl-1">
          {!hideAgentSelector && (
            <TargetSelector selectedAgent={selectedAgent} onSelectAgent={onSelectAgent} locked={lockAgent} />
          )}
          <span className="flex items-center gap-1.5 text-[11px] font-medium text-muted-foreground bg-muted/50 px-2 py-0.5 rounded-full border">
            <span className={`w-1.5 h-1.5 rounded-full ${wsConnected ? 'bg-green-500 shadow-[0_0_4px_rgba(34,197,94,0.6)]' : 'bg-red-500'}`} />
            {wsConnected ? 'Connected' : 'Offline'}
          </span>
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
              disabled={!wsConnected || disabled}
              className="w-8 h-8 rounded-lg flex items-center justify-center text-muted-foreground hover:text-foreground hover:bg-muted transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              title="添加文件引用"
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
                  <span>选择文件</span>
                </button>
                <button
                  className="flex items-center gap-2 w-full px-3 py-1.5 text-sm hover:bg-muted transition-colors text-left"
                  onClick={() => { folderInputRef.current?.click(); setShowUploadMenu(false); }}
                >
                  <FolderOpen size={14} className="text-muted-foreground" />
                  <span>选择文件夹</span>
                </button>
              </div>
            )}
          </div>

          <div className="flex-1">
            <UploadProgress items={uploadItems} />
            <SlashCommandMenu inputValue={inputValue} onSelect={handleSlashSelect} visible={showMenu} />
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
                  ? '输入消息… 拖拽文件插入 @引用 (Enter 发送)'
                  : 'Waiting for connection...'
              }
              disabled={!wsConnected || disabled}
              rows={1}
              className="w-full bg-transparent border-none px-4 py-2.5 text-[15px] text-foreground placeholder-muted-foreground/50 focus:outline-none focus:ring-0 resize-none disabled:opacity-50 disabled:cursor-not-allowed leading-relaxed"
              style={{ minHeight: '40px', maxHeight: '240px' }}
            />
          </div>
          {disabled && onStop ? (
            <button
              data-testid="stop-button"
              onClick={onStop}
              className="w-11 h-11 mb-0.5 mr-0.5 rounded-xl bg-red-500 text-white hover:bg-red-600 flex items-center justify-center shrink-0 transition-all active:scale-90 shadow-md shadow-red-500/20"
              title="停止生成"
            >
              <Square size={16} fill="currentColor" />
            </button>
          ) : (
            <button
              data-testid="send-button"
              onClick={handleSend}
              disabled={!inputValue.trim() || !wsConnected || disabled}
              className="w-11 h-11 mb-0.5 mr-0.5 rounded-xl bg-primary text-primary-foreground hover:bg-primary/90 flex items-center justify-center shrink-0 transition-all active:scale-90 disabled:opacity-50 disabled:active:scale-100 disabled:cursor-not-allowed shadow-md shadow-primary/20"
            >
              <Send size={20} className="ml-0.5" />
            </button>
          )}
        </div>
        <div className="text-center mt-2 text-[10px] text-muted-foreground/70">
          Sensenova-Claw can make mistakes. Consider verifying important information.
        </div>
      </div>
    </div>
  );
});
