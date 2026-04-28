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
import { ChatPanel, type ChatPanelHandle } from '@/components/chat/ChatPanel';
import { SlideViewer } from '@/components/ppt/PPTViewer';
import { PipelineProgress, DEFAULT_STAGES } from '@/components/ppt/PipelineProgress';
import { StoryboardPanel } from '@/components/ppt/StoryboardPanel';
import { StylePanel } from '@/components/ppt/StylePanel';
import { ReviewPanel, type PageIssue } from '@/components/ppt/ReviewPanel';
import { SpeakerNotesPanel } from '@/components/ppt/SpeakerNotesPanel';
import { AssetPanel } from '@/components/ppt/AssetPanel';
import { ExportDropdown } from '@/components/ppt/ExportDropdown';
import { TemplateStrip, type TemplateItem } from '@/components/ppt/TemplateSelector';
import { useDeckData } from '@/hooks/useDeckData';
import { useChatSession } from '@/contexts/ChatSessionContext';
import { Button } from '@/components/ui/button';
import {
  Presentation, Upload, FileDown,
  Palette, ShieldCheck, Mic, Image as ImageIcon,
  Layers, Loader2,
  RefreshCw, Plus, MessageSquare, Trash2,
  ArrowLeft,
} from 'lucide-react';
import { useRouter } from 'next/navigation';
import { cn } from '@/lib/utils';
import { authFetch, API_BASE } from '@/lib/authFetch';
import { ResizablePanelGroup, ResizablePanel, ResizableHandle } from '@/components/ui/resizable';
import { type SessionItem, getAgentId, getTitle, timeLabel } from '@/lib/chatTypes';
import { SessionContextMenu } from '@/components/session/SessionContextMenu';
import { InlineSessionTitleEditor } from '@/components/session/InlineSessionTitleEditor';

// ── 左栏 Tab 定义 ──

type LeftTab = 'outline' | 'style' | 'assets' | 'review' | 'notes';

const LEFT_TABS: { id: LeftTab; label: string; icon: React.ElementType }[] = [
  { id: 'outline', label: '大纲',   icon: Layers },
  { id: 'style',   label: '风格',   icon: Palette },
  { id: 'assets',  label: '资产',   icon: ImageIcon },
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
  const router = useRouter();
  const {
    messages,
    sendMessage,
    currentSessionId,
    sessions,
    switchSession,
    createSession,
    deleteSession,
    renameSession,
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

  // 当外部切换到非 ppt-agent 会话时，自动回退到 ppt-agent 会话或空白态
  useEffect(() => {
    if (!currentSessionId || loadingSessions) return;
    const cur = sessions.find(s => s.session_id === currentSessionId);
    if (cur && getAgentId(cur.meta) !== 'ppt-agent') {
      if (pptSessions.length > 0) {
        switchSession(pptSessions[0].session_id);
      } else {
        startNewChat();
      }
    }
  }, [currentSessionId, sessions, pptSessions, loadingSessions, switchSession, startNewChat]);

  const deckData = useDeckData(messages);
  const [activePage, setActivePage] = useState(1);
  const [leftTab, setLeftTab] = useState<LeftTab>('outline');
  const [previewPptx, setPreviewPptx] = useState<DroppedFile | null>(null);
  const [loadingDrop, setLoadingDrop] = useState(false);
  const [panelSizes, setPanelSizes] = useState({ left: 22, stage: 46, chat: 32, sessions: 20 });
  const [contextMenu, setContextMenu] = useState<{ session: SessionItem; x: number; y: number } | null>(null);
  const [editingSessionId, setEditingSessionId] = useState<string | null>(null);
  const [renameValue, setRenameValue] = useState('');
  const [exportingHtmlZip, setExportingHtmlZip] = useState(false);
  const dropContainerRef = useRef<HTMLDivElement>(null);
  const chatPanelRef = useRef<ChatPanelHandle>(null);

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

  // 模板选择：填充到输入框，由用户自行发送
  const handleTemplateSelect = useCallback((template: TemplateItem) => {
    const prompt = `帮我制作一份 PPT，使用「${template.name}」风格模板。${template.description}`;
    chatPanelRef.current?.fillInput(prompt);
  }, []);

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

  useEffect(() => {
    const updatePanelSizes = () => {
      const width = window.innerWidth;
      if (width < 1360) {
        setPanelSizes({ left: 20, stage: 40, chat: 40, sessions: 16 });
        return;
      }
      if (width < 1680) {
        setPanelSizes({ left: 21, stage: 43, chat: 36, sessions: 18 });
        return;
      }
      setPanelSizes({ left: 22, stage: 46, chat: 32, sessions: 20 });
    };
    updatePanelSizes();
    window.addEventListener('resize', updatePanelSizes);
    return () => window.removeEventListener('resize', updatePanelSizes);
  }, []);

  const hasDeck = !!deckData.slideSet || !!deckData.storyboard;
  const stages = hasDeck ? deckData.stages : DEFAULT_STAGES;

  const startRename = () => {
    if (!contextMenu) return;
    setEditingSessionId(contextMenu.session.session_id);
    setRenameValue(getTitle(contextMenu.session.meta));
  };

  const cancelRename = () => {
    setEditingSessionId(null);
    setRenameValue('');
  };

  const submitRename = async () => {
    if (!editingSessionId) return;
    const success = await renameSession(editingSessionId, renameValue);
    if (success) {
      cancelRename();
    }
  };

  const handleExport = useCallback(async (format: string, _withNotes: boolean) => {
    if (format !== 'html-zip' || !deckData.deckDir || exportingHtmlZip) return;

    setExportingHtmlZip(true);
    try {
      const res = await authFetch(
        `${API_BASE}/api/files/workdir-archive?dir=${encodeURIComponent(deckData.deckDir)}`,
      );
      if (!res.ok) return;

      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const fileName = `${deckData.deckDir.split('/').pop() || 'deck'}.zip`;
      const link = document.createElement('a');
      link.href = url;
      link.download = fileName;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
    } finally {
      setExportingHtmlZip(false);
    }
  }, [deckData.deckDir, exportingHtmlZip]);

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
            onExport={handleExport}
            hasSpeakerNotes={!!deckData.speakerNotes}
          />
        </div>
      </div>

      {/* ── 三栏主体 ── */}
      <ResizablePanelGroup orientation="horizontal" className="flex-1 overflow-hidden">

        {/* 左栏：大纲 / 风格 / 审查 / 讲稿 */}
        <ResizablePanel id="ppt-left" defaultSize={`${panelSizes.left}%`} minSize="14%" maxSize="35%" className="overflow-hidden border-r border-border/40">
          <div className="flex flex-col h-full">
            {/* Tab 切换栏 */}
            <div className="flex items-center border-b border-border/40 shrink-0 px-0.5">
              {LEFT_TABS.map(tab => {
                const Icon = tab.icon;
                const isActive = leftTab === tab.id;
                const hasBadge =
                  (tab.id === 'style' && !!deckData.styleSpec) ||
                  (tab.id === 'assets' && !!deckData.assetPlan) ||
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
              {leftTab === 'assets' && (
                <AssetPanel
                  assetPlan={deckData.assetPlan}
                  deckDir={deckData.deckDir}
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
        <ResizablePanel id="ppt-stage" defaultSize={`${panelSizes.stage}%`} minSize="25%" className="overflow-hidden relative">
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

        {/* 右栏：会话列表 + 对话面板（上下可拖拽调整） */}
        <ResizablePanel id="ppt-chat" defaultSize={`${panelSizes.chat}%`} minSize="20%" maxSize="45%" className="overflow-hidden border-l border-border/40">
          <ResizablePanelGroup orientation="vertical" className="h-full">
            {/* 上部：会话列表（可上下拖拽边框调整高度） */}
            <ResizablePanel id="ppt-sessions" defaultSize={`${panelSizes.sessions}%`} minSize="8%" maxSize="50%" className="overflow-hidden">
              <div className="flex flex-col h-full">
                <div className="flex items-center justify-between px-3 py-1.5 shrink-0">
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
                    data-testid="ppt-new-chat-button"
                    className="flex items-center gap-0.5 px-1.5 py-0.5 rounded text-[10px] font-medium text-primary hover:bg-primary/10 transition-colors"
                  >
                    <Plus className="w-3 h-3" />
                    新建
                  </button>
                </div>
                {pptSessions.length > 0 && (
                  <div className="flex-1 overflow-y-auto px-1.5 pb-1.5 space-y-0.5 scrollbar-thin">
                    {pptSessions.map(session => {
                      const isActive = currentSessionId === session.session_id;
                      const title = getTitle(session.meta);
                      return (
                        <button
                          key={session.session_id}
                          type="button"
                          onClick={() => switchSession(session.session_id)}
                          onContextMenu={(event) => {
                            event.preventDefault();
                            event.stopPropagation();
                            setContextMenu({ session, x: event.clientX, y: event.clientY });
                          }}
                          data-testid={`ppt-session-item-${session.session_id}`}
                          className={cn(
                            'w-full flex items-center gap-2 px-2 py-1.5 rounded-lg text-left transition-all text-[11px] group',
                            isActive
                              ? 'bg-primary/10 text-foreground'
                              : 'text-muted-foreground/70 hover:bg-muted/40 hover:text-foreground',
                          )}
                        >
                          <MessageSquare className={cn('w-3 h-3 shrink-0', isActive ? 'text-primary' : 'text-muted-foreground/40')} />
                          {editingSessionId === session.session_id ? (
                            <InlineSessionTitleEditor
                              value={renameValue}
                              onChange={setRenameValue}
                              onSubmit={submitRename}
                              onCancel={cancelRename}
                              testId={`ppt-rename-input-${session.session_id}`}
                              className="flex-1 rounded border border-primary/40 bg-background px-1.5 py-0.5 text-[11px] font-medium text-foreground outline-none ring-0"
                            />
                          ) : (
                            <span className="flex-1 truncate font-medium">{title}</span>
                          )}
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
            </ResizablePanel>

            <ResizableHandle orientation="vertical" />

            {/* 下部：对话面板 */}
            <ResizablePanel id="ppt-chat-panel" defaultSize="80%" minSize="40%" className="overflow-hidden">
              <ChatPanel
                ref={chatPanelRef}
                defaultAgentId="ppt-agent"
                lockAgent
              />
            </ResizablePanel>
          </ResizablePanelGroup>
        </ResizablePanel>
      </ResizablePanelGroup>

      <SessionContextMenu
        open={!!contextMenu}
        x={contextMenu?.x ?? 0}
        y={contextMenu?.y ?? 0}
        onClose={() => setContextMenu(null)}
        onRename={startRename}
        testId="ppt-session-context-menu"
      />

      {/* ── 底栏：模板条 ── */}
      <div className="shrink-0 border-t border-border/40 bg-muted/10">
        <TemplateStrip onSelect={handleTemplateSelect} />
      </div>
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
