'use client';

import { Loader2 } from 'lucide-react';

export interface UploadProgressItem {
  id: string;
  name: string;
  /** 0~100，null 表示不确定进度（小文件 loading 状态） */
  percent: number | null;
  status: 'uploading' | 'checking' | 'done' | 'error';
  error?: string;
}

interface UploadProgressProps {
  items: UploadProgressItem[];
}

export function UploadProgress({ items }: UploadProgressProps) {
  if (items.length === 0) return null;

  return (
    <div className="flex flex-col gap-1.5 px-4 py-2">
      {items.map(item => (
        <div key={item.id} className="flex items-center gap-2 text-xs text-muted-foreground">
          {item.status === 'done' ? (
            <span className="text-green-500">✓</span>
          ) : item.status === 'error' ? (
            <span className="text-destructive">✗</span>
          ) : (
            <Loader2 size={12} className="animate-spin" />
          )}
          <span className="truncate max-w-[200px]">{item.name}</span>
          {item.status === 'checking' && <span>检查中...</span>}
          {item.status === 'uploading' && item.percent !== null && (
            <>
              <div className="flex-1 max-w-[120px] h-1.5 bg-muted rounded-full overflow-hidden">
                <div
                  className="h-full bg-primary rounded-full transition-all duration-300"
                  style={{ width: `${item.percent}%` }}
                />
              </div>
              <span>{item.percent}%</span>
            </>
          )}
          {item.status === 'uploading' && item.percent === null && (
            <span>上传中...</span>
          )}
          {item.status === 'error' && (
            <span className="text-destructive">{item.error || '失败'}</span>
          )}
        </div>
      ))}
    </div>
  );
}
