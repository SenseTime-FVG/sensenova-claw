'use client';

import dynamic from 'next/dynamic';
import { type FilePreviewType } from '@/components/files/fileTypes';

const SlideViewer = dynamic(() => import('@/components/ppt/PPTViewer').then(mod => mod.SlideViewer), {
  loading: () => <div className="h-full flex items-center justify-center bg-muted/20">Loading Presentation...</div>,
  ssr: false,
});

const FilePreview = dynamic(() => import('@/components/files/FilePreview').then(mod => mod.FilePreview), {
  loading: () => <div className="h-full flex items-center justify-center bg-muted/20">Loading File...</div>,
  ssr: false,
});

interface InlinePreviewProps {
  previewHeight: number;
  onPreviewResize: (e: React.MouseEvent) => void;
  slideSet: any;
  onCloseSlides: () => void;
  filePreview: { path: string; type: FilePreviewType } | null;
  onCloseFile: () => void;
}

export function InlinePreview({
  previewHeight,
  onPreviewResize,
  slideSet,
  onCloseSlides,
  filePreview,
  onCloseFile,
}: InlinePreviewProps) {
  if (!slideSet && !filePreview) return null;

  return (
    <div className="shrink-0 flex flex-col" style={{ height: previewHeight }}>
      <div
        className="flex items-center justify-center h-2 cursor-ns-resize hover:bg-primary/20 transition-colors group border-t border-border/60"
        onMouseDown={onPreviewResize}
      >
        <div className="w-8 h-0.5 rounded-full bg-border group-hover:bg-primary/50 transition-colors" />
      </div>
      
      {slideSet && (
        <SlideViewer slideSet={slideSet} onClose={onCloseSlides} />
      )}
      
      {filePreview && !slideSet && (
        <FilePreview
          path={filePreview.path}
          type={filePreview.type}
          onClose={onCloseFile}
        />
      )}
    </div>
  );
}
