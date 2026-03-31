'use client';

import { useCallback, useState, type KeyboardEvent } from 'react';
import { Bell, CircleAlert, CircleCheck, Info, X, ShieldAlert, HelpCircle, Send, Loader2 } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import { type UnifiedToast } from './NotificationProvider';

// ── ask_user 问题数据 ──

export interface QuestionData {
  question: string;
  options: string[] | null;
  multiSelect: boolean;
  interactionId: string;
  sessionId: string;
}

// ── 等级图标映射 ──

const levelIcon = {
  info: Info,
  warning: CircleAlert,
  error: CircleAlert,
  success: CircleCheck,
} as const;

// ── 动作类型图标映射 ──

const actionKindIcon: Record<string, typeof Bell> = {
  tool_confirmation: ShieldAlert,
  user_question: HelpCircle,
};

// ── ask_user 富交互弹窗（内嵌选项 + 自定义输入） ──

function QuestionToastBody({
  toast,
  onSubmit,
}: {
  toast: UnifiedToast;
  onSubmit: (actionValue: string, inputValue?: string) => void;
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
    if (answer) onSubmit(answer);
  };

  const cancel = () => {
    onSubmit('__cancelled__');
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
          data-testid="action-toast-input"
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
          data-testid="action-toast-submit"
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

// ── 单个统一 Toast 卡片 ──

interface ToastItemProps {
  toast: UnifiedToast;
  onDismiss: (id: string) => void;
  onAction: (toastId: string, actionValue: string, inputValue?: string) => void;
}

export function ToastItem({ toast, onDismiss, onAction }: ToastItemProps) {
  const Icon = actionKindIcon[toast.source] || levelIcon[toast.level] || Bell;
  const [inputValue, setInputValue] = useState('');
  const trimmedInput = inputValue.trim();
  const isPending = Boolean(toast.pending);

  const submitInput = () => {
    if (!trimmedInput || isPending) return;
    onAction(toast.id, trimmedInput, trimmedInput);
  };

  const handleKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key !== 'Enter' || event.shiftKey) return;
    event.preventDefault();
    submitInput();
  };

  // 处理 QuestionToastBody 的提交回调
  const handleQuestionSubmit = useCallback(
    (actionValue: string, inputVal?: string) => {
      onAction(toast.id, actionValue, inputVal);
    },
    [toast.id, onAction],
  );

  return (
    <div
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
        {/* 左侧图标 */}
        <div className={cn(
          'mt-0.5 rounded-xl p-2.5',
          toast.level === 'warning'
            ? 'bg-amber-500/10 text-amber-600 dark:text-amber-400'
            : toast.level === 'info'
              ? 'bg-sky-500/10 text-sky-600 dark:text-sky-400'
              : 'bg-neutral-500/10 text-neutral-600 dark:text-neutral-400',
        )}>
          <Icon size={18} />
        </div>

        {/* 内容区域 */}
        <div className="min-w-0 flex-1">
          {/* 标题 + 关闭按钮 */}
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

          {/* 富交互：ask_user 问答 */}
          {toast.source === 'user_question' && toast.questionData ? (
            <QuestionToastBody toast={toast} onSubmit={handleQuestionSubmit} />
          ) : (
            <>
              {/* 消息正文 */}
              <p className="mt-1.5 text-[13px] leading-relaxed text-foreground/70 line-clamp-2">
                {toast.body}
              </p>

              {/* pending 状态提示 */}
              {isPending && (
                <div className="mt-3 flex items-center gap-2 rounded-lg border border-amber-300/60 bg-amber-500/10 px-3 py-2 text-xs text-amber-700 dark:text-amber-300">
                  <Loader2 size={12} className="animate-spin shrink-0" />
                  已提交，等待服务端确认…
                </div>
              )}

              {/* 自定义输入框（allowsInput 且非 pending） */}
              {toast.allowsInput && !isPending && (
                <div className="mt-3 space-y-2">
                  <textarea
                    data-testid="action-toast-input"
                    value={inputValue}
                    onChange={(event) => setInputValue(event.target.value)}
                    onKeyDown={handleKeyDown}
                    placeholder={toast.inputPlaceholder || '请输入回复'}
                    className="min-h-[88px] w-full resize-none rounded-lg border border-neutral-200 dark:border-neutral-700 bg-background px-3 py-2 text-sm text-foreground outline-none transition-colors focus:border-sky-400 dark:focus:border-sky-500"
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

              {/* 操作按钮组（非 pending） */}
              {toast.actions && toast.actions.length > 0 && !isPending && (
                <div className="mt-3 flex flex-wrap gap-2">
                  {toast.actions.map((action) => (
                    <button
                      key={action.value}
                      data-testid="action-toast-button"
                      type="button"
                      onClick={() => onAction(toast.id, action.value)}
                      className={cn(
                        'max-w-full rounded-lg border px-4 py-1.5 text-left text-xs font-semibold leading-relaxed whitespace-normal break-all transition-all hover:scale-[1.02] active:scale-[0.98]',
                        action.value === 'approve' || action.value === 'accept'
                          ? 'border-emerald-300 bg-emerald-500 text-white shadow-sm shadow-emerald-200 dark:shadow-emerald-900 hover:bg-emerald-600'
                          : action.value === 'deny' || action.value === 'reject'
                            ? 'border-rose-200 dark:border-rose-800 bg-background text-rose-600 dark:text-rose-400 hover:bg-rose-50 dark:hover:bg-rose-950'
                            : action.value === 'view_session'
                              ? 'border-violet-300 bg-violet-500 text-white shadow-sm shadow-violet-200 dark:shadow-violet-900 hover:bg-violet-600'
                              : 'border-neutral-200 dark:border-neutral-700 bg-background text-neutral-700 dark:text-neutral-300 hover:bg-neutral-50 dark:hover:bg-neutral-800',
                      )}
                    >
                      {action.label}
                    </button>
                  ))}
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}

// ── 统一 Toast 容器 ──

interface ToastContainerProps {
  toasts: UnifiedToast[];
  onDismiss: (id: string) => void;
  onMarkPending: (id: string) => void;
}

export function ToastContainer({ toasts, onDismiss, onMarkPending }: ToastContainerProps) {
  const handleAction = useCallback(
    (toastId: string, actionValue: string, inputValue?: string) => {
      const toast = toasts.find((t) => t.id === toastId);
      if (!toast) return;
      // onAction 返回 true 表示需要等待服务端确认（进入 pending 状态）
      // 否则直接关闭 toast（如 view_session 等纯前端操作）
      const needsPending = toast.onAction?.(actionValue, inputValue);
      if (needsPending === true) {
        onMarkPending(toastId);
      } else {
        onDismiss(toastId);
      }
    },
    [toasts, onMarkPending, onDismiss],
  );

  if (toasts.length === 0) return null;

  return (
    <div
      className="fixed right-4 top-16 z-[300] flex flex-col gap-3 pointer-events-auto"
      style={{ width: 'min(28rem, calc(100vw - 2rem))' }}
    >
      {toasts.slice(0, 5).map((toast) => (
        <ToastItem
          key={toast.id}
          toast={toast}
          onDismiss={onDismiss}
          onAction={handleAction}
        />
      ))}
    </div>
  );
}
