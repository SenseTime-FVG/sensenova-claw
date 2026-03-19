"use client";

import { useEffect, useState } from 'react';
import { useRouter, usePathname } from 'next/navigation';
import { useAuth } from '@/contexts/AuthContext';
import { API_BASE, authFetch } from '@/lib/authFetch';

interface WhatsAppStatus {
  enabled: boolean;
  authorized: boolean;
  state: string;
}

function shouldEnforceWhatsAppAuth(pathname: string | null): boolean {
  if (!pathname) {
    return false;
  }
  return (
    pathname === '/gateway'
    || pathname.startsWith('/gateway/')
    || pathname === '/sessions/whatsapp'
    || pathname.startsWith('/sessions/whatsapp')
  );
}

export default function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { isAuthenticated, isLoading } = useAuth();
  const router = useRouter();
  const pathname = usePathname();
  const [isWhatsAppChecking, setIsWhatsAppChecking] = useState(true);
  const [isWhatsAppBlocked, setIsWhatsAppBlocked] = useState(false);

  useEffect(() => {
    // 如果未认证且不在登录页，重定向到登录页（token 输入页）
    if (!isLoading && !isAuthenticated && pathname !== '/login') {
      router.push('/login');
    }
  }, [isAuthenticated, isLoading, pathname, router]);

  useEffect(() => {
    if (isLoading || !isAuthenticated) {
      return;
    }

    if (pathname === '/login') {
      setIsWhatsAppChecking(false);
      setIsWhatsAppBlocked(false);
      return;
    }

    if (!shouldEnforceWhatsAppAuth(pathname)) {
      setIsWhatsAppChecking(false);
      setIsWhatsAppBlocked(false);
      return;
    }

    let cancelled = false;
    setIsWhatsAppChecking(true);

    authFetch(`${API_BASE}/api/gateway/whatsapp/status`)
      .then((response) => response.json() as Promise<WhatsAppStatus>)
      .then((status) => {
        if (cancelled) {
          return;
        }

        const shouldBlock = status.enabled && !status.authorized;
        setIsWhatsAppBlocked(shouldBlock);

        if (shouldBlock && pathname !== '/gateway/whatsapp') {
          const next = encodeURIComponent(pathname || '/chat');
          router.replace(`/gateway/whatsapp?returnTo=${next}`);
          return;
        }
      })
      .catch(() => {
        if (!cancelled) {
          setIsWhatsAppBlocked(false);
        }
      })
      .finally(() => {
        if (!cancelled) {
          setIsWhatsAppChecking(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [isAuthenticated, isLoading, pathname, router]);

  // 加载中显示骨架屏
  if (isLoading || (isAuthenticated && isWhatsAppChecking && pathname !== '/login')) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary mx-auto"></div>
          <p className="mt-4 text-muted-foreground">
            {isLoading ? '验证中...' : '检查 WhatsApp 登录状态...'}
          </p>
        </div>
      </div>
    );
  }

  // 未认证且不在登录页，显示加载（等待重定向到登录页）
  if (!isAuthenticated && pathname !== '/login') {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary mx-auto"></div>
          <p className="mt-4 text-muted-foreground">跳转中...</p>
        </div>
      </div>
    );
  }

  if (isAuthenticated && isWhatsAppBlocked && pathname !== '/gateway/whatsapp') {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary mx-auto"></div>
          <p className="mt-4 text-muted-foreground">跳转到 WhatsApp 登录页...</p>
        </div>
      </div>
    );
  }

  return <>{children}</>;
}
