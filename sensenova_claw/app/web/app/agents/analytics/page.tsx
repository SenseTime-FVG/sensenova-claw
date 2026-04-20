'use client';

import { useState, useEffect } from 'react';
import Link from 'next/link';
import { Activity, Bot, Loader2, MessageSquare, Sparkles, Wrench } from 'lucide-react';
import { DashboardLayout } from '@/components/layout/DashboardLayout';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { authFetch, API_BASE } from '@/lib/authFetch';

type RangeKey = '1d' | '7d' | '30d' | 'all';

interface AgentAnalyticsRow {
  agent_id: string;
  name: string;
  sessions: number;
  turns: number;
  llm_calls: number;
  tool_calls: number;
  last_active: number;
}

interface AnalyticsResponse {
  range: RangeKey;
  since_ts: number;
  totals: {
    sessions: number;
    turns: number;
    llm_calls: number;
    tool_calls: number;
  };
  agents: AgentAnalyticsRow[];
}

const RANGE_OPTIONS: { key: RangeKey; label: string }[] = [
  { key: '1d', label: '近 1 天' },
  { key: '7d', label: '近 7 天' },
  { key: '30d', label: '近 30 天' },
  { key: 'all', label: '全部' },
];

function formatLastActive(ts: number): string {
  if (!ts) return 'never';
  const delta = Math.floor(Date.now() / 1000 - ts);
  if (delta < 60) return `${delta}s ago`;
  if (delta < 3600) return `${Math.floor(delta / 60)}m ago`;
  if (delta < 86400) return `${Math.floor(delta / 3600)}h ago`;
  return `${Math.floor(delta / 86400)}d ago`;
}

export default function AgentAnalyticsPage() {
  const [range, setRange] = useState<RangeKey>('7d');
  const [data, setData] = useState<AnalyticsResponse | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    authFetch(`${API_BASE}/api/agents/analytics?range=${range}`)
      .then((res) => res.json())
      .then((d: AnalyticsResponse) => setData(d))
      .catch(() => setData(null))
      .finally(() => setLoading(false));
  }, [range]);

  const rows = data?.agents ?? [];
  const totals = data?.totals ?? { sessions: 0, turns: 0, llm_calls: 0, tool_calls: 0 };
  const topAgent = rows[0];

  return (
    <DashboardLayout>
      <div className="flex-1 space-y-8 p-10 lg:p-12">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-4xl font-extrabold tracking-tight text-foreground/90">Analytics</h2>
            <p className="text-sm font-medium text-muted-foreground mt-2">
              按 Agent 维度的使用指标聚合
            </p>
          </div>
          <div className="flex items-center gap-2">
            {RANGE_OPTIONS.map((opt) => (
              <button
                key={opt.key}
                onClick={() => setRange(opt.key)}
                className={`px-4 py-2 rounded-xl text-sm font-bold transition-all border ${
                  range === opt.key
                    ? 'bg-primary text-primary-foreground shadow-lg shadow-primary/20 border-transparent'
                    : 'bg-background text-muted-foreground border-border/60 hover:bg-muted'
                }`}
              >
                {opt.label}
              </button>
            ))}
          </div>
        </div>

        <div className="flex flex-col md:flex-row gap-8 mt-10">
          {/* Nested Sidebar（与 agents 页保持一致） */}
          <aside className="w-full md:w-64 lg:w-72 shrink-0">
            <nav className="flex space-x-2 md:flex-col md:space-x-0 md:space-y-2">
              <p className="text-[10px] font-black uppercase tracking-[0.2em] text-muted-foreground/70 mb-2 px-4">
                Overview
              </p>
              <Link
                href="/agents"
                className="flex items-center gap-3 font-bold justify-start w-full text-base px-5 py-3.5 rounded-xl transition-all border border-transparent text-muted-foreground hover:bg-muted hover:text-foreground"
              >
                <Bot className="h-5 w-5" /> Agents
              </Link>
              <button className="flex items-center gap-3 font-bold justify-start w-full text-base px-5 py-3.5 rounded-xl transition-all border border-transparent bg-primary text-primary-foreground shadow-lg shadow-primary/20">
                <Activity className="h-5 w-5" /> Analytics
              </button>
            </nav>
          </aside>

          {/* Main Content */}
          <div className="flex-1 space-y-8">
            {/* Totals */}
            <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-4">
              <Card className="shadow-lg border-border/60">
                <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-3">
                  <CardTitle className="text-sm font-bold uppercase tracking-wider text-muted-foreground">
                    Sessions
                  </CardTitle>
                  <MessageSquare className="h-5 w-5 text-primary" />
                </CardHeader>
                <CardContent>
                  <div className="text-4xl font-black">{totals.sessions}</div>
                  <p className="text-sm font-medium text-muted-foreground mt-2">累计会话数（全量）</p>
                </CardContent>
              </Card>
              <Card className="shadow-lg border-border/60">
                <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-3">
                  <CardTitle className="text-sm font-bold uppercase tracking-wider text-muted-foreground">
                    Turns
                  </CardTitle>
                  <Activity className="h-5 w-5 text-primary" />
                </CardHeader>
                <CardContent>
                  <div className="text-4xl font-black">{totals.turns}</div>
                  <p className="text-sm font-medium text-muted-foreground mt-2">
                    对话轮数（范围内）
                  </p>
                </CardContent>
              </Card>
              <Card className="shadow-lg border-border/60">
                <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-3">
                  <CardTitle className="text-sm font-bold uppercase tracking-wider text-muted-foreground">
                    LLM Calls
                  </CardTitle>
                  <Sparkles className="h-5 w-5 text-primary" />
                </CardHeader>
                <CardContent>
                  <div className="text-4xl font-black">{totals.llm_calls}</div>
                  <p className="text-sm font-medium text-muted-foreground mt-2">LLM 调用次数</p>
                </CardContent>
              </Card>
              <Card className="shadow-lg border-border/60">
                <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-3">
                  <CardTitle className="text-sm font-bold uppercase tracking-wider text-muted-foreground">
                    Tool Calls
                  </CardTitle>
                  <Wrench className="h-5 w-5 text-primary" />
                </CardHeader>
                <CardContent>
                  <div className="text-4xl font-black">{totals.tool_calls}</div>
                  <p className="text-sm font-medium text-muted-foreground mt-2">工具调用次数</p>
                </CardContent>
              </Card>
            </div>

            {/* Ranking table */}
            <Card className="shadow-xl border-border/80 overflow-hidden">
              <CardHeader className="bg-muted/30 border-b p-8">
                <div>
                  <CardTitle className="text-2xl font-bold">Agent 使用排名</CardTitle>
                  <CardDescription className="text-base mt-2">
                    按会话数排序；turns / LLM / 工具调用数为所选时间范围内的增量。
                    {topAgent && totals.sessions > 0 && (
                      <span className="ml-2 text-foreground font-semibold">
                        最活跃：{topAgent.name}
                      </span>
                    )}
                  </CardDescription>
                </div>
              </CardHeader>
              <CardContent className="p-0">
                {loading ? (
                  <div className="flex flex-col items-center justify-center py-24 gap-4">
                    <Loader2 className="animate-spin text-primary" size={48} />
                    <p className="text-sm font-bold text-muted-foreground uppercase tracking-widest">
                      Aggregating...
                    </p>
                  </div>
                ) : rows.length === 0 ? (
                  <div className="flex flex-col items-center justify-center py-24 text-center text-muted-foreground">
                    <Bot size={64} className="mb-4 opacity-20" />
                    <p className="text-lg font-bold uppercase tracking-widest opacity-40">
                      暂无数据
                    </p>
                  </div>
                ) : (
                  <div className="overflow-x-auto">
                    <table className="w-full text-sm">
                      <thead className="bg-muted/20 text-muted-foreground">
                        <tr className="text-xs font-bold uppercase tracking-wider">
                          <th className="text-left px-6 py-4">Agent</th>
                          <th className="text-right px-4 py-4">Sessions</th>
                          <th className="text-right px-4 py-4">Turns</th>
                          <th className="text-right px-4 py-4">LLM</th>
                          <th className="text-right px-4 py-4">Tools</th>
                          <th className="text-right px-6 py-4">Last Active</th>
                        </tr>
                      </thead>
                      <tbody>
                        {rows.map((row) => (
                          <tr
                            key={row.agent_id}
                            className="border-t border-border/40 hover:bg-muted/20 transition-colors"
                          >
                            <td className="px-6 py-4">
                              <Link
                                href={`/agents/${row.agent_id}`}
                                className="font-bold text-foreground hover:text-primary transition-colors"
                              >
                                {row.name}
                              </Link>
                              <div className="text-xs text-muted-foreground mt-0.5">
                                {row.agent_id}
                              </div>
                            </td>
                            <td className="text-right px-4 py-4 font-semibold">{row.sessions}</td>
                            <td className="text-right px-4 py-4">{row.turns}</td>
                            <td className="text-right px-4 py-4">{row.llm_calls}</td>
                            <td className="text-right px-4 py-4">{row.tool_calls}</td>
                            <td className="text-right px-6 py-4 text-muted-foreground">
                              {formatLastActive(row.last_active)}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
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
