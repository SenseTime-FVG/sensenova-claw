'use client';

// 办公室视图：Phaser Canvas + 状态栏

import { useEffect, useRef, useState, memo } from 'react';
import { useOfficeState } from '@/hooks/useOfficeState';
import { STATES, type OfficeStateName } from './types';
import { authFetch, API_BASE } from '@/lib/authFetch';

/**
 * Phaser 画布容器 — 独立 memo 组件，避免父组件重渲染导致画布闪烁。
 * 只在 officeState 的 state/detail 值真正变化时才向 Phaser 推送事件。
 */
const PhaserCanvas = memo(function PhaserCanvas({
  state,
  detail,
  agents,
}: {
  state: OfficeStateName;
  detail: string;
  agents: { id: string; name: string }[];
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const gameRef = useRef<import('phaser').Game | null>(null);

  useEffect(() => {
    let mounted = true;

    async function init() {
      if (!containerRef.current || gameRef.current) return;
      const { createOfficeGame } = await import('./game');
      if (!mounted) return;
      gameRef.current = createOfficeGame(containerRef.current);
    }

    init();

    return () => {
      mounted = false;
      if (gameRef.current) {
        gameRef.current.destroy(true);
        gameRef.current = null;
      }
    };
  }, []);

  useEffect(() => {
    if (gameRef.current) {
      gameRef.current.events.emit('setState', state, detail);
    }
  }, [state, detail]);

  useEffect(() => {
    if (gameRef.current) {
      gameRef.current.events.emit('setAgents', agents);
    }
  }, [agents]);

  return <div ref={containerRef} className="absolute inset-0" />;
});

export function OfficeView() {
  const officeState = useOfficeState();
  const stateInfo = STATES[officeState.state];
  const [agents, setAgents] = useState<{ id: string; name: string }[]>([]);

  useEffect(() => {
    authFetch(`${API_BASE}/api/agents`)
      .then(res => res.json())
      .then((data: { id: string; name: string }[]) => setAgents(data))
      .catch(() => setAgents([]));
  }, []);

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* Phaser 画布：固定宽高比容器，避免 flex 尺寸震荡触发 Scale.FIT 反复重绘 */}
      <div className="flex-1 min-h-0 relative rounded-lg overflow-hidden bg-black">
        <PhaserCanvas state={officeState.state} detail={officeState.detail} agents={agents} />
      </div>
      <div className="flex-shrink-0 h-9 flex items-center justify-between px-3 text-sm">
        <div className="flex items-center gap-2 text-muted-foreground">
          <span className={`inline-block w-2 h-2 rounded-full ${
            officeState.state === 'idle' ? 'bg-green-500' :
            officeState.state === 'error' ? 'bg-red-500' :
            'bg-yellow-500 animate-pulse'
          }`} />
          <span>[{stateInfo.name}]</span>
          {officeState.detail && <span className="text-xs">{officeState.detail}</span>}
        </div>
        <div className="flex items-center gap-3 text-xs text-muted-foreground/60">
          <span>沙发=空闲</span>
          <span>工位=工作</span>
          <span>同步区=协作</span>
          <span>Bug区=出错</span>
        </div>
      </div>
    </div>
  );
}
