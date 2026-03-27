'use client';

import { createContext, useCallback, useContext, useEffect, useMemo, ReactNode } from 'react';
import { useUserPreferences } from '@/contexts/UserPreferencesContext';
import { translate, type Locale } from '@/lib/i18n';

interface I18nContextValue {
  locale: Locale;
  t: (key: string, vars?: Record<string, string | number>) => string;
}

const I18nContext = createContext<I18nContextValue | null>(null);

export function I18nProvider({ children }: { children: ReactNode }) {
  const { prefs } = useUserPreferences();

  useEffect(() => {
    document.documentElement.lang = prefs.locale;
  }, [prefs.locale]);

  const t = useCallback((key: string, vars?: Record<string, string | number>) => {
    return translate(prefs.locale, key, vars);
  }, [prefs.locale]);

  const value = useMemo<I18nContextValue>(() => ({
    locale: prefs.locale,
    t,
  }), [prefs.locale, t]);

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export function useI18n(): I18nContextValue {
  const ctx = useContext(I18nContext);
  if (!ctx) {
    throw new Error('useI18n must be used within I18nProvider');
  }
  return ctx;
}
