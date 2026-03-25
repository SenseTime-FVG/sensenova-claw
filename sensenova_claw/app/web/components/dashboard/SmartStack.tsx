'use client';

import { Sparkles } from 'lucide-react';
import { getTone } from './widgetTones';
import type { ToneName } from './widgetTones';
import type { AgentInfo } from '@/hooks/useDashboardData';
import { SectionHeader } from './SectionHeader';

const AGENT_TONES: ToneName[] = ['violet', 'blue', 'amber', 'emerald', 'rose', 'indigo'];

function guessIcon(name: string): string {
  const n = name.toLowerCase();
  if (n.includes('写作') || n.includes('writ')) return '✍️';
  if (n.includes('数据') || n.includes('data') || n.includes('分析')) return '📊';
  if (n.includes('ppt') || n.includes('演示') || n.includes('排版')) return '🎨';
  if (n.includes('研究') || n.includes('research') || n.includes('检索')) return '🔍';
  if (n.includes('办公') || n.includes('office') || n.includes('main')) return '💼';
  if (n.includes('邮') || n.includes('email') || n.includes('mail')) return '📧';
  return '🤖';
}

interface SmartStackProps {
  agents: AgentInfo[];
  onAgentClick: (agentId: string) => void;
}

function CompactAgentCard({ agent, tone, onClick }: { agent: AgentInfo; tone: ToneName; onClick: () => void }) {
  const style = getTone(tone);

  return (
    <button
      type="button"
      onClick={onClick}
      className="group relative flex items-center gap-2 overflow-hidden rounded-xl border border-[var(--glass-border)] bg-[var(--glass-bg)] px-2.5 py-1.5 text-left shadow-[0_1px_8px_rgba(15,23,42,0.04)] dark:shadow-[0_1px_8px_rgba(0,0,0,0.15)] backdrop-blur-xl transition-all duration-200 hover:-translate-y-0.5 hover:shadow-[0_4px_16px_rgba(15,23,42,0.08)] dark:hover:shadow-[0_4px_16px_rgba(0,0,0,0.25)] w-full h-full min-w-0"
    >
      <div className={`absolute inset-0 bg-gradient-to-br ${style.surface} opacity-60`} />
      <div className={`absolute -right-3 -top-3 h-8 w-8 rounded-full ${style.orb} blur-xl`} />
      <div className="relative z-10 flex items-center gap-2 min-w-0">
        <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg border border-[var(--glass-border-heavy)] bg-[var(--glass-bg-heavy)] text-xs shadow-sm">
          {guessIcon(agent.name)}
        </div>
        <div className="min-w-0">
          <div className="flex items-center gap-1">
            <span className="truncate text-[12px] font-semibold text-[var(--glass-text)]">{agent.name}</span>
            <span className={`shrink-0 rounded-full px-1 py-[0.5px] text-[8px] font-semibold ${style.pill}`}>
              常驻
            </span>
          </div>
          <div className="truncate text-[10px] leading-3 mt-0.5 text-[var(--glass-text-muted)]">
            {agent.description || '点击启动'}
          </div>
        </div>
      </div>
    </button>
  );
}

export function SmartStack({ agents, onAgentClick }: SmartStackProps) {
  const topAgents = [...agents]
    .sort((a, b) => (b.sessionCount || 0) - (a.sessionCount || 0))
    .slice(0, 12);

  if (topAgents.length === 0) return null;

  return (
    <div className="flex h-full flex-col p-2.5">
      <div className="absolute inset-0 bg-gradient-to-br from-violet-50/80 via-background/90 to-fuchsia-50/60 dark:from-violet-950/30 dark:via-background/90 dark:to-fuchsia-950/20" />
      <div className="relative z-10 flex h-full flex-col gap-1">
        <SectionHeader
          title="常用 Agent"
          subtitle="快速启动"
          tag="Smart Stack"
          tagTone="violet"
          icon={<Sparkles className="h-3.5 w-3.5 text-violet-500" />}
        />

        {/* N×2 纵向网格 */}
        <div className="flex-1 min-h-0 mt-0.5 overflow-y-auto thin-scrollbar">
          <div className="grid grid-cols-2 gap-[7px]">
            {topAgents.map((agent, i) => (
              <div key={agent.id} className="min-w-0 h-[46px]">
                <CompactAgentCard
                  agent={agent}
                  tone={AGENT_TONES[i % AGENT_TONES.length]}
                  onClick={() => onAgentClick(agent.id)}
                />
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
