'use client';

import { useState, useEffect } from 'react';
import { Search, Loader2, Shield, ShieldAlert, ShieldCheck } from 'lucide-react';
import { DashboardLayout } from '@/components/layout/DashboardLayout';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

interface Tool {
  id: string;
  name: string;
  description: string;
  category: string;
  riskLevel: string;
  enabled: boolean;
  parameters: Record<string, unknown>;
}

const riskIcons: Record<string, React.ElementType> = {
  low: ShieldCheck,
  medium: Shield,
  high: ShieldAlert,
};

const riskColors: Record<string, string> = {
  low: 'text-green-400 bg-green-400/20',
  medium: 'text-yellow-400 bg-yellow-400/20',
  high: 'text-red-400 bg-red-400/20',
};

export default function ToolsPage() {
  const [searchTerm, setSearchTerm] = useState('');
  const [tools, setTools] = useState<Tool[]>([]);
  const [loading, setLoading] = useState(true);
  const [expandedTools, setExpandedTools] = useState<Set<string>>(new Set());

  useEffect(() => {
    fetchTools();
  }, []);

  const fetchTools = () => {
    fetch(`${API_BASE}/api/tools`)
      .then(res => res.json())
      .then(data => setTools(data))
      .catch(() => setTools([]))
      .finally(() => setLoading(false));
  };

  const toggleEnabled = async (toolName: string, currentEnabled: boolean) => {
    const newEnabled = !currentEnabled;
    setTools(prev => prev.map(t => t.name === toolName ? { ...t, enabled: newEnabled } : t));
    try {
      await fetch(`${API_BASE}/api/tools/${toolName}/enabled`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ enabled: newEnabled }),
      });
    } catch {
      setTools(prev => prev.map(t => t.name === toolName ? { ...t, enabled: currentEnabled } : t));
    }
  };

  const filteredTools = tools.filter((tool) =>
    tool.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
    tool.description.toLowerCase().includes(searchTerm.toLowerCase())
  );

  const enabledCount = tools.filter(t => t.enabled).length;

  return (
    <DashboardLayout>
      <div className="h-full flex flex-col">
        <div className="bg-[#252526] border-b border-[#2d2d30] p-4">
          <div className="flex items-center justify-between mb-4">
            <h1 className="text-xl font-semibold text-[#cccccc]">Tools</h1>
          </div>
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-[#858585]" size={14} />
            <input
              type="text"
              placeholder="Search tools..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="w-full bg-[#3c3c3c] border border-[#5a5a5a] rounded px-9 py-1.5 text-xs text-[#cccccc] placeholder-[#858585] focus:outline-none focus:border-[#007acc]"
            />
          </div>
          <div className="flex gap-6 mt-4 text-sm">
            <div>
              <span className="text-[#858585]">Total: </span>
              <span className="text-[#cccccc]">{tools.length}</span>
            </div>
            <div>
              <span className="text-[#858585]">Enabled: </span>
              <span className="text-green-400">{enabledCount}</span>
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
              {filteredTools.map((tool) => {
                const RiskIcon = riskIcons[tool.riskLevel] || Shield;
                const riskColor = riskColors[tool.riskLevel] || 'text-gray-400 bg-gray-400/20';
                const isExpanded = expandedTools.has(tool.id);

                return (
                  <div key={tool.id} className="bg-[#252526] border border-[#2d2d30] rounded p-3 hover:border-[#3e3e42] transition-colors">
                    <div className="flex items-start gap-3">
                      <div className="flex flex-col items-center gap-2">
                        <div className="p-1.5 bg-[#1e1e1e] rounded">
                          <RiskIcon size={20} className="text-[#007acc]" />
                        </div>
                        {Object.keys(tool.parameters).length > 0 && (
                          <button
                            onClick={() => setExpandedTools(prev => {
                              const s = new Set(prev);
                              isExpanded ? s.delete(tool.id) : s.add(tool.id);
                              return s;
                            })}
                            className="text-xs text-[#007acc] hover:underline whitespace-nowrap"
                          >
                            {isExpanded ? 'Hide' : 'Params'}
                          </button>
                        )}
                      </div>
                      <div className="flex-1">
                        <div className="flex items-center gap-2 mb-1">
                          <h3 className="text-sm font-medium text-[#cccccc]">{tool.name}</h3>
                          <span className={`px-1.5 py-0.5 rounded text-xs ${riskColor}`}>
                            {tool.riskLevel}
                          </span>
                        </div>
                        <p className="text-xs text-[#858585]">{tool.description}</p>

                        {isExpanded && Object.keys(tool.parameters).length > 0 && (
                          <div className="mt-2 p-2 bg-[#1e1e1e] rounded border border-[#2d2d30]">
                            <div className="text-xs text-[#858585] mb-1">Parameters:</div>
                            <pre className="text-xs text-[#858585] font-mono overflow-auto">
                              {JSON.stringify(tool.parameters, null, 2)}
                            </pre>
                          </div>
                        )}
                      </div>
                      <label className="relative inline-flex items-center cursor-pointer shrink-0">
                        <input
                          type="checkbox"
                          checked={tool.enabled}
                          onChange={() => toggleEnabled(tool.name, tool.enabled)}
                          className="sr-only peer"
                        />
                        <div className="w-9 h-5 bg-[#3c3c3c] peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-[#858585] after:rounded-full after:h-4 after:w-4 after:transition-all peer-checked:bg-[#0e639c] peer-checked:after:bg-white pointer-events-none" />
                      </label>
                    </div>
                  </div>
                );
              })}
              {filteredTools.length === 0 && (
                <p className="text-sm text-[#858585] text-center py-8">No tools found</p>
              )}
            </div>
          )}
        </div>
      </div>
    </DashboardLayout>
  );
}
