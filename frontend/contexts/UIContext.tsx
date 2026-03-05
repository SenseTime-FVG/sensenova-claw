'use client';

import React, { createContext, useContext, useMemo, useState } from 'react';

type SidebarView = 'explorer' | 'history';

interface UIContextValue {
  sidebarView: SidebarView;
  setSidebarView: (view: SidebarView) => void;
}

const UIContext = createContext<UIContextValue | null>(null);

export function UIProvider({ children }: { children: React.ReactNode }) {
  const [sidebarView, setSidebarView] = useState<SidebarView>('history');
  const value = useMemo(() => ({ sidebarView, setSidebarView }), [sidebarView]);
  return <UIContext.Provider value={value}>{children}</UIContext.Provider>;
}

export function useUIContext(): UIContextValue {
  const ctx = useContext(UIContext);
  if (!ctx) {
    throw new Error('useUIContext must be used inside UIProvider');
  }
  return ctx;
}
