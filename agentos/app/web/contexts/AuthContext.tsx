"use client";

import React, { createContext, useContext, useState, useEffect, ReactNode } from 'react';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

interface User {
  user_id: string;
  username: string;
  email: string | null;
  is_active: boolean;
  is_admin: boolean;
  created_at: number;
  last_login: number | null;
}

interface AuthContextType {
  user: User | null;
  token: string | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  login: (username: string, password: string) => Promise<void>;
  logout: () => void;
  refreshToken: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [refreshTokenValue, setRefreshTokenValue] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  // 从 localStorage 加载 token
  useEffect(() => {
    const storedToken = localStorage.getItem('access_token');
    const storedRefreshToken = localStorage.getItem('refresh_token');

    if (storedToken) {
      setToken(storedToken);
      setRefreshTokenValue(storedRefreshToken);
      // 验证 token 并获取用户信息
      fetchUserInfo(storedToken);
    } else {
      setIsLoading(false);
    }
  }, []);

  // 获取用户信息
  const fetchUserInfo = async (accessToken: string) => {
    try {
      const response = await fetch(`${API_BASE}/api/auth/me`, {
        headers: {
          'Authorization': `Bearer ${accessToken}`,
        },
      });

      if (response.ok) {
        const userData = await response.json();
        setUser(userData);
      } else {
        // Token 无效，清除存储
        logout();
      }
    } catch (error) {
      console.error('Failed to fetch user info:', error);
      logout();
    } finally {
      setIsLoading(false);
    }
  };

  // 登录
  const login = async (username: string, password: string) => {
    try {
      const response = await fetch(`${API_BASE}/api/auth/login`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ username, password }),
      });

      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || 'Login failed');
      }

      const data = await response.json();
      const { access_token, refresh_token } = data;

      // 存储 token
      localStorage.setItem('access_token', access_token);
      localStorage.setItem('refresh_token', refresh_token);

      setToken(access_token);
      setRefreshTokenValue(refresh_token);

      // 获取用户信息
      await fetchUserInfo(access_token);
    } catch (error) {
      console.error('Login error:', error);
      throw error;
    }
  };

  // 登出
  const logout = () => {
    localStorage.removeItem('access_token');
    localStorage.removeItem('refresh_token');
    setToken(null);
    setRefreshTokenValue(null);
    setUser(null);
  };

  // 刷新 token
  const refreshToken = async () => {
    if (!refreshTokenValue) {
      logout();
      return;
    }

    try {
      const response = await fetch(`${API_BASE}/api/auth/refresh`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ refresh_token: refreshTokenValue }),
      });

      if (response.ok) {
        const data = await response.json();
        const { access_token, refresh_token: new_refresh_token } = data;

        localStorage.setItem('access_token', access_token);
        setToken(access_token);

        // 保存新的 refresh token（支持 token 轮换）
        if (new_refresh_token) {
          localStorage.setItem('refresh_token', new_refresh_token);
          setRefreshTokenValue(new_refresh_token);
        }
      } else {
        // Refresh token 无效，需要重新登录
        logout();
      }
    } catch (error) {
      console.error('Token refresh error:', error);
      logout();
    }
  };

  // 自动刷新 token（每 50 分钟，access token 60 分钟过期）
  useEffect(() => {
    if (!token) return;

    const interval = setInterval(() => {
      refreshToken();
    }, 50 * 60 * 1000); // 50 分钟

    return () => clearInterval(interval);
  }, [token, refreshTokenValue]);

  const value: AuthContextType = {
    user,
    token,
    isAuthenticated: !!user,
    isLoading,
    login,
    logout,
    refreshToken,
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
