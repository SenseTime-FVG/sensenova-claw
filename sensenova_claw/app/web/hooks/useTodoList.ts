'use client';

import { useState, useEffect, useCallback, useRef } from 'react';
import { authGet, authPost, authPut, authDelete, API_BASE } from '@/lib/authFetch';
import { useEventDispatcher } from '@/contexts/ws';
import type { WsInboundEvent } from '@/lib/wsEvents';

export interface TodoItem {
  id: string;
  title: string;
  priority: 'high' | 'medium' | 'low';
  due_date: string | null;
  status: 'todo' | 'done';
  order: number;
  created_at: string;
  completed_at: string | null;
}

function todayStr(): string {
  const d = new Date();
  return d.getFullYear() + '-' +
    String(d.getMonth() + 1).padStart(2, '0') + '-' +
    String(d.getDate()).padStart(2, '0');
}

export function useTodoList(date?: string) {
  const dateStr = date || todayStr();
  const [items, setItems] = useState<TodoItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const mountedRef = useRef(true);
  const fetchItems = useCallback(async () => {
    try {
      const data = await authGet<{ date: string; items: TodoItem[] }>(
        `${API_BASE}/api/todolist/${dateStr}`
      );
      if (mountedRef.current) {
        setItems(data.items.sort((a, b) => a.order - b.order));
        setError(null);
      }
    } catch (e: any) {
      if (mountedRef.current) {
        setError(e.message || '加载待办失败');
      }
    } finally {
      if (mountedRef.current) setLoading(false);
    }
  }, [dateStr]);

  // 初始加载 + 兜底轮询（间隔拉长，主要靠事件驱动）
  useEffect(() => {
    mountedRef.current = true;
    setLoading(true);
    fetchItems();
    const interval = setInterval(fetchItems, 120000);
    return () => {
      mountedRef.current = false;
      clearInterval(interval);
    };
  }, [fetchItems]);

  // 监听 WebSocket todolist_updated 事件，收到后立即刷新
  const { subscribeGlobal } = useEventDispatcher();
  useEffect(() => {
    return subscribeGlobal((event: WsInboundEvent) => {
      if (event.type === 'todolist_updated') {
        if (!event.payload.date || event.payload.date === dateStr) {
          fetchItems();
        }
      }
    });
  }, [subscribeGlobal, dateStr, fetchItems]);

  const addItem = useCallback(async (
    title: string,
    priority: 'high' | 'medium' | 'low' = 'medium',
    dueDate?: string
  ) => {
    const newItem = await authPost<TodoItem>(
      `${API_BASE}/api/todolist/${dateStr}/items`,
      { title, priority, due_date: dueDate || null }
    );
    setItems(prev => [...prev, newItem]);
  }, [dateStr]);

  const toggleItem = useCallback(async (id: string) => {
    // 乐观更新
    setItems(prev => prev.map(item =>
      item.id === id
        ? { ...item, status: item.status === 'todo' ? 'done' : 'todo' as const }
        : item
    ));
    const item = items.find(i => i.id === id);
    if (!item) return;
    const newStatus = item.status === 'todo' ? 'done' : 'todo';
    try {
      await authPut(`${API_BASE}/api/todolist/${dateStr}/items/${id}`, { status: newStatus });
    } catch {
      fetchItems(); // 回滚
    }
  }, [dateStr, items, fetchItems]);

  const updateItem = useCallback(async (id: string, updates: Partial<TodoItem>) => {
    setItems(prev => prev.map(item =>
      item.id === id ? { ...item, ...updates } : item
    ));
    try {
      await authPut(`${API_BASE}/api/todolist/${dateStr}/items/${id}`, updates);
    } catch {
      fetchItems();
    }
  }, [dateStr, fetchItems]);

  const deleteItem = useCallback(async (id: string) => {
    setItems(prev => prev.filter(item => item.id !== id));
    try {
      await authDelete(`${API_BASE}/api/todolist/${dateStr}/items/${id}`);
    } catch {
      fetchItems();
    }
  }, [dateStr, fetchItems]);

  const reorderItems = useCallback(async (itemIds: string[]) => {
    // 乐观排序
    setItems(prev => {
      const map = new Map(prev.map(i => [i.id, i]));
      return itemIds.map((id, idx) => {
        const item = map.get(id);
        return item ? { ...item, order: idx } : null;
      }).filter(Boolean) as TodoItem[];
    });
    try {
      await authPut(`${API_BASE}/api/todolist/${dateStr}/reorder`, { item_ids: itemIds });
    } catch {
      fetchItems();
    }
  }, [dateStr, fetchItems]);

  return {
    items,
    loading,
    error,
    addItem,
    toggleItem,
    updateItem,
    deleteItem,
    reorderItems,
    refresh: fetchItems,
  };
}
