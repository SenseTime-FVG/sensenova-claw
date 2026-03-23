// 小组件色调系统 — 温暖精致风格

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
    surface: 'from-blue-50/95 via-white/97 to-sky-50/80',
    orb: 'bg-blue-200/40',
    pill: 'bg-blue-500/10 text-blue-600',
    dot: 'bg-blue-500',
    progress: 'bg-blue-500',
    accent: 'text-blue-600',
    border: 'border-blue-100/60',
  },
  emerald: {
    surface: 'from-emerald-50/95 via-white/97 to-teal-50/80',
    orb: 'bg-emerald-200/40',
    pill: 'bg-emerald-500/10 text-emerald-600',
    dot: 'bg-emerald-500',
    progress: 'bg-emerald-500',
    accent: 'text-emerald-600',
    border: 'border-emerald-100/60',
  },
  amber: {
    surface: 'from-amber-50/95 via-white/97 to-orange-50/80',
    orb: 'bg-amber-200/40',
    pill: 'bg-amber-500/10 text-amber-700',
    dot: 'bg-amber-500',
    progress: 'bg-amber-500',
    accent: 'text-amber-700',
    border: 'border-amber-100/60',
  },
  violet: {
    surface: 'from-violet-50/95 via-white/97 to-purple-50/80',
    orb: 'bg-violet-200/40',
    pill: 'bg-violet-500/10 text-violet-600',
    dot: 'bg-violet-500',
    progress: 'bg-violet-500',
    accent: 'text-violet-600',
    border: 'border-violet-100/60',
  },
  rose: {
    surface: 'from-rose-50/95 via-white/97 to-pink-50/80',
    orb: 'bg-rose-200/40',
    pill: 'bg-rose-500/10 text-rose-600',
    dot: 'bg-rose-500',
    progress: 'bg-rose-500',
    accent: 'text-rose-600',
    border: 'border-rose-100/60',
  },
  indigo: {
    surface: 'from-indigo-50/95 via-white/97 to-blue-50/80',
    orb: 'bg-indigo-200/40',
    pill: 'bg-indigo-500/10 text-indigo-600',
    dot: 'bg-indigo-500',
    progress: 'bg-indigo-500',
    accent: 'text-indigo-600',
    border: 'border-indigo-100/60',
  },
  neutral: {
    surface: 'from-slate-50/95 via-white/97 to-zinc-50/85',
    orb: 'bg-slate-200/35',
    pill: 'bg-slate-500/10 text-slate-600',
    dot: 'bg-slate-500',
    progress: 'bg-slate-600',
    accent: 'text-slate-600',
    border: 'border-slate-100/60',
  },
};

export function getTone(tone: ToneName): ToneStyle {
  return widgetToneMap[tone] || widgetToneMap.neutral;
}
