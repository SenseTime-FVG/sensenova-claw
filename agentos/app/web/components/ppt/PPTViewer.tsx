'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Presentation, ChevronLeft, ChevronRight, Download, Maximize2, Minimize2, X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import { type ChatMessage } from '@/lib/chatTypes';
import { API_BASE, authFetch } from '@/lib/authFetch';

// ────────────────────────────────────────
// 类型
// ────────────────────────────────────────

export interface SlideSet {
  /** 目录路径（展示用名称，如 "default/gold_price_ppt"） */
  dir: string;
  /** 幻灯片文件列表（按序） */
  slides: { name: string; path: string }[];
  /** 自定义 URL 前缀：slide URL = `${urlPrefix}/${slide.path}`；不设则走 workdir 默认端点 */
  urlPrefix?: string;
}

// ────────────────────────────────────────
// 从聊天消息中提取幻灯片目录
// ────────────────────────────────────────

/**
 * 从 workdir 绝对路径中提取相对路径部分。
 * 例如 "D:\\...\\workdir\\default\\ppt\\page_01.html" → "default/ppt"
 */
function extractWorkdirRelDir(absPath: string): string | null {
  const normalized = absPath.replace(/\\/g, '/');
  const marker = '/workdir/';
  const idx = normalized.indexOf(marker);
  if (idx === -1) return null;
  const afterWorkdir = normalized.slice(idx + marker.length);
  const lastSlash = afterWorkdir.lastIndexOf('/');
  if (lastSlash === -1) return null;
  return afterWorkdir.slice(0, lastSlash);
}

/** 从聊天消息中提取最新的幻灯片目录 */
export function extractSlideDir(messages: ChatMessage[]): string | null {
  const pageHtmlPattern = /page_\d+\.html/i;

  // 优先从 write_file 工具结果中查找
  for (let i = messages.length - 1; i >= 0; i--) {
    const msg = messages[i];
    if (!msg.toolInfo || msg.toolInfo.status !== 'completed' || !msg.toolInfo.success) continue;

    if (msg.toolInfo.name === 'write_file') {
      const result = msg.toolInfo.result as Record<string, unknown> | undefined;
      const filePath = String(result?.file_path || msg.toolInfo.arguments?.file_path || '');
      if (pageHtmlPattern.test(filePath)) {
        const dir = extractWorkdirRelDir(filePath);
        if (dir) return dir;
      }
    }

    // bash_command 输出中可能包含幻灯片路径
    if (msg.toolInfo.name === 'bash_command') {
      const resultStr = JSON.stringify(msg.toolInfo.result || '');
      const match = resultStr.match(/workdir[/\\]+([^"'\s]+?[/\\]+)page_\d+\.html/i);
      if (match) {
        return match[1].replace(/\\/g, '/').replace(/\/$/, '');
      }
    }
  }

  // 兜底：从 assistant 消息中提取路径
  for (let i = messages.length - 1; i >= 0; i--) {
    const msg = messages[i];
    if (msg.role !== 'assistant') continue;
    // 匹配类似 `gold_price_ppt/page_01.html` 的路径
    const match = msg.content.match(/[`'"]([\w\-./\\]+\/page_\d+\.html)[`'"]/i);
    if (match) {
      const p = match[1].replace(/\\/g, '/');
      const lastSlash = p.lastIndexOf('/');
      return lastSlash > 0 ? p.slice(0, lastSlash) : null;
    }
  }

  // 也检查 .pptx 文件
  for (let i = messages.length - 1; i >= 0; i--) {
    const msg = messages[i];
    if (!msg.toolInfo || msg.toolInfo.status !== 'completed' || !msg.toolInfo.success) continue;
    if (msg.toolInfo.name === 'write_file') {
      const result = msg.toolInfo.result as Record<string, unknown> | undefined;
      const filePath = String(result?.file_path || msg.toolInfo.arguments?.file_path || '');
      if (/\.pptx?$/i.test(filePath) && /[\w]/.test(filePath)) {
        return filePath;
      }
    }
  }

  return null;
}

// ────────────────────────────────────────
// 幻灯片列表加载
// ────────────────────────────────────────

export function useSlideSet(dir: string | null): SlideSet | null {
  const [slideSet, setSlideSet] = useState<SlideSet | null>(null);

  useEffect(() => {
    if (!dir) { setSlideSet(null); return; }

    let cancelled = false;
    (async () => {
      try {
        const res = await authFetch(`${API_BASE}/api/files/workdir-list?dir=${encodeURIComponent(dir)}`);
        if (!res.ok || cancelled) return;
        const data = await res.json();
        if (cancelled) return;
        const slides = (data.slides || []) as { name: string; path: string }[];
        if (slides.length > 0) {
          setSlideSet({ dir, slides });
        }
      } catch {
        // 静默忽略
      }
    })();

    return () => { cancelled = true; };
  }, [dir]);

  return slideSet;
}

// ────────────────────────────────────────
// 空状态
// ────────────────────────────────────────

function EmptyState() {
  return (
    <div className="flex-1 flex flex-col items-center justify-center p-8">
      <div className="w-24 h-24 rounded-3xl bg-primary/5 border-2 border-dashed border-primary/20 flex items-center justify-center mb-6">
        <Presentation className="w-12 h-12 text-primary/30" />
      </div>
      <h3 className="text-lg font-semibold text-foreground/70 mb-2">演示文稿预览</h3>
      <p className="text-sm text-muted-foreground text-center max-w-sm">
        在下方对话区描述你的 PPT 需求，AI 生成完成后将在此处展示
      </p>
    </div>
  );
}

// ────────────────────────────────────────
// 幻灯片查看器
// ────────────────────────────────────────

/** 原始幻灯片尺寸（与 HTML 模板中的 .wrapper 一致） */
const SLIDE_W = 1280;
const SLIDE_H = 720;

export function SlideViewer({ slideSet, onClose }: { slideSet: SlideSet; onClose?: () => void }) {
  const [current, setCurrent] = useState(0);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [scale, setScale] = useState(1);
  const containerRef = useRef<HTMLDivElement>(null);
  const total = slideSet.slides.length;

  const slideUrl = useMemo(() => {
    const slide = slideSet.slides[current];
    if (!slide) return '';
    if (slideSet.urlPrefix) {
      return `${slideSet.urlPrefix}/${slide.path}`;
    }
    return `${API_BASE}/api/files/workdir/${slide.path}`;
  }, [slideSet, current]);

  const goPrev = useCallback(() => setCurrent(c => Math.max(0, c - 1)), []);
  const goNext = useCallback(() => setCurrent(c => Math.min(total - 1, c + 1)), [total]);

  // 根据容器大小计算缩放比
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const observer = new ResizeObserver((entries) => {
      for (const entry of entries) {
        const { width, height } = entry.contentRect;
        const pad = 32;
        const availW = width - pad;
        const availH = height - pad;
        const s = Math.min(availW / SLIDE_W, availH / SLIDE_H, 1);
        setScale(Math.max(s, 0.15));
      }
    });
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  // 键盘导航
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'ArrowLeft') goPrev();
      else if (e.key === 'ArrowRight') goNext();
      else if (e.key === 'Escape') setIsFullscreen(false);
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [goPrev, goNext]);

  useEffect(() => { setCurrent(0); }, [slideSet]);

  const toggleFullscreen = useCallback(() => setIsFullscreen(f => !f), []);

  const isFs = isFullscreen;

  const containerClass = isFs
    ? 'fixed inset-0 z-50 bg-neutral-950 flex flex-col'
    : 'flex-1 flex flex-col';

  const btnClass = isFs ? 'text-white/70 hover:text-white hover:bg-white/10' : '';

  return (
    <div className={containerClass}>
      {/* 工具栏 */}
      <div className={cn(
        "flex items-center justify-between px-4 py-2 shrink-0",
        isFs ? "bg-white/5 border-b border-white/10" : "bg-muted/30 border-b",
      )}>
        <div className="flex items-center gap-2 min-w-0">
          <Presentation className={cn("w-4 h-4 shrink-0", isFs ? "text-white/80" : "text-primary")} />
          <span className={cn("text-sm font-medium truncate", isFs ? "text-white" : "text-foreground")}>
            {slideSet.dir.split('/').pop()}
          </span>
          <span className={cn("text-xs ml-1", isFs ? "text-white/50" : "text-muted-foreground")}>
            ({total} 页)
          </span>
        </div>
        <div className="flex items-center gap-1">
          <Button variant="ghost" size="icon-sm" className={btnClass} onClick={goPrev} disabled={current === 0}>
            <ChevronLeft className="w-4 h-4" />
          </Button>
          <span className={cn("text-sm tabular-nums min-w-[3rem] text-center", isFs && "text-white/80")}>
            {current + 1} / {total}
          </span>
          <Button variant="ghost" size="icon-sm" className={btnClass} onClick={goNext} disabled={current >= total - 1}>
            <ChevronRight className="w-4 h-4" />
          </Button>
          <div className={cn("w-px h-4 mx-1", isFs ? "bg-white/15" : "bg-border")} />
          <Button variant="ghost" size="icon-sm" className={btnClass} onClick={toggleFullscreen}>
            {isFs ? <Minimize2 className="w-4 h-4" /> : <Maximize2 className="w-4 h-4" />}
          </Button>
          <Button variant="ghost" size="sm" className={btnClass} asChild>
            <a href={slideUrl} target="_blank" rel="noopener noreferrer">
              <Download className="w-3.5 h-3.5 mr-1" />
              打开
            </a>
          </Button>
          {onClose && !isFs && (
            <>
              <div className="w-px h-4 bg-border mx-1" />
              <Button variant="ghost" size="icon-sm" onClick={onClose} title="关闭预览">
                <X className="w-4 h-4" />
              </Button>
            </>
          )}
        </div>
      </div>

      {/* 幻灯片渲染区 */}
      <div
        ref={containerRef}
        className={cn(
          "flex-1 flex items-center justify-center overflow-hidden relative",
          isFs ? "bg-neutral-950" : "bg-neutral-100 dark:bg-neutral-900",
        )}
      >
        {/* 左右翻页热区 */}
        <button
          className="absolute left-0 top-0 bottom-0 w-16 z-10 opacity-0 hover:opacity-100 flex items-center justify-center transition-opacity cursor-pointer disabled:cursor-default"
          onClick={goPrev}
          disabled={current === 0}
        >
          <div className={cn("w-8 h-8 rounded-full flex items-center justify-center", isFs ? "bg-white/15" : "bg-black/40")}>
            <ChevronLeft className="w-5 h-5 text-white" />
          </div>
        </button>
        <button
          className="absolute right-0 top-0 bottom-0 w-16 z-10 opacity-0 hover:opacity-100 flex items-center justify-center transition-opacity cursor-pointer disabled:cursor-default"
          onClick={goNext}
          disabled={current >= total - 1}
        >
          <div className={cn("w-8 h-8 rounded-full flex items-center justify-center", isFs ? "bg-white/15" : "bg-black/40")}>
            <ChevronRight className="w-5 h-5 text-white" />
          </div>
        </button>

        {/* 外层按缩放尺寸占位，内层按原始尺寸渲染并 transform 缩放 */}
        <div
          className={cn(
            "rounded-lg shadow-2xl overflow-hidden relative",
            isFs && "ring-1 ring-white/20",
          )}
          style={{
            width: Math.round(SLIDE_W * scale),
            height: Math.round(SLIDE_H * scale),
          }}
        >
          <iframe
            key={slideUrl}
            src={slideUrl}
            className="border-0 absolute top-0 left-0"
            style={{
              width: SLIDE_W,
              height: SLIDE_H,
              transform: `scale(${scale})`,
              transformOrigin: 'top left',
            }}
            title={`Slide ${current + 1}`}
            sandbox="allow-same-origin"
          />
        </div>
      </div>

      {/* 缩略图条 */}
      {total > 1 && (
        <div className={cn(
          "flex items-center gap-1.5 px-4 py-2 overflow-x-auto shrink-0",
          isFs ? "bg-white/5 border-t border-white/10" : "bg-muted/30 border-t",
        )}>
          {slideSet.slides.map((slide, idx) => (
            <button
              key={slide.name}
              className={cn(
                "shrink-0 w-16 h-9 rounded border-2 transition-all overflow-hidden cursor-pointer",
                idx === current
                  ? isFs
                    ? 'border-white/80 shadow-sm ring-1 ring-white/30'
                    : 'border-primary shadow-sm ring-1 ring-primary/30'
                  : isFs
                    ? 'border-white/10 opacity-60 hover:opacity-100'
                    : 'border-transparent opacity-60 hover:opacity-100',
              )}
              onClick={() => setCurrent(idx)}
            >
              <div className={cn(
                "w-full h-full flex items-center justify-center text-[10px] font-medium",
                isFs ? "bg-white/10 text-white/70" : "bg-muted text-muted-foreground",
              )}>
                {idx + 1}
              </div>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

// ────────────────────────────────────────
// 导出组件
// ────────────────────────────────────────

interface PPTViewerProps {
  messages: ChatMessage[];
}

export function PPTViewer({ messages }: PPTViewerProps) {
  const dir = useMemo(() => extractSlideDir(messages), [messages]);
  const slideSet = useSlideSet(dir);

  return (
    <div className="flex flex-col h-full bg-background rounded-lg border overflow-hidden">
      {slideSet ? <SlideViewer slideSet={slideSet} /> : <EmptyState />}
    </div>
  );
}
