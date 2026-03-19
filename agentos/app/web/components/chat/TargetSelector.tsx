'use client';

import { useEffect, useRef, useState } from 'react';
import { Bot, ChevronDown, Check } from 'lucide-react';
import { type AgentOption } from '@/lib/chatTypes';
import { authFetch, API_BASE } from '@/lib/authFetch';

export function TargetSelector({
  selectedAgent,
  onSelectAgent,
  locked,
}: {
  selectedAgent: string;
  onSelectAgent: (id: string) => void;
  locked?: boolean;
}) {
  const [agents, setAgents] = useState<AgentOption[]>([]);
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    authFetch(`${API_BASE}/api/agents`).then(r => r.json()).catch(() => []).then(a => setAgents(a));
  }, []);

  useEffect(() => {
    const handleClick = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener('mousedown', handleClick);
    return () => document.removeEventListener('mousedown', handleClick);
  }, []);

  const currentLabel = agents.find(a => a.id === selectedAgent)?.name || selectedAgent || 'Default Agent';

  if (locked) {
    return (
      <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-secondary/50 border text-xs font-medium text-secondary-foreground">
        <Bot size={14} className="text-primary" />
        <span className="max-w-[140px] truncate">{currentLabel}</span>
      </div>
    );
  }

  return (
    <div className="relative" ref={ref}>
      <button
        onClick={() => setOpen(!open)}
        className="flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-secondary/50 border hover:bg-secondary transition-colors text-xs font-medium text-secondary-foreground"
      >
        <Bot size={14} className="text-primary" />
        <span className="max-w-[140px] truncate">{currentLabel}</span>
        <ChevronDown size={14} className="text-muted-foreground ml-1" />
      </button>

      {open && (
        <div className="absolute bottom-full left-0 mb-2 w-72 bg-popover border rounded-xl shadow-lg z-50 overflow-hidden">
          <div className="flex border-b">
            <div className="flex-1 flex items-center justify-center gap-1.5 px-3 py-2.5 text-xs font-semibold text-foreground border-b-2 border-primary">
              <Bot size={14} /> Available Agents
            </div>
          </div>
          <div className="max-h-60 overflow-auto p-2">
            {agents.length === 0 ? (
              <div className="text-center text-muted-foreground text-xs py-6">No Agents Found</div>
            ) : agents.map(a => (
              <button
                key={a.id}
                onClick={() => { onSelectAgent(a.id); setOpen(false); }}
                className={`w-full text-left px-3 py-2.5 rounded-md text-sm hover:bg-muted transition-colors flex items-center gap-3 ${
                  selectedAgent === a.id ? 'bg-muted/80' : ''
                }`}
              >
                <div className="w-6 h-6 rounded-full bg-primary/10 flex items-center justify-center shrink-0">
                  <Bot size={14} className="text-primary" />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="text-foreground font-medium truncate">{a.name}</div>
                  {a.description && <div className="text-[11px] text-muted-foreground truncate mt-0.5">{a.description}</div>}
                </div>
                {selectedAgent === a.id && <Check size={16} className="text-primary shrink-0" />}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
