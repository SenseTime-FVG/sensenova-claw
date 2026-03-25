'use client';

/**
 * 讲稿面板 —— 右栏 Tab
 *
 * 展示 ppt-speaker-notes 生成的逐页讲稿。
 */

import { cn } from '@/lib/utils';
import { Mic, FileText } from 'lucide-react';

export interface SpeakerNote {
  page_number: number;
  page_title: string;
  notes: string;
}

export function SpeakerNotesPanel({
  notes,
  activePage,
  onPageSelect,
}: {
  notes: SpeakerNote[] | null;
  activePage: number;
  onPageSelect?: (pageNumber: number) => void;
}) {
  if (!notes || notes.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-full p-4 text-center">
        <Mic className="w-8 h-8 text-muted-foreground/20 mb-2" />
        <p className="text-xs text-muted-foreground/50">
          讲稿将在导出时生成，或可在对话中要求 AI 生成
        </p>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full overflow-y-auto p-2 space-y-2 scrollbar-thin">
      {notes.map(note => (
        <button
          key={note.page_number}
          type="button"
          onClick={() => onPageSelect?.(note.page_number)}
          className={cn(
            'w-full text-left rounded-lg border p-3 transition-all',
            note.page_number === activePage
              ? 'border-primary/30 bg-primary/5'
              : 'border-border/40 hover:bg-muted/20',
          )}
        >
          <div className="flex items-center gap-1.5 mb-1.5">
            <FileText className="w-3 h-3 text-muted-foreground/50" />
            <span className="text-[10px] font-bold text-muted-foreground/60">P{note.page_number}</span>
            <span className="text-[10px] text-muted-foreground/40 truncate">{note.page_title}</span>
          </div>
          <div className="text-[11px] text-foreground/70 leading-relaxed line-clamp-4 whitespace-pre-wrap">
            {note.notes}
          </div>
        </button>
      ))}
    </div>
  );
}
