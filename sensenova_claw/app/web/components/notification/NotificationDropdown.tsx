'use client';

import { useState, useRef, useEffect, useCallback, type KeyboardEvent } from 'react';
import { useRouter } from 'next/navigation';
import {
  Bell,
  CheckCircle2,
  HelpCircle,
  ShieldAlert,
  Lightbulb,
  Info,
  Check,
  X,
  Trash2,
  Send,
} from 'lucide-react';
import { useNotification } from '@/hooks/useNotification';
import { useChatSession } from '@/contexts/ChatSessionContext';
import type { NotificationCard, NotificationCardKind } from '@/components/notification/NotificationProvider';

// ── 卡片图标 & 配色 ──

const kindConfig: Record<NotificationCardKind, {
  icon: typeof Bell;
  color: string;
  bg: string;
  border: string;
}> = {
  task_completed: {
    icon: CheckCircle2,
    color: 'text-emerald-600',
    bg: 'bg-emerald-50',
    border: 'border-emerald-200',
  },
  user_question: {
    icon: HelpCircle,
    color: 'text-sky-600',
    bg: 'bg-sky-50',
    border: 'border-sky-200',
  },
  tool_confirmation: {
    icon: ShieldAlert,
    color: 'text-amber-600',
    bg: 'bg-amber-50',
    border: 'border-amber-200',
  },
  proactive: {
    icon: Lightbulb,
    color: 'text-violet-600',
    bg: 'bg-violet-50',
    border: 'border-violet-200',
  },
  general: {
    icon: Info,
    color: 'text-neutral-600',
    bg: 'bg-neutral-50',
    border: 'border-neutral-200',
  },
};

function timeAgo(ms: number): string {
  const diff = Date.now() - ms;
  const sec = Math.floor(diff / 1000);
  if (sec < 60) return '刚刚';
  const min = Math.floor(sec / 60);
  if (min < 60) return `${min} 分钟前`;
  const hour = Math.floor(min / 60);
  if (hour < 24) return `${hour} 小时前`;
  return `${Math.floor(hour / 24)} 天前`;
}

// ── ask_user 卡片内嵌输入 ──

function QuestionCardInput({
  card,
  onSubmit,
}: {
  card: NotificationCard;
  onSubmit: (cardId: string, answer: string) => void;
}) {
  const qd = card.questionData!;
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
      if (qd.multiSelect) return multiChoices.length > 0 ? multiChoices.join(', ') : null;
      return singleChoice || null;
    }
    return null;
  };

  const submit = () => {
    const answer = getAnswer();
    if (answer) onSubmit(card.id, answer);
  };

  const cancel = () => {
    onSubmit(card.id, '__cancelled__');
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      submit();
    }
  };

  return (
    <div className="mt-2 space-y-2">
      {/* 选项 */}
      {qd.options && qd.options.length > 0 && (
        <div className="space-y-1">
          {qd.options.map((opt, idx) => (
            <label
              key={`${opt}_${idx}`}
              className="flex items-center gap-1.5 text-[11px] text-neutral-600 cursor-pointer hover:text-neutral-800"
            >
              {qd.multiSelect ? (
                <input
                  type="checkbox"
                  checked={multiChoices.includes(opt)}
                  onChange={() => toggleMulti(opt)}
                  className="accent-sky-500 h-3 w-3"
                />
              ) : (
                <input
                  type="radio"
                  name={`card-q-${card.id}`}
                  checked={singleChoice === opt}
                  onChange={() => setSingleChoice(opt)}
                  className="accent-sky-500 h-3 w-3"
                />
              )}
              <span>{opt}</span>
            </label>
          ))}
        </div>
      )}

      {/* 自定义输入 */}
      <textarea
        value={customInput}
        onChange={e => setCustomInput(e.target.value)}
        onKeyDown={handleKeyDown}
        placeholder="输入回复..."
        rows={2}
        className="w-full rounded-md border border-neutral-200 bg-white px-2 py-1 text-[11px] text-neutral-700 placeholder-neutral-400 focus:outline-none focus:border-sky-400 resize-none"
      />

      {/* 操作按钮 */}
      <div className="flex gap-1.5">
        <button
          type="button"
          onClick={cancel}
          className="rounded-md border border-neutral-200 bg-white px-2 py-0.5 text-[10px] font-medium text-neutral-500 hover:bg-neutral-50"
        >
          取消
        </button>
        <button
          type="button"
          onClick={submit}
          disabled={!getAnswer()}
          className={`flex items-center gap-1 rounded-md border px-2 py-0.5 text-[10px] font-semibold transition-colors ${
            getAnswer()
              ? 'border-sky-200 bg-sky-500 text-white hover:bg-sky-600'
              : 'border-neutral-200 bg-neutral-100 text-neutral-400 cursor-not-allowed'
          }`}
        >
          <Send className="h-2.5 w-2.5" />
          确认
        </button>
      </div>
    </div>
  );
}

function NotificationCardItem({
  card,
  onResolve,
  onDismiss,
  onNavigate,
}: {
  card: NotificationCard;
  onResolve: (id: string, action?: string) => void;
  onDismiss: (id: string) => void;
  onNavigate: (sessionId: string) => void;
}) {
  const config = kindConfig[card.kind] || kindConfig.general;
  const Icon = config.icon;

  return (
    <div
      className={`group relative rounded-xl border px-3 py-2.5 transition-all ${
        card.resolved
          ? 'border-neutral-100 bg-neutral-50/50 opacity-60'
          : card.read
            ? `${config.border} ${config.bg}/50`
            : `${config.border} ${config.bg}`
      }`}
    >
      <div className="flex items-start gap-2.5">
        {/* 图标 */}
        <div className={`mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-lg ${config.bg} ${config.color}`}>
          <Icon className="h-3.5 w-3.5" />
        </div>

        {/* 内容 */}
        <div className="min-w-0 flex-1">
          <div className="flex items-start justify-between gap-1">
            <span className="text-xs font-semibold text-neutral-800 leading-tight">{card.title}</span>
            {!card.read && !card.resolved && (
              <span className="mt-0.5 h-1.5 w-1.5 shrink-0 rounded-full bg-violet-500" />
            )}
          </div>
          <p className="mt-0.5 text-[11px] text-neutral-500 leading-relaxed line-clamp-2">{card.body}</p>
          <div className="mt-1.5 flex items-center gap-2">
            <span className="text-[10px] text-neutral-400">{timeAgo(card.createdAtMs)}</span>
            {card.source && (
              <span className="text-[10px] text-neutral-400">· {card.source}</span>
            )}
          </div>

          {/* ask_user 富交互输入 */}
          {!card.resolved && card.kind === 'user_question' && card.questionData && (
            <QuestionCardInput card={card} onSubmit={onResolve} />
          )}

          {/* 其他类型的操作按钮 */}
          {!card.resolved && card.kind !== 'user_question' && card.actions && card.actions.length > 0 && (
            <div className="mt-2 flex flex-wrap gap-1.5">
              {card.actions.map((action) => (
                <button
                  key={action.value}
                  type="button"
                  onClick={(e) => { e.stopPropagation(); onResolve(card.id, action.value); }}
                  className={`rounded-lg border px-2 py-1 text-[11px] font-medium transition-colors ${
                    action.value === 'approve' || action.value === 'accept'
                      ? 'border-emerald-200 bg-emerald-50 text-emerald-700 hover:bg-emerald-100'
                      : action.value === 'deny' || action.value === 'reject'
                        ? 'border-rose-200 bg-rose-50 text-rose-700 hover:bg-rose-100'
                        : 'border-neutral-200 bg-white text-neutral-700 hover:bg-neutral-50'
                  }`}
                >
                  {action.label}
                </button>
              ))}
            </div>
          )}

          {/* 已处理状态 */}
          {card.resolved && card.resolvedAction && (
            <div className="mt-1.5 flex items-center gap-1 text-[10px] text-neutral-400">
              <Check className="h-3 w-3" />
              <span>
                {card.resolvedAction === 'approve' ? '已批准' :
                 card.resolvedAction === 'deny' ? '已拒绝' :
                 `已处理: ${card.resolvedAction}`}
              </span>
            </div>
          )}

          {/* 跳转到会话 */}
          {card.sessionId && !card.resolved && (
            <button
              type="button"
              onClick={(e) => { e.stopPropagation(); onNavigate(card.sessionId!); }}
              className="mt-1.5 text-[10px] font-medium text-violet-600 hover:text-violet-700 transition-colors"
            >
              查看会话 →
            </button>
          )}
        </div>

        {/* 关闭按钮 */}
        <button
          type="button"
          onClick={() => onDismiss(card.id)}
          className="shrink-0 rounded-md p-0.5 text-neutral-300 opacity-0 transition-all hover:bg-neutral-100 hover:text-neutral-500 group-hover:opacity-100"
        >
          <X className="h-3 w-3" />
        </button>
      </div>
    </div>
  );
}

export function NotificationDropdown() {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const router = useRouter();
  const {
    cards,
    unreadCount,
    markAllRead,
    resolveCard,
    dismissCard,
    clearAllCards,
    setOnActionToastAction,
  } = useNotification();
  const { switchSession, wsSend, resolveInteractionFromNotification } = useChatSession();

  // 点击外部关闭
  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    if (open) document.addEventListener('mousedown', handleClick);
    return () => document.removeEventListener('mousedown', handleClick);
  }, [open]);

  const handleOpen = () => {
    setOpen(!open);
    if (!open) markAllRead();
  };

  const handleNavigate = async (sessionId: string) => {
    setOpen(false);
    await switchSession(sessionId);
    router.push('/');
  };

  // 处理卡片操作：根据类型发送 WebSocket 响应
  const handleResolve = useCallback((cardId: string, action?: string) => {
    const card = cards.find(c => c.id === cardId);
    if (!card || card.resolved) return;

    if (card.kind === 'tool_confirmation' && card.interactionId && card.sessionId) {
      // 发送工具确认响应
      wsSend({
        type: 'tool_confirmation_response',
        session_id: card.sessionId,
        payload: {
          tool_call_id: card.interactionId,
          approved: action === 'approve',
        },
        timestamp: Date.now() / 1000,
      });
    } else if (card.kind === 'user_question' && card.interactionId && card.sessionId) {
      // 判断是取消还是正常回答
      const isCancelled = action === '__cancelled__';
      // 发送问题回答
      wsSend({
        type: 'user_question_answered',
        session_id: card.sessionId,
        payload: {
          question_id: card.interactionId,
          answer: isCancelled ? null : (action || ''),
          cancelled: isCancelled,
        },
        timestamp: Date.now() / 1000,
      });
      // 同步解除 ChatSessionContext 中的 interaction 阻塞
      resolveInteractionFromNotification?.('question', card.interactionId);
    } else if (action === 'view_session' && card.sessionId) {
      // 导航到对应会话
      handleNavigate(card.sessionId);
    }

    resolveCard(cardId, action);
  }, [cards, wsSend, resolveCard]);

  // 注册操作弹窗的回调，使弹窗按钮也能发送 WebSocket 响应
  useEffect(() => {
    setOnActionToastAction((cardId: string, actionValue: string) => {
      handleResolve(cardId, actionValue);
    });
    return () => setOnActionToastAction(null);
  }, [handleResolve, setOnActionToastAction]);

  // 按类型分组
  const pendingCards = cards.filter(c => !c.resolved);
  const resolvedCards = cards.filter(c => c.resolved);

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        onClick={handleOpen}
        className="relative p-1.5 rounded-lg hover:bg-muted transition-colors"
        title={`${unreadCount} 条未读通知`}
      >
        <Bell className="w-5 h-5 text-muted-foreground" />
        {unreadCount > 0 && (
          <span className="absolute -top-0.5 -right-0.5 min-w-[16px] h-[16px] rounded-full bg-primary text-primary-foreground text-[10px] font-bold flex items-center justify-center px-0.5">
            {unreadCount > 99 ? '99+' : unreadCount}
          </span>
        )}
      </button>

      {open && (
        <div className="absolute right-0 top-full mt-2 w-96 rounded-2xl border border-white/80 bg-white/95 shadow-[0_20px_60px_rgba(15,23,42,0.12)] backdrop-blur-2xl z-[100]">
          {/* 头部 */}
          <div className="flex items-center justify-between border-b border-neutral-100 px-4 py-3">
            <div className="flex items-center gap-2">
              <span className="text-sm font-semibold text-neutral-800">通知中心</span>
              {pendingCards.length > 0 && (
                <span className="rounded-full bg-violet-500/10 px-2 py-0.5 text-[10px] font-medium text-violet-700">
                  {pendingCards.length} 待处理
                </span>
              )}
            </div>
            {cards.length > 0 && (
              <button
                type="button"
                onClick={clearAllCards}
                className="flex items-center gap-1 text-[11px] text-neutral-400 transition-colors hover:text-neutral-600"
              >
                <Trash2 className="h-3 w-3" />
                清空
              </button>
            )}
          </div>

          {/* 卡片列表 */}
          <div className="max-h-[420px] overflow-y-auto p-3 space-y-2 hide-scrollbar">
            {cards.length === 0 ? (
              <div className="flex h-24 items-center justify-center">
                <span className="text-xs text-neutral-400">暂无通知</span>
              </div>
            ) : (
              <>
                {pendingCards.map(card => (
                  <NotificationCardItem
                    key={card.id}
                    card={card}
                    onResolve={handleResolve}
                    onDismiss={dismissCard}
                    onNavigate={handleNavigate}
                  />
                ))}
                {resolvedCards.length > 0 && pendingCards.length > 0 && (
                  <div className="my-2 border-t border-neutral-100" />
                )}
                {resolvedCards.map(card => (
                  <NotificationCardItem
                    key={card.id}
                    card={card}
                    onResolve={handleResolve}
                    onDismiss={dismissCard}
                    onNavigate={handleNavigate}
                  />
                ))}
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
