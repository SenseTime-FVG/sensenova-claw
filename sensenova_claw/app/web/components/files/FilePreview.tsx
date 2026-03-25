'use client';

import { useEffect, useState } from 'react';
import { X, FileText, Image as ImageIcon, Code, FileType, AlertCircle } from 'lucide-react';
import { API_BASE, authFetch } from '@/lib/authFetch';
import { type FilePreviewType, guessLanguage } from './fileTypes';
import { MarkdownContent } from '@/components/chat/MarkdownContent';

const MAX_TEXT_SIZE = 1024 * 1024; // 1MB

interface FilePreviewProps {
  path: string;
  type: FilePreviewType;
  onClose: () => void;
}

export function FilePreview({ path, type, onClose }: FilePreviewProps) {
  const filename = path.split(/[\\/]/).pop() || path;

  return (
    <div className="flex flex-col h-full bg-background border-t border-border/60">
      {/* 标题栏 */}
      <div className="flex items-center justify-between px-3 py-2 border-b border-border/40 bg-muted/30 shrink-0">
        <div className="flex items-center gap-2 min-w-0">
          <PreviewIcon type={type} />
          <span className="text-xs font-medium truncate text-foreground/80">{filename}</span>
        </div>
        <button
          onClick={onClose}
          className="p-1 rounded-md hover:bg-muted text-muted-foreground hover:text-foreground transition-colors shrink-0"
        >
          <X className="w-4 h-4" />
        </button>
      </div>

      {/* 渲染区域 */}
      <div className="flex-1 overflow-auto min-h-0">
        <PreviewContent path={path} type={type} />
      </div>
    </div>
  );
}

function PreviewIcon({ type }: { type: FilePreviewType }) {
  const cls = "w-4 h-4 shrink-0 text-muted-foreground";
  switch (type) {
    case 'image': return <ImageIcon className={cls} />;
    case 'text': return <Code className={cls} />;
    case 'markdown': return <FileText className={cls} />;
    default: return <FileType className={cls} />;
  }
}

function PreviewContent({ path, type }: { path: string; type: FilePreviewType }) {
  const inlineUrl = `${API_BASE}/api/files/download?path=${encodeURIComponent(path)}&inline=true`;

  switch (type) {
    case 'html':
      return <iframe src={inlineUrl} sandbox="" className="w-full h-full border-0" />;

    case 'pdf':
      return <iframe src={inlineUrl} className="w-full h-full border-0" />;

    case 'image':
      return (
        <div className="flex items-center justify-center h-full p-4 bg-muted/20">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={inlineUrl}
            alt={path.split(/[\\/]/).pop() || ''}
            className="max-w-full max-h-full object-contain rounded"
          />
        </div>
      );

    case 'text':
    case 'unknown':
      return <TextPreview path={path} />;

    case 'markdown':
      return <MarkdownPreview path={path} />;

    default:
      return <ErrorDisplay message="此文件类型无法预览" />;
  }
}

/** 纯文本 / 代码文件预览，带语法高亮 */
function TextPreview({ path }: { path: string }) {
  const { content, error, truncated } = useFetchText(path);

  if (error) return <ErrorDisplay message={error} />;
  if (content === null) return <LoadingDisplay />;

  const lang = guessLanguage(path);

  return (
    <div className="p-0">
      {truncated && (
        <div className="px-3 py-1.5 text-[10px] text-amber-600 bg-amber-50 border-b border-amber-200">
          文件过大，仅展示前 1MB
        </div>
      )}
      <pre className="text-xs leading-relaxed p-4 overflow-auto">
        {lang ? (
          <code className={`language-${lang}`}>{content}</code>
        ) : (
          <code>{content}</code>
        )}
      </pre>
    </div>
  );
}

/** Markdown 预览 */
function MarkdownPreview({ path }: { path: string }) {
  const { content, error, truncated } = useFetchText(path);

  if (error) return <ErrorDisplay message={error} />;
  if (content === null) return <LoadingDisplay />;

  return (
    <div>
      {truncated && (
        <div className="px-3 py-1.5 text-[10px] text-amber-600 bg-amber-50 border-b border-amber-200">
          文件过大，仅展示前 1MB
        </div>
      )}
      <div className="p-4 prose prose-sm max-w-none dark:prose-invert">
        <MarkdownContent content={content} />
      </div>
    </div>
  );
}

/** 加载文本内容的 hook */
function useFetchText(path: string) {
  const [content, setContent] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [truncated, setTruncated] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setContent(null);
    setError(null);
    setTruncated(false);

    (async () => {
      try {
        const url = `${API_BASE}/api/files/download?path=${encodeURIComponent(path)}&inline=true`;
        const res = await authFetch(url);
        if (!res.ok) {
          if (res.status === 404) {
            setError('文件未找到');
          } else {
            setError(`加载失败 (${res.status})`);
          }
          return;
        }
        const ct = res.headers.get('content-type') || '';
        // 对 unknown 类型文件：检测是否为文本
        if (!ct.startsWith('text/') && !ct.includes('json') && !ct.includes('xml')
            && !ct.includes('yaml') && !ct.includes('javascript') && !ct.includes('typescript')) {
          const blob = await res.blob();
          const slice = blob.slice(0, 512);
          const sample = await slice.text();
          const nonPrintable = sample.split('').filter(c => {
            const code = c.charCodeAt(0);
            return code < 32 && code !== 9 && code !== 10 && code !== 13;
          }).length;
          if (nonPrintable > sample.length * 0.1) {
            if (!cancelled) setError('无法预览此文件类型');
            return;
          }
          let text = await blob.text();
          if (text.length > MAX_TEXT_SIZE) {
            text = text.slice(0, MAX_TEXT_SIZE);
            if (!cancelled) setTruncated(true);
          }
          if (!cancelled) setContent(text);
          return;
        }

        let text = await res.text();
        if (text.length > MAX_TEXT_SIZE) {
          text = text.slice(0, MAX_TEXT_SIZE);
          if (!cancelled) setTruncated(true);
        }
        if (!cancelled) setContent(text);
      } catch {
        if (!cancelled) setError('加载失败，请重试');
      }
    })();

    return () => { cancelled = true; };
  }, [path]);

  return { content, error, truncated };
}

function ErrorDisplay({ message }: { message: string }) {
  return (
    <div className="flex flex-col items-center justify-center h-full gap-2 text-muted-foreground p-8">
      <AlertCircle className="w-8 h-8 text-muted-foreground/40" />
      <span className="text-xs">{message}</span>
    </div>
  );
}

function LoadingDisplay() {
  return (
    <div className="flex items-center justify-center h-full">
      <span className="w-5 h-5 border-2 border-primary border-t-transparent rounded-full animate-spin" />
    </div>
  );
}
