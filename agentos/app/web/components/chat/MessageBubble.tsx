'use client';

import { useState } from 'react';
import { MarkdownRenderer } from '@/components/chat/MarkdownRenderer';
import { isJsonLike, previewText, stringifyContent } from '@/components/chat/messageContent';
import type { Message } from '@/types/message';

function JsonViewer({ data }: { data: unknown }) {
  try {
    const jsonString = typeof data === 'string' ? data : JSON.stringify(data, null, 2);
    return (
      <pre className="json-viewer">
        <code>{jsonString}</code>
      </pre>
    );
  } catch {
    return <div className="json-error">无法解析 JSON</div>;
  }
}

function CollapsibleContent({ content, maxLength = 500 }: { content: string; maxLength?: number }) {
  const [isExpanded, setIsExpanded] = useState(false);
  const needsCollapse = content.length > maxLength;

  if (!needsCollapse) {
    return <MarkdownRenderer className="chat-markdown--detail content-text" content={content} />;
  }

  return (
    <div className="collapsible-content">
      {!isExpanded ? <div className="content-text">{previewText(content, maxLength)}</div> : null}
      {isExpanded ? <MarkdownRenderer className="chat-markdown--detail content-text" content={content} /> : null}
      <button className="collapse-button" onClick={() => setIsExpanded(!isExpanded)}>
        {isExpanded ? '收起' : '展开'}
      </button>
    </div>
  );
}

function ToolInfoDisplay({ message }: { message: Message }) {
  const { toolInfo } = message;
  if (!toolInfo) return null;

  const [showArgs, setShowArgs] = useState(false);
  const [showResult, setShowResult] = useState(false);

  return (
    <div className="tool-info">
      <div className="tool-header">
        <span className="tool-name">{toolInfo.name}</span>
        <span className={`tool-status ${toolInfo.status}`}>
          {toolInfo.status === 'running' ? '执行中...' : toolInfo.success ? '成功' : '失败'}
        </span>
      </div>

      {/* 参数 */}
      <div className="tool-section">
        <button className="section-toggle" onClick={() => setShowArgs(!showArgs)}>
          {showArgs ? '▼' : '▶'} 参数
        </button>
        {showArgs && (
          <div className="section-content">
            {isJsonLike(toolInfo.arguments) ? (
              <JsonViewer data={toolInfo.arguments} />
            ) : (
              <CollapsibleContent content={stringifyContent(toolInfo.arguments)} />
            )}
          </div>
        )}
      </div>

      {/* 结果 */}
      {toolInfo.status === 'completed' && (
        <div className="tool-section">
          <button className="section-toggle" onClick={() => setShowResult(!showResult)}>
            {showResult ? '▼' : '▶'} 结果
          </button>
          {showResult && (
            <div className="section-content">
              {toolInfo.error ? (
                <div className="tool-error">
                  <MarkdownRenderer className="chat-markdown--detail" content={toolInfo.error} />
                </div>
              ) : isJsonLike(toolInfo.result) ? (
                <JsonViewer data={toolInfo.result} />
              ) : (
                <CollapsibleContent content={stringifyContent(toolInfo.result)} maxLength={1000} />
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export function MessageBubble({ message }: { message: Message }) {
  if (message.role === 'tool') {
    return (
      <div className="bubble tool">
        <div className="tool-message-content">
          <MarkdownRenderer className="chat-markdown--detail" content={message.content} />
        </div>
        <ToolInfoDisplay message={message} />
      </div>
    );
  }

  return (
    <div className={`bubble ${message.role}`}>
      <MarkdownRenderer content={message.content} />
    </div>
  );
}
