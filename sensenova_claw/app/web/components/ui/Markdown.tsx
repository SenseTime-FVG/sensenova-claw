'use client';

import { memo, useMemo, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import rehypeHighlight from 'rehype-highlight';
import type { Components } from 'react-markdown';
import { Check, Copy, FolderOpen, Presentation, FileText } from 'lucide-react';
import { useFilePanel } from '@/contexts/FilePanelContext';
import { getFilePreviewType, isPreviewable } from '@/components/files/fileTypes';
import { cn } from '@/lib/utils';

/* ── sensenova-claw Constants ── */
const FILE_LINK_PREFIX = '#sensenova-claw-file:';
const WORKDIR_LINK_PREFIX = '#sensenova-claw-workdir:';

function isSlideFilePath(text: string): boolean {
  return /page_\d+\.html/i.test(text);
}

function isRelativeSlidePath(text: string): boolean {
  const trimmed = text.trim();
  if (/^[A-Za-z]:\\/.test(trimmed) || /^\//.test(trimmed)) return false;
  return /[\\/]/.test(trimmed) && /page_\d+\.html/i.test(trimmed);
}

export function extractWorkdirRelDir(absPath: string): string | null {
  const normalized = absPath.replace(/\\/g, '/');
  const marker = '/workdir/';
  const idx = normalized.indexOf(marker);
  if (idx === -1) return null;
  const afterWorkdir = normalized.slice(idx + marker.length);
  const lastSlash = afterWorkdir.lastIndexOf('/');
  return lastSlash > 0 ? afterWorkdir.slice(0, lastSlash) : null;
}

function extractDirFromPath(path: string): string | null {
  const normalized = path.replace(/\\/g, '/');
  const lastSlash = normalized.lastIndexOf('/');
  return lastSlash > 0 ? normalized.slice(0, lastSlash) : null;
}

export function dispatchSlidePreview(dir: string, isAbsolute: boolean) {
  window.dispatchEvent(new CustomEvent('sensenova-claw:open-slide-preview', {
    detail: { dir, isAbsolute },
  }));
}

function preprocessFileLinks(md: string): string {
  return md.replace(
    /\[([^\]]*?)\]\((#sensenova-claw-(?:file|workdir):[^)]+)\)/g,
    (_m, display: string, href: string) => {
      if (!display.includes('\\')) return _m;
      return `[${display.replace(/\\/g, '/')}](${href})`;
    },
  );
}

/* ── UI Components ── */

function CopyButton({ code }: { code: string }) {
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    await navigator.clipboard.writeText(code);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <button
      onClick={handleCopy}
      className="absolute top-2 right-2 p-1.5 rounded-md bg-muted/80 hover:bg-muted text-muted-foreground hover:text-foreground transition-all opacity-0 group-hover/code:opacity-100"
      aria-label="Copy code"
    >
      {copied ? <Check size={14} /> : <Copy size={14} />}
    </button>
  );
}

function extractText(node: React.ReactNode): string {
  if (typeof node === 'string') return node;
  if (typeof node === 'number') return String(node);
  if (!node) return '';
  if (Array.isArray(node)) return node.map(extractText).join('');
  if (typeof node === 'object' && node !== null && 'props' in (node as any)) {
    return extractText((node as any).props.children);
  }
  return '';
}

/* ── Markdown Infrastructure ── */

const baseComponents: Partial<Components> = {
  pre({ children, ...props }) {
    const code = extractText(children);
    return (
      <div className="relative group/code my-3">
        <CopyButton code={code} />
        <pre {...props} className="overflow-x-auto rounded-lg border border-border bg-muted/50 p-4 text-sm leading-relaxed">
          {children}
        </pre>
      </div>
    );
  },
  code({ className, children, ...props }) {
    const isBlock = className?.startsWith('hljs') || className?.includes('language-');
    if (isBlock) {
      return <code className={className} {...props}>{children}</code>;
    }
    return (
      <code className="bg-muted/70 border border-border/50 rounded px-1.5 py-0.5 text-[0.85em] font-mono" {...props}>
        {children}
      </code>
    );
  },
  table({ children, ...props }) {
    return (
      <div className="overflow-x-auto my-3">
        <table className="min-w-full border-collapse border border-border text-sm" {...props}>
          {children}
        </table>
      </div>
    );
  },
  th({ children, ...props }) {
    return (
      <th className="border border-border bg-muted/50 px-3 py-2 text-left font-semibold" {...props}>
        {children}
      </th>
    );
  },
  td({ children, ...props }) {
    return (
      <td className="border border-border px-3 py-2" {...props}>
        {children}
      </td>
    );
  },
  a: ({ href, children, ...props }) => (
    <a
      {...props}
      href={href}
      rel="noreferrer noopener"
      target="_blank"
    >
        {children}
    </a>
  ),
  input: ({ type, ...props }) => {
    if (type === 'checkbox') {
    return <input {...props} disabled type="checkbox" />;
    }
    return <input {...props} type={type} />;
  },
};

interface MarkdownProps {
  content: string;
  className?: string;
  variant?: 'default' | 'user' | 'system' | 'detail';
}

export const Markdown = memo(function Markdown({ content, className, variant = 'default' }: MarkdownProps) {
  const { openToPath } = useFilePanel();
  const processed = useMemo(() => preprocessFileLinks(content), [content]);

  const mdComponents = useMemo<Components>(() => ({
    ...baseComponents,
    a({ children, href, ...props }) {
      if (href?.startsWith(FILE_LINK_PREFIX)) {
        const filePath = decodeURIComponent(href.slice(FILE_LINK_PREFIX.length));
        const handleClick = (e: React.MouseEvent) => {
          e.preventDefault();
          openToPath?.(filePath);
          if (isSlideFilePath(filePath)) {
            const dir = extractWorkdirRelDir(filePath) || extractDirFromPath(filePath);
            if (dir) dispatchSlidePreview(dir, true);
          } else if (isPreviewable(filePath)) {
            window.dispatchEvent(new CustomEvent('sensenova-claw:open-file-preview', {
              detail: { path: filePath, type: getFilePreviewType(filePath) },
            }));
          }
        };
        const isSlide = isSlideFilePath(filePath);
        const previewable = !isSlide && isPreviewable(filePath);
        return (
          <a
            href="#"
            onClick={handleClick}
            title={filePath}
            className="inline-flex items-center gap-1.5 px-2.5 py-1 my-0.5 rounded-lg bg-primary/10 text-primary hover:bg-primary/20 transition-colors text-sm font-medium no-underline border border-primary/20 cursor-pointer"
            {...props}
          >
            {isSlide ? <Presentation size={14} className="shrink-0" /> : previewable ? <FileText size={14} className="shrink-0" /> : <FolderOpen size={14} className="shrink-0" />}
            {children}
          </a>
        );
      }
      if (href?.startsWith(WORKDIR_LINK_PREFIX)) {
        const relPath = decodeURIComponent(href.slice(WORKDIR_LINK_PREFIX.length));
        const handleClick = (e: React.MouseEvent) => {
          e.preventDefault();
          const cleanPath = relPath.replace(/\/+$/, '');
          const dir = isRelativeSlidePath(relPath)
            ? (extractDirFromPath(cleanPath) || cleanPath)
            : cleanPath;
          dispatchSlidePreview(dir, false);
        };
        return (
          <a
            href="#"
            onClick={handleClick}
            title={relPath}
            className="inline-flex items-center gap-1.5 px-2.5 py-1 my-0.5 rounded-lg bg-orange-500/10 text-orange-600 dark:text-orange-400 hover:bg-orange-500/20 transition-colors text-sm font-medium no-underline border border-orange-500/20 cursor-pointer"
            {...props}
          >
            <Presentation size={14} className="shrink-0" />
            {children}
          </a>
        );
      }
      return (
        <a
          href={href}
          target="_blank"
          rel="noopener noreferrer"
          className={cn(
            "text-primary underline underline-offset-2 hover:text-primary/80 transition-colors",
            variant === 'user' && "text-primary-foreground underline-offset-4"
          )}
          {...props}
        >
          {children}
        </a>
      );
    },
  }), [openToPath, variant]);

  return (
    <div className={cn(
      "markdown-body prose prose-sm dark:prose-invert max-w-none break-words",
      variant === 'system' && "text-[10px] text-muted-foreground",
      variant === 'user' && "prose-invert",
      variant === 'detail' && "text-xs",
      className
    )}>
      <ReactMarkdown 
        remarkPlugins={[remarkGfm]} 
        rehypePlugins={variant !== 'user' ? [rehypeHighlight] : []} 
        components={mdComponents}
      >
        {processed}
      </ReactMarkdown>
    </div>
  );
});
