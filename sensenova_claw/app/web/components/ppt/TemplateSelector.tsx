'use client';

/**
 * 模板选择器 —— 底栏 / 首次创建时的模板市场
 *
 * 对应 skill：ppt-template-pack、ppt-source-analysis
 * - 预置模板风格浏览（缩略图网格）
 * - 按风格/场景/行业分类
 * - 选中模板后注入 task-pack 约束
 * - 支持上传自有模板
 */

import { useState } from 'react';
import { cn } from '@/lib/utils';
import {
  Presentation, Upload, Briefcase, GraduationCap,
  TrendingUp, Cpu, Palette, Leaf, Sparkles,
} from 'lucide-react';

export interface TemplateItem {
  id: string;
  name: string;
  category: string;
  description: string;
  thumbnail?: string;  // URL 或 base64
  keywords: string[];
}

// ── 内置模板（静态，后续可从 API 加载） ──

const BUILTIN_TEMPLATES: TemplateItem[] = [
  {
    id: 'business-pitch',
    name: '商业路演',
    category: '商务',
    description: '简洁专业的商业计划书风格，深色系配色',
    keywords: ['商务', '融资', '路演'],
  },
  {
    id: 'tech-share',
    name: '技术分享',
    category: '科技',
    description: '科技感十足的暗色主题，代码友好',
    keywords: ['技术', '开发', '架构'],
  },
  {
    id: 'annual-report',
    name: '年度总结',
    category: '商务',
    description: '数据驱动的年报风格，图表丰富',
    keywords: ['总结', '年报', '数据'],
  },
  {
    id: 'product-launch',
    name: '产品发布',
    category: '营销',
    description: '大胆醒目的产品发布风格，强调视觉冲击',
    keywords: ['产品', '发布', '营销'],
  },
  {
    id: 'education',
    name: '教学课件',
    category: '教育',
    description: '清晰易读的教学风格，层次分明',
    keywords: ['教学', '课件', '培训'],
  },
  {
    id: 'minimal',
    name: '极简白',
    category: '设计',
    description: '大量留白、黑白灰配色，注重排版节奏',
    keywords: ['极简', '设计', '排版'],
  },
  {
    id: 'nature',
    name: '自然生态',
    category: '环保',
    description: '绿色环保主题，有机曲线与自然纹理',
    keywords: ['生态', '环保', '自然'],
  },
  {
    id: 'creative',
    name: '创意展示',
    category: '设计',
    description: '大胆配色与非对称布局，个性十足',
    keywords: ['创意', '设计', '艺术'],
  },
];

const CATEGORY_ICONS: Record<string, React.ElementType> = {
  '商务': Briefcase,
  '科技': Cpu,
  '教育': GraduationCap,
  '营销': TrendingUp,
  '设计': Palette,
  '环保': Leaf,
};

const CATEGORIES = ['全部', ...new Set(BUILTIN_TEMPLATES.map(t => t.category))];

// ── 模板卡片 ──

function TemplateCard({
  template,
  isSelected,
  onClick,
}: {
  template: TemplateItem;
  isSelected: boolean;
  onClick: () => void;
}) {
  const CategoryIcon = CATEGORY_ICONS[template.category] || Presentation;

  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        'group flex flex-col rounded-xl border overflow-hidden transition-all duration-200',
        'hover:shadow-md hover:scale-[1.02]',
        isSelected
          ? 'border-primary/50 ring-2 ring-primary/20 shadow-md'
          : 'border-border/40 hover:border-border/60',
      )}
    >
      {/* 缩略图区 */}
      <div className={cn(
        'aspect-[16/9] flex items-center justify-center',
        'bg-gradient-to-br from-muted/40 to-muted/20',
      )}>
        {template.thumbnail ? (
          <img src={template.thumbnail} alt={template.name} className="w-full h-full object-cover" />
        ) : (
          <CategoryIcon className={cn(
            'w-8 h-8 transition-colors',
            isSelected ? 'text-primary/60' : 'text-muted-foreground/20 group-hover:text-muted-foreground/40',
          )} />
        )}
      </div>
      {/* 信息 */}
      <div className="p-2.5 text-left">
        <div className="text-xs font-semibold text-foreground/80 mb-0.5">{template.name}</div>
        <div className="text-[10px] text-muted-foreground/60 line-clamp-1">{template.description}</div>
        <div className="flex items-center gap-1 mt-1.5">
          {template.keywords.slice(0, 2).map(kw => (
            <span key={kw} className="text-[9px] px-1.5 py-0.5 rounded-full bg-muted/50 text-muted-foreground/60">
              {kw}
            </span>
          ))}
        </div>
      </div>
    </button>
  );
}

// ── 主面板 ──

export function TemplateSelector({
  onSelect,
  onUpload,
}: {
  onSelect: (template: TemplateItem) => void;
  onUpload?: () => void;
}) {
  const [activeCategory, setActiveCategory] = useState('全部');
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const filtered = activeCategory === '全部'
    ? BUILTIN_TEMPLATES
    : BUILTIN_TEMPLATES.filter(t => t.category === activeCategory);

  const handleSelect = (template: TemplateItem) => {
    setSelectedId(template.id);
    onSelect(template);
  };

  return (
    <div className="flex flex-col h-full">
      {/* 头部：分类 + 上传 */}
      <div className="flex items-center gap-2 px-3 py-2 border-b border-border/40 shrink-0">
        <div className="flex items-center gap-1 flex-1 overflow-x-auto scrollbar-none">
          {CATEGORIES.map(cat => (
            <button
              key={cat}
              type="button"
              onClick={() => setActiveCategory(cat)}
              className={cn(
                'px-2.5 py-1 rounded-lg text-[11px] font-medium whitespace-nowrap transition-colors',
                activeCategory === cat
                  ? 'bg-primary/10 text-primary'
                  : 'text-muted-foreground/60 hover:text-foreground hover:bg-muted/40',
              )}
            >
              {cat}
            </button>
          ))}
        </div>
        {onUpload && (
          <button
            type="button"
            onClick={onUpload}
            className="flex items-center gap-1 px-2.5 py-1 rounded-lg text-[11px] font-medium text-muted-foreground hover:text-foreground hover:bg-muted/40 transition-colors shrink-0 border border-dashed border-border/60"
          >
            <Upload className="w-3 h-3" />
            上传模板
          </button>
        )}
      </div>

      {/* 模板网格 */}
      <div className="flex-1 overflow-y-auto p-3 scrollbar-thin">
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-2.5">
          {filtered.map(tpl => (
            <TemplateCard
              key={tpl.id}
              template={tpl}
              isSelected={selectedId === tpl.id}
              onClick={() => handleSelect(tpl)}
            />
          ))}
        </div>
      </div>
    </div>
  );
}

// ── 紧凑模式（底栏水平滚动） ──

export function TemplateStrip({
  onSelect,
}: {
  onSelect: (template: TemplateItem) => void;
}) {
  const [selectedId, setSelectedId] = useState<string | null>(null);

  return (
    <div className="flex items-center gap-2 overflow-x-auto px-3 py-2 scrollbar-none">
      <div className="flex items-center gap-1.5 shrink-0">
        <Sparkles className="w-3.5 h-3.5 text-primary/50" />
        <span className="text-[10px] font-bold text-muted-foreground/60 uppercase tracking-wider whitespace-nowrap">模板</span>
      </div>
      {BUILTIN_TEMPLATES.map(tpl => {
        const Icon = CATEGORY_ICONS[tpl.category] || Presentation;
        return (
          <button
            key={tpl.id}
            type="button"
            onClick={() => { setSelectedId(tpl.id); onSelect(tpl); }}
            className={cn(
              'flex items-center gap-1.5 px-3 py-1.5 rounded-lg whitespace-nowrap text-[11px] font-medium transition-all shrink-0',
              'border',
              selectedId === tpl.id
                ? 'border-primary/40 bg-primary/8 text-primary'
                : 'border-border/40 text-muted-foreground/70 hover:bg-muted/40 hover:text-foreground',
            )}
          >
            <Icon className="w-3 h-3" />
            {tpl.name}
          </button>
        );
      })}
    </div>
  );
}
