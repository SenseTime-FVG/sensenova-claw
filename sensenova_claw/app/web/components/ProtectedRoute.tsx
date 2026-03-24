"use client";

import { useEffect, useState } from 'react';
import { useRouter, usePathname } from 'next/navigation';
import { useAuth } from '@/contexts/AuthContext';
import { authGet, API_BASE } from '@/lib/authFetch';

// 不拦截的路径（登录页和配置引导页）
const BYPASS_PATHS = ['/login', '/setup'];
const AUTH_JUST_VERIFIED_KEY = 'auth_just_verified';
const LLM_SETUP_SKIPPED_KEY = 'llm_setup_skipped';
const LLM_JUST_CONFIGURED_KEY = 'llm_just_configured';

function hasSessionFlag(key: string): boolean {
  if (typeof window === 'undefined') return false;
  return sessionStorage.getItem(key) === '1';
}

export default function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { isAuthenticated, isLoading } = useAuth();
  const router = useRouter();
  const pathname = usePathname();

  // LLM 配置检查状态
  const [llmChecked, setLlmChecked] = useState(false);
  const [llmConfigured, setLlmConfigured] = useState(true);
  const authJustVerified = hasSessionFlag(AUTH_JUST_VERIFIED_KEY);

  // 未认证时重定向到登录页
  useEffect(() => {
    if (!isLoading && isAuthenticated && authJustVerified) {
      sessionStorage.removeItem(AUTH_JUST_VERIFIED_KEY);
    }
  }, [authJustVerified, isAuthenticated, isLoading]);

  useEffect(() => {
    if (!isLoading && !isAuthenticated && !authJustVerified && !BYPASS_PATHS.includes(pathname)) {
      router.push('/login');
    }
  }, [authJustVerified, isAuthenticated, isLoading, pathname, router]);

  // 已认证时检查 LLM 配置状态
  useEffect(() => {
    if (!isAuthenticated || BYPASS_PATHS.includes(pathname)) {
      // 在 bypass 路径上无需检查
      setLlmChecked(true);
      return;
    }

    const checkLlmConfig = async () => {
      try {
        // Setup 刚完成时跳过检查，避免因 secret store 延迟导致误跳回
        if (hasSessionFlag(LLM_JUST_CONFIGURED_KEY)) {
          sessionStorage.removeItem(LLM_JUST_CONFIGURED_KEY);
          setLlmConfigured(true);
          setLlmChecked(true);
          return;
        }

        // 用户明确选择“稍后配置”后，在当前浏览器会话内不再强制打回 setup
        if (hasSessionFlag(LLM_SETUP_SKIPPED_KEY)) {
          setLlmConfigured(true);
          setLlmChecked(true);
          return;
        }

        const data = await authGet<{ configured: boolean }>(`${API_BASE}/api/config/llm-status`);
        if (!data.configured) {
          setLlmConfigured(false);
          router.push('/setup');
        } else {
          setLlmConfigured(true);
          setLlmChecked(true);
        }
      } catch (e) {
        // 接口失败时不拦截，允许正常访问
        console.warn('LLM 配置检查失败:', e);
        setLlmConfigured(true);
        setLlmChecked(true);
      }
    };

    checkLlmConfig();
  }, [isAuthenticated, pathname, router]);

  // 加载中显示骨架屏
  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary mx-auto"></div>
          <p className="mt-4 text-muted-foreground">验证中...</p>
        </div>
      </div>
    );
  }

  // 未认证且不在 bypass 路径，显示跳转中
  if (!isAuthenticated && !authJustVerified && !BYPASS_PATHS.includes(pathname)) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary mx-auto"></div>
          <p className="mt-4 text-muted-foreground">跳转中...</p>
        </div>
      </div>
    );
  }

  // 已认证但 LLM 配置检查未完成，显示检查中
  if (isAuthenticated && !BYPASS_PATHS.includes(pathname) && !llmChecked) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary mx-auto"></div>
          <p className="mt-4 text-muted-foreground">检查配置...</p>
        </div>
      </div>
    );
  }

  // LLM 未配置，等待重定向到 /setup
  if (isAuthenticated && !BYPASS_PATHS.includes(pathname) && !llmConfigured) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary mx-auto"></div>
          <p className="mt-4 text-muted-foreground">跳转中...</p>
        </div>
      </div>
    );
  }

  return <>{children}</>;
}
