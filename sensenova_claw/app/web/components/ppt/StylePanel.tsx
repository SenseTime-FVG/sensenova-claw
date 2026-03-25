'use client';

/**
 * 风格配置面板 —— 右栏 Tab
 *
 * 读取 style-spec.json，展示并允许调整：
 *   - 配色方案（主色、辅色、背景色）
 *   - 字体选择
 *   - 设计关键词标签
 *   - 风格预览缩略图
 */

import { cn } from '@/lib/utils';
import { Palette, Type, Tags, Sparkles } from 'lucide-react';

export interface StyleSpec {
  design_theme: string;
  design_keywords: string[];
  color_roles: {
    primary: string;
    secondary: string;
    accent: string;
    background: string;
    surface: string;
    text_primary: string;
    text_secondary: string;
    [key: string]: string;
  };
  typography: {
    heading_font: string;
    body_font: string;
    mono_font?: string;
    [key: string]: string | undefined;
  };
  page_type_principles: Record<string, string>;
  anti_patterns: string[];
  [key: string]: unknown;
}

// ── 颜色色块 ──

function ColorSwatch({ label, color }: { label: string; color: string }) {
  const colorStr = typeof color === 'string' ? color : String(color ?? '');
  const isHex = colorStr.startsWith('#');
  return (
    <div className="flex items-center gap-2">
      <div
        className="w-6 h-6 rounded-md border border-border/40 shadow-inner shrink-0"
        style={isHex ? { backgroundColor: colorStr } : undefined}
      >
        {!isHex && (
          <div className="w-full h-full rounded-md bg-muted flex items-center justify-center text-[8px] text-muted-foreground">
            ?
          </div>
        )}
      </div>
      <div className="min-w-0">
        <div className="text-[10px] font-medium text-foreground/70 capitalize">{label}</div>
        <div className="text-[9px] text-muted-foreground/60 font-mono truncate">{colorStr}</div>
      </div>
    </div>
  );
}

// ── 关键词标签 ──

function KeywordTag({ keyword }: { keyword: string }) {
  return (
    <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-medium bg-primary/8 text-primary/80 border border-primary/15">
      {keyword}
    </span>
  );
}

// ── 主面板 ──

export function StylePanel({
  styleSpec,
  onRefineRequest,
}: {
  styleSpec: StyleSpec | null;
  onRefineRequest?: (instruction: string) => void;
}) {
  if (!styleSpec) {
    return (
      <div className="flex flex-col items-center justify-center h-full p-4 text-center">
        <Palette className="w-8 h-8 text-muted-foreground/20 mb-2" />
        <p className="text-xs text-muted-foreground/50">
          风格规格将在 AI 生成 style-spec 后显示
        </p>
      </div>
    );
  }

  const colorEntries = Object.entries(styleSpec.color_roles || {}).filter(
    ([, v]) => typeof v === 'string' || typeof v === 'number',
  );
  const keywords = styleSpec.design_keywords || [];
  const typography = styleSpec.typography || {};

  return (
    <div className="flex flex-col h-full overflow-y-auto p-3 space-y-4 scrollbar-thin">
      {/* 主题 */}
      <div>
        <div className="flex items-center gap-1.5 mb-2">
          <Sparkles className="w-3.5 h-3.5 text-primary/60" />
          <span className="text-[11px] font-bold text-foreground/80 uppercase tracking-wider">设计主题</span>
        </div>
        <div className="text-xs text-foreground/70 bg-muted/30 rounded-lg p-2.5 leading-relaxed">
          {styleSpec.design_theme || '未指定'}
        </div>
      </div>

      {/* 关键词 */}
      {keywords.length > 0 && (
        <div>
          <div className="flex items-center gap-1.5 mb-2">
            <Tags className="w-3.5 h-3.5 text-primary/60" />
            <span className="text-[11px] font-bold text-foreground/80 uppercase tracking-wider">设计关键词</span>
          </div>
          <div className="flex flex-wrap gap-1.5">
            {keywords.map(kw => <KeywordTag key={kw} keyword={kw} />)}
          </div>
        </div>
      )}

      {/* 配色 */}
      {colorEntries.length > 0 && (
        <div>
          <div className="flex items-center gap-1.5 mb-2">
            <Palette className="w-3.5 h-3.5 text-primary/60" />
            <span className="text-[11px] font-bold text-foreground/80 uppercase tracking-wider">配色方案</span>
          </div>
          <div className="grid grid-cols-2 gap-2">
            {colorEntries.map(([key, val]) => (
              <ColorSwatch key={key} label={key.replace(/_/g, ' ')} color={val} />
            ))}
          </div>
        </div>
      )}

      {/* 字体 */}
      {Object.keys(typography).length > 0 && (
        <div>
          <div className="flex items-center gap-1.5 mb-2">
            <Type className="w-3.5 h-3.5 text-primary/60" />
            <span className="text-[11px] font-bold text-foreground/80 uppercase tracking-wider">字体</span>
          </div>
          <div className="space-y-1.5">
            {Object.entries(typography).filter(([, v]) => v).map(([key, val]) => (
              <div key={key} className="flex items-center justify-between px-2.5 py-1.5 rounded-lg bg-muted/30">
                <span className="text-[10px] text-muted-foreground capitalize">{key.replace(/_/g, ' ')}</span>
                <span className="text-[11px] font-medium text-foreground/80">{val}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* 优化按钮 */}
      {onRefineRequest && (
        <button
          type="button"
          onClick={() => onRefineRequest('请优化当前风格，使设计更加精致统一')}
          className="w-full py-2 rounded-lg border border-primary/20 text-xs font-medium text-primary hover:bg-primary/5 transition-colors"
        >
          优化风格
        </button>
      )}
    </div>
  );
}
