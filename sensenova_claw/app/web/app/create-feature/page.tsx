'use client';

import { useState, useEffect, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { DashboardLayout } from '@/components/layout/DashboardLayout';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Card } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { authFetch, API_BASE } from '@/lib/authFetch';
import { useCustomPages } from '@/hooks/useCustomPages';
import {
  Plus, Trash2, ArrowLeft, Sparkles, BookOpen, Zap, Presentation,
  Code, Globe, Music, Image, FileText, Database, Shield,
  Brain, Rocket, Target, Heart, Star, Lightbulb, Puzzle, Workflow,
} from 'lucide-react';
import { cn } from '@/lib/utils';

const ICON_OPTIONS = [
  { name: 'Sparkles', icon: Sparkles },
  { name: 'BookOpen', icon: BookOpen },
  { name: 'Zap', icon: Zap },
  { name: 'Presentation', icon: Presentation },
  { name: 'Code', icon: Code },
  { name: 'Globe', icon: Globe },
  { name: 'Music', icon: Music },
  { name: 'Image', icon: Image },
  { name: 'FileText', icon: FileText },
  { name: 'Database', icon: Database },
  { name: 'Shield', icon: Shield },
  { name: 'Brain', icon: Brain },
  { name: 'Rocket', icon: Rocket },
  { name: 'Target', icon: Target },
  { name: 'Heart', icon: Heart },
  { name: 'Star', icon: Star },
  { name: 'Lightbulb', icon: Lightbulb },
  { name: 'Puzzle', icon: Puzzle },
];

interface AgentInfo {
  id: string;
  name: string;
}

interface TemplateItem {
  title: string;
  desc: string;
}

type WorkspaceMode = 'scratch' | 'reuse';
type BuilderType = 'builtin' | 'acp';

export default function CreateFeaturePage() {
  const router = useRouter();
  const { refresh: refreshCustomPages } = useCustomPages();

  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [generationPrompt, setGenerationPrompt] = useState('');
  const [icon, setIcon] = useState('Sparkles');
  const [agentId, setAgentId] = useState('default');
  const [createDedicatedAgent, setCreateDedicatedAgent] = useState(true);
  const [workspaceMode, setWorkspaceMode] = useState<WorkspaceMode>('scratch');
  const [sourceProjectPath, setSourceProjectPath] = useState('');
  const [builderType, setBuilderType] = useState<BuilderType>('builtin');
  const [systemPrompt, setSystemPrompt] = useState('');
  const [templates, setTemplates] = useState<TemplateItem[]>([
    { title: '', desc: '' },
  ]);
  const [agents, setAgents] = useState<AgentInfo[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState('');

  const loadAgents = useCallback(async () => {
    try {
      const res = await authFetch(`${API_BASE}/api/agents`);
      const data = await res.json();
      if (Array.isArray(data)) {
        const nextAgents = data.map((a: Record<string, string>) => ({ id: a.id, name: a.name || a.id }));
        setAgents(nextAgents);
        if (nextAgents.length > 0 && !nextAgents.some(agent => agent.id === agentId)) {
          setAgentId(nextAgents[0].id);
        }
      }
    } catch {
      // ignore
    }
  }, [agentId]);

  useEffect(() => {
    loadAgents();
  }, [loadAgents]);

  const addTemplate = () => setTemplates(prev => [...prev, { title: '', desc: '' }]);
  const removeTemplate = (idx: number) => setTemplates(prev => prev.filter((_, i) => i !== idx));
  const updateTemplate = (idx: number, field: 'title' | 'desc', value: string) => {
    setTemplates(prev => prev.map((t, i) => (i === idx ? { ...t, [field]: value } : t)));
  };

  const handleSubmit = async () => {
    if (!name.trim()) return;
    setSubmitError('');
    setSubmitting(true);
    try {
      const validTemplates = templates.filter(t => t.title.trim());
      const res = await authFetch(`${API_BASE}/api/custom-pages`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: name.trim(),
          description: description.trim(),
          generation_prompt: generationPrompt.trim() || description.trim() || name.trim(),
          icon,
          agent_id: agentId,
          create_dedicated_agent: createDedicatedAgent,
          workspace_mode: workspaceMode,
          source_project_path: workspaceMode === 'reuse' ? sourceProjectPath.trim() : '',
          builder_type: builderType,
          system_prompt: systemPrompt.trim(),
          templates: validTemplates,
        }),
      });
      const page = await res.json();
      if (!res.ok) {
        setSubmitError(page.detail || page.message || '创建失败');
        return;
      }
      if (page.slug) {
        await refreshCustomPages();
        router.push(`/features/${page.slug}`);
      }
    } catch {
      setSubmitError('创建失败，请检查后端服务或输入内容');
    } finally {
      setSubmitting(false);
    }
  };

  const SelectedIcon = ICON_OPTIONS.find(o => o.name === icon)?.icon || Sparkles;

  return (
    <DashboardLayout>
      <div className="flex-1 overflow-y-auto">
        <div className="max-w-4xl mx-auto px-6 py-8">
          <button
            onClick={() => router.back()}
            className="flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground mb-6 transition-colors"
          >
            <ArrowLeft className="w-4 h-4" />
            返回
          </button>

          <Card className="p-7 mb-8 border-primary/20 bg-[radial-gradient(circle_at_top_left,_rgba(56,189,248,0.16),_transparent_32%),radial-gradient(circle_at_bottom_right,_rgba(16,185,129,0.16),_transparent_28%)]">
            <div className="flex flex-col gap-5 md:flex-row md:items-center md:justify-between">
              <div className="flex items-center gap-4">
                <div className="w-16 h-16 rounded-3xl bg-primary/10 flex items-center justify-center border border-primary/20">
                  <SelectedIcon className="w-8 h-8 text-primary" />
                </div>
                <div>
                  <div className="flex items-center gap-2 mb-2">
                    <Badge variant="secondary">Mini-App</Badge>
                    <Badge variant="outline">{workspaceMode === 'scratch' ? '从零生成' : '复用现有项目'}</Badge>
                    <Badge variant="outline">{builderType === 'builtin' ? '内置构建' : 'ACP 构建'}</Badge>
                  </div>
                  <h1 className="text-2xl font-bold text-foreground mb-1">
                    {name || '创建专属 Mini-App 工作区'}
                  </h1>
                  <p className="text-sm text-muted-foreground max-w-2xl">
                    {description || '让 AI 为你生成一个自带 Web 服务端的 workspace。大部分交互在 workspace 自己的前后端内完成，Agent 只做最后兜底和后台补货。'}
                  </p>
                </div>
              </div>
              <div className="flex items-center gap-2 text-sm text-muted-foreground">
                <Workflow className="w-4 h-4" />
                <span>{createDedicatedAgent ? '将创建专属 Agent' : '复用现有 Agent'}</span>
              </div>
            </div>
          </Card>

          <div className="grid gap-8 lg:grid-cols-[1.35fr_0.85fr]">
            <div className="space-y-6">
              <div className="space-y-2">
                <Label htmlFor="name">工作区名称 *</Label>
                <Input
                  id="name"
                  value={name}
                  onChange={e => setName(e.target.value)}
                  placeholder="例如：语言教练、销售作战台、研究任务板"
                  data-testid="miniapp-name-input"
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="desc">用途描述</Label>
                <textarea
                  id="desc"
                  value={description}
                  onChange={e => setDescription(e.target.value)}
                  placeholder="描述这个 mini-app 要服务的场景、用户和目标"
                  rows={3}
                  className="flex w-full rounded-lg border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 resize-none"
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="goal">给 AI 的构建要求</Label>
                <textarea
                  id="goal"
                  value={generationPrompt}
                  onChange={e => setGenerationPrompt(e.target.value)}
                  placeholder="例如：做一个自带 server 的学习工作区，预先准备 3 个单元；用户完成单元只记录到服务端；普通问答点按钮才发给 Agent，且不触发即时刷新；夜间再后台补充下一批内容。"
                  rows={6}
                  className="flex w-full rounded-xl border border-input bg-background px-3 py-3 text-sm leading-6 ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 resize-y"
                  data-testid="miniapp-prompt-input"
                />
              </div>

              <div className="grid gap-6 md:grid-cols-2">
                <div className="space-y-3">
                  <Label>工作区来源</Label>
                  <div className="grid gap-3">
                    <button
                      type="button"
                      onClick={() => setWorkspaceMode('scratch')}
                      className={cn(
                        'rounded-2xl border p-4 text-left transition-colors',
                        workspaceMode === 'scratch'
                          ? 'border-primary bg-primary/5'
                          : 'border-border hover:border-primary/30'
                      )}
                    >
                      <div className="font-medium text-foreground mb-1">从零生成</div>
                      <p className="text-sm text-muted-foreground">由 AI 直接生成全新的 workspace 前端、服务端接口与持久化状态结构。</p>
                    </button>
                    <button
                      type="button"
                      onClick={() => setWorkspaceMode('reuse')}
                      className={cn(
                        'rounded-2xl border p-4 text-left transition-colors',
                        workspaceMode === 'reuse'
                          ? 'border-primary bg-primary/5'
                          : 'border-border hover:border-primary/30'
                      )}
                    >
                      <div className="font-medium text-foreground mb-1">复用现有项目</div>
                      <p className="text-sm text-muted-foreground">复制已有目录并保留 LICENSE / NOTICE，再由 Agent 继续改造。</p>
                    </button>
                  </div>
                </div>

                <div className="space-y-3">
                  <Label>构建执行方式</Label>
                  <div className="grid gap-3">
                    <button
                      type="button"
                      onClick={() => setBuilderType('builtin')}
                      className={cn(
                        'rounded-2xl border p-4 text-left transition-colors',
                        builderType === 'builtin'
                          ? 'border-primary bg-primary/5'
                          : 'border-border hover:border-primary/30'
                      )}
                    >
                      <div className="font-medium text-foreground mb-1">内置构建</div>
                      <p className="text-sm text-muted-foreground">立即生成可运行的 client-server 初版，包含 `server.py`、状态存储与独立预览。</p>
                    </button>
                    <button
                      type="button"
                      onClick={() => setBuilderType('acp')}
                      className={cn(
                        'rounded-2xl border p-4 text-left transition-colors',
                        builderType === 'acp'
                          ? 'border-primary bg-primary/5'
                          : 'border-border hover:border-primary/30'
                      )}
                    >
                      <div className="font-medium text-foreground mb-1">ACP 构建</div>
                      <p className="text-sm text-muted-foreground">交给 Claude Code / Codex 一类 ACP coding agent 在后台编写完整 workspace 前后端。</p>
                    </button>
                  </div>
                </div>
              </div>

              {workspaceMode === 'reuse' && (
                <div className="space-y-2">
                  <Label htmlFor="sourceProjectPath">现有项目路径</Label>
                  <Input
                    id="sourceProjectPath"
                    value={sourceProjectPath}
                    onChange={e => setSourceProjectPath(e.target.value)}
                    placeholder="/absolute/path/to/project"
                    data-testid="miniapp-source-path-input"
                  />
                  <p className="text-xs text-muted-foreground">
                    会复制目录内容到 mini-app 工作区；外层仍会补上统一的 workspace server 入口，并自动保留检测到的 LICENSE / NOTICE 文件。
                  </p>
                </div>
              )}

              <div className="space-y-2">
                <Label htmlFor="agent">基础 Agent 配置</Label>
                <select
                  id="agent"
                  value={agentId}
                  onChange={e => setAgentId(e.target.value)}
                  className="flex h-10 w-full rounded-lg border border-input bg-background px-3 py-1 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
                >
                  {agents.length > 0 ? (
                    agents.map(a => (
                      <option key={a.id} value={a.id}>{a.name}</option>
                    ))
                  ) : (
                    <option value="default">default</option>
                  )}
                </select>
                <label className="flex items-start gap-3 rounded-2xl border border-border p-4 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={createDedicatedAgent}
                    onChange={e => setCreateDedicatedAgent(e.target.checked)}
                    className="mt-1"
                  />
                  <div>
                    <div className="font-medium text-foreground">创建专属 Agent</div>
                    <p className="text-sm text-muted-foreground">
                      推荐开启。系统会复制上面所选 Agent 的模型、工具和技能配置，并把整个 workspace 根目录设为它的工作目录。
                    </p>
                  </div>
                </label>
              </div>

              <div className="space-y-2">
                <Label htmlFor="prompt">附加系统提示词（可选）</Label>
                <textarea
                  id="prompt"
                  value={systemPrompt}
                  onChange={e => setSystemPrompt(e.target.value)}
                  placeholder="补充这个 workspace 的业务规则、刷新策略、是否需要夜间 cron、哪些交互必须留在本地或服务端解决"
                  rows={3}
                  className="flex w-full rounded-lg border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 resize-none"
                />
              </div>

              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <Label>可直接触发的模板动作</Label>
                  <Button variant="ghost" size="sm" onClick={addTemplate}>
                    <Plus className="w-4 h-4 mr-1" />
                    添加
                  </Button>
                </div>
                <div className="space-y-3">
                  {templates.map((tmpl, i) => (
                    <Card key={i} className="p-4 relative group">
                      <div className="space-y-2">
                        <Input
                          value={tmpl.title}
                          onChange={e => updateTemplate(i, 'title', e.target.value)}
                          placeholder="模板标题，例如：开始今天的英语课"
                          className="text-sm"
                        />
                        <Input
                          value={tmpl.desc}
                          onChange={e => updateTemplate(i, 'desc', e.target.value)}
                          placeholder="简短描述（可选）"
                          className="text-sm"
                        />
                      </div>
                      {templates.length > 1 && (
                        <button
                          onClick={() => removeTemplate(i)}
                          className="absolute top-2 right-2 text-muted-foreground hover:text-destructive opacity-0 group-hover:opacity-100 transition-opacity"
                        >
                          <Trash2 className="w-4 h-4" />
                        </button>
                      )}
                    </Card>
                  ))}
                </div>
              </div>

              {submitError && (
                <div className="rounded-xl border border-destructive/30 bg-destructive/5 px-4 py-3 text-sm text-destructive">
                  {submitError}
                </div>
              )}

              <div className="flex items-center gap-3 pt-4 border-t border-border">
                <Button onClick={handleSubmit} disabled={!name.trim() || submitting} data-testid="miniapp-create-button">
                  {submitting ? '创建中...' : '创建 Mini-App 工作区'}
                </Button>
                <Button variant="outline" onClick={() => router.back()}>
                  取消
                </Button>
              </div>
            </div>

            <div className="space-y-6">
              <Card className="p-5">
                <h2 className="text-base font-semibold mb-4">图标</h2>
                <div className="grid grid-cols-6 gap-2">
                  {ICON_OPTIONS.map(opt => {
                    const Icon = opt.icon;
                    return (
                      <button
                        key={opt.name}
                        type="button"
                        onClick={() => setIcon(opt.name)}
                        className={cn(
                          'w-11 h-11 rounded-xl flex items-center justify-center transition-all border',
                          icon === opt.name
                            ? 'bg-primary/10 border-primary text-primary'
                            : 'bg-muted/30 border-transparent text-muted-foreground hover:bg-muted hover:text-foreground'
                        )}
                      >
                        <Icon className="w-5 h-5" />
                      </button>
                    );
                  })}
                </div>
              </Card>

              <Card className="p-5">
                <h2 className="text-base font-semibold mb-4">创建后会发生什么</h2>
                <div className="space-y-3 text-sm text-muted-foreground">
                  <p>1. 后端会为你创建一个 workspace 目录，默认包含 `app/` 前端与 `server.py` 服务端入口。</p>
                  <p>2. 如果启用了专属 Agent，它会把整个 workspace 根目录当成自己的主工作目录，而不只是单个前端页面目录。</p>
                  <p>3. 生成 prompt 会强制要求：优先本地/服务端处理交互、Agent 作为最后兜底、普通问答不默认触发刷新、可选夜间 cron/后台补货。</p>
                  <p>4. 如果你选择 ACP，后台还会记录构建日志，方便追踪 Claude Code / Codex 如何编写这个 workspace 的前后端。</p>
                </div>
              </Card>

              <Card className="p-5">
                <h2 className="text-base font-semibold mb-3">预览摘要</h2>
                <div className="space-y-2 text-sm">
                  <div className="flex justify-between gap-4">
                    <span className="text-muted-foreground">工作区名称</span>
                    <span className="text-right text-foreground">{name || '未填写'}</span>
                  </div>
                  <div className="flex justify-between gap-4">
                    <span className="text-muted-foreground">执行方式</span>
                    <span className="text-right text-foreground">{builderType === 'builtin' ? '内置构建' : 'ACP 构建'}</span>
                  </div>
                  <div className="flex justify-between gap-4">
                    <span className="text-muted-foreground">目录来源</span>
                    <span className="text-right text-foreground">{workspaceMode === 'scratch' ? '从零生成' : '复用现有项目'}</span>
                  </div>
                  <div className="flex justify-between gap-4">
                    <span className="text-muted-foreground">Agent 策略</span>
                    <span className="text-right text-foreground">{createDedicatedAgent ? '专属 Agent' : '复用现有 Agent'}</span>
                  </div>
                </div>
              </Card>
            </div>
          </div>
        </div>
      </div>
    </DashboardLayout>
  );
}
