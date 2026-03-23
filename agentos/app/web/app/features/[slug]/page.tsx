'use client';

import { useEffect, useMemo, useState, useCallback } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { DashboardLayout } from '@/components/layout/DashboardLayout';
import { WorkbenchShell } from '@/components/workbench/WorkbenchShell';
import { MiniAppBuildFeed } from '@/components/workbench/MiniAppBuildFeed';
import { ChatPanel } from '@/components/chat/ChatPanel';
import { useChatSession } from '@/contexts/ChatSessionContext';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { ResizablePanel, ResizablePanelGroup, ResizableHandle } from '@/components/ui/resizable';
import { authFetch, API_BASE } from '@/lib/authFetch';
import {
  Sparkles, BookOpen, Zap, Presentation, Code, Globe,
  Music, Image, FileText, Database, Shield, Brain,
  Rocket, Target, Heart, Star, Lightbulb, Puzzle,
  Loader2, RefreshCw, ExternalLink, Workflow,
} from 'lucide-react';
import type { LucideIcon } from 'lucide-react';

type ActionTarget = 'local' | 'server' | 'agent';

const ICON_MAP: Record<string, LucideIcon> = {
  Sparkles, BookOpen, Zap, Presentation, Code, Globe,
  Music, Image, FileText, Database, Shield, Brain,
  Rocket, Target, Heart, Star, Lightbulb, Puzzle,
};

interface BuildRunLog {
  ts: number;
  level: string;
  message: string;
}

interface BuildRun {
  id: string;
  builder_type: 'builtin' | 'acp';
  status: 'queued' | 'running' | 'completed' | 'failed';
  prompt: string;
  started_at_ms: number;
  ended_at_ms: number | null;
  logs: BuildRunLog[];
  error?: string;
}

interface CustomPageData {
  id: string;
  slug: string;
  name: string;
  description: string;
  icon: string;
  type?: string;
  agent_id: string;
  base_agent_id?: string;
  create_dedicated_agent?: boolean;
  system_prompt: string;
  templates: Array<{ title: string; desc: string }>;
  workspace_mode?: 'scratch' | 'reuse';
  source_project_path?: string;
  builder_type?: 'builtin' | 'acp';
  generation_prompt?: string;
  entry_file_path?: string;
  bridge_script_path?: string;
  preserved_license_files?: string[];
  build_status?: 'pending' | 'queued' | 'running' | 'ready' | 'failed';
  build_summary?: string;
  latest_run_id?: string;
  last_interaction_session_id?: string;
  workspace_root?: string;
  app_dir?: string;
  updated_at?: number;
  runs?: BuildRun[];
}

interface MiniAppPostMessagePayload {
  source?: string;
  slug?: string;
  kind?: 'interaction' | 'state' | 'log' | 'config';
  action?: string;
  payload?: Record<string, unknown>;
  target?: ActionTarget | string;
  meta?: {
    defaultTarget?: ActionTarget | string;
    routes?: Record<string, ActionTarget | string>;
  };
}

interface LocalEvent {
  ts: number;
  label: string;
  detail: string;
}

interface RuntimeActionRouting {
  defaultTarget: ActionTarget;
  routes: Record<string, ActionTarget>;
}

function formatBuildStatus(status: CustomPageData['build_status']): { label: string; variant: 'default' | 'secondary' | 'outline' | 'destructive' } {
  switch (status) {
    case 'ready':
      return { label: '已就绪', variant: 'default' };
    case 'running':
      return { label: '生成中', variant: 'secondary' };
    case 'queued':
      return { label: '排队中', variant: 'outline' };
    case 'failed':
      return { label: '失败', variant: 'destructive' };
    default:
      return { label: '待生成', variant: 'outline' };
  }
}

function formatTime(ts?: number | null): string {
  if (!ts) return '--';
  return new Date(ts).toLocaleString('zh-CN', {
    hour12: false,
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  });
}

function ChatEmptyState({
  page,
  onQuickTask,
}: {
  page: CustomPageData;
  onQuickTask: (message: string) => void;
}) {
  const Icon = ICON_MAP[page.icon] || Sparkles;

  return (
    <div className="flex h-full flex-col items-center justify-center px-6 text-center">
      <div className="w-16 h-16 rounded-2xl bg-primary/10 flex items-center justify-center mb-4">
        <Icon className="w-8 h-8 text-primary" />
      </div>
      <h3 className="text-xl font-semibold text-foreground mb-2">{page.name} Agent</h3>
      <p className="text-sm text-muted-foreground max-w-md mb-6">
        你可以直接要求它继续修改当前 mini-app。页面动作也可以按 local、server、agent 分流，只有真正需要判断或改造时才进入 Agent。
      </p>
      {page.templates.length > 0 && (
        <div className="grid gap-3 w-full max-w-lg">
          {page.templates.map((template, index) => (
            <Card
              key={`${template.title}-${index}`}
              className="p-4 text-left cursor-pointer hover:border-primary/30 transition-colors"
              onClick={() => onQuickTask(`请围绕「${template.title}」继续改进这个 mini-app。${template.desc || ''}`)}
            >
              <div className="font-medium text-foreground">{template.title}</div>
              {template.desc && <p className="mt-1 text-sm text-muted-foreground">{template.desc}</p>}
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}

export default function DynamicFeaturePage() {
  const params = useParams();
  const router = useRouter();
  const slug = params.slug as string;

  const {
    sendMessage,
    switchSession,
    currentSessionId,
  } = useChatSession();

  const [page, setPage] = useState<CustomPageData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [buildPrompt, setBuildPrompt] = useState('');
  const [buildSubmitting, setBuildSubmitting] = useState(false);
  const [localEvents, setLocalEvents] = useState<LocalEvent[]>([]);
  const [interactionSubmitting, setInteractionSubmitting] = useState(false);
  const [runtimeRouting, setRuntimeRouting] = useState<RuntimeActionRouting>({
    defaultTarget: 'agent',
    routes: {},
  });

  const loadPage = useCallback(async (silent = false) => {
    if (!silent) setLoading(true);
    setError(false);
    try {
      const res = await authFetch(`${API_BASE}/api/custom-pages/${encodeURIComponent(slug)}`);
      if (!res.ok) {
        setError(true);
        return;
      }
      const data = await res.json();
      setPage(data);
      setBuildPrompt(data.generation_prompt || data.description || data.name || '');
    } catch {
      setError(true);
    } finally {
      if (!silent) setLoading(false);
    }
  }, [slug]);

  useEffect(() => {
    loadPage();
  }, [loadPage]);

  useEffect(() => {
    if (!page) return;
    if (page.build_status !== 'queued' && page.build_status !== 'running') return;
    const timer = window.setInterval(() => {
      loadPage(true);
    }, 2500);
    return () => window.clearInterval(timer);
  }, [page, loadPage]);

  const previewUrl = useMemo(() => {
    if (!page?.entry_file_path) return '';
    const version = page.updated_at || Date.now();
    return `${API_BASE}/api/files/workdir/${page.entry_file_path}?v=${version}`;
  }, [page]);

  const handleRefresh = useCallback(async () => {
    setRefreshing(true);
    try {
      await loadPage(true);
    } finally {
      setRefreshing(false);
    }
  }, [loadPage]);

  const handleGenerate = useCallback(async () => {
    if (!page) return;
    setBuildSubmitting(true);
    try {
      const res = await authFetch(`${API_BASE}/api/custom-pages/${encodeURIComponent(page.slug)}/generate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ prompt: buildPrompt.trim() || page.generation_prompt || page.description || page.name }),
      });
      if (!res.ok) return;
      const data = await res.json();
      if (data.page) {
        setPage(data.page);
      }
      await loadPage(true);
    } finally {
      setBuildSubmitting(false);
    }
  }, [buildPrompt, loadPage, page]);

  const appendLocalEvent = useCallback((label: string, detail: string) => {
    setLocalEvents(prev => [
      { ts: Date.now(), label, detail },
      ...prev,
    ].slice(0, 16));
  }, []);

  const dispatchAction = useCallback(async (
    action: string,
    payload: Record<string, unknown>,
    target: ActionTarget,
  ) => {
    if (!page) return;
    const label = target === 'local' ? '本地动作' : target === 'server' ? '服务动作' : 'Agent 动作';
    appendLocalEvent(label, `${action} -> ${JSON.stringify(payload)}`);

    if (target === 'local') {
      return;
    }

    setInteractionSubmitting(true);
    try {
      const res = await authFetch(`${API_BASE}/api/custom-pages/${encodeURIComponent(page.slug)}/actions`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          action,
          payload,
          target,
          session_id: target === 'agent' ? (currentSessionId || page.last_interaction_session_id || '') : '',
        }),
      });
      if (!res.ok) return;
      const data = await res.json();
      if (target === 'agent' && data.session_id && data.session_id !== currentSessionId) {
        await switchSession(data.session_id);
      }
      await loadPage(true);
    } finally {
      setInteractionSubmitting(false);
    }
  }, [appendLocalEvent, currentSessionId, loadPage, page, switchSession]);

  const resolveActionTarget = useCallback((action: string, explicitTarget?: string): ActionTarget => {
    if (explicitTarget === 'local' || explicitTarget === 'server' || explicitTarget === 'agent') {
      return explicitTarget;
    }
    return runtimeRouting.routes[action] || runtimeRouting.defaultTarget || 'agent';
  }, [runtimeRouting]);

  useEffect(() => {
    const onMessage = async (event: MessageEvent<MiniAppPostMessagePayload>) => {
      const data = event.data;
      if (!data || data.source !== 'agentos-miniapp' || data.slug !== slug) return;

      if (data.kind === 'interaction' && data.action) {
        const target = resolveActionTarget(data.action, typeof data.target === 'string' ? data.target : '');
        await dispatchAction(data.action, (data.payload || {}) as Record<string, unknown>, target);
        return;
      }

      if (data.kind === 'config') {
        const incomingDefault = data.meta?.defaultTarget;
        const nextDefault: ActionTarget =
          incomingDefault === 'local' || incomingDefault === 'server' || incomingDefault === 'agent'
            ? incomingDefault
            : 'agent';
        const nextRoutes = Object.fromEntries(
          Object.entries(data.meta?.routes || {}).filter(([, value]) =>
            value === 'local' || value === 'server' || value === 'agent')
        ) as Record<string, ActionTarget>;
        setRuntimeRouting({
          defaultTarget: nextDefault,
          routes: nextRoutes,
        });
        appendLocalEvent('动作路由', JSON.stringify({ defaultTarget: nextDefault, routes: nextRoutes }));
        return;
      }

      if (data.kind === 'state') {
        appendLocalEvent('页面状态', JSON.stringify(data.payload || {}));
        return;
      }

      if (data.kind === 'log') {
        appendLocalEvent('页面日志', JSON.stringify(data.payload || {}));
      }
    };

    window.addEventListener('message', onMessage);
    return () => window.removeEventListener('message', onMessage);
  }, [appendLocalEvent, dispatchAction, resolveActionTarget, slug]);

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

  const Icon = ICON_MAP[page.icon] || Sparkles;
  const status = formatBuildStatus(page.build_status);
  const latestRun = page.runs?.[0];
  const latestRunIsActive = latestRun?.status === 'queued' || latestRun?.status === 'running' || latestRun?.status === 'failed';
  const showBuildFeed = !currentSessionId && !page.last_interaction_session_id && latestRunIsActive;

  return (
    <DashboardLayout>
      <WorkbenchShell>
        <div className="flex flex-col h-full min-h-0">
          <div className="flex flex-wrap items-center justify-between gap-3 px-4 py-3 border-b border-border/50 bg-muted/20">
            <div className="flex items-center gap-3 min-w-0">
              <div className="w-10 h-10 rounded-2xl bg-primary/10 flex items-center justify-center shrink-0">
                <Icon className="w-5 h-5 text-primary" />
              </div>
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2 mb-1">
                  <span className="text-sm font-semibold text-foreground truncate">{page.name}</span>
                  <Badge variant={status.variant}>{status.label}</Badge>
                  <Badge variant="outline">{page.builder_type === 'acp' ? 'ACP Builder' : 'Builtin Builder'}</Badge>
                  {page.create_dedicated_agent && <Badge variant="outline">专属 Agent</Badge>}
                </div>
                <p className="text-xs text-muted-foreground truncate">
                  {page.description || '由 AgentOS 维护的专属 mini-app 工作区'}
                </p>
              </div>
            </div>

            <div className="flex items-center gap-2">
              <Button variant="outline" size="sm" onClick={handleRefresh} disabled={refreshing}>
                {refreshing ? <Loader2 className="w-4 h-4 animate-spin" /> : <RefreshCw className="w-4 h-4" />}
                <span className="ml-1">刷新</span>
              </Button>
              {previewUrl && (
                <Button variant="outline" size="sm" asChild>
                  <a href={previewUrl} target="_blank" rel="noreferrer">
                    <ExternalLink className="w-4 h-4 mr-1" />
                    打开页面
                  </a>
                </Button>
              )}
            </div>
          </div>

          <ResizablePanelGroup orientation="horizontal" className="flex-1 min-h-0">
            <ResizablePanel defaultSize="63%" minSize="38%" className="min-w-0">
              <Tabs defaultValue="workspace" className="h-full min-h-0">
                <div className="px-4 pt-4">
                  <TabsList>
                    <TabsTrigger value="workspace">工作区</TabsTrigger>
                    <TabsTrigger value="runs">构建记录</TabsTrigger>
                    <TabsTrigger value="details">详情</TabsTrigger>
                  </TabsList>
                </div>

                <TabsContent value="workspace" className="h-full min-h-0 px-4 pb-4">
                  <div className="grid gap-4 md:grid-cols-[1.35fr_0.85fr] mb-4">
                    <Card className="p-4">
                      <div className="flex items-center gap-2 mb-2 text-sm text-muted-foreground">
                        <Workflow className="w-4 h-4" />
                        <span>工作区状态</span>
                      </div>
                      <div className="text-sm text-foreground leading-6">
                        {page.build_summary || '工作区已准备好'}
                      </div>
                      <div className="mt-3 flex flex-wrap gap-2 text-xs text-muted-foreground">
                        <span>Agent: {page.agent_id}</span>
                        <span>工作区: {page.workspace_root || '--'}</span>
                      </div>
                    </Card>

                    <Card className="p-4">
                      <div className="text-sm text-muted-foreground mb-2">最近交互</div>
                      <div className="space-y-2 text-sm">
                        {localEvents.length > 0 ? (
                          localEvents.slice(0, 3).map((event, index) => (
                            <div key={`${event.ts}-${index}`} className="rounded-xl bg-muted/50 px-3 py-2">
                              <div className="font-medium text-foreground">{event.label}</div>
                              <div className="text-muted-foreground break-all">{event.detail}</div>
                            </div>
                          ))
                        ) : (
                          <div className="text-muted-foreground">
                            暂无页面回传事件。点击 mini-app 中的按钮后，这里会显示最近的交互。
                          </div>
                        )}
                      </div>
                    </Card>
                  </div>

                  <Card className="h-[calc(100%-8.5rem)] min-h-[420px] overflow-hidden">
                    {previewUrl ? (
                      <iframe
                        key={previewUrl}
                        src={previewUrl}
                        title={`${page.name} preview`}
                        className="w-full h-full bg-white"
                        sandbox="allow-scripts allow-same-origin allow-forms"
                        data-testid="miniapp-preview"
                      />
                    ) : (
                      <ChatEmptyState page={page} onQuickTask={message => sendMessage(message, undefined, page.agent_id)} />
                    )}
                  </Card>
                </TabsContent>

                <TabsContent value="runs" className="h-full min-h-0 px-4 pb-4">
                  <div className="grid gap-4 lg:grid-cols-[0.95fr_1.05fr] h-full min-h-0">
                    <Card className="p-4">
                      <div className="text-sm font-medium text-foreground mb-2">继续生成 / 重构页面</div>
                      <textarea
                        value={buildPrompt}
                        onChange={e => setBuildPrompt(e.target.value)}
                        rows={10}
                        className="flex w-full rounded-xl border border-input bg-background px-3 py-3 text-sm leading-6 ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 resize-y"
                        placeholder="输入新的构建要求，例如：把这套课程改成更偏口语训练，加入闯关进度和错题回顾。"
                        data-testid="miniapp-build-prompt"
                      />
                      <div className="mt-3 flex items-center gap-2">
                        <Button onClick={handleGenerate} disabled={buildSubmitting} data-testid="miniapp-regenerate-button">
                          {buildSubmitting ? '提交中...' : '重新生成'}
                        </Button>
                        <span className="text-xs text-muted-foreground">
                          如果当前版本不符合预期，可以走这里重新构建；细粒度修改更适合直接在右侧聊天里让 Agent 调整。
                        </span>
                      </div>
                    </Card>

                    <div className="min-h-0 overflow-auto space-y-3">
                      {page.runs && page.runs.length > 0 ? (
                        page.runs.map(run => (
                          <Card key={run.id} className="p-4">
                            <div className="flex items-center justify-between gap-3 mb-3">
                              <div>
                                <div className="font-medium text-foreground">{run.builder_type === 'acp' ? 'ACP 构建任务' : '内置构建任务'}</div>
                                <div className="text-xs text-muted-foreground">
                                  {formatTime(run.started_at_ms)} {run.ended_at_ms ? `→ ${formatTime(run.ended_at_ms)}` : ''}
                                </div>
                              </div>
                              <Badge variant={run.status === 'failed' ? 'destructive' : run.status === 'completed' ? 'default' : run.status === 'running' ? 'secondary' : 'outline'}>
                                {run.status}
                              </Badge>
                            </div>
                            <div className="text-sm text-muted-foreground whitespace-pre-wrap break-words mb-3">
                              {run.prompt}
                            </div>
                            <div className="space-y-2">
                              {(run.logs || []).slice(-8).reverse().map((log, index) => (
                                <div key={`${run.id}-${log.ts}-${index}`} className="rounded-xl bg-muted/40 px-3 py-2 text-sm">
                                  <div className="flex items-center justify-between gap-3 mb-1">
                                    <span className="font-medium text-foreground">{log.level}</span>
                                    <span className="text-xs text-muted-foreground">{formatTime(log.ts)}</span>
                                  </div>
                                  <div className="text-muted-foreground break-words">{log.message}</div>
                                </div>
                              ))}
                            </div>
                          </Card>
                        ))
                      ) : (
                        <Card className="p-4 text-sm text-muted-foreground">
                          还没有构建记录。
                        </Card>
                      )}
                    </div>
                  </div>
                </TabsContent>

                <TabsContent value="details" className="h-full min-h-0 px-4 pb-4">
                  <div className="grid gap-4 lg:grid-cols-[1fr_1fr]">
                    <Card className="p-4">
                      <div className="text-sm font-medium text-foreground mb-3">页面信息</div>
                      <div className="space-y-2 text-sm">
                        <div><span className="text-muted-foreground">Slug：</span><span className="text-foreground">{page.slug}</span></div>
                        <div><span className="text-muted-foreground">Builder：</span><span className="text-foreground">{page.builder_type || 'builtin'}</span></div>
                        <div><span className="text-muted-foreground">来源模式：</span><span className="text-foreground">{page.workspace_mode === 'reuse' ? '复用现有项目' : '从零生成'}</span></div>
                        <div><span className="text-muted-foreground">基础 Agent：</span><span className="text-foreground">{page.base_agent_id || page.agent_id}</span></div>
                        {page.source_project_path && (
                          <div className="break-all"><span className="text-muted-foreground">来源目录：</span><span className="text-foreground">{page.source_project_path}</span></div>
                        )}
                        <div className="break-all"><span className="text-muted-foreground">入口文件：</span><span className="text-foreground">{page.entry_file_path || '--'}</span></div>
                        <div className="break-all"><span className="text-muted-foreground">桥接脚本：</span><span className="text-foreground">{page.bridge_script_path || '--'}</span></div>
                      </div>
                    </Card>

                    <Card className="p-4">
                      <div className="text-sm font-medium text-foreground mb-3">授权与模板</div>
                      <div className="space-y-3">
                        <div>
                          <div className="text-xs uppercase tracking-wide text-muted-foreground mb-2">保留的授权文件</div>
                          {page.preserved_license_files && page.preserved_license_files.length > 0 ? (
                            <div className="space-y-2">
                              {page.preserved_license_files.map(file => (
                                <div key={file} className="rounded-xl bg-muted/40 px-3 py-2 text-sm break-all">
                                  {file}
                                </div>
                              ))}
                            </div>
                          ) : (
                            <div className="text-sm text-muted-foreground">当前工作区没有额外授权文件。</div>
                          )}
                        </div>

                        <div>
                          <div className="text-xs uppercase tracking-wide text-muted-foreground mb-2">快捷模板</div>
                          {page.templates.length > 0 ? (
                            <div className="grid gap-2">
                              {page.templates.map((template, index) => (
                                <button
                                  key={`${template.title}-${index}`}
                                  type="button"
                                  onClick={() => sendMessage(`请围绕「${template.title}」继续改造这个 mini-app。${template.desc || ''}`, undefined, page.agent_id)}
                                  className="rounded-xl border border-border bg-background px-3 py-3 text-left hover:border-primary/30 transition-colors"
                                >
                                  <div className="font-medium text-foreground">{template.title}</div>
                                  {template.desc && <div className="text-sm text-muted-foreground mt-1">{template.desc}</div>}
                                </button>
                              ))}
                            </div>
                          ) : (
                            <div className="text-sm text-muted-foreground">当前没有快捷模板。</div>
                          )}
                        </div>
                      </div>
                    </Card>
                  </div>
                </TabsContent>
              </Tabs>
            </ResizablePanel>

            <ResizableHandle />

            <ResizablePanel defaultSize="37%" minSize="28%" className="min-w-0 border-l border-border/50 bg-background">
              <div className="flex flex-col h-full min-h-0">
                <div className="flex items-center justify-between gap-3 px-4 py-3 border-b border-border/50">
                  <div>
                    <div className="text-sm font-medium text-foreground">专属 Agent</div>
                    <div className="text-xs text-muted-foreground">
                      {interactionSubmitting
                        ? '正在处理来自页面的交互...'
                        : showBuildFeed
                          ? '正在转发当前构建任务的 builder 消息...'
                          : `当前绑定：${page.agent_id}`}
                    </div>
                  </div>
                  <Badge variant="outline">
                    {currentSessionId || page.last_interaction_session_id || latestRun?.id || '新会话'}
                  </Badge>
                </div>
                <div className="flex-1 min-h-0">
                  <ChatPanel
                    defaultAgentId={page.agent_id}
                    hideAgentSelector
                    lockAgent
                    emptyState={
                      showBuildFeed && latestRun ? (
                        <MiniAppBuildFeed
                          agentName={page.name}
                          latestRun={latestRun}
                        />
                      ) : (
                        <ChatEmptyState page={page} onQuickTask={message => sendMessage(message, undefined, page.agent_id)} />
                      )
                    }
                  />
                </div>
              </div>
            </ResizablePanel>
          </ResizablePanelGroup>
        </div>
      </WorkbenchShell>
    </DashboardLayout>
  );
}
