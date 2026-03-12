'use client';

import { useState, useEffect, useCallback } from 'react';
import { Search, Loader2 } from 'lucide-react';
import { SkillCard } from './SkillCard';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

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
}

export function InstalledTab() {
  const [skills, setSkills] = useState<InstalledSkill[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchTerm, setSearchTerm] = useState('');

  const fetchSkills = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/api/skills`);
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
    fetch(`${API_BASE}/api/skills/check-updates`, { method: 'POST' })
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
    await fetch(`${API_BASE}/api/skills/${name}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ enabled }),
    });
    fetchSkills();
  };

  const handleUninstall = async (name: string) => {
    if (!confirm(`确定卸载 ${name}？`)) return;
    await fetch(`${API_BASE}/api/skills/${name}`, { method: 'DELETE' });
    fetchSkills();
  };

  const handleUpdate = async (name: string) => {
    await fetch(`${API_BASE}/api/skills/${name}/update`, { method: 'POST' });
    fetchSkills();
  };

  const filtered = skills.filter(s =>
    s.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
    s.description.toLowerCase().includes(searchTerm.toLowerCase())
  );

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="animate-spin text-[#858585]" size={32} />
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-[#858585]" size={16} />
          <input
            className="w-full bg-[#3c3c3c] border border-[#2d2d30] rounded pl-9 pr-3 py-2 text-sm text-[#cccccc] placeholder-[#858585] focus:border-[#007acc] focus:outline-none"
            placeholder="搜索已安装的 skills..."
            value={searchTerm}
            onChange={e => setSearchTerm(e.target.value)}
          />
        </div>
        <span className="text-sm text-[#858585]">
          共 {skills.length} 个 / 启用 {skills.filter(s => s.enabled).length} 个
        </span>
      </div>

      <div className="space-y-2">
        {filtered.length === 0 ? (
          <div className="text-center text-[#858585] py-8">无匹配结果</div>
        ) : (
          filtered.map(skill => (
            <SkillCard
              key={skill.id}
              name={skill.name}
              description={skill.description}
              source={skill.source}
              version={skill.version}
              enabled={skill.enabled}
              hasUpdate={skill.has_update}
              onToggle={enabled => handleToggle(skill.name, enabled)}
              onUninstall={() => handleUninstall(skill.name)}
              onUpdate={() => handleUpdate(skill.name)}
            />
          ))
        )}
      </div>
    </div>
  );
}
