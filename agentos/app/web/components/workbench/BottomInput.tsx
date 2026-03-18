'use client';

import { useState } from 'react';
import { Send, Mail, Calendar, FileText, BarChart } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';

interface BottomInputProps {
  onSubmit?: (message: string) => void;
  disabled?: boolean;
  connected?: boolean;
}

const quickActions = [
  { id: 'email', label: '写邮件', icon: Mail },
  { id: 'meeting', label: '安排会议', icon: Calendar },
  { id: 'summary', label: '总结文档', icon: FileText },
  { id: 'report', label: '生成周报', icon: BarChart },
];

export function BottomInput({ onSubmit, disabled, connected = true }: BottomInputProps) {
  const [message, setMessage] = useState('');

  const handleSubmit = () => {
    const content = message.trim();
    if (!content || disabled) return;
    onSubmit?.(content);
    setMessage('');
  };

  const handleQuickAction = (label: string) => {
    if (disabled) return;
    onSubmit?.(label);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  return (
    <div className="border-t border-border bg-card/50 backdrop-blur-sm shrink-0">
      {/* 快捷意图 */}
      <div className="px-4 pt-3 pb-2 border-b border-border">
        <div className="flex gap-2">
          {quickActions.map((action) => {
            const Icon = action.icon;
            return (
              <Button
                key={action.id}
                variant="outline"
                size="sm"
                onClick={() => handleQuickAction(action.label)}
                disabled={disabled}
                className="gap-1.5 text-xs"
              >
                <Icon className="w-3.5 h-3.5" />
                {action.label}
              </Button>
            );
          })}
        </div>
      </div>

      {/* 输入区 */}
      <div className="p-4">
        <div className="flex items-center gap-2 mb-2">
          <span className={cn(
            'flex items-center gap-1.5 text-xs font-medium px-2 py-1 rounded-full border',
            connected
              ? 'text-muted-foreground bg-muted/50'
              : 'text-destructive bg-destructive/10 border-destructive/20'
          )}>
            <span className={cn(
              'w-2 h-2 rounded-full',
              connected ? 'bg-green-500 shadow-[0_0_6px_rgba(34,197,94,0.6)]' : 'bg-red-500'
            )} />
            {connected ? '已连接' : '未连接'}
          </span>
        </div>

        <div className="flex items-end gap-3 bg-background border border-border/80 rounded-2xl shadow-sm focus-within:ring-2 focus-within:ring-primary/10 focus-within:border-primary transition-all p-3">
          <textarea
            value={message}
            onChange={(e) => setMessage(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={connected ? '描述你需要完成的任务...' : '等待连接...'}
            disabled={disabled || !connected}
            rows={1}
            className="flex-1 bg-transparent border-none px-3 py-2 text-sm text-foreground placeholder-muted-foreground/50 focus:outline-none focus:ring-0 resize-none disabled:opacity-50 disabled:cursor-not-allowed min-h-[40px] max-h-[120px]"
          />
          <Button
            onClick={handleSubmit}
            size="icon"
            disabled={!message.trim() || disabled || !connected}
            className="shrink-0 w-10 h-10 rounded-xl"
          >
            <Send className="w-4 h-4" />
          </Button>
        </div>
        <p className="text-[10px] text-muted-foreground/70 mt-2 px-3">
          按 Enter 发送，Shift + Enter 换行
        </p>
      </div>
    </div>
  );
}
