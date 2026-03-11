'use client';

import { useState, useEffect } from 'react';
import { Search, Loader2, Sparkles } from 'lucide-react';
import { DashboardLayout } from '@/components/layout/DashboardLayout';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

interface Skill {
  id: string;
  name: string;
  description: string;
  category: string;
  enabled: boolean;
  path: string;
}

export default function SkillsPage() {
  const [searchTerm, setSearchTerm] = useState('');
  const [skills, setSkills] = useState<Skill[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch(`${API_BASE}/api/skills`)
      .then(res => res.json())
      .then(data => setSkills(data))
      .catch(() => setSkills([]))
      .finally(() => setLoading(false));
  }, []);

  const filteredSkills = skills.filter((skill) =>
    skill.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
    skill.description.toLowerCase().includes(searchTerm.toLowerCase())
  );

  return (
    <DashboardLayout>
      <div className="h-full flex flex-col">
        <div className="bg-[#252526] border-b border-[#2d2d30] p-4">
          <div className="flex items-center justify-between mb-4">
            <h1 className="text-xl font-semibold text-[#cccccc]">Skills</h1>
          </div>
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-[#858585]" size={14} />
            <input
              type="text"
              placeholder="Search skills..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="w-full bg-[#3c3c3c] border border-[#5a5a5a] rounded px-9 py-1.5 text-xs text-[#cccccc] placeholder-[#858585] focus:outline-none focus:border-[#007acc]"
            />
          </div>
          <div className="flex gap-6 mt-4 text-sm">
            <div>
              <span className="text-[#858585]">Total: </span>
              <span className="text-[#cccccc]">{skills.length}</span>
            </div>
            <div>
              <span className="text-[#858585]">Enabled: </span>
              <span className="text-green-400">{skills.filter(s => s.enabled).length}</span>
            </div>
          </div>
        </div>

        <div className="flex-1 overflow-auto p-4">
          {loading ? (
            <div className="flex items-center justify-center h-64">
              <Loader2 className="animate-spin text-[#858585]" size={32} />
            </div>
          ) : (
            <div className="space-y-2">
              {filteredSkills.map((skill) => (
                <div key={skill.id} className="bg-[#252526] border border-[#2d2d30] rounded p-3 hover:border-[#3e3e42] transition-colors">
                  <div className="flex items-start gap-3">
                    <div className="p-1.5 bg-[#1e1e1e] rounded">
                      <Sparkles size={20} className="text-[#007acc]" />
                    </div>
                    <div className="flex-1">
                      <div className="flex items-center gap-2 mb-1">
                        <h3 className="text-sm font-medium text-[#cccccc]">{skill.name}</h3>
                        <span className="px-1.5 py-0.5 rounded text-xs bg-purple-500/20 text-purple-400">
                          {skill.category}
                        </span>
                      </div>
                      <p className="text-xs text-[#858585]">{skill.description}</p>
                    </div>
                    <div className={`w-2 h-2 rounded-full mt-2 ${skill.enabled ? 'bg-green-500' : 'bg-gray-500'}`} />
                  </div>
                </div>
              ))}
              {filteredSkills.length === 0 && (
                <p className="text-sm text-[#858585] text-center py-8">No skills found</p>
              )}
            </div>
          )}
        </div>
      </div>
    </DashboardLayout>
  );
}
