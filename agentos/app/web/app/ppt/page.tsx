'use client';

import { useState, useCallback, useRef } from 'react';
import { useDrop } from 'react-dnd';
import { DashboardLayout } from '@/components/layout/DashboardLayout';
import { WorkbenchShell } from '@/components/workbench/WorkbenchShell';
import { ChatPanel } from '@/components/chat/ChatPanel';
import { SlideViewer, type SlideSet } from '@/components/ppt/PPTViewer';
import { Button } from '@/components/ui/button';
import { Presentation, Upload, FileDown } from 'lucide-react';
import { cn } from '@/lib/utils';
import { authFetch, API_BASE } from '@/lib/authFetch';

interface DroppedFile {
  name: string;
  path: string;
}

// ── PPTX 文件预览（浏览器不能直接渲染 pptx，提供下载） ──

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
        <Button asChild>
          <a href={downloadUrl} target="_blank" rel="noopener noreferrer">
            <FileDown className="w-4 h-4 mr-2" />
            下载文件
          </a>
        </Button>
        <Button variant="outline" onClick={onClose}>
          关闭
        </Button>
      </div>
    </div>
  );
}

// ── PPT 工作区（含拖拽接收） ──

function PPTWorkspace() {
  const [previewSlides, setPreviewSlides] = useState<SlideSet | null>(null);
  const [previewPptx, setPreviewPptx] = useState<DroppedFile | null>(null);
  const [loadingDrop, setLoadingDrop] = useState(false);
  const dropContainerRef = useRef<HTMLDivElement>(null);

  const closePreview = useCallback(() => {
    setPreviewSlides(null);
    setPreviewPptx(null);
  }, []);

  const handleDrop = useCallback(async (item: DroppedFile) => {
    if (/\.pptx?$/i.test(item.name)) {
      setPreviewPptx(item);
      setPreviewSlides(null);
      return;
    }

    // 假定是文件夹 → 获取 token 和幻灯片列表
    setLoadingDrop(true);
    try {
      const res = await authFetch(
        `${API_BASE}/api/files/dir-token?path=${encodeURIComponent(item.path)}`,
      );
      if (!res.ok) return;
      const data = await res.json();
      if (data.slides?.length > 0) {
        setPreviewSlides({
          dir: item.name,
          slides: data.slides,
          urlPrefix: `${API_BASE}/api/files/serve/${data.token}`,
        });
        setPreviewPptx(null);
      }
    } catch {
      // 静默
    } finally {
      setLoadingDrop(false);
    }
  }, []);

  const [{ isOver, canDrop }, dropRef] = useDrop(
    () => ({
      accept: 'FILE',
      drop: (item: DroppedFile) => {
        handleDrop(item);
      },
      collect: (monitor) => ({
        isOver: monitor.isOver(),
        canDrop: monitor.canDrop(),
      }),
    }),
    [handleDrop],
  );

  // 合并 drop ref 到容器
  const setRef = useCallback(
    (node: HTMLDivElement | null) => {
      (dropRef as unknown as (el: HTMLDivElement | null) => void)(node);
      (dropContainerRef as React.MutableRefObject<HTMLDivElement | null>).current = node;
    },
    [dropRef],
  );

  const hasPreview = !!previewSlides || !!previewPptx;

  const emptyState = (
    <div className="flex-1 flex flex-col items-center justify-center p-8">
      <div
        className={cn(
          'w-24 h-24 rounded-3xl flex items-center justify-center mb-6 transition-colors',
          isOver && canDrop
            ? 'bg-primary/15 border-2 border-primary border-dashed'
            : 'bg-primary/5 border-2 border-dashed border-primary/20',
        )}
      >
        {isOver && canDrop ? (
          <Upload className="w-12 h-12 text-primary/60" />
        ) : (
          <Presentation className="w-12 h-12 text-primary/30" />
        )}
      </div>
      {loadingDrop ? (
        <p className="text-sm text-muted-foreground">加载中…</p>
      ) : isOver && canDrop ? (
        <>
          <h3 className="text-lg font-semibold text-primary/80 mb-2">释放以预览</h3>
          <p className="text-sm text-muted-foreground text-center max-w-sm">
            支持包含 HTML 幻灯片的文件夹或 PPTX 文件
          </p>
        </>
      ) : (
        <>
          <h3 className="text-lg font-semibold text-foreground/70 mb-2">创建演示文稿</h3>
          <p className="text-sm text-muted-foreground text-center max-w-sm">
            在下方输入框描述你的 PPT 需求，或从左侧文件区拖入 html 文件夹 / PPTX 文件预览、编辑
          </p>
        </>
      )}
    </div>
  );

  return (
    <div ref={setRef} className="flex flex-col h-full relative">
      {/* 拖拽经过整个区域时的全局高亮 */}
      {isOver && canDrop && hasPreview && (
        <div className="absolute inset-0 z-30 bg-primary/5 border-2 border-dashed border-primary rounded-xl flex items-center justify-center pointer-events-none">
          <div className="text-center">
            <Upload className="w-12 h-12 text-primary mx-auto mb-2" />
            <p className="text-primary font-medium">释放以替换预览</p>
          </div>
        </div>
      )}

      {/* 预览覆盖层 */}
      {hasPreview && (
        <div className="absolute inset-0 z-20 bg-background flex flex-col">
          {previewSlides && (
            <SlideViewer slideSet={previewSlides} onClose={closePreview} />
          )}
          {previewPptx && (
            <PptxPreview file={previewPptx} onClose={closePreview} />
          )}
        </div>
      )}

      <ChatPanel
        defaultAgentId="ppt-agent"
        lockAgent
        emptyState={emptyState}
      />
    </div>
  );
}

// ── 页面入口 ──

export default function PPTPage() {
  return (
    <DashboardLayout>
      <WorkbenchShell agentFilter="ppt-agent">
        <PPTWorkspace />
      </WorkbenchShell>
    </DashboardLayout>
  );
}
