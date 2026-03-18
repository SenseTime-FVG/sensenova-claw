'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { Clock, Folder, File, ChevronRight } from 'lucide-react';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { cn } from '@/lib/utils';
import { authFetch, API_BASE } from '@/lib/authFetch';

interface SessionItem {
  session_id: string;
  created_at: number;
  last_active: number;
  meta: string;
  status: string;
}

interface FileNode {
  name: string;
  type: 'file' | 'folder';
  children?: FileNode[];
}

const mockFileTree: FileNode[] = [
  {
    name: '项目文档',
    type: 'folder',
    children: [
      { name: 'Q1产品路线图.pdf', type: 'file' },
      { name: '技术架构设计.docx', type: 'file' },
    ],
  },
  {
    name: '数据分析',
    type: 'folder',
    children: [
      { name: 'sales_data.xlsx', type: 'file' },
      { name: '用户行为报告.pdf', type: 'file' },
    ],
  },
  { name: '会议记录.txt', type: 'file' },
  { name: 'OKR规划表.xlsx', type: 'file' },
];

function getTitle(meta: string): string {
  try { return JSON.parse(meta).title || '未命名任务'; } catch { return '未命名任务'; }
}

function timeLabel(ts: number): string {
  const diff = Date.now() / 1000 - ts;
  if (diff < 60) return '刚刚';
  if (diff < 3600) return `${Math.floor(diff / 60)}分钟前`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}小时前`;
  return `${Math.floor(diff / 86400)}天前`;
}

function FileTreeItem({ node }: { node: FileNode }) {
  const [expanded, setExpanded] = useState(false);
  const isFolder = node.type === 'folder';

  return (
    <div>
      <div
        className="flex items-center gap-2 px-3 py-1.5 rounded hover:bg-muted cursor-pointer text-sm"
        onClick={() => isFolder && setExpanded(!expanded)}
      >
        {isFolder && (
          <ChevronRight className={cn(
            'w-3 h-3 text-muted-foreground transition-transform',
            expanded && 'rotate-90'
          )} />
        )}
        {isFolder ? (
          <Folder className="w-4 h-4 text-primary" />
        ) : (
          <File className="w-4 h-4 text-muted-foreground" />
        )}
        <span className="text-foreground/80 truncate">{node.name}</span>
      </div>
      {isFolder && expanded && node.children && (
        <div className="ml-4 mt-0.5 space-y-0.5">
          {node.children.map((child, i) => (
            <FileTreeItem key={i} node={child} />
          ))}
        </div>
      )}
    </div>
  );
}

export function LeftNav() {
  const router = useRouter();
  const [sessions, setSessions] = useState<SessionItem[]>([]);

  useEffect(() => {
    authFetch(`${API_BASE}/api/sessions`)
      .then((r) => r.json())
      .then((d) => setSessions((d.sessions || []).slice(0, 10)))
      .catch(() => {});
  }, []);

  return (
    <nav className="w-56 border-r border-border bg-muted/20 flex flex-col shrink-0">
      <Tabs defaultValue="tasks" className="flex-1 flex flex-col">
        <TabsList className="w-full grid grid-cols-2 rounded-none border-b border-border bg-transparent p-0 h-auto">
          <TabsTrigger
            value="tasks"
            className="rounded-none py-2.5 text-xs data-[state=active]:border-b-2 data-[state=active]:border-primary data-[state=active]:bg-transparent data-[state=active]:shadow-none"
          >
            任务
          </TabsTrigger>
          <TabsTrigger
            value="files"
            className="rounded-none py-2.5 text-xs data-[state=active]:border-b-2 data-[state=active]:border-primary data-[state=active]:bg-transparent data-[state=active]:shadow-none"
          >
            文件区
          </TabsTrigger>
        </TabsList>

        <TabsContent value="tasks" className="flex-1 p-3 mt-0 overflow-y-auto">
          <h3 className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider mb-2 px-1">
            最近任务
          </h3>
          <div className="space-y-1">
            {sessions.length === 0 && (
              <p className="text-xs text-muted-foreground/50 px-1 py-4 text-center">
                暂无任务记录
              </p>
            )}
            {sessions.map((s) => (
              <div
                key={s.session_id}
                onClick={() => router.push(`/chat?session=${s.session_id}`)}
                className="px-3 py-2 rounded-lg cursor-pointer hover:bg-muted transition-colors"
              >
                <div className="flex items-center gap-2">
                  <Clock className="w-3 h-3 text-muted-foreground shrink-0" />
                  <span className="text-sm text-foreground truncate">
                    {getTitle(s.meta)}
                  </span>
                </div>
                <span className="text-[10px] text-muted-foreground ml-5">
                  {timeLabel(s.last_active)}
                </span>
              </div>
            ))}
          </div>
        </TabsContent>

        <TabsContent value="files" className="flex-1 p-3 mt-0 overflow-y-auto">
          <h3 className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider mb-2 px-1">
            我的文件
          </h3>
          <div className="space-y-0.5">
            {mockFileTree.map((node, i) => (
              <FileTreeItem key={i} node={node} />
            ))}
          </div>
        </TabsContent>
      </Tabs>
    </nav>
  );
}
