'use client';

import { useState, useEffect, useCallback, useRef, useMemo } from 'react';
import {
  Folder, FolderOpen, File, ChevronRight, ChevronDown,
  Loader2, RefreshCw, CheckCircle2,
  Search, Presentation, Cog, Sparkles, Plus,
} from 'lucide-react';
import Link from 'next/link';
import { useDrag } from 'react-dnd';
import { cn } from '@/lib/utils';
import { authFetch, API_BASE } from '@/lib/authFetch';
import { useFilePanel } from '@/contexts/FilePanelContext';
import { useChatSession } from '@/contexts/ChatSessionContext';
import { useFeatureNavItems } from '@/components/layout/DashboardNav';
import { ResizablePanelGroup, ResizablePanel, ResizableHandle } from '@/components/ui/resizable';

interface FileItem {
  name: string;
  path: string;
  type: 'file' | 'folder';
}

function norm(p: string): string {
  return p.replace(/\\/g, '/').replace(/\/+$/, '');
}

/* ── 文件树节点 ── */

function FileTreeItem({ item, depth = 0, expandToPath }: {
  item: FileItem;
  depth?: number;
  expandToPath?: string | null;
}) {
  const [expanded, setExpanded] = useState(false);
  const [children, setChildren] = useState<FileItem[] | null>(null);
  const [loading, setLoading] = useState(false);
  const userCollapsed = useRef(false);
  const prevExpandTo = useRef(expandToPath);
  const itemRef = useRef<HTMLDivElement>(null);
  const isFolder = item.type === 'folder';

  const normItem = norm(item.path);
  const normTarget = expandToPath ? norm(expandToPath) : null;
  const shouldAutoExpand = isFolder && normTarget !== null && normTarget.startsWith(normItem + '/');
  const isTarget = normTarget !== null && normTarget === normItem;

  const loadChildren = useCallback(async () => {
    if (!isFolder || loading) return;
    setLoading(true);
    try {
      const res = await authFetch(`${API_BASE}/api/files?path=${encodeURIComponent(item.path)}`);
      const data = await res.json();
      setChildren(data.items || []);
    } catch { setChildren([]); }
    finally { setLoading(false); }
  }, [isFolder, item.path, loading]);

  useEffect(() => {
    if (prevExpandTo.current !== expandToPath) {
      userCollapsed.current = false;
      prevExpandTo.current = expandToPath;
    }
  }, [expandToPath]);

  useEffect(() => {
    if (shouldAutoExpand && !expanded && !userCollapsed.current) {
      setExpanded(true);
    }
  }, [shouldAutoExpand, expanded]);

  useEffect(() => {
    if (expanded && children === null && !loading) {
      loadChildren();
    }
  }, [expanded, children, loading, loadChildren]);

  useEffect(() => {
    if (isTarget && itemRef.current) {
      itemRef.current.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
  }, [isTarget]);

  const [{ isDragging }, dragRef] = useDrag(() => ({
    type: 'FILE',
    item: { name: item.name, path: item.path },
    collect: (monitor) => ({ isDragging: monitor.isDragging() }),
  }), [item]);

  const setRefs = useCallback((el: HTMLDivElement | null) => {
    (dragRef as unknown as (el: HTMLDivElement | null) => void)(el);
    if (isTarget && el) (itemRef as React.MutableRefObject<HTMLDivElement | null>).current = el;
  }, [dragRef, isTarget]);

  const toggleFolder = async () => {
    if (!isFolder) return;
    if (expanded) {
      userCollapsed.current = true;
      setExpanded(false);
      return;
    }
    userCollapsed.current = false;
    if (!children) await loadChildren();
    setExpanded(true);
  };

  return (
    <div style={{ opacity: isDragging ? 0.5 : 1 }}>
      <div
        ref={setRefs}
        className={cn(
          'flex items-center gap-1.5 px-2 py-1.5 rounded-lg hover:bg-muted cursor-grab active:cursor-grabbing text-sm transition-colors',
          isTarget && 'bg-primary/10 text-primary font-semibold ring-1 ring-primary/30',
        )}
        style={{ paddingLeft: `${depth * 16 + 8}px` }}
        onClick={toggleFolder}
      >
        {isFolder && (expanded
          ? <ChevronDown className="w-3 h-3 text-muted-foreground shrink-0" />
          : <ChevronRight className="w-3 h-3 text-muted-foreground shrink-0" />
        )}
        {isFolder ? (
          expanded
            ? <FolderOpen className="w-4 h-4 text-primary shrink-0" />
            : <Folder className="w-4 h-4 text-primary shrink-0" />
        ) : (
          <File className={cn('w-4 h-4 shrink-0', isTarget ? 'text-primary' : 'text-muted-foreground')} />
        )}
        <span className={cn('truncate text-xs', isTarget ? 'text-primary' : 'text-foreground/80')}>
          {item.name}
        </span>
        {loading && <Loader2 className="w-3 h-3 text-muted-foreground ml-auto animate-spin" />}
      </div>

      {isFolder && expanded && children && (
        <div>
          {children.map(child => (
            <FileTreeItem key={child.path} item={child} depth={depth + 1} expandToPath={expandToPath} />
          ))}
          {children.length === 0 && (
            <div className="text-[10px] text-muted-foreground/50 py-1" style={{ paddingLeft: `${(depth + 1) * 16 + 8}px` }}>
              空文件夹
            </div>
          )}
        </div>
      )}

      {isFolder && expanded && children === null && loading && (
        <div className="py-1" style={{ paddingLeft: `${(depth + 1) * 16 + 8}px` }}>
          <Loader2 className="w-3 h-3 animate-spin text-muted-foreground" />
        </div>
      )}
    </div>
  );
}

/* ── 合并连续相同操作的 step ── */

interface MergedStep {
  label: string;
  count: number;
  status: 'done' | 'running' | 'pending';
}

function mergeSteps(steps: { label: string; status: string }[]): MergedStep[] {
  const merged: MergedStep[] = [];
  for (const s of steps) {
    const last = merged[merged.length - 1];
    if (last && last.label === s.label && last.status === s.status) {
      last.count++;
    } else {
      merged.push({ label: s.label, count: 1, status: s.status as MergedStep['status'] });
    }
  }
  return merged;
}

interface MergedProgress {
  task: string;
  done: number;
  total: number;
}

function mergeProgress(items: { task: string; step: number; total: number; status: string }[]): MergedProgress[] {
  const merged: MergedProgress[] = [];
  for (const t of items) {
    const last = merged[merged.length - 1];
    if (last && last.task === t.task) {
      last.done += t.step;
      last.total += t.total;
    } else {
      merged.push({ task: t.task, done: t.step, total: t.total });
    }
  }
  return merged;
}

/* ── AI 工作区（空闲：功能入口 / 对话中：执行进度） ── */

const FEATURE_ICONS: Record<string, React.ReactNode> = {
  '深度研究': <Search className="w-4 h-4" />,
  'PPT': <Presentation className="w-4 h-4" />,
  '自动化': <Cog className="w-4 h-4" />,
  '+ 创建': <Plus className="w-4 h-4" />,
};

function AIWorkspace() {
  const { currentSessionId, taskProgress } = useChatSession();
  const featureNavItems = useFeatureNavItems();
  const mergedProgress = useMemo(() => mergeProgress(taskProgress), [taskProgress]);

  const isInConversation = Boolean(currentSessionId);
  const hasProgress = mergedProgress.length > 0;

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center justify-between px-4 py-3 shrink-0 border-b border-border/40">
        <div className="flex items-center gap-2">
          <div className="w-1.5 h-1.5 rounded-full bg-primary/60" />
          <span className="text-[10px] font-bold text-muted-foreground/80 uppercase tracking-[0.15em]">
            AI 工作区
          </span>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto px-2 pb-2">
        {isInConversation ? (
          /* ── 对话中：显示任务执行状态 ── */
          hasProgress ? (
            <div className="space-y-1 pt-2">
              {mergedProgress.map((task, index) => {
                const isDone = task.done >= task.total;
                return (
                  <div key={index} className="flex items-center gap-2 px-2 py-1.5 rounded-lg hover:bg-muted/50 transition-colors">
                    {isDone
                      ? <CheckCircle2 className="w-3.5 h-3.5 text-emerald-500 shrink-0" />
                      : <Loader2 className="w-3.5 h-3.5 text-primary animate-spin shrink-0" />
                    }
                    <span className={cn(
                      'text-xs truncate flex-1 min-w-0',
                      isDone ? 'text-muted-foreground' : 'text-foreground font-medium',
                    )}>
                      {task.task}
                    </span>
                    <span className={cn(
                      'text-[10px] font-semibold shrink-0 tabular-nums',
                      isDone ? 'text-muted-foreground/60' : 'text-amber-500',
                    )}>
                      {task.done}/{task.total}
                    </span>
                  </div>
                );
              })}
            </div>
          ) : (
            <div className="text-[10px] text-muted-foreground/50 px-1 py-4 text-center">
              暂无执行任务
            </div>
          )
        ) : (
          /* ── 空闲：显示功能入口 ── */
          <div className="space-y-1.5 pt-2">
            {featureNavItems.map((item) => (
              <Link
                key={item.path}
                href={item.path}
                className="flex items-center gap-2.5 rounded-xl border border-border/30 bg-muted/20 px-3 py-2.5 text-xs font-medium text-muted-foreground hover:text-foreground hover:bg-muted/50 hover:border-border/60 transition-all duration-150"
              >
                <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-primary/8 text-primary">
                  {FEATURE_ICONS[item.label] || <Sparkles className="w-4 h-4" />}
                </span>
                <span>{item.label}</span>
              </Link>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

/* ── 全局文件面板（常驻右侧） ── */

function bestMatchRoot(roots: FileItem[], target: string | null): string | null {
  if (!target) return null;
  const nt = norm(target);
  let best: string | null = null;
  let bestLen = -1;
  for (const r of roots) {
    const nr = norm(r.path);
    if (nt.startsWith(nr + '/') || nt === nr) {
      if (nr.length > bestLen) { best = nr; bestLen = nr.length; }
    }
  }
  return best;
}

export function GlobalFilePanel() {
  const { focusPath, focusGeneration } = useFilePanel();
  const localTreeKey = `${focusPath ?? 'manual'}-${focusGeneration}`;
  const [roots, setRoots] = useState<FileItem[]>([]);

  const loadRoots = useCallback(async () => {
    try {
      const res = await authFetch(`${API_BASE}/api/files/roots`);
      if (!res.ok) { setRoots([]); return; }
      const data = await res.json();
      setRoots(data.roots || []);
    } catch { setRoots([]); }
  }, []);

  useEffect(() => { loadRoots(); }, [loadRoots]);

  const bestRoot = bestMatchRoot(roots, focusPath);

  return (
    <ResizablePanelGroup orientation="vertical" className="h-full gap-2.5">
      {/* 文件区 */}
      <ResizablePanel id="file-tree" defaultSize="50%" minSize="20%" className="rounded-[var(--panel-radius)] border border-border/40 overflow-hidden bg-background shadow-sm">
        <div className="flex flex-col h-full">
          <div className="flex items-center justify-between px-4 py-3 shrink-0 border-b border-border/40">
            <div className="flex items-center gap-2">
              <div className="w-1.5 h-1.5 rounded-full bg-teal-500/60" />
              <span className="text-[10px] font-bold text-muted-foreground/80 uppercase tracking-[0.15em]">文件区</span>
            </div>
            <button onClick={loadRoots} className="p-1.5 rounded-lg hover:bg-muted text-muted-foreground/50 hover:text-foreground transition-all">
              <RefreshCw className="w-3 h-3" />
            </button>
          </div>
          <div className="flex-1 overflow-y-auto py-1">
            <div className="space-y-0.5 px-1" key={localTreeKey}>
              {roots.map(r => (
                <FileTreeItem
                  key={r.path}
                  item={r}
                  expandToPath={bestRoot === norm(r.path) ? focusPath : null}
                />
              ))}
              {roots.length === 0 && (
                <div className="text-[10px] text-muted-foreground/50 px-3 py-4 text-center">
                  <Loader2 className="w-4 h-4 mx-auto mb-1 animate-spin opacity-40" />
                  加载中…
                </div>
              )}
            </div>
          </div>
        </div>
      </ResizablePanel>

      <ResizableHandle invisible orientation="vertical" />

      {/* AI 工作区 */}
      <ResizablePanel id="ai-workspace" defaultSize="50%" minSize="15%" className="rounded-[var(--panel-radius)] border border-border/40 overflow-hidden bg-background shadow-sm">
        <AIWorkspace />
      </ResizablePanel>
    </ResizablePanelGroup>
  );
}
