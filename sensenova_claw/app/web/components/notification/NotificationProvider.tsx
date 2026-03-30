'use client';

import { createContext, useCallback, useEffect, useRef, useState } from 'react';

import {
  NotificationToast,
  ActionToastPanel,
  type ToastNotification,
  type ActionToast,
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

// 需要弹窗提醒的卡片类型
const ACTIONABLE_KINDS: NotificationCardKind[] = ['tool_confirmation', 'user_question', 'task_completed', 'general'];

interface NotificationContextValue {
  notifications: ToastNotification[];
  permission: NotificationPermission | 'unsupported';
  pushNotification: (
    notification: NotificationInput,
    options?: { browser?: boolean; toast?: boolean },
  ) => void;
  dismissNotification: (id: string) => void;
  requestBrowserPermission: () => Promise<NotificationPermission | 'unsupported'>;
  // 通知卡片
  cards: NotificationCard[];
  unreadCount: number;
  pushCard: (card: Omit<NotificationCard, 'id' | 'createdAtMs' | 'read'> & { id?: string; createdAtMs?: number }) => void;
  markCardRead: (id: string) => void;
  markAllRead: () => void;
  markCardPending: (id: string, action?: string) => void;
  resolveCard: (id: string, action?: string) => void;
  dismissCard: (id: string) => void;
  clearAllCards: () => void;
  // 操作弹窗回调（由 NotificationDropdown 注册）
  onActionToastAction: ((cardId: string, actionValue: string, inputValue?: string) => void) | null;
  setOnActionToastAction: (fn: ((cardId: string, actionValue: string, inputValue?: string) => void) | null) => void;
}

export const NotificationContext = createContext<NotificationContextValue | null>(null);

function makeNotificationId() {
  return `notif_${Date.now()}_${Math.random().toString(16).slice(2)}`;
}

const MAX_CARDS = 50;
const ACTION_TOAST_AUTO_DISMISS_MS = 60_000;

export function NotificationProvider({ children }: { children: React.ReactNode }) {
  const [notifications, setNotifications] = useState<ToastNotification[]>([]);
  const [cards, setCards] = useState<NotificationCard[]>([]);
  const [actionToasts, setActionToasts] = useState<ActionToast[]>([]);
  const [permission, setPermission] = useState<NotificationPermission | 'unsupported'>('unsupported');
  // 操作回调：由 NotificationDropdown 注册，处理 WebSocket 响应
  const [onActionToastAction, setOnActionToastActionRaw] = useState<((cardId: string, actionValue: string, inputValue?: string) => void) | null>(null);
  const actionToastTimeoutsRef = useRef<Map<string, number>>(new Map());

  const setOnActionToastAction = useCallback((fn: ((cardId: string, actionValue: string, inputValue?: string) => void) | null) => {
    setOnActionToastActionRaw(() => fn);
  }, []);

  const clearActionToastTimer = useCallback((toastId: string) => {
    const timerId = actionToastTimeoutsRef.current.get(toastId);
    if (timerId === undefined) return;
    window.clearTimeout(timerId);
    actionToastTimeoutsRef.current.delete(toastId);
  }, []);

  const removeActionToast = useCallback((toastId: string) => {
    clearActionToastTimer(toastId);
    setActionToasts(prev => prev.filter(t => t.id !== toastId));
  }, [clearActionToastTimer]);

  useEffect(() => {
    if (typeof window === 'undefined' || !('Notification' in window)) {
      setPermission('unsupported');
      return;
    }
    setPermission(window.Notification.permission);
  }, []);

  useEffect(() => {
    const visibleToastIds = new Set(actionToasts.map(toast => toast.id));
    for (const toastId of actionToastTimeoutsRef.current.keys()) {
      const toast = actionToasts.find(item => item.id === toastId);
      if (!toast || toast.pending) {
        clearActionToastTimer(toastId);
      }
    }

    actionToasts.forEach((toast) => {
      if (toast.pending || actionToastTimeoutsRef.current.has(toast.id)) {
        return;
      }
      const remainingMs = Math.max(0, toast.createdAtMs + ACTION_TOAST_AUTO_DISMISS_MS - Date.now());
      const timerId = window.setTimeout(() => {
        actionToastTimeoutsRef.current.delete(toast.id);
        setActionToasts(prev => prev.filter(t => t.id !== toast.id));
      }, remainingMs);
      actionToastTimeoutsRef.current.set(toast.id, timerId);
    });

    for (const toastId of actionToastTimeoutsRef.current.keys()) {
      if (!visibleToastIds.has(toastId)) {
        clearActionToastTimer(toastId);
      }
    }
  }, [actionToasts, clearActionToastTimer]);

  useEffect(() => {
    return () => {
      for (const timerId of actionToastTimeoutsRef.current.values()) {
        window.clearTimeout(timerId);
      }
      actionToastTimeoutsRef.current.clear();
    };
  }, []);

  const dismissNotification = (id: string) => {
    setNotifications((prev) => prev.filter((item) => item.id !== id));
  };

  const requestBrowserPermission = async (): Promise<NotificationPermission | 'unsupported'> => {
    if (typeof window === 'undefined' || !('Notification' in window)) {
      setPermission('unsupported');
      return 'unsupported';
    }
    const result = await window.Notification.requestPermission();
    setPermission(result);
    return result;
  };

  const pushNotification = (
    notification: NotificationInput,
    options?: { browser?: boolean; toast?: boolean },
  ) => {
    const nextNotification: ToastNotification = {
      id: notification.id || makeNotificationId(),
      title: notification.title,
      body: notification.body,
      level: notification.level || 'info',
      source: notification.source || 'system',
      createdAtMs: notification.createdAtMs || Date.now(),
    };
    const shouldShowToast = options?.toast !== false;
    const shouldShowBrowser = options?.browser === true;

    if (shouldShowToast) {
      setNotifications((prev) => [nextNotification, ...prev].slice(0, 5));
    }

    if (
      shouldShowBrowser &&
      permission === 'granted' &&
      typeof window !== 'undefined' &&
      'Notification' in window
    ) {
      new window.Notification(nextNotification.title, {
        body: nextNotification.body,
      });
    }

    if (shouldShowToast) {
      window.setTimeout(() => {
        dismissNotification(nextNotification.id);
      }, 5000);
    }
  };

  // ── 通知卡片管理 ──

  const pushCard = useCallback((input: Omit<NotificationCard, 'id' | 'createdAtMs' | 'read'> & { id?: string; createdAtMs?: number }) => {
    const card: NotificationCard = {
      ...input,
      id: input.id || makeNotificationId(),
      createdAtMs: input.createdAtMs || Date.now(),
      read: false,
    };
    setCards(prev => {
      if (prev.some(c => c.id === card.id)) return prev;
      return [card, ...prev].slice(0, MAX_CARDS);
    });

    // 如果是需要用户操作的类型，同时弹出操作弹窗
    if (ACTIONABLE_KINDS.includes(card.kind) && ((card.actions && card.actions.length > 0) || card.allowsInput)) {
      const toast: ActionToast = {
        id: `toast_${card.id}`,
        title: card.title,
        body: card.body,
        level: card.level,
        source: card.kind,
        createdAtMs: card.createdAtMs,
        actions: card.actions,
        allowsInput: card.allowsInput,
        inputPlaceholder: card.inputPlaceholder,
        cardId: card.id,
        questionData: card.questionData,
      };
      setActionToasts(prev => {
        if (prev.some(t => t.cardId === card.id)) return prev;
        return [toast, ...prev];
      });
    }

    // 对于 user_question 类型，即使没有 actions 也弹出富交互弹窗
    if (card.kind === 'user_question' && card.questionData && (!card.actions || card.actions.length === 0)) {
      const toast: ActionToast = {
        id: `toast_${card.id}`,
        title: card.title,
        body: card.body,
        level: card.level,
        source: card.kind,
        createdAtMs: card.createdAtMs,
        actions: [],
        cardId: card.id,
        questionData: card.questionData,
      };
      setActionToasts(prev => {
        if (prev.some(t => t.cardId === card.id)) return prev;
        return [toast, ...prev];
      });
    }
  }, []);

  const markCardRead = useCallback((id: string) => {
    setCards(prev => prev.map(c => c.id === id ? { ...c, read: true } : c));
  }, []);

  const markAllRead = useCallback(() => {
    setCards(prev => prev.map(c => ({ ...c, read: true })));
  }, []);

  const markCardPending = useCallback((id: string, action?: string) => {
    setCards(prev => prev.map(c =>
      c.id === id && !c.resolved
        ? { ...c, pending: true, pendingAction: action, read: true }
        : c
    ));
    setActionToasts(prev => prev.map(t =>
      t.cardId === id
        ? { ...t, pending: true, pendingAction: action }
        : t
    ));
  }, []);

  const resolveCard = useCallback((id: string, action?: string) => {
    setCards(prev => prev.map(c =>
      c.id === id
        ? {
            ...c,
            pending: false,
            resolved: true,
            resolvedAction: action || c.pendingAction,
            read: true,
          }
        : c
    ));
    // 同时移除对应的操作弹窗
    setActionToasts(prev => {
      const matchedToasts = prev.filter(t => t.cardId === id);
      matchedToasts.forEach((toast) => clearActionToastTimer(toast.id));
      return prev.filter(t => t.cardId !== id);
    });
  }, [clearActionToastTimer]);

  const dismissCard = useCallback((id: string) => {
    setCards(prev => prev.filter(c => c.id !== id));
    setActionToasts(prev => {
      const matchedToasts = prev.filter(t => t.cardId === id);
      matchedToasts.forEach((toast) => clearActionToastTimer(toast.id));
      return prev.filter(t => t.cardId !== id);
    });
  }, [clearActionToastTimer]);

  const clearAllCards = useCallback(() => {
    setCards([]);
    setActionToasts([]);
  }, []);

  // 操作弹窗：用户点击按钮
  const handleActionToastAction = useCallback((toastId: string, cardId: string, actionValue: string, inputValue?: string) => {
    clearActionToastTimer(toastId);
    setActionToasts(prev => prev.map(t =>
      t.id === toastId
        ? { ...t, pending: true, pendingAction: actionValue }
        : t
    ));
    // 触发回调（发送 WebSocket 响应）
    onActionToastAction?.(cardId, actionValue, inputValue);
    if (!onActionToastAction) {
      markCardPending(cardId, actionValue);
    }
  }, [clearActionToastTimer, markCardPending, onActionToastAction]);

  // 操作弹窗：用户关闭（不操作）
  const handleActionToastDismiss = useCallback((toastId: string) => {
    removeActionToast(toastId);
  }, [removeActionToast]);

  const unreadCount = cards.filter(c => !c.read && !c.resolved).length;

  return (
    <NotificationContext.Provider
      value={{
        notifications,
        permission,
        pushNotification,
        dismissNotification,
        requestBrowserPermission,
        cards,
        unreadCount,
        pushCard,
        markCardRead,
        markAllRead,
        markCardPending,
        resolveCard,
        dismissCard,
        clearAllCards,
        onActionToastAction,
        setOnActionToastAction,
      }}
    >
      {children}
      <NotificationToast notifications={notifications} dismissNotification={dismissNotification} />
      <ActionToastPanel
        toasts={actionToasts}
        onAction={handleActionToastAction}
        onDismiss={handleActionToastDismiss}
      />
    </NotificationContext.Provider>
  );
}
