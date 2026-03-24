'use client';

import { useState, type KeyboardEvent } from 'react';

import { Bell, CircleAlert, CircleCheck, Info, X, ShieldAlert, HelpCircle } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';

export interface ToastNotification {
  id: string;
  title: string;
  body: string;
  level: 'info' | 'warning' | 'error' | 'success';
  source: string;
  createdAtMs: number;
}

// ── 带操作按钮的弹窗 ──

export interface ActionToast {
  id: string;
  title: string;
  body: string;
  level: 'info' | 'warning' | 'error' | 'success';
  source: string;
  createdAtMs: number;
  actions?: { label: string; value: string }[];
  allowsInput?: boolean;
  inputPlaceholder?: string;
  // 关联的通知卡片 ID
  cardId: string;
}

const levelIcon = {
  info: Info,
  warning: CircleAlert,
  error: CircleAlert,
  success: CircleCheck,
} as const;

const levelStyles = {
  info: 'border-sky-500/30 bg-sky-500/10 text-sky-700 dark:text-sky-300',
  warning: 'border-amber-500/30 bg-amber-500/10 text-amber-700 dark:text-amber-300',
  error: 'border-rose-500/30 bg-rose-500/10 text-rose-700 dark:text-rose-300',
  success: 'border-emerald-500/30 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300',
} as const;

const actionKindIcon: Record<string, typeof Bell> = {
  tool_confirmation: ShieldAlert,
  user_question: HelpCircle,
};

// ── 普通 Toast（自动消失） ──

export function NotificationToast({
  notifications,
  dismissNotification,
}: {
  notifications: ToastNotification[];
  dismissNotification: (id: string) => void;
}) {
  if (notifications.length === 0) {
    return null;
  }

  return (
    <div className="pointer-events-none fixed right-4 top-20 z-[250] flex w-[min(28rem,calc(100vw-2rem))] flex-col gap-3">
      {notifications.map((notification) => {
        const Icon = levelIcon[notification.level] ?? Bell;
        return (
          <div
            key={notification.id}
            className={cn(
              'pointer-events-auto rounded-2xl border shadow-2xl backdrop-blur-sm',
              'bg-background/95',
              levelStyles[notification.level],
            )}
          >
            <div className="flex items-start gap-3 p-4">
              <div className="mt-0.5 rounded-full bg-background/80 p-2 text-current">
                <Icon size={16} />
              </div>
              <div className="min-w-0 flex-1">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <p className="text-sm font-bold text-foreground">{notification.title}</p>
                    <p className="mt-1 text-xs font-semibold uppercase tracking-[0.18em] text-muted-foreground">
                      {notification.source}
                    </p>
                  </div>
                  <Button
                    variant="ghost"
                    size="icon-sm"
                    className="h-7 w-7 shrink-0 rounded-full"
                    onClick={() => dismissNotification(notification.id)}
                  >
                    <X size={14} />
                  </Button>
                </div>
                <p className="mt-3 whitespace-pre-wrap text-sm leading-relaxed text-foreground/80">
                  {notification.body}
                </p>
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}

// ── 操作弹窗（不自动消失，需要用户操作） ──

function ActionToastItem({
  toast,
  onAction,
  onDismiss,
}: {
  toast: ActionToast;
  onAction: (toastId: string, cardId: string, actionValue: string, inputValue?: string) => void;
  onDismiss: (toastId: string) => void;
}) {
  const Icon = actionKindIcon[toast.source] || levelIcon[toast.level] || Bell;
  const [inputValue, setInputValue] = useState('');
  const trimmedInput = inputValue.trim();

  const submitInput = () => {
    if (!trimmedInput) return;
    onAction(toast.id, toast.cardId, trimmedInput, trimmedInput);
  };

  const handleKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key !== 'Enter' || event.shiftKey) return;
    event.preventDefault();
    submitInput();
  };

  return (
    <div
      key={toast.id}
      data-testid="action-toast"
      className={cn(
        'pointer-events-auto rounded-2xl border-2 shadow-[0_20px_60px_rgba(15,23,42,0.2)] backdrop-blur-xl animate-in slide-in-from-top-4 fade-in duration-300',
        'bg-background/98',
        toast.level === 'warning'
          ? 'border-amber-400/60'
          : toast.level === 'info'
            ? 'border-sky-400/60'
            : 'border-neutral-300/60',
      )}
    >
      <div className="flex items-start gap-3 p-4">
        <div className={cn(
          'mt-0.5 rounded-xl p-2.5',
          toast.level === 'warning'
            ? 'bg-amber-500/10 text-amber-600'
            : toast.level === 'info'
              ? 'bg-sky-500/10 text-sky-600'
              : 'bg-neutral-500/10 text-neutral-600',
        )}>
          <Icon size={18} />
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex items-start justify-between gap-2">
            <p className="text-sm font-bold text-foreground">{toast.title}</p>
            <Button
              variant="ghost"
              size="icon-sm"
              className="h-6 w-6 shrink-0 rounded-full opacity-50 hover:opacity-100"
              onClick={() => onDismiss(toast.id)}
            >
              <X size={12} />
            </Button>
          </div>
          <p className="mt-1.5 text-[13px] leading-relaxed text-foreground/70 line-clamp-2">
            {toast.body}
          </p>
          {toast.allowsInput && (
            <div className="mt-3 space-y-2">
              <textarea
                data-testid="action-toast-input"
                value={inputValue}
                onChange={(event) => setInputValue(event.target.value)}
                onKeyDown={handleKeyDown}
                placeholder={toast.inputPlaceholder || '请输入回复'}
                className="min-h-[88px] w-full resize-none rounded-lg border border-neutral-200 bg-white px-3 py-2 text-sm text-foreground outline-none transition-colors focus:border-sky-400"
                rows={3}
              />
              <div className="flex items-center justify-between gap-2">
                <span className="text-[11px] text-muted-foreground">Enter 提交，Shift+Enter 换行</span>
                <button
                  data-testid="action-toast-submit"
                  type="button"
                  onClick={submitInput}
                  disabled={!trimmedInput}
                  className="rounded-lg border border-sky-300 bg-sky-500 px-3 py-1.5 text-xs font-semibold text-white transition-colors hover:bg-sky-600 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  确认
                </button>
              </div>
            </div>
          )}
          {toast.actions && toast.actions.length > 0 && (
            <div className="mt-3 flex flex-wrap gap-2">
              {toast.actions.map((action) => (
                <button
                  key={action.value}
                  data-testid="action-toast-button"
                  type="button"
                  onClick={() => onAction(toast.id, toast.cardId, action.value)}
                  className={cn(
                    'max-w-full rounded-lg border px-4 py-1.5 text-left text-xs font-semibold leading-relaxed whitespace-normal break-all transition-all hover:scale-[1.02] active:scale-[0.98]',
                    action.value === 'approve' || action.value === 'accept'
                      ? 'border-emerald-300 bg-emerald-500 text-white shadow-sm shadow-emerald-200 hover:bg-emerald-600'
                      : action.value === 'deny' || action.value === 'reject'
                        ? 'border-rose-200 bg-white text-rose-600 hover:bg-rose-50'
                        : action.value === 'view_session'
                          ? 'border-violet-300 bg-violet-500 text-white shadow-sm shadow-violet-200 hover:bg-violet-600'
                          : 'border-neutral-200 bg-white text-neutral-700 hover:bg-neutral-50',
                  )}
                >
                  {action.label}
                </button>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export function ActionToastPanel({
  toasts,
  onAction,
  onDismiss,
}: {
  toasts: ActionToast[];
  onAction: (toastId: string, cardId: string, actionValue: string, inputValue?: string) => void;
  onDismiss: (toastId: string) => void;
}) {
  if (toasts.length === 0) return null;

  return (
    <div className="pointer-events-none fixed right-4 top-16 z-[300] flex w-[min(24rem,calc(100vw-2rem))] flex-col gap-3">
      {toasts.map((toast) => (
        <ActionToastItem
          key={toast.id}
          toast={toast}
          onAction={onAction}
          onDismiss={onDismiss}
        />
      ))}
    </div>
  );
}
