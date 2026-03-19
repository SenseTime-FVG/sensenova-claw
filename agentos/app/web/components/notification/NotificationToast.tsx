'use client';

import { Bell, CircleAlert, CircleCheck, Info, X } from 'lucide-react';

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
    <div className="pointer-events-none fixed right-4 top-4 z-[80] flex w-[min(28rem,calc(100vw-2rem))] flex-col gap-3">
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
