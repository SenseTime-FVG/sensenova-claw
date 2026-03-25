'use client';

/**
 * 导出与交付面板 —— 顶栏按钮 + 下拉面板
 *
 * 功能：
 *   - HTML 打包下载
 *   - PDF 导出
 *   - PPTX 导出
 *   - 讲稿附带选项
 *   - 分享链接
 */

import { useState, useRef, useEffect } from 'react';
import { cn } from '@/lib/utils';
import {
  Download, FileText, FileImage, Presentation,
  Link2, Mic, ChevronDown, ExternalLink, Package,
} from 'lucide-react';
import { Button } from '@/components/ui/button';

interface ExportOption {
  id: string;
  label: string;
  description: string;
  icon: React.ElementType;
  disabled?: boolean;
}

const EXPORT_OPTIONS: ExportOption[] = [
  {
    id: 'html-zip',
    label: 'HTML 打包下载',
    description: '包含所有幻灯片和资源文件',
    icon: Package,
  },
  {
    id: 'pdf',
    label: 'PDF 导出',
    description: '将幻灯片转为 PDF 文件',
    icon: FileImage,
    disabled: true,
  },
  {
    id: 'pptx',
    label: 'PPTX 导出',
    description: '转为 PowerPoint 格式',
    icon: Presentation,
    disabled: true,
  },
];

export function ExportDropdown({
  deckDir,
  onExport,
  hasSpeakerNotes,
}: {
  deckDir: string | null;
  onExport?: (format: string, withNotes: boolean) => void;
  hasSpeakerNotes?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const [includeNotes, setIncludeNotes] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, []);

  return (
    <div ref={ref} className="relative">
      <Button
        variant="outline"
        size="sm"
        onClick={() => setOpen(!open)}
        disabled={!deckDir}
        className="h-7 text-xs gap-1.5"
      >
        <Download className="w-3.5 h-3.5" />
        导出
        <ChevronDown className={cn('w-3 h-3 transition-transform', open && 'rotate-180')} />
      </Button>

      {open && (
        <div className="absolute right-0 top-full mt-1 w-64 rounded-xl border border-border/60 bg-background shadow-xl z-50 overflow-hidden animate-in fade-in slide-in-from-top-1 duration-150">
          <div className="p-1.5 space-y-0.5">
            {EXPORT_OPTIONS.map(opt => {
              const Icon = opt.icon;
              return (
                <button
                  key={opt.id}
                  type="button"
                  disabled={opt.disabled}
                  onClick={() => {
                    onExport?.(opt.id, includeNotes);
                    setOpen(false);
                  }}
                  className={cn(
                    'w-full flex items-start gap-2.5 px-3 py-2.5 rounded-lg text-left transition-colors',
                    opt.disabled
                      ? 'opacity-40 cursor-not-allowed'
                      : 'hover:bg-muted/50 cursor-pointer',
                  )}
                >
                  <Icon className="w-4 h-4 text-muted-foreground shrink-0 mt-0.5" />
                  <div>
                    <div className="text-xs font-medium text-foreground/80">{opt.label}</div>
                    <div className="text-[10px] text-muted-foreground/60">{opt.description}</div>
                    {opt.disabled && (
                      <div className="text-[9px] text-muted-foreground/40 mt-0.5">即将推出</div>
                    )}
                  </div>
                </button>
              );
            })}
          </div>

          {/* 讲稿选项 */}
          <div className="border-t border-border/40 px-3 py-2">
            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="checkbox"
                checked={includeNotes}
                onChange={e => setIncludeNotes(e.target.checked)}
                disabled={!hasSpeakerNotes}
                className="w-3.5 h-3.5 rounded border-border accent-primary"
              />
              <div className="flex items-center gap-1">
                <Mic className="w-3 h-3 text-muted-foreground/50" />
                <span className={cn(
                  'text-[11px]',
                  hasSpeakerNotes ? 'text-foreground/70' : 'text-muted-foreground/40',
                )}>
                  附带讲稿
                </span>
              </div>
            </label>
          </div>
        </div>
      )}
    </div>
  );
}
