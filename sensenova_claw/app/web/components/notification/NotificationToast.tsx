'use client';

import { useState, type KeyboardEvent } from 'react';
import { Bell, CircleAlert, CircleCheck, Info, X, ShieldAlert, HelpCircle, Send } from 'lucide-react';

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

// ── ask_user 问题数据 ──

export interface QuestionData {
  question: string;
  options: string[] | null;
  multiSelect: boolean;
  interactionId: string;
  sessionId: string;
}

// ── 带操作按钮的弹窗 ──

export interface ActionToast {
  id: string;
  title: string;
  body: string;
  level: 'info' | 'warning' | 'error' | 'success';
  source: string;
  createdAtMs: number;
  actions: { label: string; value: string }[];
  // 关联的通知卡片 ID
  cardId: string;
  // ask_user 富交互数据
  questionData?: QuestionData;
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

// ── ask_user 富交互弹窗（内嵌选项 + 自定义输入） ──

function QuestionToastBody({
  toast,
  onAction,
}: {
  toast: ActionToast;
  onAction: (toastId: string, cardId: string, actionValue: string) => void;
}) {
  const qd = toast.questionData!;
  const [customInput, setCustomInput] = useState('');
  const [singleChoice, setSingleChoice] = useState('');
  const [multiChoices, setMultiChoices] = useState<string[]>([]);

  const toggleMulti = (opt: string) => {
    setMultiChoices(prev =>
      prev.includes(opt) ? prev.filter(v => v !== opt) : [...prev, opt],
    );
  };

  const getAnswer = (): string | null => {
    const custom = customInput.trim();
    if (custom) return custom;
    if (qd.options && qd.options.length > 0) {
      if (qd.multiSelect) {
        return multiChoices.length > 0 ? multiChoices.join(', ') : null;
      }
      return singleChoice || null;
    }
    return null;
  };

  const submit = () => {
    const answer = getAnswer();
    if (answer) onAction(toast.id, toast.cardId, answer);
  };

  const cancel = () => {
    onAction(toast.id, toast.cardId, '__cancelled__');
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      submit();
    }
  };

  return (
    <div className="mt-2 space-y-2.5">
      {/* 问题文本 */}
      <p className="text-[13px] leading-relaxed text-foreground/80 whitespace-pre-wrap">
        {qd.question}
      </p>

      {/* 选项 */}
      {qd.options && qd.options.length > 0 && (
        <div className="space-y-1.5">
          <div className="text-[11px] text-muted-foreground">
            {qd.multiSelect ? '可多选' : '可单选'}
          </div>
          <div className="space-y-1">
            {qd.options.map((opt, idx) => (
              <label
                key={`${opt}_${idx}`}
                className="flex items-center gap-2 text-[13px] text-foreground/80 cursor-pointer hover:text-foreground transition-colors"
              >
                {qd.multiSelect ? (
                  <input
                    type="checkbox"
                    checked={multiChoices.includes(opt)}
                    onChange={() => toggleMulti(opt)}
                    className="accent-sky-500 h-3.5 w-3.5"
                  />
                ) : (
                  <input
                    type="radio"
                    name={`toast-q-${toast.id}`}
                    checked={singleChoice === opt}
                    onChange={() => setSingleChoice(opt)}
                    className="accent-sky-500 h-3.5 w-3.5"
                  />
                )}
                <span>{opt}</span>
              </label>
            ))}
          </div>
        </div>
      )}

      {/* 自定义输入 */}
      <div className="space-y-1">
        <div className="text-[11px] text-muted-foreground">
          {qd.options && qd.options.length > 0 ? '自定义输入（优先级高于选项）' : '请输入回复'}
        </div>
        <textarea
          value={customInput}
          onChange={e => setCustomInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="输入你的回复..."
          rows={2}
          className="w-full rounded-lg border border-neutral-200 bg-white px-3 py-1.5 text-[13px] text-foreground placeholder-muted-foreground/50 focus:outline-none focus:border-sky-400 resize-none"
        />
      </div>

      {/* 操作按钮 */}
      <div className="flex gap-2">
        <button
          type="button"
          onClick={cancel}
          className="rounded-lg border border-neutral-200 bg-white px-3 py-1.5 text-xs font-medium text-neutral-600 hover:bg-neutral-50 transition-colors"
        >
          取消
        </button>
        <button
          type="button"
          onClick={submit}
          disabled={!getAnswer()}
          className={cn(
            'flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-xs font-semibold transition-all',
            getAnswer()
              ? 'border-sky-300 bg-sky-500 text-white shadow-sm shadow-sky-200 hover:bg-sky-600'
              : 'border-neutral-200 bg-neutral-100 text-neutral-400 cursor-not-allowed',
          )}
        >
          <Send size={12} />
          确认
        </button>
      </div>
    </div>
  );
}

// ── 操作弹窗（不自动消失，需要用户操作） ──

export function ActionToastPanel({
  toasts,
  onAction,
  onDismiss,
}: {
  toasts: ActionToast[];
  onAction: (toastId: string, cardId: string, actionValue: string) => void;
  onDismiss: (toastId: string) => void;
}) {
  if (toasts.length === 0) return null;

  // 只显示前 5 个，剩余的在处理后自动补位
  const visibleToasts = toasts.slice(0, 5);

  return (
    <div className="pointer-events-none fixed right-4 top-16 z-[300] flex w-[min(24rem,calc(100vw-2rem))] flex-col gap-3">
      {visibleToasts.map((toast) => {
        const Icon = actionKindIcon[toast.source] || levelIcon[toast.level] || Bell;
        const isQuestion = toast.source === 'user_question' && !!toast.questionData;
        return (
          <div
            key={toast.id}
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

                {isQuestion ? (
                  /* ask_user 富交互 */
                  <QuestionToastBody toast={toast} onAction={onAction} />
                ) : (
                  /* 默认：简单按钮 */
                  <>
                    <p className="mt-1.5 text-[13px] leading-relaxed text-foreground/70 line-clamp-2">
                      {toast.body}
                    </p>
                    <div className="mt-3 flex gap-2">
                      {toast.actions.map((action) => (
                        <button
                          key={action.value}
                          type="button"
                          onClick={() => onAction(toast.id, toast.cardId, action.value)}
                          className={cn(
                            'rounded-lg border px-4 py-1.5 text-xs font-semibold transition-all hover:scale-[1.02] active:scale-[0.98]',
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
                  </>
                )}
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}
