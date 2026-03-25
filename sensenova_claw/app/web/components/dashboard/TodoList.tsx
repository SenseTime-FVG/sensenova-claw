'use client';

import { useState, useRef, useCallback } from 'react';
import { useDrag, useDrop } from 'react-dnd';
import {
  GripVertical,
  Plus,
  X,
  Calendar,
  Flag,
  Pencil,
  Check,
  ListTodo,
} from 'lucide-react';
import { SectionHeader } from './SectionHeader';
import { useTodoList, type TodoItem } from '@/hooks/useTodoList';

const TODO_DND_TYPE = 'PERSONAL_TODO_ITEM';

// ── 优先级配色 ──────────────────────────────────────────────

const priorityConfig = {
  high: {
    dot: 'bg-rose-500',
    label: '高',
    pill: 'bg-rose-500/10 text-rose-700 border-rose-200',
  },
  medium: {
    dot: 'bg-amber-500',
    label: '中',
    pill: 'bg-amber-500/10 text-amber-700 border-amber-200',
  },
  low: {
    dot: 'bg-sky-500',
    label: '低',
    pill: 'bg-sky-500/10 text-sky-700 border-sky-200',
  },
} as const;

// ── 日期辅助 ──────────────────────────────────────────────

function isOverdue(dueDate: string | null): boolean {
  if (!dueDate) return false;
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  return new Date(dueDate) < today;
}

function formatDueDate(dueDate: string): string {
  const d = new Date(dueDate);
  return `${d.getMonth() + 1}/${d.getDate()}`;
}

// ── 拖拽项 ──────────────────────────────────────────────────

interface DragItem {
  index: number;
  id: string;
}

function TodoItemCard({
  item,
  index,
  onToggle,
  onDelete,
  onUpdate,
  onMove,
}: {
  item: TodoItem;
  index: number;
  onToggle: (id: string) => void;
  onDelete: (id: string) => void;
  onUpdate: (id: string, updates: Partial<TodoItem>) => void;
  onMove: (dragIndex: number, hoverIndex: number) => void;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const titleInputRef = useRef<HTMLInputElement>(null);
  const isDone = item.status === 'done';
  const pConfig = priorityConfig[item.priority];
  const overdue = !isDone && isOverdue(item.due_date);

  // 编辑状态
  const [editing, setEditing] = useState(false);
  const [editTitle, setEditTitle] = useState(item.title);
  const [editPriority, setEditPriority] = useState(item.priority);
  const [editDueDate, setEditDueDate] = useState(item.due_date || '');

  const startEdit = () => {
    setEditTitle(item.title);
    setEditPriority(item.priority);
    setEditDueDate(item.due_date || '');
    setEditing(true);
    setTimeout(() => titleInputRef.current?.focus(), 0);
  };

  const saveEdit = () => {
    const trimmed = editTitle.trim();
    if (!trimmed) {
      setEditing(false);
      return;
    }
    const updates: Partial<TodoItem> = {};
    if (trimmed !== item.title) updates.title = trimmed;
    if (editPriority !== item.priority) updates.priority = editPriority;
    const newDue = editDueDate || null;
    if (newDue !== item.due_date) updates.due_date = newDue;
    if (Object.keys(updates).length > 0) {
      onUpdate(item.id, updates);
    }
    setEditing(false);
  };

  const cancelEdit = () => {
    setEditing(false);
  };

  const [{ isDragging }, drag, preview] = useDrag({
    type: TODO_DND_TYPE,
    item: { index, id: item.id },
    canDrag: !editing,
    collect: (monitor) => ({ isDragging: monitor.isDragging() }),
  });

  const [, drop] = useDrop<DragItem>({
    accept: TODO_DND_TYPE,
    hover(dragItem, monitor) {
      if (!ref.current) return;
      const dragIndex = dragItem.index;
      const hoverIndex = index;
      if (dragIndex === hoverIndex) return;

      const rect = ref.current.getBoundingClientRect();
      const hoverMiddleY = (rect.bottom - rect.top) / 2;
      const clientOffset = monitor.getClientOffset();
      if (!clientOffset) return;
      const hoverClientY = clientOffset.y - rect.top;

      if (dragIndex < hoverIndex && hoverClientY < hoverMiddleY) return;
      if (dragIndex > hoverIndex && hoverClientY > hoverMiddleY) return;

      onMove(dragIndex, hoverIndex);
      dragItem.index = hoverIndex;
    },
  });

  preview(drop(ref));

  // ── 编辑模式 ──
  if (editing) {
    return (
      <div
        ref={ref}
        className="relative flex flex-col gap-2 rounded-2xl border border-violet-200 dark:border-violet-800 bg-[var(--glass-bg-heavy)] px-3 py-3 shadow-[0_6px_18px_rgba(15,23,42,0.06)] dark:shadow-[0_6px_18px_rgba(0,0,0,0.2)] backdrop-blur-xl"
      >
        {/* 标题编辑 */}
        <input
          ref={titleInputRef}
          type="text"
          value={editTitle}
          onChange={(e) => setEditTitle(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') saveEdit();
            if (e.key === 'Escape') cancelEdit();
          }}
          className="flex-1 rounded-lg border border-[var(--glass-border-heavy)] bg-[var(--glass-bg)] px-2 py-1.5 text-sm text-[var(--glass-text)] outline-none focus:border-violet-300 dark:focus:border-violet-600"
          placeholder="待办内容"
        />

        {/* 优先级 + 日期 + 操作 */}
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-1.5">
            <Flag className="h-3.5 w-3.5 text-muted-foreground" />
            {(['high', 'medium', 'low'] as const).map((p) => (
              <button
                key={p}
                type="button"
                onClick={() => setEditPriority(p)}
                className={`rounded-full border px-2 py-0.5 text-[11px] font-medium transition-all ${
                  editPriority === p
                    ? priorityConfig[p].pill + ' border-current'
                    : 'border-transparent text-muted-foreground hover:text-foreground'
                }`}
              >
                {priorityConfig[p].label}
              </button>
            ))}
          </div>

          <div className="relative flex items-center gap-1.5">
            <Calendar className="h-3.5 w-3.5 text-muted-foreground" />
            <div className="relative">
              <input
                type="date"
                value={editDueDate}
                onChange={(e) => setEditDueDate(e.target.value)}
                className={`rounded-lg border border-[var(--glass-border-heavy)] bg-[var(--glass-bg)] px-2 py-0.5 text-[11px] outline-none ${
                  editDueDate ? 'text-muted-foreground' : 'text-transparent'
                }`}
                style={{ minWidth: '5.5rem' }}
              />
              {!editDueDate && (
                <span className="pointer-events-none absolute inset-0 flex items-center px-2 text-[11px] text-muted-foreground">
                  截止日期
                </span>
              )}
            </div>
          </div>

          <div className="ml-auto flex items-center gap-1">
            <button
              type="button"
              onClick={saveEdit}
              className="rounded-lg bg-violet-500 px-2.5 py-1 text-xs font-medium text-white shadow-sm transition-colors hover:bg-violet-600"
            >
              <Check className="h-3.5 w-3.5" />
            </button>
            <button
              type="button"
              onClick={cancelEdit}
              className="rounded-lg px-2.5 py-1 text-xs text-muted-foreground transition-colors hover:bg-muted"
            >
              <X className="h-3.5 w-3.5" />
            </button>
          </div>
        </div>
      </div>
    );
  }

  // ── 展示模式 ──
  return (
    <div
      ref={ref}
      className={`group relative flex items-center gap-3 rounded-2xl border border-[var(--glass-border-heavy)] bg-[var(--glass-bg)] px-3 py-3 shadow-[0_6px_18px_rgba(15,23,42,0.04)] dark:shadow-[0_6px_18px_rgba(0,0,0,0.12)] backdrop-blur-xl transition-all duration-200 ${
        isDragging ? 'opacity-40 scale-[0.97]' : 'opacity-100'
      } ${isDone ? 'bg-[var(--glass-bg-light)]' : ''}`}
    >
      {/* 拖拽手柄 */}
      <div
        ref={(node) => { drag(node); }}
        className="flex cursor-grab items-center text-muted-foreground/50 transition-colors hover:text-muted-foreground active:cursor-grabbing"
      >
        <GripVertical className="h-4 w-4" />
      </div>

      {/* Checkbox */}
      <button
        type="button"
        onClick={() => onToggle(item.id)}
        className={`relative flex h-5 w-5 shrink-0 items-center justify-center rounded-md border-2 transition-all duration-300 ${
          isDone
            ? 'border-violet-400 bg-violet-400 shadow-sm shadow-violet-200 dark:shadow-violet-900/50'
            : 'border-muted-foreground/30 bg-background hover:border-violet-400'
        }`}
      >
        {isDone && (
          <svg
            className="h-3 w-3 text-white dark:text-background"
            viewBox="0 0 12 12"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <path d="M2 6l3 3 5-5" />
          </svg>
        )}
      </button>

      {/* 标题 - 双击编辑 */}
      <span
        className={`min-w-0 flex-1 text-sm cursor-default transition-all duration-300 ${
          isDone
            ? 'text-muted-foreground line-through decoration-muted-foreground/50'
            : 'text-[var(--glass-text)] font-medium'
        }`}
        onDoubleClick={startEdit}
        title="双击编辑"
      >
        {item.title}
      </span>

      {/* 优先级色点 */}
      <div
        className={`h-2 w-2 shrink-0 rounded-full ${pConfig.dot} transition-opacity ${
          isDone ? 'opacity-30' : 'opacity-100'
        }`}
        title={`优先级: ${pConfig.label}`}
      />

      {/* 截止日期 */}
      {item.due_date && (
        <span
          className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-medium transition-colors ${
            overdue
              ? 'border-rose-200 dark:border-rose-800 bg-rose-500/10 text-rose-600 dark:text-rose-400'
              : 'border-[var(--glass-border-heavy)] bg-[var(--glass-bg)] text-muted-foreground'
          }`}
        >
          <Calendar className="h-3 w-3" />
          {formatDueDate(item.due_date)}
        </span>
      )}

      {/* 编辑按钮 */}
      <button
        type="button"
        onClick={startEdit}
        className="shrink-0 rounded-lg p-1 text-muted-foreground/50 opacity-0 transition-all hover:bg-violet-50 dark:hover:bg-violet-950 hover:text-violet-500 group-hover:opacity-100"
        title="编辑"
      >
        <Pencil className="h-3.5 w-3.5" />
      </button>

      {/* 删除按钮 */}
      <button
        type="button"
        onClick={() => onDelete(item.id)}
        className="shrink-0 rounded-lg p-1 text-muted-foreground/50 opacity-0 transition-all hover:bg-rose-50 dark:hover:bg-rose-950 hover:text-rose-500 group-hover:opacity-100"
      >
        <X className="h-3.5 w-3.5" />
      </button>
    </div>
  );
}

// ── 快速新增 ──────────────────────────────────────────────

function TodoQuickAdd({
  onAdd,
}: {
  onAdd: (title: string, priority: TodoItem['priority'], dueDate?: string) => void;
}) {
  const [title, setTitle] = useState('');
  const [priority, setPriority] = useState<TodoItem['priority']>('medium');
  const [dueDate, setDueDate] = useState('');
  const [showOptions, setShowOptions] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const handleSubmit = () => {
    const trimmed = title.trim();
    if (!trimmed) return;
    onAdd(trimmed, priority, dueDate || undefined);
    setTitle('');
    setDueDate('');
    setPriority('medium');
    setShowOptions(false);
    inputRef.current?.focus();
  };

  return (
    <div className="mb-4">
      <div className="flex items-center gap-2 rounded-2xl border border-[var(--glass-border-heavy)] bg-[var(--glass-bg)] px-3 py-2 shadow-inner backdrop-blur-xl transition-colors focus-within:border-violet-300 dark:focus-within:border-violet-600 focus-within:bg-[var(--glass-bg-heavy)]">
        <Plus className="h-4 w-4 text-muted-foreground" />
        <input
          ref={inputRef}
          type="text"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') handleSubmit();
          }}
          onFocus={() => setShowOptions(true)}
          placeholder="添加新待办..."
          className="flex-1 bg-transparent text-sm text-[var(--glass-text)] placeholder:text-muted-foreground outline-none"
        />
        {title.trim() && (
          <button
            type="button"
            onClick={handleSubmit}
            className="rounded-lg bg-violet-500 px-3 py-1 text-xs font-medium text-white shadow-sm transition-colors hover:bg-violet-600"
          >
            添加
          </button>
        )}
      </div>

      {/* 选项行：优先级 + 日期 */}
      {showOptions && (
        <div className="mt-2 flex items-center gap-3 px-1">
          <div className="flex items-center gap-1.5">
            <Flag className="h-3.5 w-3.5 text-muted-foreground" />
            {(['high', 'medium', 'low'] as const).map((p) => (
              <button
                key={p}
                type="button"
                onClick={() => setPriority(p)}
                className={`rounded-full border px-2 py-0.5 text-[11px] font-medium transition-all ${
                  priority === p
                    ? priorityConfig[p].pill + ' border-current'
                    : 'border-transparent text-muted-foreground hover:text-foreground'
                }`}
              >
                {priorityConfig[p].label}
              </button>
            ))}
          </div>
          <div className="relative flex items-center gap-1.5">
            <Calendar className="h-3.5 w-3.5 text-muted-foreground" />
            <div className="relative">
              <input
                type="date"
                value={dueDate}
                onChange={(e) => setDueDate(e.target.value)}
                className={`rounded-lg border border-[var(--glass-border-heavy)] bg-[var(--glass-bg)] px-2 py-0.5 text-[11px] outline-none ${
                  dueDate ? 'text-muted-foreground' : 'text-transparent'
                }`}
                style={{ minWidth: '5.5rem' }}
                title="截止日期"
              />
              {!dueDate && (
                <span className="pointer-events-none absolute inset-0 flex items-center px-2 text-[11px] text-muted-foreground">
                  截止日期
                </span>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// ── 主组件 ──────────────────────────────────────────────────

export function TodoList() {
  const {
    items,
    loading,
    addItem,
    toggleItem,
    updateItem,
    deleteItem,
    reorderItems,
  } = useTodoList();

  const [localItems, setLocalItems] = useState<TodoItem[]>([]);

  // 同步 hook 数据到本地状态（用于拖拽时的即时重排）
  const itemsRef = useRef(items);
  if (items !== itemsRef.current) {
    itemsRef.current = items;
    setLocalItems(items);
  }

  const handleMove = useCallback((dragIndex: number, hoverIndex: number) => {
    setLocalItems((prev) => {
      const updated = [...prev];
      const [removed] = updated.splice(dragIndex, 1);
      updated.splice(hoverIndex, 0, removed);
      return updated;
    });
  }, []);

  const handleDrop = useCallback(() => {
    const ids = localItems.map((i) => i.id);
    reorderItems(ids);
  }, [localItems, reorderItems]);

  // 使用 drop end 事件来触发保存
  const displayItems = localItems.length > 0 ? localItems : items;
  const todoCount = displayItems.filter((i) => i.status === 'todo').length;
  const doneCount = displayItems.filter((i) => i.status === 'done').length;

  return (
    <div className="flex h-full flex-col p-4">
      {/* 背景渐变 */}
      <div className="absolute inset-0 bg-gradient-to-br from-violet-50/70 via-background/90 to-fuchsia-50/50 dark:from-violet-950/30 dark:via-background/90 dark:to-fuchsia-950/20" />
      <div className="absolute -right-8 -top-8 h-24 w-24 rounded-full bg-violet-200/30 dark:bg-violet-800/20 blur-3xl" />

      <div className="relative z-10 flex h-full flex-col">
        <div className="flex items-center justify-between mb-3">
          <SectionHeader
            title="今日待办"
            subtitle={`${todoCount} 项待完成${doneCount > 0 ? ` · ${doneCount} 已完成` : ''}`}
            tag="Todo"
            tagTone="violet"
            icon={<ListTodo className="h-4 w-4 text-violet-500" />}
          />
        </div>

        <TodoQuickAdd
          onAdd={(title, priority, dueDate) => addItem(title, priority, dueDate)}
        />

        {loading ? (
          <div className="flex flex-1 items-center justify-center">
            <span className="text-[11px] text-muted-foreground">加载中...</span>
          </div>
        ) : displayItems.length === 0 ? (
          <div className="flex flex-1 items-center justify-center rounded-xl border border-dashed border-border bg-[var(--glass-bg-light)]">
            <span className="text-[11px] text-muted-foreground">添加一个待办吧</span>
          </div>
        ) : (
          <div
            className="flex-1 space-y-1.5 overflow-auto thin-scrollbar"
            onMouseUp={handleDrop}
          >
            {displayItems.map((item, index) => (
              <TodoItemCard
                key={item.id}
                item={item}
                index={index}
                onToggle={toggleItem}
                onDelete={deleteItem}
                onUpdate={updateItem}
                onMove={handleMove}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
