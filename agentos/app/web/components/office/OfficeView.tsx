'use client';

// 办公室视图：Phaser Canvas + 状态栏

import { useEffect, useRef } from 'react';
import { useOfficeState } from '@/hooks/useOfficeState';
import { STATES } from './types';

export function OfficeView() {
  const containerRef = useRef<HTMLDivElement>(null);
  const gameRef = useRef<import('phaser').Game | null>(null);
  const officeState = useOfficeState();

  // 动态 import Phaser（避免 SSR），创建/销毁游戏实例
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

  // 状态变更时推送到 Phaser 场景
  useEffect(() => {
    if (gameRef.current) {
      gameRef.current.events.emit('setState', officeState.state, officeState.detail);
    }
  }, [officeState]);

  const stateInfo = STATES[officeState.state];

  return (
    <div className="flex flex-col h-full">
      <div className="flex-1 relative rounded-lg overflow-hidden bg-black">
        <div ref={containerRef} className="w-full h-full" />
      </div>
      <div className="mt-2 flex items-center justify-between px-3 py-1.5 text-sm">
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
