'use client';

import { useState, useEffect, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { DashboardLayout } from '@/components/layout/DashboardLayout';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Card } from '@/components/ui/card';
import { authFetch, API_BASE } from '@/lib/authFetch';
import { useCustomPages } from '@/hooks/useCustomPages';
import {
  Plus, Trash2, ArrowLeft, Sparkles, BookOpen, Zap, Presentation,
  Code, Globe, Music, Image, FileText, Database, Shield,
  Brain, Rocket, Target, Heart, Star, Lightbulb, Puzzle,
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

export default function CreateFeaturePage() {
  const router = useRouter();
  const { refresh: refreshCustomPages } = useCustomPages();

  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [icon, setIcon] = useState('Sparkles');
  const [agentId, setAgentId] = useState('office-main');
  const [systemPrompt, setSystemPrompt] = useState('');
  const [templates, setTemplates] = useState<TemplateItem[]>([
    { title: '', desc: '' },
  ]);
  const [agents, setAgents] = useState<AgentInfo[]>([]);
  const [submitting, setSubmitting] = useState(false);

  const loadAgents = useCallback(async () => {
    try {
      const res = await authFetch(`${API_BASE}/api/agents`);
      const data = await res.json();
      if (Array.isArray(data)) {
        setAgents(data.map((a: Record<string, string>) => ({ id: a.id, name: a.name || a.id })));
      }
    } catch { /* ignore */ }
  }, []);

  useEffect(() => { loadAgents(); }, [loadAgents]);

  const addTemplate = () => setTemplates(prev => [...prev, { title: '', desc: '' }]);
  const removeTemplate = (idx: number) => setTemplates(prev => prev.filter((_, i) => i !== idx));
  const updateTemplate = (idx: number, field: 'title' | 'desc', value: string) => {
    setTemplates(prev => prev.map((t, i) => i === idx ? { ...t, [field]: value } : t));
  };

  const handleSubmit = async () => {
    if (!name.trim()) return;
    setSubmitting(true);
    try {
      const validTemplates = templates.filter(t => t.title.trim());
      const res = await authFetch(`${API_BASE}/api/custom-pages`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: name.trim(),
          description: description.trim(),
          icon,
          agent_id: agentId,
          system_prompt: systemPrompt.trim(),
          templates: validTemplates,
        }),
      });
      const page = await res.json();
      if (page.slug) {
        await refreshCustomPages();
        router.push(`/features/${page.slug}`);
      }
    } catch {
      // ignore
    } finally {
      setSubmitting(false);
    }
  };

  const SelectedIcon = ICON_OPTIONS.find(o => o.name === icon)?.icon || Sparkles;

  return (
    <DashboardLayout>
      <div className="flex-1 overflow-y-auto">
        <div className="max-w-2xl mx-auto px-6 py-8">
          <button
            onClick={() => router.back()}
            className="flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground mb-6 transition-colors"
          >
            <ArrowLeft className="w-4 h-4" />
            返回
          </button>

          <div className="mb-8">
            <h1 className="text-2xl font-bold text-foreground mb-2">创建功能页</h1>
            <p className="text-muted-foreground text-sm">
              自定义一个功能页面，绑定 Agent 和快捷模板，打造属于你的专属工具
            </p>
          </div>

          {/* 预览 */}
          <Card className="p-6 mb-8 bg-gradient-to-br from-primary/5 to-transparent border-primary/20">
            <div className="flex items-center gap-4">
              <div className="w-14 h-14 rounded-2xl bg-primary/10 flex items-center justify-center">
                <SelectedIcon className="w-7 h-7 text-primary" />
              </div>
              <div>
                <h2 className="text-lg font-semibold text-foreground">
                  {name || '功能页名称'}
                </h2>
                <p className="text-sm text-muted-foreground mt-0.5">
                  {description || '在此添加描述...'}
                </p>
              </div>
            </div>
          </Card>

          <div className="space-y-6">
            {/* 名称 */}
            <div className="space-y-2">
              <Label htmlFor="name">名称 *</Label>
              <Input
                id="name"
                value={name}
                onChange={e => setName(e.target.value)}
                placeholder="例如：代码助手、翻译工具、写作助手"
              />
            </div>

            {/* 描述 */}
            <div className="space-y-2">
              <Label htmlFor="desc">描述</Label>
              <textarea
                id="desc"
                value={description}
                onChange={e => setDescription(e.target.value)}
                placeholder="简单描述这个功能页的用途"
                rows={2}
                className="flex w-full rounded-lg border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 resize-none"
              />
            </div>

            {/* 图标 */}
            <div className="space-y-2">
              <Label>图标</Label>
              <div className="grid grid-cols-9 gap-2">
                {ICON_OPTIONS.map(opt => {
                  const Icon = opt.icon;
                  return (
                    <button
                      key={opt.name}
                      onClick={() => setIcon(opt.name)}
                      className={cn(
                        'w-10 h-10 rounded-lg flex items-center justify-center transition-all border',
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
            </div>

            {/* Agent */}
            <div className="space-y-2">
              <Label htmlFor="agent">绑定 Agent</Label>
              <select
                id="agent"
                value={agentId}
                onChange={e => setAgentId(e.target.value)}
                className="flex h-9 w-full rounded-lg border border-input bg-background px-3 py-1 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
              >
                {agents.length > 0 ? (
                  agents.map(a => (
                    <option key={a.id} value={a.id}>{a.name}</option>
                  ))
                ) : (
                  <option value="office-main">office-main</option>
                )}
              </select>
            </div>

            {/* System Prompt */}
            <div className="space-y-2">
              <Label htmlFor="prompt">系统提示词（可选）</Label>
              <textarea
                id="prompt"
                value={systemPrompt}
                onChange={e => setSystemPrompt(e.target.value)}
                placeholder="为这个功能页添加特定的系统指令，Agent 会按照此提示执行任务"
                rows={3}
                className="flex w-full rounded-lg border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 resize-none"
              />
            </div>

            {/* 快捷模板 */}
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <Label>快捷模板</Label>
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
                        placeholder="模板标题"
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

            {/* 提交 */}
            <div className="flex items-center gap-3 pt-4 border-t border-border">
              <Button onClick={handleSubmit} disabled={!name.trim() || submitting}>
                {submitting ? '创建中...' : '创建功能页'}
              </Button>
              <Button variant="outline" onClick={() => router.back()}>
                取消
              </Button>
            </div>
          </div>
        </div>
      </div>
    </DashboardLayout>
  );
}
