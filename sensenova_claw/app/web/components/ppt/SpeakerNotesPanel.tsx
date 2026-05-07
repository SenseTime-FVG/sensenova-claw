'use client';

/**
 * 讲稿面板 —— 左栏 Tab
 *
 * 支持两种格式：
 * - 旧格式: SpeakerNote[]（数组，每项含 page_number、page_title、notes 字符串）
 * - 新格式 (schema_version: "1.0"): SpeakerNotesDoc（含 notes[]，每项有
 *     opening、key_points、script、transition、tips、duration_seconds 等字段）
 */

import { useState } from 'react';
import { cn } from '@/lib/utils';
import {
  Mic, FileText, ChevronDown, ChevronRight,
  Clock, Lightbulb, ArrowRight, List,
} from 'lucide-react';

// ── 旧格式 ──

export interface SpeakerNote {
  page_number: number;
  page_title: string;
  notes: string;
}

// ── 新格式 ──

export interface SpeakerNoteItem {
  page_id: string;
  page_number: number;
  title: string;
  duration_seconds: number;
  opening: string;
  key_points: string[];
  script: string;
  transition: string;
  tips: string[];
}

export interface SpeakerNotesSummary {
  total_duration_formatted: string;
  page_count: number;
  scene_type: string;
  tone: string;
  notes: string[];
}

export interface SpeakerNotesDoc {
  schema_version: string;
  language?: string;
  total_pages?: number;
  total_duration_seconds?: number;
  scene_type?: string;
  audience?: string;
  notes: SpeakerNoteItem[];
  summary?: SpeakerNotesSummary;
}

// ── 新格式单页卡片 ──

function NoteCard({
  note,
  isActive,
  onClick,
}: {
  note: SpeakerNoteItem;
  isActive: boolean;
  onClick: () => void;
}) {
  const [expanded, setExpanded] = useState(isActive);
  const mins = Math.floor(note.duration_seconds / 60);
  const secs = note.duration_seconds % 60;
  const durationLabel = mins > 0 ? `${mins}分${secs > 0 ? secs + '秒' : ''}` : `${secs}秒`;

  return (
    <div
      className={cn(
        'rounded-lg border transition-all',
        isActive ? 'border-primary/30 bg-primary/5' : 'border-border/40',
      )}
    >
      {/* 页头 */}
      <button
        type="button"
        className="w-full text-left px-3 py-2.5 flex items-center gap-2"
        onClick={() => { onClick(); setExpanded(e => !e); }}
      >
        <FileText className="w-3 h-3 text-muted-foreground/50 shrink-0" />
        <span className="text-[10px] font-bold text-muted-foreground/60 shrink-0">P{note.page_number}</span>
        <span className="text-[11px] text-foreground/70 flex-1 truncate">{note.title}</span>
        <span className="flex items-center gap-1 text-[9px] text-muted-foreground/40 shrink-0">
          <Clock className="w-2.5 h-2.5" />
          {durationLabel}
        </span>
        {expanded
          ? <ChevronDown className="w-3 h-3 text-muted-foreground/40 shrink-0" />
          : <ChevronRight className="w-3 h-3 text-muted-foreground/40 shrink-0" />
        }
      </button>

      {expanded && (
        <div className="px-3 pb-3 space-y-2.5 border-t border-border/30 pt-2.5">
          {/* 开场白 */}
          <div>
            <div className="text-[9px] font-bold text-primary/60 uppercase tracking-wider mb-1">开场白</div>
            <p className="text-[11px] text-foreground/80 leading-relaxed italic">"{note.opening}"</p>
          </div>

          {/* 核心要点 */}
          {note.key_points && note.key_points.length > 0 && (
            <div>
              <div className="flex items-center gap-1 text-[9px] font-bold text-foreground/50 uppercase tracking-wider mb-1">
                <List className="w-2.5 h-2.5" />
                核心要点
              </div>
              <ul className="space-y-0.5">
                {note.key_points.map((kp, i) => (
                  <li key={i} className="flex items-start gap-1.5 text-[10px] text-foreground/70">
                    <span className="text-primary/40 shrink-0 mt-0.5">·</span>
                    <span>{kp}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* 讲稿正文 */}
          {note.script && (
            <div>
              <div className="text-[9px] font-bold text-foreground/50 uppercase tracking-wider mb-1">讲稿</div>
              <p className="text-[11px] text-foreground/75 leading-relaxed whitespace-pre-line">
                {note.script}
              </p>
            </div>
          )}

          {/* 过渡语 */}
          {note.transition && (
            <div className="flex items-start gap-1.5 bg-muted/30 rounded px-2 py-1.5">
              <ArrowRight className="w-3 h-3 text-primary/50 shrink-0 mt-0.5" />
              <p className="text-[10px] text-foreground/60 italic">{note.transition}</p>
            </div>
          )}

          {/* 演讲技巧 */}
          {note.tips && note.tips.length > 0 && (
            <div>
              <div className="flex items-center gap-1 text-[9px] font-bold text-amber-500/70 uppercase tracking-wider mb-1">
                <Lightbulb className="w-2.5 h-2.5" />
                演讲技巧
              </div>
              <ul className="space-y-0.5">
                {note.tips.map((tip, i) => (
                  <li key={i} className="flex items-start gap-1.5 text-[10px] text-muted-foreground/70">
                    <span className="text-amber-500/40 shrink-0 mt-0.5">·</span>
                    <span>{tip}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ── 主面板 ──

export function SpeakerNotesPanel({
  notes,
  activePage,
  onPageSelect,
}: {
  notes: SpeakerNote[] | SpeakerNotesDoc | null;
  activePage: number;
  onPageSelect?: (pageNumber: number) => void;
}) {
  if (!notes) {
    return (
      <div className="flex flex-col items-center justify-center h-full p-4 text-center">
        <Mic className="w-8 h-8 text-muted-foreground/20 mb-2" />
        <p className="text-xs text-muted-foreground/50">
          讲稿将在导出时生成，或可在对话中要求 AI 生成
        </p>
      </div>
    );
  }

  // 检测新格式
  if (!Array.isArray(notes) && notes.schema_version) {
    const doc = notes as SpeakerNotesDoc;
    const items = doc.notes || [];

    if (items.length === 0) {
      return (
        <div className="flex flex-col items-center justify-center h-full p-4 text-center">
          <Mic className="w-8 h-8 text-muted-foreground/20 mb-2" />
          <p className="text-xs text-muted-foreground/50">暂无讲稿内容</p>
        </div>
      );
    }

    return (
      <div className="flex flex-col h-full overflow-hidden">
        {/* 顶部摘要条 */}
        {doc.summary && (
          <div className="px-3 py-2 border-b border-border/30 flex items-center gap-3 shrink-0">
            <Clock className="w-3.5 h-3.5 text-muted-foreground/40 shrink-0" />
            <span className="text-[10px] text-muted-foreground/60">{doc.summary.total_duration_formatted}</span>
            <span className="text-[10px] text-muted-foreground/40">·</span>
            <span className="text-[10px] text-muted-foreground/60 truncate">{doc.summary.tone}</span>
          </div>
        )}

        {/* 逐页讲稿 */}
        <div className="flex-1 overflow-y-auto p-2 space-y-1.5 scrollbar-thin">
          {items.map(item => (
            <NoteCard
              key={item.page_id}
              note={item}
              isActive={item.page_number === activePage}
              onClick={() => onPageSelect?.(item.page_number)}
            />
          ))}
        </div>
      </div>
    );
  }

  // 旧格式
  const oldNotes = notes as SpeakerNote[];
  if (oldNotes.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-full p-4 text-center">
        <Mic className="w-8 h-8 text-muted-foreground/20 mb-2" />
        <p className="text-xs text-muted-foreground/50">暂无讲稿内容</p>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full overflow-y-auto p-2 space-y-2 scrollbar-thin">
      {oldNotes.map(note => (
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
