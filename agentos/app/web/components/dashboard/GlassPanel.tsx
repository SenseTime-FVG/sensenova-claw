'use client';

import { type ToneName, getTone } from './widgetTones';

interface GlassPanelProps {
  tone?: ToneName;
  className?: string;
  children: React.ReactNode;
}

export function GlassPanel({ tone = 'neutral', className = '', children }: GlassPanelProps) {
  const style = getTone(tone);

  return (
    <div
      className={`relative overflow-hidden rounded-[30px] border border-white/70 bg-white/65 shadow-[0_20px_60px_rgba(15,23,42,0.08)] backdrop-blur-2xl ring-1 ring-black/[0.03] ${className}`}
    >
      <div className={`absolute inset-0 bg-gradient-to-br ${style.surface}`} />
      <div className={`absolute -right-10 -top-10 h-28 w-28 rounded-full ${style.orb} blur-3xl`} />
      <div className="absolute inset-0 bg-[radial-gradient(circle_at_top_left,rgba(255,255,255,0.72),transparent_36%)]" />
      <div className="relative z-10">{children}</div>
    </div>
  );
}
