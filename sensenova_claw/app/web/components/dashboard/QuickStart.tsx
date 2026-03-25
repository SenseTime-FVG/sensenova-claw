'use client';

import Link from 'next/link';
import { BookOpen, Presentation, Zap, Plus, ArrowRight } from 'lucide-react';
import { GlassPanel } from './GlassPanel';
import { SectionHeader } from './SectionHeader';
import { getTone } from './widgetTones';
import type { ToneName } from './widgetTones';

const quickItems: { path: string; label: string; desc: string; icon: string; tone: ToneName }[] = [
  { path: '/research', label: '深度研究', desc: '深入分析行业趋势、竞品调研和技术方案', icon: '🔎', tone: 'blue' },
  { path: '/ppt', label: 'PPT 生成', desc: '自动生成专业演示文稿和报告课件', icon: '🪄', tone: 'amber' },
  { path: '/automation', label: '自动化', desc: '定时任务、数据监控和批量处理', icon: '⚡', tone: 'violet' },
];

function QuickCard({ item }: { item: (typeof quickItems)[number] }) {
  const tone = getTone(item.tone);

  return (
    <Link href={item.path} className="group">
      <div className="relative overflow-hidden rounded-[22px] border border-[var(--glass-border-heavy)] bg-[var(--glass-bg)] p-5 text-left shadow-[0_10px_26px_rgba(15,23,42,0.05)] dark:shadow-[0_10px_26px_rgba(0,0,0,0.2)] backdrop-blur-xl transition duration-200 hover:-translate-y-0.5">
        <div className={`absolute inset-0 bg-gradient-to-br ${tone.surface}`} />
        <div className={`absolute -right-8 -top-8 h-20 w-20 rounded-full ${tone.orb} blur-3xl`} />
        <div className="relative z-10">
          <div className="flex items-center gap-3 mb-3">
            <div className="flex h-11 w-11 items-center justify-center rounded-[16px] border border-[var(--glass-border-heavy)] bg-[var(--glass-bg-heavy)] text-lg shadow-sm">
              {item.icon}
            </div>
            <div>
              <div className="text-sm font-semibold text-[var(--glass-text)]">{item.label}</div>
              <div className="text-xs text-muted-foreground">{item.desc}</div>
            </div>
          </div>
          <div className="flex items-center gap-1 text-xs font-medium opacity-0 group-hover:opacity-100 transition-opacity duration-300">
            <span className={getTone(item.tone).pill.split(' ')[1]}>进入</span>
            <ArrowRight className="w-3.5 h-3.5 text-muted-foreground" />
          </div>
        </div>
      </div>
    </Link>
  );
}

export function QuickStart() {
  return (
    <GlassPanel tone="neutral" className="p-5">
      <SectionHeader
        title="快速开始"
        subtitle="选择一个功能快速启动，或在下方输入你的需求"
        tag="Quick Start"
        tagTone="blue"
      />
      <div className="grid grid-cols-3 gap-4">
        {quickItems.map(item => (
          <QuickCard key={item.path} item={item} />
        ))}
      </div>
    </GlassPanel>
  );
}
