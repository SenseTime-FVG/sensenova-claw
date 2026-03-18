'use client';

import { useState, useEffect } from 'react';
import { Search, Loader2, Shield, ShieldAlert, ShieldCheck, Wrench } from 'lucide-react';
import { DashboardLayout } from '@/components/layout/DashboardLayout';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { authFetch, API_BASE } from '@/lib/authFetch';

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

export default function ToolsPage() {
  const [searchTerm, setSearchTerm] = useState('');
  const [tools, setTools] = useState<Tool[]>([]);
  const [loading, setLoading] = useState(true);
  const [expandedTools, setExpandedTools] = useState<Set<string>>(new Set());

  useEffect(() => {
    fetchTools();
  }, []);

  const fetchTools = () => {
    authFetch(`${API_BASE}/api/tools`)
      .then(res => res.json())
      .then(data => setTools(data))
      .catch(() => setTools([]))
      .finally(() => setLoading(false));
  };

  const toggleEnabled = async (toolName: string, currentEnabled: boolean) => {
    const newEnabled = !currentEnabled;
    setTools(prev => prev.map(t => t.name === toolName ? { ...t, enabled: newEnabled } : t));
    try {
      await authFetch(`${API_BASE}/api/tools/${toolName}/enabled`, {
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
      <div className="flex-1 space-y-8 p-10 lg:p-12">
        <div className="flex items-center justify-between space-y-2">
          <h2 className="text-4xl font-extrabold tracking-tight text-foreground/90">Tools Workspace</h2>
        </div>

        <div className="flex flex-col md:flex-row gap-8 mt-10">
          {/* Nested Sidebar */}
          <aside className="w-full md:w-64 lg:w-72 shrink-0">
            <nav className="flex space-x-2 md:flex-col md:space-x-0 md:space-y-2">
               <p className="text-[10px] font-black uppercase tracking-[0.2em] text-muted-foreground/70 mb-2 px-4">Management</p>
               <button className="flex items-center gap-3 font-bold justify-start w-full text-base px-5 py-3.5 rounded-xl transition-all border border-transparent bg-primary text-primary-foreground shadow-lg shadow-primary/20">
                  <Wrench className="h-5 w-5" /> Tool Registry
               </button>
               <button className="flex items-center gap-3 font-bold justify-start w-full text-base px-5 py-3.5 rounded-xl transition-all border border-transparent text-muted-foreground hover:bg-muted hover:text-foreground opacity-60">
                  <ShieldCheck className="h-5 w-5" /> Safety Configs
               </button>
            </nav>
          </aside>

          {/* Main Content Area */}
          <div className="flex-1 space-y-8">
            <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
              <Card className="shadow-lg border-border/60">
                <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-3">
                  <CardTitle className="text-sm font-bold text-muted-foreground uppercase tracking-wider">Functional Units</CardTitle>
                  <Wrench className="h-5 w-5 text-primary" />
                </CardHeader>
                <CardContent>
                  <div className="text-4xl font-black">{tools.length}</div>
                  <p className="text-sm font-medium text-muted-foreground mt-2">Registered tool modules</p>
                </CardContent>
              </Card>
              <Card className="shadow-lg border-border/60">
                <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-3">
                  <CardTitle className="text-sm font-bold text-muted-foreground uppercase tracking-wider">Active Safety</CardTitle>
                  <ShieldCheck className="h-5 w-5 text-green-500" />
                </CardHeader>
                <CardContent>
                  <div className="text-4xl font-black text-green-600 dark:text-green-500">{enabledCount}</div>
                  <p className="text-sm font-medium text-muted-foreground mt-2">Enabled and verified</p>
                </CardContent>
              </Card>
            </div>

            <Card className="shadow-xl border-border/80 overflow-hidden">
              <CardHeader className="bg-muted/30 border-b p-8">
                <div className="flex flex-col md:flex-row md:items-center justify-between gap-6">
                  <div>
                    <CardTitle className="text-2xl font-bold">Available Tools</CardTitle>
                    <CardDescription className="text-base mt-2">
                       Manage and configure the tools available to your agents.
                    </CardDescription>
                  </div>
                  <div className="relative w-full md:w-96">
                    <Search className="absolute left-4 top-4 h-5 w-5 text-muted-foreground" />
                    <Input
                      type="text"
                      placeholder="Search tools..."
                      value={searchTerm}
                      onChange={(e) => setSearchTerm(e.target.value)}
                      className="pl-12 py-7 text-base bg-background rounded-2xl shadow-inner border-border/60"
                    />
                  </div>
                </div>
              </CardHeader>
              <CardContent className="p-8">
                {loading ? (
                  <div className="flex flex-col items-center justify-center py-24 gap-4">
                    <Loader2 className="animate-spin text-primary" size={48} />
                    <p className="text-sm font-bold text-muted-foreground uppercase tracking-widest">Hydrating tool registry...</p>
                  </div>
                ) : (
                  <div className="space-y-6">
                    {filteredTools.map((tool) => {
                      const RiskIcon = riskIcons[tool.riskLevel] || Shield;
                      const isExpanded = expandedTools.has(tool.id);

                      return (
                        <div key={tool.id} className="flex flex-col sm:flex-row p-8 border border-border/60 rounded-2xl bg-card hover:bg-muted/30 transition-all shadow-sm group">
                          <div className="flex items-start gap-6 flex-1">
                            <div className="p-4 bg-primary/10 rounded-xl shrink-0 group-hover:scale-105 transition-transform">
                              <RiskIcon size={28} className="text-primary" />
                            </div>
                            <div className="flex-1 space-y-2">
                              <div className="flex items-center gap-3">
                                <h3 className="text-lg font-bold text-foreground">{tool.name}</h3>
                                <Badge variant={tool.riskLevel === 'high' ? 'destructive' : tool.riskLevel === 'medium' ? 'secondary' : 'default'} className="text-[10px] px-3 font-black uppercase tracking-wider">
                                  {tool.riskLevel}
                                </Badge>
                              </div>
                              <p className="text-base text-muted-foreground leading-relaxed">{tool.description}</p>

                              {Object.keys(tool.parameters).length > 0 && (
                                <div className="pt-3">
                                  <button
                                    onClick={() => setExpandedTools(prev => {
                                      const s = new Set(prev);
                                      isExpanded ? s.delete(tool.id) : s.add(tool.id);
                                      return s;
                                    })}
                                    className="text-sm text-primary hover:underline font-bold flex items-center gap-1"
                                  >
                                    {isExpanded ? 'Hide Parameters' : 'View Configuration Parameters'}
                                    <span className={`transition-transform ${isExpanded ? 'rotate-180' : ''}`}>↓</span>
                                  </button>
                                </div>
                              )}

                              {isExpanded && Object.keys(tool.parameters).length > 0 && (
                                <div className="mt-4 p-6 bg-muted/50 rounded-xl border border-border/40 font-mono text-sm overflow-auto">
                                  <pre className="whitespace-pre-wrap text-muted-foreground leading-relaxed">
                                    {JSON.stringify(tool.parameters, null, 2)}
                                  </pre>
                                </div>
                              )}
                            </div>
                          </div>
                          
                          <div className="mt-6 sm:mt-0 sm:ml-6 flex items-start shrink-0">
                            <label className="relative inline-flex items-center cursor-pointer">
                              <input
                                type="checkbox"
                                checked={tool.enabled}
                                onChange={() => toggleEnabled(tool.name, tool.enabled)}
                                className="sr-only peer"
                              />
                              <div className="w-12 h-7 bg-muted peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:rounded-full after:h-6 after:w-6 after:transition-all peer-checked:bg-primary pointer-events-none shadow-md active:after:w-7" />
                            </label>
                          </div>
                        </div>
                      );
                    })}
                    {filteredTools.length === 0 && (
                      <div className="py-24 border border-dashed rounded-2xl text-center text-muted-foreground bg-muted/5">
                        <p className="text-lg font-bold opacity-30 uppercase tracking-widest">No matching tools detected</p>
                      </div>
                    )}
                  </div>
                )}
              </CardContent>
            </Card>
          </div>
        </div>
      </div>
    </DashboardLayout>
  );
}
