'use client';

import { useState, useCallback, useMemo, type RefObject } from 'react';
import { ResponsiveGridLayout, useContainerWidth, type Layout, type LayoutItem, type ResponsiveLayouts } from 'react-grid-layout';
import { GripHorizontal, RotateCcw, ZoomIn, ZoomOut } from 'lucide-react';
import { useDashboardData } from '@/hooks/useDashboardData';
import { useChatSession } from '@/contexts/ChatSessionContext';
import { useNotification } from '@/hooks/useNotification';
import { SmartStack } from './SmartStack';
import { RecentOutputs } from './RecentOutputs';
import { ScheduledTasks } from './ScheduledTasks';
import { ProactiveAgentPanel } from './ProactiveAgentPanel';
import { KanbanBoard } from './KanbanBoard';
import { TodoList } from './TodoList';

type Layouts = ResponsiveLayouts;
const ResponsiveGrid = ResponsiveGridLayout;

// ── 布局持久化 ──────────────────────────────────────────────

const LAYOUT_STORAGE_KEY = 'sensenova-claw-dashboard-layout-v3';
const ZOOM_STORAGE_KEY = 'sensenova-claw-dashboard-zoom';
const ZOOM_STEPS = [0.7, 0.8, 0.9, 1.0, 1.1, 1.2] as const;
const DEFAULT_ZOOM = 1.0;

const DEFAULT_LAYOUTS: Layouts = {
  lg: [
    { i: 'smartstack',  x: 0, y: 0, w: 6,  h: 5, minW: 4, minH: 5, maxH: 5 },
    { i: 'todo',        x: 6, y: 0, w: 6,  h: 5, minW: 3, minH: 4 },
    { i: 'kanban',      x: 0, y: 5, w: 6,  h: 6, minW: 3, minH: 4 },
    { i: 'outputs',     x: 6, y: 5, w: 6,  h: 6, minW: 3, minH: 4 },
    { i: 'scheduled',   x: 0, y: 11, w: 6, h: 4, minW: 2, minH: 3 },
    { i: 'proactive',   x: 6, y: 11, w: 6, h: 4, minW: 3, minH: 3 },
  ],
  md: [
    { i: 'smartstack',  x: 0, y: 0, w: 5,  h: 5, minW: 3, minH: 5, maxH: 5 },
    { i: 'todo',        x: 5, y: 0, w: 5,  h: 5, minW: 3, minH: 4 },
    { i: 'kanban',      x: 0, y: 5, w: 5,  h: 6, minW: 3, minH: 4 },
    { i: 'outputs',     x: 5, y: 5, w: 5,  h: 6, minW: 3, minH: 4 },
    { i: 'scheduled',   x: 0, y: 11, w: 5, h: 4, minW: 2, minH: 3 },
    { i: 'proactive',   x: 5, y: 11, w: 5, h: 4, minW: 3, minH: 3 },
  ],
  sm: [
    { i: 'smartstack',  x: 0, y: 0, w: 6,  h: 5, minW: 3, minH: 5, maxH: 5 },
    { i: 'todo',        x: 0, y: 5, w: 6,  h: 5, minW: 3, minH: 4 },
    { i: 'kanban',      x: 0, y: 10, w: 6, h: 5, minW: 3, minH: 3 },
    { i: 'outputs',     x: 0, y: 15, w: 6, h: 5, minW: 3, minH: 4 },
    { i: 'scheduled',   x: 0, y: 20, w: 6, h: 4, minW: 2, minH: 3 },
    { i: 'proactive',   x: 0, y: 24, w: 6, h: 4, minW: 3, minH: 3 },
  ],
};

const SMARTSTACK_MAX_H = 5;

function loadLayouts(): Layouts {
  if (typeof window === 'undefined') return DEFAULT_LAYOUTS;
  try {
    const raw = localStorage.getItem(LAYOUT_STORAGE_KEY);
    if (raw) {
      const stored = JSON.parse(raw) as Layouts;
      for (const items of Object.values(stored)) {
        for (const item of items as LayoutItem[]) {
          if (item.i === 'smartstack') {
            if (item.h > SMARTSTACK_MAX_H) item.h = SMARTSTACK_MAX_H;
            item.maxH = SMARTSTACK_MAX_H;
            item.minH = SMARTSTACK_MAX_H;
          }
        }
      }
      return stored;
    }
  } catch { /* ignore */ }
  return DEFAULT_LAYOUTS;
}

function saveLayouts(layouts: Layouts) {
  try {
    localStorage.setItem(LAYOUT_STORAGE_KEY, JSON.stringify(layouts));
  } catch { /* ignore */ }
}

// ── 拖拽手柄组件 ──────────────────────────────────────────────

function DragHandle() {
  return (
    <div className="dashboard-drag-handle absolute top-3 left-1/2 -translate-x-1/2 z-30 flex items-center gap-1 rounded-full bg-[var(--glass-bg-heavy)] border border-black/[0.04] dark:border-white/[0.06] px-2.5 py-1 shadow-sm opacity-0 group-hover/widget:opacity-100 transition-opacity duration-200">
      <GripHorizontal className="h-3.5 w-3.5 text-muted-foreground" />
      <span className="text-[10px] font-medium text-muted-foreground tracking-wide">拖拽</span>
    </div>
  );
}

// ── 卡片容器 ──────────────────────────────────────────────

function WidgetCard({ children, className = '' }: { children: React.ReactNode; className?: string }) {
  return (
    <div className={`group/widget relative h-full rounded-[24px] border border-[var(--glass-border)] bg-[var(--glass-bg-heavy)] shadow-[0_4px_32px_rgba(15,23,42,0.06)] dark:shadow-[0_4px_32px_rgba(0,0,0,0.25)] backdrop-blur-2xl transition-shadow duration-300 hover:shadow-[0_8px_40px_rgba(15,23,42,0.10)] dark:hover:shadow-[0_8px_40px_rgba(0,0,0,0.35)] ${className}`}>
      <DragHandle />
      <div className="h-full overflow-auto thin-scrollbar p-0">
        {children}
      </div>
    </div>
  );
}

// ── Dashboard 主组件 ──────────────────────────────────────────

interface DashboardProps {
  onSelectAgent?: (agentId: string) => void;
}

export function Dashboard({ onSelectAgent }: DashboardProps) {
  const {
    agents,
    cronJobs,
    kanbanColumns,
    recentOutputs,
    proactiveOutputs,
    recommendations,
    loading,
  } = useDashboardData();

  const { switchSession, createSession, prefillInput } = useChatSession();
  const { pushNotification } = useNotification();

  const { containerRef, width: containerWidth, mounted: containerMounted } = useContainerWidth({ initialWidth: 1200 });

  const [layouts, setLayouts] = useState<Layouts>(loadLayouts);
  const [isCustomized, setIsCustomized] = useState(() => {
    if (typeof window === 'undefined') return false;
    return !!localStorage.getItem(LAYOUT_STORAGE_KEY);
  });

  // ── 缩放 ──
  const [zoom, setZoom] = useState<number>(() => {
    if (typeof window === 'undefined') return DEFAULT_ZOOM;
    try {
      const stored = localStorage.getItem(ZOOM_STORAGE_KEY);
      if (stored) {
        const val = parseFloat(stored);
        if (ZOOM_STEPS.includes(val as typeof ZOOM_STEPS[number])) return val;
      }
    } catch { /* ignore */ }
    return DEFAULT_ZOOM;
  });

  const zoomIn = useCallback(() => {
    setZoom(prev => {
      const idx = ZOOM_STEPS.indexOf(prev as typeof ZOOM_STEPS[number]);
      const next = idx < ZOOM_STEPS.length - 1 ? ZOOM_STEPS[idx + 1] : prev;
      try { localStorage.setItem(ZOOM_STORAGE_KEY, String(next)); } catch { /* ignore */ }
      return next;
    });
  }, []);

  const zoomOut = useCallback(() => {
    setZoom(prev => {
      const idx = ZOOM_STEPS.indexOf(prev as typeof ZOOM_STEPS[number]);
      const next = idx > 0 ? ZOOM_STEPS[idx - 1] : prev;
      try { localStorage.setItem(ZOOM_STORAGE_KEY, String(next)); } catch { /* ignore */ }
      return next;
    });
  }, []);

  const handleAgentClick = useCallback((agentId: string) => {
    onSelectAgent?.(agentId);
    createSession(agentId);
  }, [onSelectAgent, createSession]);

  const handleTaskClick = useCallback((sessionId: string) => {
    switchSession(sessionId);
  }, [switchSession]);

  const handleOutputClick = useCallback((sessionId: string) => {
    switchSession(sessionId);
  }, [switchSession]);

  const handleRecommendationClick = useCallback(async (
    sourceSessionId: string,
    recommendationId: string,
    prompt: string,
  ) => {
    try {
      await switchSession(sourceSessionId);
      prefillInput({
        text: prompt,
        recommendation: {
          recommendationId,
          sourceSessionId,
        },
      });
    } catch {
      pushNotification(
        {
          title: '会话切换失败',
          body: '该推荐对应的会话暂时不可用，请稍后重试',
          level: 'warning',
          source: 'system',
        },
        { toast: true, browser: false },
      );
    }
  }, [switchSession, prefillInput, pushNotification]);

  const handleLayoutChange = useCallback((_layout: Layout, allLayouts: Layouts) => {
    setLayouts(allLayouts);
    saveLayouts(allLayouts);
    setIsCustomized(true);
  }, []);

  const resetLayout = useCallback(() => {
    setLayouts(DEFAULT_LAYOUTS);
    localStorage.removeItem(LAYOUT_STORAGE_KEY);
    setIsCustomized(false);
  }, []);

  const visibleWidgets = useMemo(() => {
    return new Set(['smartstack', 'kanban', 'todo', 'outputs', 'scheduled', 'proactive']);
  }, []);

  const filteredLayouts = useMemo(() => {
    const result: Layouts = {};
    for (const [bp, items] of Object.entries(layouts)) {
      result[bp] = (items as LayoutItem[]).filter(item => visibleWidgets.has(item.i));
    }
    return result;
  }, [layouts, visibleWidgets]);

  if (loading) {
    return (
      <div className="flex flex-1 items-center justify-center p-6">
        <div className="flex flex-col items-center gap-3">
          <div className="h-8 w-8 rounded-full border-2 border-violet-200 dark:border-violet-800 border-t-violet-500 animate-spin" />
          <div className="text-sm text-muted-foreground font-medium">加载中...</div>
        </div>
      </div>
    );
  }

  return (
    <div className="flex-1 overflow-y-auto">
      <div className="mx-auto max-w-[1400px] px-5 pt-4 pb-10">
        {/* 顶部工具栏 */}
        <div className="mb-4 flex items-center justify-between">
          <div>
            <h1 className="text-lg font-bold text-[var(--glass-text)] tracking-tight" style={{ fontFamily: "'DM Sans', sans-serif" }}>
              工作台
            </h1>
            <p className="text-xs text-muted-foreground mt-0.5">拖拽卡片自定义布局</p>
          </div>
          <div className="flex items-center gap-2">
            {/* 缩放控制 */}
            <div className="flex items-center gap-0.5 rounded-full border border-border bg-[var(--glass-bg-heavy)] shadow-sm backdrop-blur-xl">
              <button
                type="button"
                onClick={zoomOut}
                disabled={zoom <= ZOOM_STEPS[0]}
                className="flex items-center justify-center w-7 h-7 rounded-full text-muted-foreground transition-all hover:text-foreground disabled:opacity-30 disabled:cursor-not-allowed"
                title="缩小"
              >
                <ZoomOut className="h-3.5 w-3.5" />
              </button>
              <span className="text-[10px] font-semibold text-muted-foreground min-w-[32px] text-center tabular-nums">
                {Math.round(zoom * 100)}%
              </span>
              <button
                type="button"
                onClick={zoomIn}
                disabled={zoom >= ZOOM_STEPS[ZOOM_STEPS.length - 1]}
                className="flex items-center justify-center w-7 h-7 rounded-full text-muted-foreground transition-all hover:text-foreground disabled:opacity-30 disabled:cursor-not-allowed"
                title="放大"
              >
                <ZoomIn className="h-3.5 w-3.5" />
              </button>
            </div>

            {isCustomized && (
              <button
                type="button"
                onClick={resetLayout}
                className="flex items-center gap-1.5 rounded-full border border-border bg-[var(--glass-bg-heavy)] px-3 py-1.5 text-xs font-medium text-muted-foreground shadow-sm transition-all hover:bg-[var(--glass-bg)] hover:text-foreground hover:shadow-md backdrop-blur-xl"
              >
                <RotateCcw className="h-3 w-3" />
                重置布局
              </button>
            )}
          </div>
        </div>

        {/* 可拖拽网格 */}
        <div ref={containerRef as RefObject<HTMLDivElement>} style={{ transform: `scale(${zoom})`, transformOrigin: 'top left', width: zoom !== 1 ? `${100 / zoom}%` : undefined }}>
          {containerMounted && containerWidth > 0 && (
            <ResponsiveGrid
              className="layout"
              layouts={filteredLayouts}
              width={containerWidth}
              breakpoints={{ lg: 1100, md: 768, sm: 0 }}
              cols={{ lg: 12, md: 10, sm: 6 }}
              rowHeight={52}
              margin={[16, 16]}
              containerPadding={[0, 0]}
              onLayoutChange={handleLayoutChange}
              dragConfig={{ enabled: true, bounded: false, handle: '.dashboard-drag-handle', threshold: 3 }}
              resizeConfig={{ enabled: true }}
            >
          {/* 常用 Agent */}
          {visibleWidgets.has('smartstack') && (
            <div key="smartstack">
              <WidgetCard>
                <SmartStack agents={agents} onAgentClick={handleAgentClick} />
              </WidgetCard>
            </div>
          )}

          {/* 任务看板 */}
          {visibleWidgets.has('kanban') && (
            <div key="kanban">
              <WidgetCard>
                <KanbanBoard columns={kanbanColumns} onTaskClick={handleTaskClick} />
              </WidgetCard>
            </div>
          )}

          {/* 今日待办 */}
          {visibleWidgets.has('todo') && (
            <div key="todo">
              <WidgetCard>
                <TodoList />
              </WidgetCard>
            </div>
          )}

          {/* 今日任务产出 */}
          {visibleWidgets.has('outputs') && (
            <div key="outputs">
              <WidgetCard>
                <RecentOutputs items={recentOutputs} onItemClick={handleOutputClick} />
              </WidgetCard>
            </div>
          )}

          {/* 定时任务 */}
          {visibleWidgets.has('scheduled') && (
            <div key="scheduled">
              <WidgetCard>
                <ScheduledTasks cronJobs={cronJobs} />
              </WidgetCard>
            </div>
          )}

          {/* Proactive Agent 产出 */}
          {visibleWidgets.has('proactive') && (
            <div key="proactive">
              <WidgetCard>
                <ProactiveAgentPanel
                  items={proactiveOutputs}
                  onItemClick={handleOutputClick}
                  recommendations={recommendations}
                  onRecommendationClick={handleRecommendationClick}
                />
              </WidgetCard>
            </div>
          )}
        </ResponsiveGrid>
          )}
        </div>
      </div>
    </div>
  );
}
