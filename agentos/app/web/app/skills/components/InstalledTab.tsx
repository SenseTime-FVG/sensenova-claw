'use client';

import { useState, useEffect, useCallback } from 'react';
import { Search, Loader2 } from 'lucide-react';
import { SkillCard } from './SkillCard';
import { SkillDetailModal } from './SkillDetailModal';
import { Input } from '@/components/ui/input';
import { authFetch, API_BASE } from '@/lib/authFetch';

interface InstalledSkill {
  id: string;
  name: string;
  description: string;
  category: string;
  enabled: boolean;
  source: string;
  version: string | null;
  has_update: boolean;
  update_version: string | null;
  dependencies: Record<string, boolean> | null;
  all_deps_met: boolean;
}

const categoryLabels: Record<string, string> = {
  builtin: '内置',
  workspace: '工作区',
  installed: '已安装',
};

const categoryOrder = ['builtin', 'installed', 'workspace'];

interface InstalledTabProps {
  categoryFilter?: string;
}

export function InstalledTab({ categoryFilter }: InstalledTabProps) {
  const [skills, setSkills] = useState<InstalledSkill[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchTerm, setSearchTerm] = useState('');
  const [detailModal, setDetailModal] = useState<{ name: string } | null>(null);

  const fetchSkills = useCallback(async () => {
    try {
      const res = await authFetch(`${API_BASE}/api/skills`);
      const data = await res.json();
      setSkills(data);
    } catch {
      setSkills([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchSkills(); }, [fetchSkills]);

  // 检查更新
  useEffect(() => {
    authFetch(`${API_BASE}/api/skills/check-updates`, { method: 'POST' })
      .then(r => r.json())
      .then(data => {
        const updateMap = new Map(
          // eslint-disable-next-line @typescript-eslint/no-explicit-any
          (data.updates || []).map((u: any) => [u.skill_name, u.latest_version])
        );
        setSkills(prev => prev.map(s => ({
          ...s,
          has_update: updateMap.has(s.name),
          update_version: (updateMap.get(s.name) as string) || null,
        })));
      })
      .catch(() => {});
  }, []);

  const handleToggle = async (name: string, enabled: boolean) => {
    await authFetch(`${API_BASE}/api/skills/${name}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ enabled }),
    });
    fetchSkills();
  };

  const handleUninstall = async (name: string) => {
    if (!confirm(`确定卸载 ${name}？`)) return;
    await authFetch(`${API_BASE}/api/skills/${name}`, { method: 'DELETE' });
    fetchSkills();
  };

  const handleUpdate = async (name: string) => {
    await authFetch(`${API_BASE}/api/skills/${name}/update`, { method: 'POST' });
    fetchSkills();
  };

  // 过滤
  let filtered = skills.filter(s =>
    s.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
    s.description.toLowerCase().includes(searchTerm.toLowerCase())
  );
  if (categoryFilter) {
    filtered = filtered.filter(s => s.category === categoryFilter);
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 className="animate-spin text-muted-foreground" size={32} />
      </div>
    );
  }

  // 按 category 分组
  const grouped = categoryOrder
    .map(cat => ({
      category: cat,
      label: categoryLabels[cat] || cat,
      items: filtered.filter(s => s.category === cat),
    }))
    .filter(g => g.items.length > 0);

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <div className="relative flex-1 max-w-sm">
          <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
          <Input
            className="pl-8 bg-background"
            placeholder="Filter installed skills..."
            value={searchTerm}
            onChange={e => setSearchTerm(e.target.value)}
          />
        </div>
        <span className="text-sm text-muted-foreground">
          Total: {skills.length} / Enabled: {skills.filter(s => s.enabled).length}
        </span>
      </div>

      {grouped.length === 0 ? (
        <div className="text-center text-muted-foreground py-12 border border-dashed rounded-lg bg-muted/10">No matching skills found.</div>
      ) : (
        grouped.map(group => (
          <div key={group.category} className="space-y-3">
            <h3 className="text-sm font-semibold text-muted-foreground pb-2 border-b">
              {group.label} ({group.items.length})
            </h3>
            <div className="grid gap-3 grid-cols-1 md:grid-cols-2 lg:grid-cols-3">
              {group.items.map(skill => (
                <SkillCard
                  key={skill.id}
                  name={skill.name}
                  description={skill.description}
                  category={skill.category}
                  source={skill.source}
                  version={skill.version}
                  enabled={skill.enabled}
                  hasUpdate={skill.has_update}
                  dependencies={skill.dependencies}
                  allDepsMet={skill.all_deps_met}
                  onToggle={enabled => handleToggle(skill.name, enabled)}
                  onUninstall={() => handleUninstall(skill.name)}
                  onUpdate={() => handleUpdate(skill.name)}
                  onClick={() => setDetailModal({ name: skill.name })}
                />
              ))}
            </div>
          </div>
        ))
      )}

      {/* 本地 skill 详情弹窗 */}
      {detailModal && (
        <SkillDetailModal
          source="local"
          skillId={detailModal.name}
          onClose={() => setDetailModal(null)}
          installed
        />
      )}
    </div>
  );
}
