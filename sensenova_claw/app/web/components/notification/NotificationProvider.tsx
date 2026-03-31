'use client';

import { createContext, useCallback, useEffect, useRef, useState } from 'react';

import {
  ToastContainer,
  type QuestionData,
} from '@/components/notification/NotificationToast';

export interface NotificationInput {
  id?: string;
  title: string;
  body: string;
  level?: 'info' | 'warning' | 'error' | 'success';
  source?: string;
  createdAtMs?: number;
}

// ── 通知卡片（持久化，不自动消失） ──

export type NotificationCardKind =
  | 'task_completed'     // 任务完成提醒
  | 'user_question'      // ask_user_tool 需要确认
  | 'tool_confirmation'  // 工具执行需要授权
  | 'proactive'          // proactive agent 建议
  | 'general';           // 普通通知

export interface NotificationCard {
  id: string;
  kind: NotificationCardKind;
  title: string;
  body: string;
  level: 'info' | 'warning' | 'error' | 'success';
  source: string;
  createdAtMs: number;
  read: boolean;
  // 用于交互类通知
  sessionId?: string;
  interactionId?: string;
  // 用于 proactive / 可操作通知
  actions?: { label: string; value: string }[];
  // ask_user 富交互数据
  questionData?: QuestionData;
  allowsInput?: boolean;
  inputPlaceholder?: string;
  pending?: boolean;
  pendingAction?: string;
  // 已处理标记
  resolved?: boolean;
  resolvedAction?: string;
}

// ── 统一 Toast 类型 ──

export type ToastKind =
  | 'info'
  | 'tool_confirmation'
  | 'user_question'
  | 'task_completed'
  | 'proactive'
  | 'general';

export interface ToastAction {
  label: string;
  value: string;
}

export interface UnifiedToast {
  id: string;
  kind: ToastKind;
  title: string;
  body: string;
  level: 'info' | 'warning' | 'error' | 'success';
  source: string;
  actions?: ToastAction[];
  allowsInput?: boolean;
  inputPlaceholder?: string;
  questionData?: QuestionData;
  onAction?: (actionValue: string, inputValue?: string) => boolean | void;  // 返回 true 表示需要 pending（等待服务端确认）
  autoDismissMs: number;
  createdAtMs: number;
  pending: boolean;
  cardId?: string;
  sessionId?: string;
  eventKey?: string;
}

export interface PushToastConfig {
  kind?: ToastKind;
  title: string;
  body: string;
  level?: 'info' | 'warning' | 'error' | 'success';
  source?: string;
  actions?: ToastAction[];
  allowsInput?: boolean;
  inputPlaceholder?: string;
  questionData?: QuestionData;
  autoDismissMs?: number;
  sessionId?: string;
  cardId?: string;
  eventKey?: string;
  onAction?: (actionValue: string, inputValue?: string) => boolean | void;  // 返回 true 表示需要 pending（等待服务端确认）
  browser?: boolean;
}

export interface NotificationContextValue {
  // Toast 队列（统一弹窗）
  toasts: UnifiedToast[];
  pushToast: (config: PushToastConfig) => string;
  dismissToast: (id: string) => void;
  resolveToast: (id: string, action?: string) => void;
  markToastPending: (id: string) => void;

  // Card（通知中心，保持原有签名但 pushCard 改为返回 string）
  cards: NotificationCard[];
  pushCard: (card: Omit<NotificationCard, 'id' | 'createdAtMs' | 'read'> & { id?: string; createdAtMs?: number }) => string;
  markCardRead: (id: string) => void;
  markAllRead: () => void;
  markCardPending: (id: string, action?: string) => void;
  resolveCard: (id: string, action?: string) => void;
  dismissCard: (id: string) => void;
  clearAllCards: () => void;
  unreadCount: number;

  // 浏览器通知权限（不变）
  permission: NotificationPermission | 'unsupported';
  requestBrowserPermission: () => Promise<NotificationPermission | 'unsupported'>;
}

export const NotificationContext = createContext<NotificationContextValue | null>(null);

function makeNotificationId() {
  return `notif_${Date.now()}_${Math.random().toString(16).slice(2)}`;
}

const MAX_CARDS = 50;

export function NotificationProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = useState<UnifiedToast[]>([]);
  const [cards, setCards] = useState<NotificationCard[]>([]);
  const [permission, setPermission] = useState<NotificationPermission | 'unsupported'>('unsupported');

  // Toast 定时器管理
  const toastTimersRef = useRef<Map<string, ReturnType<typeof setTimeout>>>(new Map());

  const clearToastTimer = useCallback((toastId: string) => {
    const timer = toastTimersRef.current.get(toastId);
    if (timer) {
      clearTimeout(timer);
      toastTimersRef.current.delete(toastId);
    }
  }, []);

  const clearAllToastTimers = useCallback(() => {
    toastTimersRef.current.forEach((timer) => clearTimeout(timer));
    toastTimersRef.current.clear();
  }, []);

  // 组件卸载时清理所有定时器
  useEffect(() => {
    return () => clearAllToastTimers();
  }, [clearAllToastTimers]);

  // 初始化浏览器通知权限
  useEffect(() => {
    if (typeof window === 'undefined' || !('Notification' in window)) {
      setPermission('unsupported');
      return;
    }
    setPermission(window.Notification.permission);
  }, []);

  const requestBrowserPermission = async (): Promise<NotificationPermission | 'unsupported'> => {
    if (typeof window === 'undefined' || !('Notification' in window)) {
      setPermission('unsupported');
      return 'unsupported';
    }
    const result = await window.Notification.requestPermission();
    setPermission(result);
    return result;
  };

  // ── 统一 Toast 管理 ──

  const pushToast = useCallback((config: PushToastConfig): string => {
    const id = makeNotificationId();
    const hasInteraction = (config.actions && config.actions.length > 0) || config.allowsInput;
    const autoDismissMs = config.autoDismissMs ?? (hasInteraction ? 60_000 : 5_000);

    const toast: UnifiedToast = {
      id,
      kind: config.kind ?? 'info',
      title: config.title,
      body: config.body,
      level: config.level ?? 'info',
      source: config.source ?? 'system',
      actions: config.actions,
      allowsInput: config.allowsInput,
      inputPlaceholder: config.inputPlaceholder,
      questionData: config.questionData,
      onAction: config.onAction,
      autoDismissMs,
      createdAtMs: Date.now(),
      pending: false,
      cardId: config.cardId,
      sessionId: config.sessionId,
      eventKey: config.eventKey,
    };

    setToasts((prev) => {
      if (config.eventKey) {
        const existing = prev.find((t) => t.eventKey === config.eventKey);
        // 已有相同 eventKey 且处于 pending 状态时跳过
        if (existing?.pending) return prev;
        const filtered = prev.filter((t) => t.eventKey !== config.eventKey);
        if (existing) clearToastTimer(existing.id);
        return [toast, ...filtered].slice(0, 20);
      }
      return [toast, ...prev].slice(0, 20);
    });

    // 设置自动消失定时器
    if (autoDismissMs > 0) {
      const timer = setTimeout(() => {
        setToasts((prev) => prev.filter((t) => t.id !== id));
        toastTimersRef.current.delete(id);
      }, autoDismissMs);
      toastTimersRef.current.set(id, timer);
    }

    // 浏览器原生通知
    if (
      config.browser &&
      permission === 'granted' &&
      typeof window !== 'undefined' &&
      'Notification' in window
    ) {
      new window.Notification(config.title, { body: config.body });
    }

    return id;
  }, [clearToastTimer, permission]);

  const dismissToast = useCallback((id: string) => {
    clearToastTimer(id);
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, [clearToastTimer]);

  const resolveToast = useCallback((id: string, action?: string) => {
    clearToastTimer(id);
    setToasts((prev) => {
      const toast = prev.find((t) => t.id === id);
      if (toast?.cardId) {
        // 注意：resolveCard 在下方定义，通过 setCards 联动，避免循环依赖
        setCards((prevCards) =>
          prevCards.map((c) =>
            c.id === toast.cardId
              ? { ...c, resolved: true, resolvedAction: action }
              : c
          )
        );
      }
      return prev.filter((t) => t.id !== id);
    });
  }, [clearToastTimer]);

  const markToastPending = useCallback((id: string) => {
    clearToastTimer(id);
    setToasts((prev) =>
      prev.map((t) => (t.id === id ? { ...t, pending: true } : t))
    );
  }, [clearToastTimer]);

  // ── 通知卡片管理 ──

  const resolveCard = useCallback((id: string, action?: string) => {
    setCards((prev) =>
      prev.map((c) =>
        c.id === id
          ? {
              ...c,
              pending: false,
              resolved: true,
              resolvedAction: action || c.pendingAction,
              read: true,
            }
          : c
      )
    );
    // 联动移除关联的 toast
    setToasts((prev) => {
      const toast = prev.find((t) => t.cardId === id);
      if (toast) clearToastTimer(toast.id);
      return prev.filter((t) => t.cardId !== id);
    });
  }, [clearToastTimer]);

  const pushCard = useCallback((cardInput: Omit<NotificationCard, 'id' | 'createdAtMs' | 'read'> & { id?: string; createdAtMs?: number }): string => {
    const card: NotificationCard = {
      ...cardInput,
      id: cardInput.id || makeNotificationId(),
      createdAtMs: cardInput.createdAtMs || Date.now(),
      read: false,
    };

    setCards((prev) => {
      if (prev.some((c) => c.id === card.id)) return prev;
      return [card, ...prev].slice(0, MAX_CARDS);
    });

    return card.id;
  }, []);

  const markCardRead = useCallback((id: string) => {
    setCards(prev => prev.map(c => c.id === id ? { ...c, read: true } : c));
  }, []);

  const markAllRead = useCallback(() => {
    setCards(prev => prev.map(c => ({ ...c, read: true })));
  }, []);

  const markCardPending = useCallback((id: string, action?: string) => {
    setCards((prev) =>
      prev.map((c) =>
        c.id === id ? { ...c, pending: true, read: true, resolvedAction: action } : c
      )
    );
    setToasts((prev) => {
      const toast = prev.find((t) => t.cardId === id);
      if (toast) {
        clearToastTimer(toast.id);
        return prev.map((t) =>
          t.cardId === id ? { ...t, pending: true } : t
        );
      }
      return prev;
    });
  }, [clearToastTimer]);

  const dismissCard = useCallback((id: string) => {
    setCards((prev) => prev.filter((c) => c.id !== id));
  }, []);

  const clearAllCards = useCallback(() => {
    setCards([]);
    setToasts((prev) => {
      const removed = prev.filter((t) => t.cardId);
      removed.forEach((t) => clearToastTimer(t.id));
      return prev.filter((t) => !t.cardId);
    });
  }, [clearToastTimer]);

  const unreadCount = cards.filter(c => !c.read && !c.resolved).length;

  const value: NotificationContextValue = {
    toasts,
    pushToast,
    dismissToast,
    resolveToast,
    markToastPending,
    cards,
    pushCard,
    markCardRead,
    markAllRead,
    markCardPending,
    resolveCard,
    dismissCard,
    clearAllCards,
    unreadCount,
    permission,
    requestBrowserPermission,
  };

  return (
    <NotificationContext.Provider value={value}>
      {children}
      <ToastContainer toasts={toasts} onDismiss={dismissToast} onMarkPending={markToastPending} />
    </NotificationContext.Provider>
  );
}
