'use client';

import { useRef, useState, useCallback } from 'react';
import { Send, X, FileText } from 'lucide-react';
import { useDrop } from 'react-dnd';
import { TargetSelector } from './TargetSelector';
import { SlashCommandMenu, useSlashCommand } from './SlashCommandMenu';
import { type ContextFileRef } from '@/lib/chatTypes';

interface ChatInputProps {
  defaultAgentId: string;
  selectedAgent: string;
  onSelectAgent: (id: string) => void;
  onSend: (content: string, contextFiles?: ContextFileRef[]) => void;
  onSlashSubmit: (content: string) => boolean;
  disabled: boolean;
  wsConnected: boolean;
  handleSkillInvoke: (skillName: string, args: string) => void;
}

export function ChatInput({
  defaultAgentId,
  selectedAgent,
  onSelectAgent,
  onSend,
  onSlashSubmit,
  disabled,
  wsConnected,
  handleSkillInvoke,
}: ChatInputProps) {
  const [inputValue, setInputValue] = useState('');
  const [droppedFiles, setDroppedFiles] = useState<ContextFileRef[]>([]);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const { showMenu, handleSelect: handleSlashSelect, handleSubmit: handleSlashSubmitHook } = useSlashCommand(
    inputValue, setInputValue, handleSkillInvoke,
  );

  // react-dnd drop target
  const [{ isOver }, dropRef] = useDrop(() => ({
    accept: 'FILE',
    drop: (item: { name: string; path: string }) => {
      setDroppedFiles(prev => {
        if (prev.some(f => f.path === item.path)) return prev;
        return [...prev, { name: item.name, path: item.path }];
      });
    },
    collect: (monitor) => ({
      isOver: monitor.isOver(),
    }),
  }), []);

  const removeFile = (path: string) => {
    setDroppedFiles(prev => prev.filter(f => f.path !== path));
  };

  const handleSend = useCallback(() => {
    const content = inputValue.trim();
    if (!content || !wsConnected || disabled) return;

    // 斜杠命令拦截
    if (handleSlashSubmitHook(content)) {
      setInputValue('');
      if (textareaRef.current) textareaRef.current.style.height = 'auto';
      return;
    }

    if (onSlashSubmit(content)) {
      setInputValue('');
      if (textareaRef.current) textareaRef.current.style.height = 'auto';
      return;
    }

    onSend(content, droppedFiles.length > 0 ? droppedFiles : undefined);
    setInputValue('');
    setDroppedFiles([]);
    if (textareaRef.current) textareaRef.current.style.height = 'auto';
  }, [inputValue, wsConnected, disabled, handleSlashSubmitHook, onSlashSubmit, onSend, droppedFiles]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend(); }
  };

  const handleInput = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setInputValue(e.target.value);
    const ta = e.target;
    ta.style.height = 'auto';
    ta.style.height = Math.min(ta.scrollHeight, 120) + 'px';
  };

  return (
    <div className="border-t bg-card/50 backdrop-blur-sm p-4 shrink-0 shadow-[0_-4px_16px_rgba(0,0,0,0.02)]">
      <div className="max-w-4xl mx-auto">
        <div className="flex items-center gap-3 mb-3 pl-1">
          <TargetSelector selectedAgent={selectedAgent} onSelectAgent={onSelectAgent} />
          <span className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground bg-muted/50 px-2 py-1 rounded-full border">
            <span className={`w-2 h-2 rounded-full ${wsConnected ? 'bg-green-500 shadow-[0_0_6px_rgba(34,197,94,0.6)]' : 'bg-red-500'}`} />
            {wsConnected ? 'Connected' : 'Offline'}
          </span>
        </div>

        {/* 已拖入的文件 Badge */}
        {droppedFiles.length > 0 && (
          <div className="flex flex-wrap gap-2 mb-2 pl-1">
            {droppedFiles.map(f => (
              <span key={f.path} className="flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-primary/10 text-primary text-xs font-medium border border-primary/20">
                <FileText size={12} />
                <span className="max-w-[120px] truncate">{f.name}</span>
                <button onClick={() => removeFile(f.path)} className="hover:text-destructive transition-colors">
                  <X size={12} />
                </button>
              </span>
            ))}
          </div>
        )}

        <div
          ref={dropRef as unknown as React.Ref<HTMLDivElement>}
          className={`flex items-end gap-3 bg-background border rounded-[2rem] shadow-xl focus-within:ring-4 focus-within:ring-primary/10 focus-within:border-primary transition-all p-3 relative ${
            isOver ? 'border-primary bg-primary/5 ring-4 ring-primary/20' : 'border-border/80'
          }`}
        >
          <div className="flex-1">
            <SlashCommandMenu inputValue={inputValue} onSelect={handleSlashSelect} visible={showMenu} />
            <textarea
              ref={textareaRef}
              value={inputValue}
              onChange={handleInput}
              onKeyDown={handleKeyDown}
              placeholder={
                wsConnected
                  ? 'Message AgentOS... (Enter to send, Shift+Enter for new line)'
                  : 'Waiting for connection...'
              }
              disabled={!wsConnected || disabled}
              rows={1}
              className="w-full bg-transparent border-none px-5 py-4 text-lg text-foreground placeholder-muted-foreground/50 focus:outline-none focus:ring-0 resize-none disabled:opacity-50 disabled:cursor-not-allowed leading-relaxed"
              style={{ minHeight: '56px', maxHeight: '300px' }}
            />
          </div>
          <button
            onClick={handleSend}
            disabled={!inputValue.trim() || !wsConnected || disabled}
            className="w-14 h-14 mb-1 mr-1 rounded-2xl bg-primary text-primary-foreground hover:bg-primary/90 flex items-center justify-center shrink-0 transition-all active:scale-90 disabled:opacity-50 disabled:active:scale-100 disabled:cursor-not-allowed shadow-lg shadow-primary/20"
          >
            <Send size={24} className="ml-1" />
          </button>
        </div>
        <div className="text-center mt-3 text-[10px] text-muted-foreground/70">
          AgentOS can make mistakes. Consider verifying important information.
        </div>
      </div>
    </div>
  );
}
