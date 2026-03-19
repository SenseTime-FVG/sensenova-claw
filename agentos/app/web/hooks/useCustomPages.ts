'use client';

import { useState, useEffect, useCallback } from 'react';
import { authFetch, API_BASE } from '@/lib/authFetch';

export interface CustomPageInfo {
  id: string;
  slug: string;
  name: string;
  icon: string;
}

let cachedPages: CustomPageInfo[] | null = null;
let cacheListeners: Array<(pages: CustomPageInfo[]) => void> = [];

function notifyListeners(pages: CustomPageInfo[]) {
  cachedPages = pages;
  cacheListeners.forEach(fn => fn(pages));
}

export function useCustomPages() {
  const [pages, setPages] = useState<CustomPageInfo[]>(cachedPages || []);
  const [loading, setLoading] = useState(!cachedPages);

  useEffect(() => {
    const listener = (newPages: CustomPageInfo[]) => setPages(newPages);
    cacheListeners.push(listener);
    return () => {
      cacheListeners = cacheListeners.filter(l => l !== listener);
    };
  }, []);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const res = await authFetch(`${API_BASE}/api/custom-pages`);
      const data = await res.json();
      const list: CustomPageInfo[] = (data.pages || []).map((p: Record<string, string>) => ({
        id: p.id,
        slug: p.slug,
        name: p.name,
        icon: p.icon || 'Sparkles',
      }));
      notifyListeners(list);
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!cachedPages) {
      refresh();
    }
  }, [refresh]);

  return { pages, loading, refresh };
}

export function invalidateCustomPages() {
  cachedPages = null;
}
