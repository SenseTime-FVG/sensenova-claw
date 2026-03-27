'use client';

import { createContext, useContext, useState, useEffect, useCallback, ReactNode } from 'react';
import { useTheme } from 'next-themes';
import { type Locale } from '@/lib/i18n';

// ── 类型定义 ──

export type AccentColor = 'teal' | 'indigo' | 'amber' | 'rose' | 'violet' | 'slate';
export type FontSize = 'compact' | 'standard' | 'comfortable';
export type PanelRadius = 'rounded' | 'sharp';

export interface UserPreferences {
  accentColor: AccentColor;
  fontSize: FontSize;
  panelRadius: PanelRadius;
  locale: Locale;
}

const DEFAULT_PREFS: UserPreferences = {
  accentColor: 'teal',
  fontSize: 'standard',
  panelRadius: 'rounded',
  locale: 'zh-CN',
};

const STORAGE_KEY = 'sensenova-claw-user-prefs';

// ── 预设色板定义 ──

interface AccentColorDef {
  label: string;
  light: string; // hsl 值
  dark: string;
  lightForeground: string;
  darkForeground: string;
}

export const ACCENT_COLORS: Record<AccentColor, AccentColorDef> = {
  teal: {
    label: '青绿',
    light: 'hsl(172, 66%, 40%)',
    dark: 'hsl(172, 60%, 48%)',
    lightForeground: 'hsl(0, 0%, 100%)',
    darkForeground: 'hsl(225, 15%, 8%)',
  },
  indigo: {
    label: '靛蓝',
    light: 'hsl(234, 89%, 60%)',
    dark: 'hsl(234, 80%, 66%)',
    lightForeground: 'hsl(0, 0%, 100%)',
    darkForeground: 'hsl(225, 15%, 8%)',
  },
  amber: {
    label: '琥珀',
    light: 'hsl(38, 92%, 50%)',
    dark: 'hsl(38, 90%, 56%)',
    lightForeground: 'hsl(0, 0%, 100%)',
    darkForeground: 'hsl(225, 15%, 8%)',
  },
  rose: {
    label: '玫瑰',
    light: 'hsl(347, 77%, 50%)',
    dark: 'hsl(347, 70%, 58%)',
    lightForeground: 'hsl(0, 0%, 100%)',
    darkForeground: 'hsl(225, 15%, 8%)',
  },
  violet: {
    label: '紫罗兰',
    light: 'hsl(263, 70%, 58%)',
    dark: 'hsl(263, 65%, 65%)',
    lightForeground: 'hsl(0, 0%, 100%)',
    darkForeground: 'hsl(225, 15%, 8%)',
  },
  slate: {
    label: '石板蓝',
    light: 'hsl(215, 20%, 40%)',
    dark: 'hsl(215, 18%, 52%)',
    lightForeground: 'hsl(0, 0%, 100%)',
    darkForeground: 'hsl(225, 15%, 8%)',
  },
};

const FONT_SIZE_MAP: Record<FontSize, string> = {
  compact: '12px',
  standard: '13px',
  comfortable: '14px',
};

const PANEL_RADIUS_MAP: Record<PanelRadius, { panel: string; base: string }> = {
  rounded: { panel: '14px', base: '0.625rem' },
  sharp: { panel: '6px', base: '0.25rem' },
};

// ── Context ──

interface UserPreferencesContextValue {
  prefs: UserPreferences;
  setAccentColor: (color: AccentColor) => void;
  setFontSize: (size: FontSize) => void;
  setPanelRadius: (radius: PanelRadius) => void;
  setLocale: (locale: Locale) => void;
}

const UserPreferencesContext = createContext<UserPreferencesContextValue | null>(null);

export function useUserPreferences() {
  const ctx = useContext(UserPreferencesContext);
  if (!ctx) throw new Error('useUserPreferences must be used within UserPreferencesProvider');
  return ctx;
}

// ── Provider ──

function loadPrefs(): UserPreferences {
  if (typeof window === 'undefined') return DEFAULT_PREFS;
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return DEFAULT_PREFS;
    const parsed = JSON.parse(raw);
    return { ...DEFAULT_PREFS, ...parsed };
  } catch {
    return DEFAULT_PREFS;
  }
}

function savePrefs(prefs: UserPreferences) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(prefs));
  } catch { /* 静默失败 */ }
}

// 将偏好应用到 DOM
function applyPrefs(prefs: UserPreferences, resolvedTheme: string | undefined) {
  const root = document.documentElement;
  const isDark = resolvedTheme === 'dark';

  // 主题色
  const colorDef = ACCENT_COLORS[prefs.accentColor];
  const primaryColor = isDark ? colorDef.dark : colorDef.light;
  const primaryFg = isDark ? colorDef.darkForeground : colorDef.lightForeground;

  root.style.setProperty('--primary', primaryColor);
  root.style.setProperty('--primary-foreground', primaryFg);
  root.style.setProperty('--ring', primaryColor);
  root.style.setProperty('--sidebar-primary', primaryColor);
  root.style.setProperty('--sidebar-primary-foreground', primaryFg);
  root.style.setProperty('--sidebar-ring', primaryColor);
  root.style.setProperty('--chart-1', primaryColor);

  // 字号
  root.style.setProperty('font-size', FONT_SIZE_MAP[prefs.fontSize]);

  // 面板圆角
  const radiusDef = PANEL_RADIUS_MAP[prefs.panelRadius];
  root.style.setProperty('--panel-radius', radiusDef.panel);
  root.style.setProperty('--radius', radiusDef.base);
}

export function UserPreferencesProvider({ children }: { children: ReactNode }) {
  const [prefs, setPrefs] = useState<UserPreferences>(DEFAULT_PREFS);
  const { resolvedTheme } = useTheme();
  const [mounted, setMounted] = useState(false);

  // 初始化：从 localStorage 加载
  useEffect(() => {
    setPrefs(loadPrefs());
    setMounted(true);
  }, []);

  // 偏好变化时应用到 DOM 并持久化
  useEffect(() => {
    if (!mounted) return;
    applyPrefs(prefs, resolvedTheme);
    savePrefs(prefs);
  }, [prefs, resolvedTheme, mounted]);

  const setAccentColor = useCallback((color: AccentColor) => {
    setPrefs(prev => ({ ...prev, accentColor: color }));
  }, []);

  const setFontSize = useCallback((size: FontSize) => {
    setPrefs(prev => ({ ...prev, fontSize: size }));
  }, []);

  const setPanelRadius = useCallback((radius: PanelRadius) => {
    setPrefs(prev => ({ ...prev, panelRadius: radius }));
  }, []);

  const setLocale = useCallback((locale: Locale) => {
    setPrefs(prev => ({ ...prev, locale }));
  }, []);

  return (
    <UserPreferencesContext.Provider value={{ prefs, setAccentColor, setFontSize, setPanelRadius, setLocale }}>
      {children}
    </UserPreferencesContext.Provider>
  );
}
