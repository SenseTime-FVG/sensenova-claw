'use client';

import { forwardRef, useCallback, useEffect, useImperativeHandle, useRef, useState } from 'react';
import { Bot, ChevronLeft } from 'lucide-react';
import { useChatSession, type RecommendationSendMeta } from '@/contexts/ChatSessionContext';
import { useFilePanel } from '@/contexts/FilePanelContext';
import { MessageList } from './MessageBubble';
import { TypingIndicator } from './TypingIndicator';
import { ChatInput, type ChatInputHandle } from './ChatInput';
import { SlideViewer, useSlideSet } from '@/components/ppt/PPTViewer';
import { FilePreview } from '@/components/files/FilePreview';
import type { FilePreviewType } from '@/components/files/fileTypes';
import { type ContextFileRef, getAgentId } from '@/lib/chatTypes';
import { authFetch, API_BASE } from '@/lib/authFetch';

/* ── workdir 根目录缓存 ── */
let _workdirRootCache: string | null | undefined;
async function fetchWorkdirRoot(): Promise<string | null> {
  if (_workdirRootCache !== undefined) return _workdirRootCache as string | null;
  let result: string | null = null;
  try {
    const res = await authFetch(`${API_BASE}/api/files/roots`);
    if (res.ok) {
      const data = await res.json();
      const entry = (data.roots || []).find((r: { name: string }) => r.name === 'Agent 工作区');
      result = entry?.path ?? null;
    }
  } catch { /* ignore */ }
  _workdirRootCache = result;
  return result;
}

interface ChatPanelProps {
  defaultAgentId: string;
  emptyState?: React.ReactNode | ((helpers: { fillInput: (text: string) => void; selectAgent: (agentId: string) => void }) => React.ReactNode);
  hideAgentSelector?: boolean;
  lockAgent?: boolean;
  /**
   * 工作台类页面：从左侧「最近对话」进入会话后，在对话区左上角显示返回按钮，
   * 点击后清空当前会话并恢复本页的 emptyState（主视图）。
   */
  returnToMainLabel?: string;
}

export interface ChatPanelHandle {
  fillInput: (text: string) => void;
}

export const ChatPanel = forwardRef<ChatPanelHandle, ChatPanelProps>(function ChatPanel({ defaultAgentId, emptyState, hideAgentSelector, lockAgent, returnToMainLabel }, ref) {
  const {
    wsConnected,
    currentSessionId,
    sessions,
    messages,
    isTyping,
    sendMessage,
    resetIfNeeded,
    startNewChat,
    handleSkillInvoke,
    cancelTurn,
    wsSend,
  } = useChatSession();

  const { openToPath } = useFilePanel();
  const [selectedAgent, setSelectedAgent] = useState(defaultAgentId);
  const [slidePreviewDir, setSlidePreviewDir] = useState<string | null>(null);
  const [filePreview, setFilePreview] = useState<{ path: string; type: FilePreviewType } | null>(null);
  const [previewHeight, setPreviewHeight] = useState(350);
  const chatEndRef = useRef<HTMLDivElement>(null);
  const chatInputRef = useRef<ChatInputHandle>(null);

  const slideSet = useSlideSet(slidePreviewDir);

  const onPreviewResize = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    const startY = e.clientY;
    const startH = previewHeight;
    const onMove = (ev: MouseEvent) => {
      const delta = startY - ev.clientY;
      setPreviewHeight(Math.max(180, Math.min(window.innerHeight * 0.8, startH + delta)));
    };
    const onUp = () => {
      document.removeEventListener('mousemove', onMove);
      document.removeEventListener('mouseup', onUp);
    };
    document.addEventListener('mousemove', onMove);
    document.addEventListener('mouseup', onUp);
  }, [previewHeight]);

  // 页面挂载时：通过 switchSession 跳转过来则保留会话，否则重置为干净状态
  useEffect(() => {
    resetIfNeeded();
    setSelectedAgent(defaultAgentId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // 当切换 session 时，从 session meta 中提取 agent_id 并设置为当前选中的 agent
  useEffect(() => {
    if (currentSessionId) {
      const currentSession = sessions.find(s => s.session_id === currentSessionId);
      if (currentSession) {
        const agentId = getAgentId(currentSession.meta);
        if (agentId) {
          setSelectedAgent(agentId);
        }
      }
    }
  }, [currentSessionId, sessions]);

  // 自动滚动到底部
  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isTyping]);

  // 监听消息中目录/幻灯片链接点击 → 内联预览 + 文件面板定位
  useEffect(() => {
    const handler = (e: Event) => {
      const detail = (e as CustomEvent).detail as { dir: string; isAbsolute: boolean };
      let resolvedDir: string;

      if (detail.isAbsolute) {
        resolvedDir = detail.dir;
      } else {
        const curSession = sessions.find(s => s.session_id === currentSessionId);
        const agentId = (curSession ? getAgentId(curSession.meta) : null) || defaultAgentId || 'default';
        const firstSegment = detail.dir.split('/')[0];
        resolvedDir = firstSegment === agentId ? detail.dir : `${agentId}/${detail.dir}`;

        fetchWorkdirRoot().then(root => {
          if (root) {
            const sep = root.includes('\\') ? '\\' : '/';
            const fullPath = [root, resolvedDir.replace(/\//g, sep)].join(sep);
            openToPath(fullPath);
          }
        });
      }

      setSlidePreviewDir(resolvedDir);
      setFilePreview(null); // 互斥：关闭文件预览
      setTimeout(() => chatEndRef.current?.scrollIntoView({ behavior: 'smooth' }), 100);
    };

    window.addEventListener('sensenova-claw:open-slide-preview', handler);
    return () => window.removeEventListener('sensenova-claw:open-slide-preview', handler);
  }, [defaultAgentId, currentSessionId, sessions, openToPath]);

  // 切换会话时关闭预览
  useEffect(() => {
    setSlidePreviewDir(null);
    setFilePreview(null);
  }, [currentSessionId]);

  // 监听文件预览事件
  useEffect(() => {
    const handler = (e: Event) => {
      const detail = (e as CustomEvent).detail as { path: string; type: FilePreviewType };
      setFilePreview(detail);
      setSlidePreviewDir(null); // 互斥：关闭 PPT 预览
      setTimeout(() => chatEndRef.current?.scrollIntoView({ behavior: 'smooth' }), 100);
    };
    window.addEventListener('sensenova-claw:open-file-preview', handler);
    return () => window.removeEventListener('sensenova-claw:open-file-preview', handler);
  }, []);

  const handleSend = useCallback((
    content: string,
    contextFiles?: ContextFileRef[],
    recommendation?: RecommendationSendMeta | null,
  ) => {
    sendMessage(content, contextFiles, selectedAgent, recommendation);
  }, [sendMessage, selectedAgent]);

  // 斜杠命令处理（不在 ChatInput 层处理的额外逻辑）
  const handleSlashSubmit = useCallback((_content: string) => {
    return false; // ChatInput 内部已处理
  }, []);

  const fillInput = useCallback((text: string) => {
    chatInputRef.current?.setInput(text);
  }, []);

  useImperativeHandle(ref, () => ({ fillInput }), [fillInput]);

  const defaultEmptyState = (
    <div className="flex flex-col items-center justify-center h-full gap-5 text-muted-foreground max-w-md mx-auto text-center">
      <div className="w-16 h-16 rounded-2xl bg-primary/10 flex items-center justify-center text-primary mb-2 shadow-sm">
        <Bot size={32} />
      </div>
      <h3 className="text-2xl font-bold text-foreground tracking-tight">How can I help you today?</h3>
      <p className="text-sm leading-relaxed">Type a message below to start a new conversation with Sensenova-Claw.</p>
    </div>
  );

  const resolvedEmptyState = typeof emptyState === 'function' ? emptyState({ fillInput, selectAgent: setSelectedAgent }) : (emptyState || defaultEmptyState);

  const showReturnToMain =
    Boolean(returnToMainLabel) && (Boolean(currentSessionId) || messages.length > 0);

  return (
    <div className="flex flex-col h-full min-w-0">
      {showReturnToMain && (
        <div className="shrink-0 flex items-center gap-1 px-3 py-2 border-b border-border/60 bg-muted/30">
          <button
            type="button"
            onClick={() => startNewChat()}
            className="inline-flex items-center gap-1.5 rounded-lg px-2 py-1.5 text-sm font-medium text-muted-foreground hover:text-foreground hover:bg-muted/80 transition-colors"
          >
            <ChevronLeft className="w-4 h-4 shrink-0" />
            <span>{returnToMainLabel}</span>
          </button>
        </div>
      )}
      {/* 消息区域 */}
      <div className="flex-1 overflow-y-auto p-4 md:p-8 min-h-0">
        {messages.length === 0 && !currentSessionId ? (
          resolvedEmptyState
        ) : (
          <>
            <MessageList messages={messages} />
            {isTyping && <TypingIndicator />}
            <div ref={chatEndRef} />
          </>
        )}
      </div>

      {/* PPT 幻灯片内联预览（可拖拽调整高度） */}
      {slideSet && (
        <div className="shrink-0 flex flex-col" style={{ height: previewHeight }}>
          <div
            className="flex items-center justify-center h-2 cursor-ns-resize hover:bg-primary/20 transition-colors group border-t border-border/60"
            onMouseDown={onPreviewResize}
          >
            <div className="w-8 h-0.5 rounded-full bg-border group-hover:bg-primary/50 transition-colors" />
          </div>
          <SlideViewer slideSet={slideSet} onClose={() => setSlidePreviewDir(null)} />
        </div>
      )}

      {/* 文件内联预览（可拖拽调整高度） */}
      {filePreview && !slideSet && (
        <div className="shrink-0 flex flex-col" style={{ height: previewHeight }}>
          <div
            className="flex items-center justify-center h-2 cursor-ns-resize hover:bg-primary/20 transition-colors group border-t border-border/60"
            onMouseDown={onPreviewResize}
          >
            <div className="w-8 h-0.5 rounded-full bg-border group-hover:bg-primary/50 transition-colors" />
          </div>
          <FilePreview
            path={filePreview.path}
            type={filePreview.type}
            onClose={() => setFilePreview(null)}
          />
        </div>
      )}

      {/* 底部输入区 */}
      <ChatInput
        ref={chatInputRef}
        defaultAgentId={defaultAgentId}
        selectedAgent={selectedAgent}
        onSelectAgent={setSelectedAgent}
        onSend={handleSend}
        onSlashSubmit={handleSlashSubmit}
        onStop={cancelTurn}
        disabled={isTyping}
        wsConnected={wsConnected}
        handleSkillInvoke={handleSkillInvoke}
        hideAgentSelector={hideAgentSelector}
        lockAgent={lockAgent}
      />

    </div>
  );
});
