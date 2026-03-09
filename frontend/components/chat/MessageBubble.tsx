'use client';

import { useState } from 'react';
import type { Message } from '@/types/message';

function JsonViewer({ data }: { data: any }) {
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

function isJsonLike(value: any): boolean {
  if (typeof value === 'object' && value !== null) return true;
  if (typeof value === 'string') {
    try {
      JSON.parse(value);
      return true;
    } catch {
      return false;
    }
  }
  return false;
}

function CollapsibleContent({ content, maxLength = 500 }: { content: string; maxLength?: number }) {
  const [isExpanded, setIsExpanded] = useState(false);
  const needsCollapse = content.length > maxLength;

  if (!needsCollapse) {
    return <div className="content-text">{content}</div>;
  }

  return (
    <div className="collapsible-content">
      <div className="content-text">
        {isExpanded ? content : content.slice(0, maxLength) + '...'}
      </div>
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
              <CollapsibleContent content={String(toolInfo.arguments)} />
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
                <div className="tool-error">{toolInfo.error}</div>
              ) : isJsonLike(toolInfo.result) ? (
                <JsonViewer data={toolInfo.result} />
              ) : (
                <CollapsibleContent content={String(toolInfo.result)} maxLength={1000} />
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
        <div className="tool-message-content">{message.content}</div>
        <ToolInfoDisplay message={message} />
      </div>
    );
  }

  return <div className={`bubble ${message.role}`}>{message.content}</div>;
}
