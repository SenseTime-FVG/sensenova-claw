'use client';

import { memo, useMemo, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import rehypeHighlight from 'rehype-highlight';
import type { Components } from 'react-markdown';
import { Check, Copy, FolderOpen } from 'lucide-react';
import { API_BASE } from '@/lib/authFetch';
import { useFilePanel } from '@/contexts/FilePanelContext';

/* ── 文件路径自动链接 ── */

const FILE_LINK_PREFIX = '#agentos-file:';
const WIN_PATH_RE = /([A-Za-z]:\\[^\s<>"'*\[\]|]+\.\w+)/g;
const UNIX_PATH_RE = /(\/(?:home|Users|tmp|var|opt|root|mnt)[^\s<>"'*\[\]|]*\/[^\s<>"'*\[\]|/]+\.\w+)/g;

function isFilePath(text: string): boolean {
  return /^[A-Za-z]:\\/.test(text.trim()) || /^\/(?:home|Users|tmp|var|opt|root|mnt)\//.test(text.trim());
}

function buildFileMarker(filePath: string): string {
  return `${FILE_LINK_PREFIX}${encodeURIComponent(filePath.trim())}`;
}

function extractFileName(filePath: string): string {
  return filePath.split(/[/\\]/).pop() || filePath;
}

function linkifyFilePaths(md: string): string {
  const parts = md.split(/(```[\s\S]*?```)/g);
  return parts.map((part, i) => {
    if (i % 2 !== 0) return part;

    part = part.replace(/`([^`\n]+)`/g, (_match, code: string) => {
      const trimmed = code.trim();
      if (isFilePath(trimmed)) {
        return `[${extractFileName(trimmed)}](${buildFileMarker(trimmed)})`;
      }
      return _match;
    });

    part = part.replace(WIN_PATH_RE, (m) => `[${extractFileName(m)}](${buildFileMarker(m)})`);
    part = part.replace(UNIX_PATH_RE, (m) => `[${extractFileName(m)}](${buildFileMarker(m)})`);

    return part;
  }).join('');
}

/* ── 复制按钮 ── */

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
  if (typeof node === 'object' && 'props' in node) {
    return extractText((node as React.ReactElement).props.children);
  }
  return '';
}

/* ── 不依赖 onFileClick 的基础组件 ── */

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
};

export const MarkdownContent = memo(function MarkdownContent({ content }: { content: string }) {
  const { openToPath } = useFilePanel();
  const processed = linkifyFilePaths(content);

  const mdComponents = useMemo<Components>(() => ({
    ...baseComponents,
    a({ children, href, ...props }) {
      if (href?.startsWith(FILE_LINK_PREFIX)) {
        const filePath = decodeURIComponent(href.slice(FILE_LINK_PREFIX.length));
        const handleClick = (e: React.MouseEvent) => {
          e.preventDefault();
          openToPath(filePath);
        };
        return (
          <a
            href="#"
            onClick={handleClick}
            className="inline-flex items-center gap-1.5 px-2.5 py-1 my-0.5 rounded-lg bg-primary/10 text-primary hover:bg-primary/20 transition-colors text-sm font-medium no-underline border border-primary/20 cursor-pointer"
            {...props}
          >
            <FolderOpen size={14} className="shrink-0" />
            {children}
          </a>
        );
      }
      return (
        <a
          href={href}
          target="_blank"
          rel="noopener noreferrer"
          className="text-primary underline underline-offset-2 hover:text-primary/80 transition-colors"
          {...props}
        >
          {children}
        </a>
      );
    },
  }), [openToPath]);

  return (
    <div className="markdown-body prose prose-sm dark:prose-invert max-w-none break-words">
      <ReactMarkdown remarkPlugins={[remarkGfm]} rehypePlugins={[rehypeHighlight]} components={mdComponents}>
        {processed}
      </ReactMarkdown>
    </div>
  );
});
