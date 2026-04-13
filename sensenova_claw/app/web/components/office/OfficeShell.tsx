'use client';

import Image from 'next/image';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useCallback, useEffect, useMemo, useState } from 'react';

import { OfficeView } from '@/components/office/OfficeView';
import { authFetch, API_BASE } from '@/lib/authFetch';
import { cn } from '@/lib/utils';

interface OfficeAgentSummary {
  id: string;
  name: string;
}

interface OfficeShellProps {
  selectedAgentId?: string;
}

export function OfficeShell({ selectedAgentId }: OfficeShellProps) {
  const pathname = usePathname();
  const [agents, setAgents] = useState<OfficeAgentSummary[]>([]);
  const [refreshing, setRefreshing] = useState(false);

  const loadAgents = useCallback(async () => {
    const res = await authFetch(`${API_BASE}/api/agents`);
    const data = await res.json();
    const next = Array.isArray(data) ? data as OfficeAgentSummary[] : [];
    setAgents(next);
    return next;
  }, []);

  useEffect(() => {
    loadAgents().catch(() => setAgents([]));
  }, [loadAgents]);

  const roomTitle = useMemo(() => {
    if (!selectedAgentId) return 'Sensenova-Claw';
    return agents.find(agent => agent.id === selectedAgentId)?.name ?? selectedAgentId;
  }, [agents, selectedAgentId]);

  const visibleAgents = useMemo(() => {
    if (!selectedAgentId) return agents;
    return agents.filter(agent => agent.id === selectedAgentId);
  }, [agents, selectedAgentId]);

  const refreshOffice = useCallback(async () => {
    if (refreshing) return;
    setRefreshing(true);
    try {
      await loadAgents();
    } finally {
      setRefreshing(false);
    }
  }, [loadAgents, refreshing]);

  return (
    <div className="flex h-full overflow-hidden bg-[#09090b]">
      <aside className="w-64 shrink-0 border-r border-[#473222] bg-[linear-gradient(180deg,#120e0c_0%,#09090b_100%)] p-2">
        <div className="flex h-full flex-col rounded-xl border border-[#5a412d] bg-[linear-gradient(180deg,rgba(52,36,24,0.96)_0%,rgba(22,16,12,0.98)_100%)] p-3 shadow-[inset_0_0_0_1px_rgba(255,220,180,0.06)]">
          <div className="mb-3 border-b border-[#6f5138] pb-3">
            <OfficeEntry
              href="/office"
              label="Sensenova-Claw"
              active={pathname === '/office'}
              testId="office-entry-global"
            />
          </div>
          <div className="mb-2 px-1 text-[10px] font-bold uppercase tracking-[0.24em] text-[#caa887]">
            Agent 办公室
          </div>
          <div className="min-h-0 flex-1 space-y-2 overflow-y-auto pr-1">
            {agents.map((agent) => (
              <OfficeEntry
                key={agent.id}
                href={`/office/${agent.id}`}
                label={agent.name}
                active={pathname === `/office/${agent.id}`}
                testId={`office-entry-${agent.id}`}
              />
            ))}
          </div>
        </div>
      </aside>
      <div className="min-w-0 flex-1">
        <OfficeView
          agents={visibleAgents}
          mode={selectedAgentId ? 'agent' : 'global'}
          roomTitle={roomTitle}
          refreshing={refreshing}
          onRefresh={refreshOffice}
        />
      </div>
    </div>
  );
}

function OfficeEntry({
  href,
  label,
  active,
  testId,
}: {
  href: string;
  label: string;
  active: boolean;
  testId: string;
}) {
  return (
    <Link
      href={href}
      aria-current={active ? 'page' : undefined}
      data-testid={testId}
      className={cn(
        'flex items-center gap-2 rounded-xl border px-2 py-2 transition-colors',
        active
          ? 'border-[#f0bf74] bg-[#5c3820] text-[#fff4dc] shadow-[inset_0_0_0_1px_rgba(255,226,176,0.18)]'
          : 'border-[#4a3426] bg-[#1a1410] text-[#d4beaa] hover:border-[#70503a] hover:bg-[#241a14]'
      )}
    >
      <span className={cn(
        'flex size-7 items-center justify-center rounded-lg border overflow-hidden',
        active ? 'border-[#f0bf74] bg-[#8f5a2e]' : 'border-[#604431] bg-[#2a1e17]'
      )}>
        <Image
          src="/claw-icon.png"
          alt=""
          width={22}
          height={22}
          className="size-[22px] pixelated"
        />
      </span>
      <span className="line-clamp-2 text-[12px] leading-tight">{label}</span>
    </Link>
  );
}
