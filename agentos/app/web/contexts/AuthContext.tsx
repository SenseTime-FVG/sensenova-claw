"use client";

import React, { createContext, useContext, useState, useEffect, useCallback, ReactNode } from 'react';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
const COOKIE_NAME = 'agentos_token';

interface AuthContextType {
  isAuthenticated: boolean;
  isLoading: boolean;
  verifyToken: (token: string) => Promise<boolean>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

/** 从 document.cookie 读取指定 cookie */
function getCookie(name: string): string | null {
  const match = document.cookie.match(new RegExp(`(?:^|; )${name}=([^;]*)`));
  return match ? decodeURIComponent(match[1]) : null;
}

/** 设置 cookie（30 天） */
function setCookie(name: string, value: string, maxAgeDays = 30) {
  document.cookie = `${name}=${encodeURIComponent(value)}; path=/; max-age=${maxAgeDays * 86400}; samesite=lax`;
}

/** 删除 cookie */
function deleteCookie(name: string) {
  document.cookie = `${name}=; path=/; max-age=0`;
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [isLoading, setIsLoading] = useState(true);

  /** 调用后端验证 token 并设置 cookie */
  const verifyToken = useCallback(async (token: string): Promise<boolean> => {
    try {
      const response = await fetch(`${API_BASE}/api/auth/verify-token`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ token }),
      });

      if (!response.ok) return false;

      const data = await response.json();
      if (data.authenticated) {
        // 同时在前端设置 cookie（确保跨端口场景可用）
        setCookie(COOKIE_NAME, token);
        setIsAuthenticated(true);
        return true;
      }
      return false;
    } catch (error) {
      console.error('Token verification failed:', error);
      return false;
    }
  }, []);

  /** 登出 */
  const logout = useCallback(() => {
    deleteCookie(COOKIE_NAME);
    setIsAuthenticated(false);
    // 调用后端清除 cookie
    fetch(`${API_BASE}/api/auth/logout`, {
      method: 'POST',
      credentials: 'include',
    }).catch(() => {});
  }, []);

  /** 初始化：检查 URL ?token= 或已有 cookie */
  useEffect(() => {
    const init = async () => {
      // 1. 检查 URL 中的 ?token= 参数
      const params = new URLSearchParams(window.location.search);
      const urlToken = params.get('token');
      const pathname = window.location.pathname;

      // 根路径统一跳转到 /chat，让 /chat?token=... 成为唯一带 token 入口。
      if (pathname === '/' && urlToken) {
        const targetUrl = params.toString() ? `/chat?${params.toString()}` : '/chat';
        window.location.replace(targetUrl);
        return;
      }

      if (urlToken) {
        const valid = await verifyToken(urlToken);
        if (valid) {
          // 清除 URL 中的 token 参数
          params.delete('token');
          const newUrl = params.toString()
            ? `${window.location.pathname}?${params.toString()}`
            : window.location.pathname;
          window.history.replaceState({}, '', newUrl);
          setIsLoading(false);
          return;
        }
      }

      // 2. 检查已有 cookie
      const existingToken = getCookie(COOKIE_NAME);
      if (existingToken) {
        try {
          const response = await fetch(`${API_BASE}/api/auth/status`, {
            credentials: 'include',
            headers: existingToken ? { 'Authorization': `Bearer ${existingToken}` } : {},
          });
          if (response.ok) {
            const data = await response.json();
            if (data.authenticated) {
              setIsAuthenticated(true);
              setIsLoading(false);
              return;
            }
          }
        } catch (error) {
          console.error('Auth status check failed:', error);
          // 后端未就绪时清除旧 cookie，避免卡在加载状态
          deleteCookie(COOKIE_NAME);
        }
      }

      // 3. 未认证
      setIsAuthenticated(false);
      setIsLoading(false);
    };

    init();
  }, [verifyToken]);

  const value: AuthContextType = {
    isAuthenticated,
    isLoading,
    verifyToken,
    logout,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
}
