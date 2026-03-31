'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { ChevronLeft, ChevronRight, Download, Maximize2, Minimize2, Presentation, X } from 'lucide-react';

import { API_BASE, authFetch } from '@/lib/authFetch';
import { type ChatMessage } from '@/lib/chatTypes';
import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/button';

export interface SlideSet {
  /** 目录路径，例如 `default/gold_price_ppt`。 */
  dir: string;
  /** 幻灯片文件列表，按顺序排列。 */
  slides: { name: string; path: string }[];
  /** 自定义 URL 前缀，不传时走默认 workdir 端点。 */
  urlPrefix?: string;
}

/**
 * 从 workdir 绝对路径中提取相对目录。
 * 例如：`D:\...\workdir\default\ppt\page_01.html` -> `default/ppt`
 */
function extractWorkdirRelDir(absPath: string): string | null {
  const normalized = absPath.replace(/\\/g, '/');
  const marker = '/workdir/';
  const markerIndex = normalized.indexOf(marker);
  if (markerIndex === -1) return null;

  const afterWorkdir = normalized.slice(markerIndex + marker.length);
  const lastSlash = afterWorkdir.lastIndexOf('/');
  if (lastSlash === -1) return null;
  return afterWorkdir.slice(0, lastSlash);
}

/** 从聊天消息中提取最近一次生成的幻灯片目录。 */
export function extractSlideDir(messages: ChatMessage[]): string | null {
  const pageHtmlPattern = /page_\d+\.html/i;

  // 优先从 write_file 工具结果中查找。
  for (let index = messages.length - 1; index >= 0; index -= 1) {
    const message = messages[index];
    if (!message.toolInfo || message.toolInfo.status !== 'completed' || !message.toolInfo.success) continue;

    if (message.toolInfo.name === 'write_file') {
      const result = message.toolInfo.result as Record<string, unknown> | undefined;
      const filePath = String(result?.file_path || message.toolInfo.arguments?.file_path || '');
      if (pageHtmlPattern.test(filePath)) {
        const dir = extractWorkdirRelDir(filePath);
        if (dir) return dir;
      }
    }

    if (message.toolInfo.name === 'bash_command') {
      const resultString = JSON.stringify(message.toolInfo.result || '');
      const match = resultString.match(/workdir[/\\]+([^"'\s]+?[/\\]+)page_\d+\.html/i);
      if (match) {
        return match[1].replace(/\\/g, '/').replace(/\/$/, '');
      }
    }
  }

  // 兜底：从 assistant 文本里提取 `foo/bar/page_01.html`。
  for (let index = messages.length - 1; index >= 0; index -= 1) {
    const message = messages[index];
    if (message.role !== 'assistant') continue;

    const match = message.content.match(/[`'"]([\w\-./\\]+\/page_\d+\.html)[`'"]/i);
    if (match) {
      const normalized = match[1].replace(/\\/g, '/');
      const lastSlash = normalized.lastIndexOf('/');
      return lastSlash > 0 ? normalized.slice(0, lastSlash) : null;
    }
  }

  // 兼容仅生成 `.pptx` 的场景。
  for (let index = messages.length - 1; index >= 0; index -= 1) {
    const message = messages[index];
    if (!message.toolInfo || message.toolInfo.status !== 'completed' || !message.toolInfo.success) continue;
    if (message.toolInfo.name !== 'write_file') continue;

    const result = message.toolInfo.result as Record<string, unknown> | undefined;
    const filePath = String(result?.file_path || message.toolInfo.arguments?.file_path || '');
    if (/\.pptx?$/i.test(filePath) && /[\w]/.test(filePath)) {
      return filePath;
    }
  }

  return null;
}

/** 根据目录加载幻灯片列表。 */
export function useSlideSet(dir: string | null): SlideSet | null {
  const [slideSet, setSlideSet] = useState<SlideSet | null>(null);

  useEffect(() => {
    if (!dir) {
      setSlideSet(null);
      return undefined;
    }

    let cancelled = false;

    void (async () => {
      try {
        const response = await authFetch(`${API_BASE}/api/files/workdir-list?dir=${encodeURIComponent(dir)}`);
        if (!response.ok || cancelled) return;

        const data = await response.json();
        if (cancelled) return;

        const slides = (data.slides || []) as { name: string; path: string }[];
        if (slides.length > 0) {
          setSlideSet({ dir, slides });
        }
      } catch {
        // 预览区允许静默失败。
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [dir]);

  return slideSet;
}

function EmptyState() {
  return (
    <div className="flex flex-1 flex-col items-center justify-center p-8">
      <div className="mb-6 flex h-24 w-24 items-center justify-center rounded-3xl border-2 border-dashed border-primary/20 bg-primary/5">
        <Presentation className="h-12 w-12 text-primary/30" />
      </div>
      <h3 className="mb-2 text-lg font-semibold text-foreground/70">演示文稿预览</h3>
      <p className="max-w-sm text-center text-sm text-muted-foreground">
        在下方对话区描述你的 PPT 需求，AI 生成完成后会在这里展示。
      </p>
    </div>
  );
}

/** HTML 幻灯片的基准尺寸，要和页面模板里的 `.wrapper` 一致。 */
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
  }, [current, slideSet]);

  const goPrev = useCallback(() => {
    setCurrent((value) => Math.max(0, value - 1));
  }, []);

  const goNext = useCallback(() => {
    setCurrent((value) => Math.min(total - 1, value + 1));
  }, [total]);

  // 根据容器尺寸自适应缩放比例。
  useEffect(() => {
    const element = containerRef.current;
    if (!element) return undefined;

    const observer = new ResizeObserver((entries) => {
      for (const entry of entries) {
        const { width, height } = entry.contentRect;
        const padding = 32;
        const availableWidth = width - padding;
        const availableHeight = height - padding;
        const nextScale = Math.min(availableWidth / SLIDE_W, availableHeight / SLIDE_H, 1);
        setScale(Math.max(nextScale, 0.15));
      }
    });

    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  // 键盘导航：左右键翻页，Esc 退出放大。
  useEffect(() => {
    const handler = (event: KeyboardEvent) => {
      if (event.key === 'ArrowLeft') {
        goPrev();
      } else if (event.key === 'ArrowRight') {
        goNext();
      } else if (event.key === 'Escape') {
        setIsFullscreen(false);
      }
    };

    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [goNext, goPrev]);

  useEffect(() => {
    setCurrent(0);
  }, [slideSet]);

  const toggleFullscreen = useCallback(() => {
    setIsFullscreen((value) => !value);
  }, []);

  const isFs = isFullscreen;
  const fullscreenLabel = isFs ? '退出放大' : '放大预览';
  const containerClass = isFs
    ? 'fixed inset-0 z-[260] flex flex-col bg-neutral-950'
    : 'flex flex-1 flex-col';
  const btnClass = isFs ? 'text-white/70 hover:bg-white/10 hover:text-white' : '';

  return (
    <div
      className={containerClass}
      data-testid="slide-viewer"
      data-fullscreen={isFs ? 'true' : 'false'}
    >
      <div
        className={cn(
          'flex shrink-0 items-center justify-between px-4 py-2',
          isFs ? 'border-b border-white/10 bg-white/5' : 'border-b bg-muted/30',
        )}
      >
        <div className="flex min-w-0 items-center gap-2">
          <Presentation className={cn('h-4 w-4 shrink-0', isFs ? 'text-white/80' : 'text-primary')} />
          <span className={cn('truncate text-sm font-medium', isFs ? 'text-white' : 'text-foreground')}>
            {slideSet.dir.split('/').pop()}
          </span>
          <span className={cn('ml-1 text-xs', isFs ? 'text-white/50' : 'text-muted-foreground')}>
            ({total} 页)
          </span>
        </div>

        <div className="flex items-center gap-1">
          <Button
            variant="ghost"
            size="icon-sm"
            className={btnClass}
            onClick={goPrev}
            disabled={current === 0}
            title="上一页"
            aria-label="上一页"
          >
            <ChevronLeft className="h-4 w-4" />
          </Button>

          <span className={cn('min-w-[3rem] text-center text-sm tabular-nums', isFs && 'text-white/80')}>
            {current + 1} / {total}
          </span>

          <Button
            variant="ghost"
            size="icon-sm"
            className={btnClass}
            onClick={goNext}
            disabled={current >= total - 1}
            title="下一页"
            aria-label="下一页"
          >
            <ChevronRight className="h-4 w-4" />
          </Button>

          <div className={cn('mx-1 h-4 w-px', isFs ? 'bg-white/15' : 'bg-border')} />

          <Button
            variant="ghost"
            size={isFs ? 'sm' : 'icon-sm'}
            className={btnClass}
            onClick={toggleFullscreen}
            title={fullscreenLabel}
            aria-label={fullscreenLabel}
            data-testid="slide-fullscreen-toggle"
          >
            {isFs ? (
              <>
                <Minimize2 className="h-4 w-4" />
                <span>退出放大</span>
              </>
            ) : (
              <Maximize2 className="h-4 w-4" />
            )}
          </Button>

          <Button variant="ghost" size="sm" className={btnClass} asChild>
            <a href={slideUrl} target="_blank" rel="noopener noreferrer">
              <Download className="mr-1 h-3.5 w-3.5" />
              打开
            </a>
          </Button>

          {onClose && (
            <>
              <div className={cn('mx-1 h-4 w-px', isFs ? 'bg-white/15' : 'bg-border')} />
              <Button
                variant="ghost"
                size={isFs ? 'sm' : 'icon-sm'}
                className={btnClass}
                onClick={onClose}
                title="关闭预览"
                aria-label="关闭预览"
              >
                <X className="h-4 w-4" />
                {isFs ? <span>关闭预览</span> : null}
              </Button>
            </>
          )}
        </div>
      </div>

      <div
        ref={containerRef}
        className={cn(
          'relative flex flex-1 items-center justify-center overflow-hidden',
          isFs ? 'bg-neutral-950' : 'bg-neutral-100 dark:bg-neutral-900',
        )}
      >
        <button
          className="absolute bottom-0 left-0 top-0 z-10 flex w-16 cursor-pointer items-center justify-center opacity-0 transition-opacity hover:opacity-100 disabled:cursor-default"
          onClick={goPrev}
          disabled={current === 0}
          title="上一页"
          aria-label="上一页"
        >
          <div className={cn('flex h-8 w-8 items-center justify-center rounded-full', isFs ? 'bg-white/15' : 'bg-black/40')}>
            <ChevronLeft className="h-5 w-5 text-white" />
          </div>
        </button>

        <button
          className="absolute bottom-0 right-0 top-0 z-10 flex w-16 cursor-pointer items-center justify-center opacity-0 transition-opacity hover:opacity-100 disabled:cursor-default"
          onClick={goNext}
          disabled={current >= total - 1}
          title="下一页"
          aria-label="下一页"
        >
          <div className={cn('flex h-8 w-8 items-center justify-center rounded-full', isFs ? 'bg-white/15' : 'bg-black/40')}>
            <ChevronRight className="h-5 w-5 text-white" />
          </div>
        </button>

        <div
          className={cn(
            'relative overflow-hidden rounded-lg shadow-2xl',
            isFs && 'ring-1 ring-white/20',
          )}
          style={{
            width: Math.round(SLIDE_W * scale),
            height: Math.round(SLIDE_H * scale),
          }}
        >
          <iframe
            key={slideUrl}
            src={slideUrl}
            className="absolute left-0 top-0 border-0"
            style={{
              width: SLIDE_W,
              height: SLIDE_H,
              transform: `scale(${scale})`,
              transformOrigin: 'top left',
            }}
            title={`Slide ${current + 1}`}
            sandbox="allow-same-origin allow-scripts"
          />
        </div>
      </div>

      {total > 1 && (
        <div
          className={cn(
            'flex shrink-0 items-center gap-1.5 overflow-x-auto px-4 py-2',
            isFs ? 'border-t border-white/10 bg-white/5' : 'border-t bg-muted/30',
          )}
        >
          {slideSet.slides.map((slide, index) => (
            <button
              key={slide.name}
              className={cn(
                'h-9 w-16 shrink-0 cursor-pointer overflow-hidden rounded border-2 transition-all',
                index === current
                  ? isFs
                    ? 'border-white/80 shadow-sm ring-1 ring-white/30'
                    : 'border-primary shadow-sm ring-1 ring-primary/30'
                  : isFs
                    ? 'border-white/10 opacity-60 hover:opacity-100'
                    : 'border-transparent opacity-60 hover:opacity-100',
              )}
              onClick={() => setCurrent(index)}
              title={`跳转到第 ${index + 1} 页`}
              aria-label={`跳转到第 ${index + 1} 页`}
            >
              <div
                className={cn(
                  'flex h-full w-full items-center justify-center text-[10px] font-medium',
                  isFs ? 'bg-white/10 text-white/70' : 'bg-muted text-muted-foreground',
                )}
              >
                {index + 1}
              </div>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

interface PPTViewerProps {
  messages: ChatMessage[];
}

export function PPTViewer({ messages }: PPTViewerProps) {
  const dir = useMemo(() => extractSlideDir(messages), [messages]);
  const slideSet = useSlideSet(dir);

  return (
    <div className="flex h-full flex-col overflow-hidden rounded-lg border bg-background">
      {slideSet ? <SlideViewer slideSet={slideSet} /> : <EmptyState />}
    </div>
  );
}
