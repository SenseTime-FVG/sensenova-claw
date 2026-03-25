'use client';

import { useState, useRef, useEffect } from 'react';
import { ListTodo, Check } from 'lucide-react';
import { useTodoList, type TodoItem } from '@/hooks/useTodoList';

const priorityDot: Record<TodoItem['priority'], string> = {
  high: 'bg-rose-500',
  medium: 'bg-amber-500',
  low: 'bg-sky-500',
};

export function TodoDropdown() {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const { items, toggleItem, loading } = useTodoList();

  const pendingCount = items.filter((i) => i.status === 'todo').length;

  // 点击外部关闭
  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    if (open) document.addEventListener('mousedown', handleClick);
    return () => document.removeEventListener('mousedown', handleClick);
  }, [open]);

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="relative p-1.5 rounded-lg hover:bg-muted transition-colors"
        title={`${pendingCount} 项待办`}
      >
        <ListTodo className="w-5 h-5 text-muted-foreground" />
        {pendingCount > 0 && (
          <span className="absolute -top-0.5 -right-0.5 min-w-[16px] h-[16px] rounded-full bg-violet-500 text-white text-[10px] font-bold flex items-center justify-center px-0.5">
            {pendingCount > 99 ? '99+' : pendingCount}
          </span>
        )}
      </button>

      {open && (
        <div className="absolute right-0 top-full mt-2 w-80 rounded-2xl border border-[var(--glass-border-heavy)] bg-[var(--glass-bg-heavy)] p-3 shadow-[0_20px_60px_rgba(15,23,42,0.12)] dark:shadow-[0_20px_60px_rgba(0,0,0,0.35)] backdrop-blur-2xl z-[100]">
          <div className="mb-2 flex items-center justify-between px-1">
            <span className="text-sm font-semibold text-[var(--glass-text)]">今日待办</span>
            <span className="rounded-full bg-violet-500/10 px-2 py-0.5 text-[11px] font-medium text-violet-700 dark:text-violet-300">
              {pendingCount} 项待完成
            </span>
          </div>

          {loading ? (
            <div className="flex h-20 items-center justify-center">
              <span className="text-xs text-[var(--glass-text-muted)]">加载中...</span>
            </div>
          ) : items.length === 0 ? (
            <div className="flex h-20 items-center justify-center">
              <span className="text-xs text-[var(--glass-text-muted)]">暂无待办</span>
            </div>
          ) : (
            <div className="max-h-[320px] space-y-1 overflow-y-auto hide-scrollbar">
              {items.map((item) => {
                const isDone = item.status === 'done';
                return (
                  <button
                    key={item.id}
                    type="button"
                    onClick={() => toggleItem(item.id)}
                    className="flex w-full items-center gap-2.5 rounded-xl px-2 py-2 text-left transition-colors hover:bg-muted"
                  >
                    {/* Checkbox */}
                    <div
                      className={`flex h-4.5 w-4.5 shrink-0 items-center justify-center rounded-md border-2 transition-all duration-200 ${
                        isDone
                          ? 'border-violet-400 bg-violet-400'
                          : 'border-muted-foreground/30 bg-background'
                      }`}
                      style={{ width: 18, height: 18 }}
                    >
                      {isDone && <Check className="h-3 w-3 text-white dark:text-background" />}
                    </div>

                    {/* 标题 */}
                    <span
                      className={`min-w-0 flex-1 truncate text-sm ${
                        isDone
                          ? 'text-muted-foreground line-through'
                          : 'text-[var(--glass-text)]'
                      }`}
                    >
                      {item.title}
                    </span>

                    {/* 优先级色点 */}
                    <div
                      className={`h-2 w-2 shrink-0 rounded-full ${priorityDot[item.priority]} ${
                        isDone ? 'opacity-30' : ''
                      }`}
                    />
                  </button>
                );
              })}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
