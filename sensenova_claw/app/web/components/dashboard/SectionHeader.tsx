'use client';

import { type ToneName, getTone } from './widgetTones';

interface SectionHeaderProps {
  title: string;
  subtitle?: string;
  tag?: string;
  tagTone?: ToneName;
  icon?: React.ReactNode;
}

export function SectionHeader({ title, subtitle, tag, tagTone = 'neutral', icon }: SectionHeaderProps) {
  const tone = getTone(tagTone);

  return (
    <div className="mb-3 flex items-center justify-between gap-3">
      <div className="flex items-center gap-2">
        {icon && (
          <div className="flex h-7 w-7 items-center justify-center rounded-lg border border-[var(--glass-border)] bg-[var(--glass-bg-heavy)] shadow-sm">
            {icon}
          </div>
        )}
        <div>
          <div className="text-[13px] font-bold text-[var(--glass-text)] tracking-tight" style={{ fontFamily: "'DM Sans', sans-serif" }}>
            {title}
          </div>
          {subtitle && <div className="text-[10px] mt-0.5 text-[var(--glass-text-muted)]">{subtitle}</div>}
        </div>
      </div>
      {tag && (
        <span
          className={`rounded-full border border-[var(--glass-border)] bg-[var(--glass-bg)] px-2.5 py-0.5 text-[10px] font-semibold shadow-sm backdrop-blur-xl ${tone.pill}`}
        >
          {tag}
        </span>
      )}
    </div>
  );
}
