'use client';

/**
 * PPT 工作台页面 —— 综合布局
 *
 * 布局结构：
 * ┌─────────────────────────────────────────────────────────┐
 * │  顶栏：Deck 标题 / 流水线进度条 / 导出按钮             │
 * ├──────────┬──────────────────────────────┬───────────────┤
 * │  左栏    │       主舞台                 │    右栏       │
 * │ ·大纲    │   幻灯片预览/编辑区          │               │
 * │ ·风格    │   (SlideViewer)              │  对话面板     │
 * │ ·审查    │                              │  (ChatPanel)  │
 * │ ·讲稿    │                              │               │
 * ├──────────┴──────────────────────────────┴───────────────┤
 * │  底栏：模板选择器（首次创建时）/ 进度概要               │
 * └─────────────────────────────────────────────────────────┘
 */

import { Suspense, useState, useCallback, useRef, useEffect } from 'react';
import { useDrop } from 'react-dnd';
import { DashboardLayout } from '@/components/layout/DashboardLayout';
import { ChatPanel } from '@/components/chat/ChatPanel';
import { SlideViewer } from '@/components/ppt/PPTViewer';
import { PipelineProgress, DEFAULT_STAGES } from '@/components/ppt/PipelineProgress';
import { StoryboardPanel } from '@/components/ppt/StoryboardPanel';
import { StylePanel } from '@/components/ppt/StylePanel';
import { ReviewPanel, type PageIssue } from '@/components/ppt/ReviewPanel';
import { SpeakerNotesPanel } from '@/components/ppt/SpeakerNotesPanel';
import { ExportDropdown } from '@/components/ppt/ExportDropdown';
import { TemplateStrip, type TemplateItem } from '@/components/ppt/TemplateSelector';
import { useDeckData } from '@/hooks/useDeckData';
import { useChatSession } from '@/contexts/ChatSessionContext';
import { Button } from '@/components/ui/button';
import {
  Presentation, Upload, FileDown, Sparkles, Wand2,
  Palette, ShieldCheck, Mic,
  Search as SearchIcon, BookOpen, Layers, FileText, ArrowRight, Loader2,
  RefreshCw, Plus, MessageSquare, Trash2, Clock,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { authFetch, API_BASE } from '@/lib/authFetch';
import { ResizablePanelGroup, ResizablePanel, ResizableHandle } from '@/components/ui/resizable';
import { type SessionItem, getAgentId, getTitle, timeLabel } from '@/lib/chatTypes';

// ── 快捷模板入口 ──

const QUICK_TEMPLATES = [
  { label: '商业路演', prompt: '帮我制作一份商业路演 PPT，包含项目背景、市场分析、商业模式、团队介绍和融资计划', emoji: '🏢' },
  { label: '技术分享', prompt: '帮我制作一份技术分享 PPT，主题是', emoji: '💻' },
  { label: '年度总结', prompt: '帮我制作一份年度工作总结 PPT，包含业绩回顾、项目成果、个人成长和来年规划', emoji: '📊' },
  { label: '产品介绍', prompt: '帮我制作一份产品介绍 PPT，包含产品概述、核心功能、竞品对比和未来规划', emoji: '🚀' },
  { label: '教学课件', prompt: '帮我制作一份教学课件 PPT，主题是', emoji: '📚' },
  { label: '项目汇报', prompt: '帮我制作一份项目进展汇报 PPT，包含项目目标、当前进度、风险与问题、下一步计划', emoji: '📋' },
];

// ── Pipeline 阶段大卡（欢迎页用） ──

const PIPELINE_STAGES_DISPLAY = [
  { icon: SearchIcon, title: '素材研究', subtitle: 'Research Pack', gradient: 'from-amber-500/15 to-orange-500/10', accent: 'text-amber-600 dark:text-amber-400', ring: 'ring-amber-500/20' },
  { icon: BookOpen,   title: '叙事编排', subtitle: 'Storyboard',    gradient: 'from-sky-500/15 to-blue-500/10',     accent: 'text-sky-600 dark:text-sky-400',     ring: 'ring-sky-500/20' },
  { icon: Palette,    title: '风格定义', subtitle: 'Style Spec',    gradient: 'from-violet-500/15 to-purple-500/10', accent: 'text-violet-600 dark:text-violet-400', ring: 'ring-violet-500/20' },
  { icon: Layers,     title: '资源规划', subtitle: 'Asset Plan',    gradient: 'from-emerald-500/15 to-teal-500/10',  accent: 'text-emerald-600 dark:text-emerald-400', ring: 'ring-emerald-500/20' },
  { icon: FileText,   title: '页面生成', subtitle: 'Page HTML',     gradient: 'from-rose-500/15 to-pink-500/10',     accent: 'text-rose-600 dark:text-rose-400',     ring: 'ring-rose-500/20' },
];

function PipelineVisualHero() {
  return (
    <div className="flex items-center gap-2 overflow-x-auto px-1 py-2 scrollbar-none">
      {PIPELINE_STAGES_DISPLAY.map((stage, idx) => {
        const Icon = stage.icon;
        return (
          <div key={stage.subtitle} className="flex items-center gap-2 shrink-0">
            <div className={cn('flex items-center gap-3 rounded-xl bg-gradient-to-br px-4 py-3 ring-1 transition-all duration-200 hover:scale-[1.03] hover:shadow-md cursor-default', stage.gradient, stage.ring)}>
              <div className={cn('shrink-0', stage.accent)}>
                <Icon className="w-4 h-4" />
              </div>
              <div className="min-w-0">
                <div className="text-xs font-semibold text-foreground/90 leading-tight">{stage.title}</div>
                <div className="text-[10px] text-muted-foreground/70 leading-tight mt-0.5">{stage.subtitle}</div>
              </div>
            </div>
            {idx < PIPELINE_STAGES_DISPLAY.length - 1 && (
              <ArrowRight className="w-3.5 h-3.5 text-muted-foreground/30 shrink-0" />
            )}
          </div>
        );
      })}
    </div>
  );
}

// ── 左栏 Tab 定义 ──

type LeftTab = 'outline' | 'style' | 'review' | 'notes';

const LEFT_TABS: { id: LeftTab; label: string; icon: React.ElementType }[] = [
  { id: 'outline', label: '大纲',   icon: Layers },
  { id: 'style',   label: '风格',   icon: Palette },
  { id: 'review',  label: '审查',   icon: ShieldCheck },
  { id: 'notes',   label: '讲稿',   icon: Mic },
];

// ── PPTX 文件预览 ──

interface DroppedFile { name: string; path: string; }

function PptxPreview({ file, onClose }: { file: DroppedFile; onClose: () => void }) {
  const downloadUrl = `${API_BASE}/api/files/download?path=${encodeURIComponent(file.path)}`;
  return (
    <div className="flex-1 flex flex-col items-center justify-center gap-6 p-8">
      <div className="w-24 h-24 rounded-3xl bg-primary/10 flex items-center justify-center">
        <Presentation className="w-12 h-12 text-primary/60" />
      </div>
      <div className="text-center">
        <h3 className="text-lg font-semibold text-foreground mb-1">{file.name}</h3>
        <p className="text-sm text-muted-foreground">PPTX 文件需要下载后用本地应用打开</p>
      </div>
      <div className="flex items-center gap-3">
        <Button asChild><a href={downloadUrl} target="_blank" rel="noopener noreferrer"><FileDown className="w-4 h-4 mr-2" />下载文件</a></Button>
        <Button variant="outline" onClick={onClose}>关闭</Button>
      </div>
    </div>
  );
}

// ── 主工作区 ──

function PPTWorkspace() {
  const {
    messages,
    sendMessage,
    currentSessionId,
    sessions,
    switchSession,
    createSession,
    deleteSession,
    startNewChat,
    loadingSessions,
  } = useChatSession();

  // ppt-agent 相关的会话列表
  const pptSessions = sessions
    .filter(s => getAgentId(s.meta) === 'ppt-agent')
    .sort((a, b) => b.last_active - a.last_active);

  // 页面加载时自动切换到最近的 ppt-agent 会话
  const initDone = useRef(false);
  useEffect(() => {
    if (initDone.current || loadingSessions) return;
    initDone.current = true;

    // 当前已在 ppt-agent 会话中，保持不动
    if (currentSessionId) {
      const cur = sessions.find(s => s.session_id === currentSessionId);
      if (cur && getAgentId(cur.meta) === 'ppt-agent') return;
    }

    // 自动切换到最近的 ppt-agent 会话
    if (pptSessions.length > 0) {
      switchSession(pptSessions[0].session_id);
    }
  }, [loadingSessions, currentSessionId, sessions, pptSessions, switchSession]);

  const deckData = useDeckData(messages);
  const [activePage, setActivePage] = useState(1);
  const [leftTab, setLeftTab] = useState<LeftTab>('outline');
  const [previewPptx, setPreviewPptx] = useState<DroppedFile | null>(null);
  const [loadingDrop, setLoadingDrop] = useState(false);
  const [showWelcome, setShowWelcome] = useState(true);
  const dropContainerRef = useRef<HTMLDivElement>(null);

  // 当有 deck 数据时切换到工作区模式
  useEffect(() => {
    if (deckData.deckDir || (messages.length > 0 && messages.some(m => m.role === 'assistant'))) {
      setShowWelcome(false);
    }
  }, [deckData.deckDir, messages]);

  // 同步活动页到 SlideViewer
  const handlePageSelect = useCallback((pageNumber: number) => {
    setActivePage(pageNumber);
  }, []);

  // 修复问题：发送指令给 AI
  const handleFixIssue = useCallback((issue: PageIssue) => {
    const instruction = `请修复第 ${issue.page_number} 页的问题：${issue.description}`;
    sendMessage(instruction, [], 'ppt-agent');
  }, [sendMessage]);

  // 风格优化
  const handleStyleRefine = useCallback((instruction: string) => {
    sendMessage(instruction, [], 'ppt-agent');
    setLeftTab('outline');
  }, [sendMessage]);

  // 模板选择
  const handleTemplateSelect = useCallback((template: TemplateItem) => {
    const prompt = `帮我制作一份 PPT，使用「${template.name}」风格模板。${template.description}`;
    sendMessage(prompt, [], 'ppt-agent');
    setShowWelcome(false);
  }, [sendMessage]);

  // 拖拽接收
  const handleDrop = useCallback(async (item: DroppedFile) => {
    if (/\.pptx?$/i.test(item.name)) {
      setPreviewPptx(item);
      return;
    }
    setLoadingDrop(true);
    try {
      const res = await authFetch(`${API_BASE}/api/files/dir-token?path=${encodeURIComponent(item.path)}`);
      if (!res.ok) return;
      const data = await res.json();
      if (data.slides?.length > 0) {
        setPreviewPptx(null);
      }
    } catch { /* 静默 */ }
    finally { setLoadingDrop(false); }
  }, []);

  const [{ isOver, canDrop }, dropRef] = useDrop(
    () => ({
      accept: 'FILE',
      drop: (item: DroppedFile, monitor) => { if (!monitor.didDrop()) handleDrop(item); },
      collect: (monitor) => ({ isOver: monitor.isOver({ shallow: true }), canDrop: monitor.canDrop() }),
    }),
    [handleDrop],
  );

  const setRef = useCallback(
    (node: HTMLDivElement | null) => {
      (dropRef as unknown as (el: HTMLDivElement | null) => void)(node);
      (dropContainerRef as React.MutableRefObject<HTMLDivElement | null>).current = node;
    },
    [dropRef],
  );

  const hasDeck = !!deckData.slideSet || !!deckData.storyboard;
  const stages = hasDeck ? deckData.stages : DEFAULT_STAGES;

  // ── 欢迎状态（首次创建） ──
  if (showWelcome && !currentSessionId) {
    return (
      <div ref={setRef} className="flex flex-col h-full">
        {/* 欢迎页 Hero */}
        <div className="flex-1 flex flex-col items-center justify-center px-6 py-10 overflow-auto">
          <div className="text-center mb-8">
            <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-primary/8 text-primary text-xs font-medium mb-4">
              <Wand2 className="w-3.5 h-3.5" />
              AI 驱动的演示文稿工作流
            </div>
            <h2 className="text-2xl font-bold text-foreground tracking-tight mb-2">创建专业演示文稿</h2>
            <p className="text-sm text-muted-foreground max-w-lg mx-auto leading-relaxed">
              描述你的需求，AI 将自动完成研究、编排、设计到页面生成的完整流水线
            </p>
          </div>
          <div className="w-full max-w-3xl mb-8"><PipelineVisualHero /></div>
          <div className="w-full max-w-2xl mb-8">
            <div className="text-xs font-semibold text-muted-foreground/70 uppercase tracking-wider mb-3 px-1">快速开始</div>
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
              {QUICK_TEMPLATES.map(tpl => (
                <button key={tpl.label} onClick={() => { sendMessage(tpl.prompt, [], 'ppt-agent'); setShowWelcome(false); }}
                  className="flex items-center gap-2.5 px-4 py-3 rounded-xl text-left transition-all duration-200 border border-border/50 hover:border-primary/30 hover:bg-primary/5 hover:shadow-sm group cursor-pointer">
                  <span className="text-lg shrink-0">{tpl.emoji}</span>
                  <span className="text-sm font-medium text-foreground/80 group-hover:text-foreground transition-colors">{tpl.label}</span>
                </button>
              ))}
            </div>
          </div>
          {/* 拖拽区 */}
          <div className={cn(
            'w-full max-w-md rounded-2xl border-2 border-dashed px-8 py-6 text-center transition-all duration-300',
            isOver && canDrop ? 'border-primary bg-primary/5 scale-[1.02]' : 'border-border/40 hover:border-border/60',
          )}>
            {loadingDrop ? (
              <p className="text-sm text-muted-foreground">加载中...</p>
            ) : isOver && canDrop ? (
              <><Upload className="w-8 h-8 text-primary/60 mx-auto mb-2" /><p className="text-sm font-medium text-primary/80">释放以预览</p></>
            ) : (
              <><Sparkles className="w-6 h-6 text-muted-foreground/30 mx-auto mb-2" /><p className="text-xs text-muted-foreground/60">或从文件面板拖入 HTML 文件夹 / PPTX 文件预览</p></>
            )}
          </div>
        </div>
        {/* 底栏模板条 */}
        <div className="shrink-0 border-t border-border/40 bg-muted/10">
          <TemplateStrip onSelect={handleTemplateSelect} />
        </div>
      </div>
    );
  }

  // ── 工作台模式（三栏布局） ──
  return (
    <div ref={setRef} className="flex flex-col h-full overflow-hidden">
      {/* ── 顶栏：进度 + 导出 ── */}
      <div className="flex items-center gap-3 px-4 py-2 border-b border-border/40 shrink-0 bg-background/80 backdrop-blur-sm">
        <div className="flex items-center gap-2 min-w-0 shrink-0">
          <Presentation className="w-4 h-4 text-primary shrink-0" />
          <span className="text-sm font-semibold text-foreground truncate max-w-[200px]">
            {deckData.storyboard?.ppt_title || 'PPT 工作台'}
          </span>
        </div>

        <div className="flex-1 min-w-0 overflow-hidden">
          <PipelineProgress stages={stages} compact={false} />
        </div>

        <div className="flex items-center gap-1.5 shrink-0">
          <Button
            variant="ghost" size="icon-sm"
            onClick={deckData.refresh}
            disabled={deckData.loading}
            className="text-muted-foreground"
          >
            <RefreshCw className={cn('w-3.5 h-3.5', deckData.loading && 'animate-spin')} />
          </Button>
          <ExportDropdown
            deckDir={deckData.deckDir}
            hasSpeakerNotes={!!deckData.speakerNotes}
          />
        </div>
      </div>

      {/* ── 三栏主体 ── */}
      <ResizablePanelGroup orientation="horizontal" className="flex-1 overflow-hidden">

        {/* 左栏：大纲 / 风格 / 审查 / 讲稿 */}
        <ResizablePanel id="ppt-left" defaultSize="22%" minSize="14%" maxSize="35%" className="overflow-hidden border-r border-border/40">
          <div className="flex flex-col h-full">
            {/* Tab 切换栏 */}
            <div className="flex items-center border-b border-border/40 shrink-0 px-0.5">
              {LEFT_TABS.map(tab => {
                const Icon = tab.icon;
                const isActive = leftTab === tab.id;
                const hasBadge =
                  (tab.id === 'style' && !!deckData.styleSpec) ||
                  (tab.id === 'review' && !!deckData.review) ||
                  (tab.id === 'notes' && !!deckData.speakerNotes);

                return (
                  <button
                    key={tab.id}
                    type="button"
                    onClick={() => setLeftTab(tab.id)}
                    className={cn(
                      'flex items-center gap-1 px-2.5 py-2 text-[11px] font-medium transition-all relative',
                      isActive
                        ? 'text-primary border-b-2 border-primary'
                        : 'text-muted-foreground/60 hover:text-foreground border-b-2 border-transparent',
                    )}
                  >
                    <Icon className="w-3 h-3" />
                    {tab.label}
                    {hasBadge && !isActive && (
                      <span className="w-1.5 h-1.5 rounded-full bg-primary absolute top-1.5 right-0.5" />
                    )}
                  </button>
                );
              })}
            </div>

            {/* Tab 内容 */}
            <div className="flex-1 overflow-hidden">
              {leftTab === 'outline' && (
                <StoryboardPanel
                  storyboard={deckData.storyboard}
                  activePage={activePage}
                  onPageSelect={handlePageSelect}
                />
              )}
              {leftTab === 'style' && (
                <StylePanel
                  styleSpec={deckData.styleSpec}
                  onRefineRequest={handleStyleRefine}
                />
              )}
              {leftTab === 'review' && (
                <ReviewPanel
                  review={deckData.review}
                  onFixIssue={handleFixIssue}
                />
              )}
              {leftTab === 'notes' && (
                <SpeakerNotesPanel
                  notes={deckData.speakerNotes}
                  activePage={activePage}
                  onPageSelect={handlePageSelect}
                />
              )}
            </div>
          </div>
        </ResizablePanel>

        <ResizableHandle invisible />

        {/* 中栏：幻灯片主舞台 */}
        <ResizablePanel id="ppt-stage" defaultSize="46%" minSize="25%" className="overflow-hidden relative">
          <div className="flex flex-col h-full">
            {previewPptx ? (
              <PptxPreview file={previewPptx} onClose={() => setPreviewPptx(null)} />
            ) : deckData.slideSet ? (
              <SlideViewer slideSet={deckData.slideSet} />
            ) : (
              <div className="flex-1 flex flex-col items-center justify-center p-8">
                <div className="w-20 h-20 rounded-2xl bg-primary/5 border-2 border-dashed border-primary/20 flex items-center justify-center mb-4">
                  <Presentation className="w-10 h-10 text-primary/20" />
                </div>
                <p className="text-sm font-medium text-foreground/50 mb-1">幻灯片预览区</p>
                <p className="text-xs text-muted-foreground/40 text-center max-w-xs">
                  {deckData.storyboard
                    ? '大纲已生成，页面正在制作中...'
                    : '在右侧对话中描述你的 PPT 需求，AI 将逐步生成'}
                </p>
                {deckData.loading && (
                  <Loader2 className="w-5 h-5 text-primary/40 animate-spin mt-4" />
                )}
              </div>
            )}

            {/* 拖拽覆盖层 */}
            {isOver && canDrop && (
              <div className="absolute inset-0 z-30 bg-primary/5 border-2 border-dashed border-primary rounded-lg flex items-center justify-center pointer-events-none">
                <div className="text-center">
                  <Upload className="w-10 h-10 text-primary mx-auto mb-2" />
                  <p className="text-primary font-medium text-sm">释放以预览</p>
                </div>
              </div>
            )}
          </div>
        </ResizablePanel>

        <ResizableHandle invisible />

        {/* 右栏：会话列表 + 对话面板 */}
        <ResizablePanel id="ppt-chat" defaultSize="32%" minSize="20%" maxSize="45%" className="overflow-hidden border-l border-border/40">
          <div className="flex flex-col h-full">
            {/* 紧凑会话列表头 */}
            <div className="shrink-0 border-b border-border/40">
              <div className="flex items-center justify-between px-3 py-1.5">
                <div className="flex items-center gap-1.5">
                  <MessageSquare className="w-3 h-3 text-muted-foreground/50" />
                  <span className="text-[10px] font-bold text-muted-foreground/70 uppercase tracking-wider">
                    PPT 对话
                  </span>
                  {pptSessions.length > 0 && (
                    <span className="text-[10px] text-muted-foreground/40">{pptSessions.length}</span>
                  )}
                </div>
                <button
                  type="button"
                  onClick={() => { startNewChat(); createSession('ppt-agent'); }}
                  className="flex items-center gap-0.5 px-1.5 py-0.5 rounded text-[10px] font-medium text-primary hover:bg-primary/10 transition-colors"
                >
                  <Plus className="w-3 h-3" />
                  新建
                </button>
              </div>
              {/* 会话列表（可滚动，最多显示几条） */}
              {pptSessions.length > 0 && (
                <div className="max-h-[120px] overflow-y-auto px-1.5 pb-1.5 space-y-0.5 scrollbar-thin">
                  {pptSessions.map(session => {
                    const isActive = currentSessionId === session.session_id;
                    const title = getTitle(session.meta);
                    return (
                      <button
                        key={session.session_id}
                        type="button"
                        onClick={() => switchSession(session.session_id)}
                        className={cn(
                          'w-full flex items-center gap-2 px-2 py-1.5 rounded-lg text-left transition-all text-[11px] group',
                          isActive
                            ? 'bg-primary/10 text-foreground'
                            : 'text-muted-foreground/70 hover:bg-muted/40 hover:text-foreground',
                        )}
                      >
                        <MessageSquare className={cn('w-3 h-3 shrink-0', isActive ? 'text-primary' : 'text-muted-foreground/40')} />
                        <span className="flex-1 truncate font-medium">{title}</span>
                        <span className="text-[9px] text-muted-foreground/40 shrink-0">{timeLabel(session.last_active)}</span>
                        <button
                          type="button"
                          onClick={(e) => { e.stopPropagation(); deleteSession(session.session_id); }}
                          className="shrink-0 p-0.5 rounded opacity-0 group-hover:opacity-100 text-muted-foreground/40 hover:text-destructive transition-all"
                        >
                          <Trash2 className="w-2.5 h-2.5" />
                        </button>
                      </button>
                    );
                  })}
                </div>
              )}
            </div>
            {/* 对话面板 */}
            <div className="flex-1 overflow-hidden">
              <ChatPanel
                defaultAgentId="ppt-agent"
                lockAgent
                hideAgentSelector
              />
            </div>
          </div>
        </ResizablePanel>
      </ResizablePanelGroup>

      {/* ── 底栏：模板条（有 deck 时不显示） ── */}
      {!hasDeck && (
        <div className="shrink-0 border-t border-border/40 bg-muted/10">
          <TemplateStrip onSelect={handleTemplateSelect} />
        </div>
      )}
    </div>
  );
}

// ── 页面入口 ──

export default function PPTPage() {
  return (
    <DashboardLayout>
      <Suspense fallback={
        <div className="flex items-center justify-center h-full">
          <Loader2 className="animate-spin text-muted-foreground" size={32} />
        </div>
      }>
        <PPTWorkspace />
      </Suspense>
    </DashboardLayout>
  );
}
