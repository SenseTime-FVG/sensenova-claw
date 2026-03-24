'use client';

import { createContext, useCallback, useEffect, useState } from 'react';

import {
  NotificationToast,
  ActionToastPanel,
  type ToastNotification,
  type ActionToast,
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
  allowsInput?: boolean;
  inputPlaceholder?: string;
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

export function NotificationProvider({ children }: { children: React.ReactNode }) {
  const [notifications, setNotifications] = useState<ToastNotification[]>([]);
  const [cards, setCards] = useState<NotificationCard[]>([]);
  const [actionToasts, setActionToasts] = useState<ActionToast[]>([]);
  const [permission, setPermission] = useState<NotificationPermission | 'unsupported'>('unsupported');
  // 操作回调：由 NotificationDropdown 注册，处理 WebSocket 响应
  const [onActionToastAction, setOnActionToastActionRaw] = useState<((cardId: string, actionValue: string, inputValue?: string) => void) | null>(null);

  const setOnActionToastAction = useCallback((fn: ((cardId: string, actionValue: string, inputValue?: string) => void) | null) => {
    setOnActionToastActionRaw(() => fn);
  }, []);

  useEffect(() => {
    if (typeof window === 'undefined' || !('Notification' in window)) {
      setPermission('unsupported');
      return;
    }
    setPermission(window.Notification.permission);
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
      };
      setActionToasts(prev => {
        if (prev.some(t => t.cardId === card.id)) return prev;
        return [toast, ...prev].slice(0, 5);
      });
    }
  }, []);

  const markCardRead = useCallback((id: string) => {
    setCards(prev => prev.map(c => c.id === id ? { ...c, read: true } : c));
  }, []);

  const markAllRead = useCallback(() => {
    setCards(prev => prev.map(c => ({ ...c, read: true })));
  }, []);

  const resolveCard = useCallback((id: string, action?: string) => {
    setCards(prev => prev.map(c =>
      c.id === id ? { ...c, resolved: true, resolvedAction: action, read: true } : c
    ));
    // 同时移除对应的操作弹窗
    setActionToasts(prev => prev.filter(t => t.cardId !== id));
  }, []);

  const dismissCard = useCallback((id: string) => {
    setCards(prev => prev.filter(c => c.id !== id));
    setActionToasts(prev => prev.filter(t => t.cardId !== id));
  }, []);

  const clearAllCards = useCallback(() => {
    setCards([]);
    setActionToasts([]);
  }, []);

  // 操作弹窗：用户点击按钮
  const handleActionToastAction = useCallback((toastId: string, cardId: string, actionValue: string, inputValue?: string) => {
    // 移除弹窗
    setActionToasts(prev => prev.filter(t => t.id !== toastId));
    // 标记卡片已处理
    resolveCard(cardId, actionValue);
    // 触发回调（发送 WebSocket 响应）
    onActionToastAction?.(cardId, actionValue, inputValue);
  }, [resolveCard, onActionToastAction]);

  // 操作弹窗：用户关闭（不操作）
  const handleActionToastDismiss = useCallback((toastId: string) => {
    setActionToasts(prev => prev.filter(t => t.id !== toastId));
  }, []);

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
