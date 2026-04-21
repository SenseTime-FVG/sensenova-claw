"use client";

import React, { createContext, useContext, useState, useEffect, useCallback, ReactNode, useRef } from 'react';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || '';
const COOKIE_NAME = 'sensenova_claw_token';
const AUTH_JUST_VERIFIED_KEY = 'auth_just_verified';

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
  const verifiedInSessionRef = useRef(false);

  /** 调用后端验证 token 并设置 cookie。
   *  网络错误时 throw，token 无效时返回 false。 */
  const verifyToken = useCallback(async (token: string): Promise<boolean> => {
    let response: Response;
    try {
      response = await fetch(`${API_BASE}/api/auth/verify-token`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ token }),
      });
    } catch (error) {
      console.error('Token verification failed:', error);
      throw new Error('无法连接后端服务，请确认后端已启动且端口可访问');
    }

    if (!response.ok) return false;

    const data = await response.json();
    if (data.authenticated) {
      // 同时在前端设置 cookie（确保跨端口场景可用）
      setCookie(COOKIE_NAME, token);
      sessionStorage.setItem(AUTH_JUST_VERIFIED_KEY, '1');
      verifiedInSessionRef.current = true;
      setIsAuthenticated(true);
      return true;
    }
    verifiedInSessionRef.current = false;
    return false;
  }, []);

  /** 登出 */
  const logout = useCallback(() => {
    deleteCookie(COOKIE_NAME);
    verifiedInSessionRef.current = false;
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

      if (urlToken) {
        try {
          const valid = await verifyToken(urlToken);
          if (valid) {
            params.delete('token');
            const newUrl = pathname === '/' && params.toString()
              ? `/?${params.toString()}`
              : pathname === '/'
                ? '/'
                : params.toString()
                  ? `${pathname}?${params.toString()}`
                  : pathname;
            window.history.replaceState({}, '', newUrl);
            setIsLoading(false);
            return;
          }
        } catch (error) {
          console.error('Token verification during init failed:', error);
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
      if (verifiedInSessionRef.current) {
        setIsAuthenticated(true);
        setIsLoading(false);
        return;
      }
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
