'use client';

import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { cn } from '@/lib/utils';

interface MarkdownRendererProps {
  content: string;
  className?: string;
}

export function MarkdownRenderer({ content, className }: MarkdownRendererProps) {
  return (
    <div className={cn('chat-markdown', className)}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          a: ({ href, ...props }) => (
            <a
              {...props}
              href={href}
              rel="noreferrer noopener"
              target="_blank"
            />
          ),
          input: ({ type, ...props }) => {
            if (type === 'checkbox') {
              return <input {...props} disabled type="checkbox" />;
            }
            return <input {...props} type={type} />;
          },
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}
