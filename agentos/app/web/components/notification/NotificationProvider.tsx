'use client';

import { createContext, useEffect, useState } from 'react';

import { NotificationToast, ToastNotification } from '@/components/notification/NotificationToast';

export interface NotificationInput {
  id?: string;
  title: string;
  body: string;
  level?: 'info' | 'warning' | 'error' | 'success';
  source?: string;
  createdAtMs?: number;
}

interface NotificationContextValue {
  notifications: ToastNotification[];
  permission: NotificationPermission | 'unsupported';
  pushNotification: (
    notification: NotificationInput,
    options?: { browser?: boolean; toast?: boolean },
  ) => void;
  dismissNotification: (id: string) => void;
  requestBrowserPermission: () => Promise<NotificationPermission | 'unsupported'>;
}

export const NotificationContext = createContext<NotificationContextValue | null>(null);

function makeNotificationId() {
  return `notif_${Date.now()}_${Math.random().toString(16).slice(2)}`;
}

export function NotificationProvider({ children }: { children: React.ReactNode }) {
  const [notifications, setNotifications] = useState<ToastNotification[]>([]);
  const [permission, setPermission] = useState<NotificationPermission | 'unsupported'>('unsupported');

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

  return (
    <NotificationContext.Provider
      value={{
        notifications,
        permission,
        pushNotification,
        dismissNotification,
        requestBrowserPermission,
      }}
    >
      {children}
      <NotificationToast notifications={notifications} dismissNotification={dismissNotification} />
    </NotificationContext.Provider>
  );
}
