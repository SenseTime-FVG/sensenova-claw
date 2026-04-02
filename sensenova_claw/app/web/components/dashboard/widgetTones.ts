// 小组件色调系统 — 温暖精致风格（支持深色模式）

export type ToneName = 'blue' | 'emerald' | 'amber' | 'violet' | 'neutral' | 'rose' | 'indigo';

export interface ToneStyle {
  surface: string;
  orb: string;
  pill: string;
  dot: string;
  progress: string;
  accent: string;
  border: string;
}

export const widgetToneMap: Record<ToneName, ToneStyle> = {
  blue: {
    surface: 'from-blue-50/95 via-white/97 to-sky-50/80 dark:from-blue-950/40 dark:via-slate-900/50 dark:to-sky-950/30',
    orb: 'bg-blue-200/40 dark:bg-blue-500/20',
    pill: 'bg-blue-500/10 text-blue-600 dark:bg-blue-500/20 dark:text-blue-300',
    dot: 'bg-blue-500 dark:bg-blue-400',
    progress: 'bg-blue-500 dark:bg-blue-400',
    accent: 'text-blue-600 dark:text-blue-300',
    border: 'border-blue-100/60 dark:border-blue-500/20',
  },
  emerald: {
    surface: 'from-emerald-50/95 via-white/97 to-teal-50/80 dark:from-emerald-950/40 dark:via-slate-900/50 dark:to-teal-950/30',
    orb: 'bg-emerald-200/40 dark:bg-emerald-500/20',
    pill: 'bg-emerald-500/10 text-emerald-600 dark:bg-emerald-500/20 dark:text-emerald-300',
    dot: 'bg-emerald-500 dark:bg-emerald-400',
    progress: 'bg-emerald-500 dark:bg-emerald-400',
    accent: 'text-emerald-600 dark:text-emerald-300',
    border: 'border-emerald-100/60 dark:border-emerald-500/20',
  },
  amber: {
    surface: 'from-amber-50/95 via-white/97 to-orange-50/80 dark:from-amber-950/40 dark:via-slate-900/50 dark:to-orange-950/30',
    orb: 'bg-amber-200/40 dark:bg-amber-500/20',
    pill: 'bg-amber-500/10 text-amber-700 dark:bg-amber-500/20 dark:text-amber-300',
    dot: 'bg-amber-500 dark:bg-amber-400',
    progress: 'bg-amber-500 dark:bg-amber-400',
    accent: 'text-amber-700 dark:text-amber-300',
    border: 'border-amber-100/60 dark:border-amber-500/20',
  },
  violet: {
    surface: 'from-violet-50/95 via-white/97 to-purple-50/80 dark:from-violet-950/40 dark:via-slate-900/50 dark:to-purple-950/30',
    orb: 'bg-violet-200/40 dark:bg-violet-500/20',
    pill: 'bg-violet-500/10 text-violet-600 dark:bg-violet-500/20 dark:text-violet-300',
    dot: 'bg-violet-500 dark:bg-violet-400',
    progress: 'bg-violet-500 dark:bg-violet-400',
    accent: 'text-violet-600 dark:text-violet-300',
    border: 'border-violet-100/60 dark:border-violet-500/20',
  },
  rose: {
    surface: 'from-rose-50/95 via-white/97 to-pink-50/80 dark:from-rose-950/40 dark:via-slate-900/50 dark:to-pink-950/30',
    orb: 'bg-rose-200/40 dark:bg-rose-500/20',
    pill: 'bg-rose-500/10 text-rose-600 dark:bg-rose-500/20 dark:text-rose-300',
    dot: 'bg-rose-500 dark:bg-rose-400',
    progress: 'bg-rose-500 dark:bg-rose-400',
    accent: 'text-rose-600 dark:text-rose-300',
    border: 'border-rose-100/60 dark:border-rose-500/20',
  },
  indigo: {
    surface: 'from-indigo-50/95 via-white/97 to-blue-50/80 dark:from-indigo-950/40 dark:via-slate-900/50 dark:to-blue-950/30',
    orb: 'bg-indigo-200/40 dark:bg-indigo-500/20',
    pill: 'bg-indigo-500/10 text-indigo-600 dark:bg-indigo-500/20 dark:text-indigo-300',
    dot: 'bg-indigo-500 dark:bg-indigo-400',
    progress: 'bg-indigo-500 dark:bg-indigo-400',
    accent: 'text-indigo-600 dark:text-indigo-300',
    border: 'border-indigo-100/60 dark:border-indigo-500/20',
  },
  neutral: {
    surface: 'from-slate-50/95 via-white/97 to-zinc-50/85 dark:from-slate-900/50 dark:via-slate-900/60 dark:to-zinc-900/40',
    orb: 'bg-slate-200/35 dark:bg-slate-500/15',
    pill: 'bg-slate-500/10 text-slate-600 dark:bg-slate-500/20 dark:text-slate-300',
    dot: 'bg-slate-500 dark:bg-slate-400',
    progress: 'bg-slate-600 dark:bg-slate-400',
    accent: 'text-slate-600 dark:text-slate-300',
    border: 'border-slate-100/60 dark:border-slate-500/20',
  },
};

export function getTone(tone: ToneName): ToneStyle {
  return widgetToneMap[tone] || widgetToneMap.neutral;
}
