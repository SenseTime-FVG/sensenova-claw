'use client';

import Link from 'next/link';
import {
  Sparkles, BookOpen, Presentation, Zap, Plus, ArrowRight,
  Code, Globe, Music, Image, FileText, Database, Shield,
  Brain, Rocket, Target, Heart, Star, Lightbulb, Puzzle,
} from 'lucide-react';
import { useCustomPages } from '@/hooks/useCustomPages';
import type { LucideIcon } from 'lucide-react';
import { cn } from '@/lib/utils';

const ICON_MAP: Record<string, LucideIcon> = {
  Sparkles, BookOpen, Zap, Presentation, Code, Globe,
  Music, Image, FileText, Database, Shield, Brain,
  Rocket, Target, Heart, Star, Lightbulb, Puzzle,
};

const COLOR_THEMES = [
  { bg: 'from-blue-100/40 via-blue-50/20 to-indigo-100/30 dark:from-blue-500/15 dark:via-blue-500/8 dark:to-indigo-500/10', iconBg: 'bg-blue-500/15', iconColor: 'text-blue-600 dark:text-blue-400', ring: 'ring-blue-200/60 hover:ring-blue-300/80 dark:ring-blue-500/15 dark:hover:ring-blue-500/30' },
  { bg: 'from-amber-100/40 via-amber-50/20 to-orange-100/30 dark:from-amber-500/15 dark:via-amber-500/8 dark:to-orange-500/10', iconBg: 'bg-amber-500/15', iconColor: 'text-amber-600 dark:text-amber-400', ring: 'ring-amber-200/60 hover:ring-amber-300/80 dark:ring-amber-500/15 dark:hover:ring-amber-500/30' },
  { bg: 'from-violet-100/40 via-violet-50/20 to-purple-100/30 dark:from-violet-500/15 dark:via-violet-500/8 dark:to-purple-500/10', iconBg: 'bg-violet-500/15', iconColor: 'text-violet-600 dark:text-violet-400', ring: 'ring-violet-200/60 hover:ring-violet-300/80 dark:ring-violet-500/15 dark:hover:ring-violet-500/30' },
  { bg: 'from-emerald-100/40 via-emerald-50/20 to-teal-100/30 dark:from-emerald-500/15 dark:via-emerald-500/8 dark:to-teal-500/10', iconBg: 'bg-emerald-500/15', iconColor: 'text-emerald-600 dark:text-emerald-400', ring: 'ring-emerald-200/60 hover:ring-emerald-300/80 dark:ring-emerald-500/15 dark:hover:ring-emerald-500/30' },
  { bg: 'from-rose-100/40 via-rose-50/20 to-pink-100/30 dark:from-rose-500/15 dark:via-rose-500/8 dark:to-pink-500/10', iconBg: 'bg-rose-500/15', iconColor: 'text-rose-600 dark:text-rose-400', ring: 'ring-rose-200/60 hover:ring-rose-300/80 dark:ring-rose-500/15 dark:hover:ring-rose-500/30' },
  { bg: 'from-cyan-100/40 via-cyan-50/20 to-sky-100/30 dark:from-cyan-500/15 dark:via-cyan-500/8 dark:to-sky-500/10', iconBg: 'bg-cyan-500/15', iconColor: 'text-cyan-600 dark:text-cyan-400', ring: 'ring-cyan-200/60 hover:ring-cyan-300/80 dark:ring-cyan-500/15 dark:hover:ring-cyan-500/30' },
];

const builtinFeatures = [
  { path: '/research', label: '深度研究', desc: '深入分析行业趋势、竞品调研和技术方案', icon: BookOpen },
  { path: '/ppt', label: 'PPT 生成', desc: '自动生成专业演示文稿和报告课件', icon: Presentation },
  { path: '/automation', label: '自动化', desc: '定时任务、数据监控和批量处理', icon: Zap },
];

export function TaskTemplates() {
  const { pages } = useCustomPages();

  const customFeatures = pages.map(p => ({
    path: `/features/${p.slug}`,
    label: p.name,
    desc: '',
    icon: ICON_MAP[p.icon] || Sparkles,
  }));

  const allFeatures = [...builtinFeatures, ...customFeatures];

  return (
    <div className="flex-1 flex flex-col items-center justify-center p-6">
      <div className="max-w-3xl mx-auto w-full">
        {/* 标题区 */}
        <div className="text-center pt-4 pb-10">
          <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-primary/15 to-primary/5 flex items-center justify-center mx-auto mb-5 shadow-sm">
            <Sparkles className="w-8 h-8 text-primary" />
          </div>
          <h2 className="text-2xl font-bold text-foreground mb-2 tracking-tight">
            你想做什么？
          </h2>
          <p className="text-muted-foreground text-sm">
            选择一个功能快速开始，或直接在下方输入你的需求
          </p>
        </div>

        {/* 功能卡片网格 */}
        <div className="grid grid-cols-2 gap-5">
          {allFeatures.map((feat, i) => {
            const Icon = feat.icon;
            const theme = COLOR_THEMES[i % COLOR_THEMES.length];
            return (
              <Link key={feat.path} href={feat.path} className="group">
                <div
                  className={cn(
                    'relative rounded-2xl p-6 bg-gradient-to-br ring-1 transition-all duration-300 h-full',
                    'hover:shadow-lg hover:-translate-y-0.5',
                    theme.bg,
                    theme.ring,
                  )}
                >
                  <div className={cn('w-12 h-12 rounded-xl flex items-center justify-center mb-5', theme.iconBg)}>
                    <Icon className={cn('w-6 h-6', theme.iconColor)} />
                  </div>
                  <h3 className="font-bold text-foreground text-base mb-1.5">{feat.label}</h3>
                  {feat.desc && (
                    <p className="text-[13px] text-muted-foreground leading-relaxed line-clamp-2">{feat.desc}</p>
                  )}
                  <div className="flex items-center gap-1 mt-4 text-xs font-medium opacity-0 group-hover:opacity-100 transition-opacity duration-300">
                    <span className={theme.iconColor}>进入</span>
                    <ArrowRight className={cn('w-3.5 h-3.5', theme.iconColor)} />
                  </div>
                </div>
              </Link>
            );
          })}

          {/* 创建功能页 */}
          <Link href="/create-feature" className="group">
            <div
              className={cn(
                'relative rounded-2xl p-6 ring-1 ring-dashed transition-all duration-300 h-full',
                'ring-border/60 hover:ring-primary/30',
                'hover:shadow-lg hover:-translate-y-0.5',
                'bg-gradient-to-br from-muted/30 to-transparent',
              )}
            >
              <div className="w-12 h-12 rounded-xl bg-muted/60 flex items-center justify-center mb-5 group-hover:bg-primary/10 transition-colors duration-300">
                <Plus className="w-6 h-6 text-muted-foreground group-hover:text-primary transition-colors duration-300" />
              </div>
              <h3 className="font-bold text-foreground text-base mb-1.5">创建功能页</h3>
              <p className="text-[13px] text-muted-foreground leading-relaxed">
                自定义 Agent 和模板，打造专属工具
              </p>
              <div className="flex items-center gap-1 mt-4 text-xs font-medium opacity-0 group-hover:opacity-100 transition-opacity duration-300">
                <span className="text-primary">创建</span>
                <ArrowRight className="w-3.5 h-3.5 text-primary" />
              </div>
            </div>
          </Link>
        </div>
      </div>
    </div>
  );
}
