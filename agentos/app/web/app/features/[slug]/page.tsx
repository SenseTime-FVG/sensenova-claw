'use client';

import { useEffect, useState, useCallback } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { DashboardLayout } from '@/components/layout/DashboardLayout';
import { WorkbenchShell } from '@/components/workbench/WorkbenchShell';
import { ChatPanel } from '@/components/chat/ChatPanel';
import { useChatSession } from '@/contexts/ChatSessionContext';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { authFetch, API_BASE } from '@/lib/authFetch';
import {
  Sparkles, BookOpen, Zap, Presentation, Code, Globe,
  Music, Image, FileText, Database, Shield, Brain,
  Rocket, Target, Heart, Star, Lightbulb, Puzzle,
  Settings2, Loader2,
} from 'lucide-react';
import type { LucideIcon } from 'lucide-react';

const ICON_MAP: Record<string, LucideIcon> = {
  Sparkles, BookOpen, Zap, Presentation, Code, Globe,
  Music, Image, FileText, Database, Shield, Brain,
  Rocket, Target, Heart, Star, Lightbulb, Puzzle,
};

interface CustomPageData {
  id: string;
  slug: string;
  name: string;
  description: string;
  icon: string;
  agent_id: string;
  system_prompt: string;
  templates: Array<{ title: string; desc: string }>;
}

function CustomTemplates({
  page,
  onQuickTask,
}: {
  page: CustomPageData;
  onQuickTask: (msg: string) => void;
}) {
  const Icon = ICON_MAP[page.icon] || Sparkles;

  return (
    <div className="flex-1 flex flex-col items-center justify-center p-6">
      <div className="max-w-2xl mx-auto w-full">
        <div className="text-center py-8">
          <div className="w-16 h-16 rounded-2xl bg-primary/10 flex items-center justify-center mx-auto mb-4">
            <Icon className="w-8 h-8 text-primary" />
          </div>
          <h2 className="text-xl font-semibold text-foreground mb-2">{page.name}</h2>
          {page.description && (
            <p className="text-muted-foreground text-sm mb-8">{page.description}</p>
          )}
        </div>

        {page.templates.length > 0 && (
          <div className="grid grid-cols-2 gap-4">
            {page.templates.map((tmpl, i) => (
              <Card
                key={i}
                className="p-4 hover:shadow-md transition-shadow cursor-pointer hover:border-primary/30"
                onClick={() => onQuickTask(tmpl.title)}
              >
                <h3 className="font-semibold text-foreground mb-1 text-sm">{tmpl.title}</h3>
                {tmpl.desc && (
                  <p className="text-xs text-muted-foreground">{tmpl.desc}</p>
                )}
              </Card>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

export default function DynamicFeaturePage() {
  const params = useParams();
  const router = useRouter();
  const slug = params.slug as string;

  const { sendMessage } = useChatSession();
  const [page, setPage] = useState<CustomPageData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  const loadPage = useCallback(async () => {
    setLoading(true);
    setError(false);
    try {
      const res = await authFetch(`${API_BASE}/api/custom-pages/${encodeURIComponent(slug)}`);
      const data = await res.json();
      if (data.error) {
        setError(true);
      } else {
        setPage(data);
      }
    } catch {
      setError(true);
    } finally {
      setLoading(false);
    }
  }, [slug]);

  useEffect(() => { loadPage(); }, [loadPage]);

  if (loading) {
    return (
      <DashboardLayout>
        <div className="flex-1 flex items-center justify-center">
          <Loader2 className="w-8 h-8 text-muted-foreground animate-spin" />
        </div>
      </DashboardLayout>
    );
  }

  if (error || !page) {
    return (
      <DashboardLayout>
        <div className="flex-1 flex flex-col items-center justify-center gap-4">
          <p className="text-muted-foreground">功能页未找到</p>
          <Button variant="outline" onClick={() => router.push('/')}>
            返回首页
          </Button>
        </div>
      </DashboardLayout>
    );
  }

  return (
    <DashboardLayout>
      <WorkbenchShell>
        <div className="flex flex-col h-full">
          <div className="flex items-center justify-between px-4 py-2 border-b border-border/50 bg-muted/20">
            <div className="flex items-center gap-2">
              {(() => {
                const Icon = ICON_MAP[page.icon] || Sparkles;
                return <Icon className="w-4 h-4 text-primary" />;
              })()}
              <span className="text-sm font-medium text-foreground">{page.name}</span>
            </div>
            <Button
              variant="ghost"
              size="icon-sm"
              onClick={() => router.push(`/features/${slug}/edit`)}
              title="编辑功能页"
            >
              <Settings2 className="w-4 h-4" />
            </Button>
          </div>
          <div className="flex-1 min-h-0">
            <ChatPanel
              defaultAgentId={page.agent_id}
              emptyState={
                <CustomTemplates page={page} onQuickTask={(msg) => sendMessage(msg)} />
              }
              returnToMainLabel={`返回 ${page.name}`}
            />
          </div>
        </div>
      </WorkbenchShell>
    </DashboardLayout>
  );
}
