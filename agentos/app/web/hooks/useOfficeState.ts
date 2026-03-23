'use client';

// WebSocket 事件 → 办公室状态映射
// 基于 ChatSessionContext 暴露的 isTyping / steps / messages 推导状态

import { useRef } from 'react';
import { useChatSession } from '@/contexts/ChatSessionContext';
import type { OfficeStateName, OfficeState } from '@/components/office/types';

const SEARCH_TOOLS = ['serper_search', 'brave_search', 'baidu_search', 'tavily_search'];
const SYNC_TOOLS = ['send_message', 'create_agent'];

function mapToolToState(toolName: string): OfficeStateName {
  if (SEARCH_TOOLS.some(t => toolName.includes(t))) return 'researching';
  if (SYNC_TOOLS.some(t => toolName.includes(t))) return 'syncing';
  return 'executing';
}

function deriveState(
  isTyping: boolean,
  steps: { label: string; status: string }[],
  messages: { role: string; toolInfo?: { name: string; status: string } }[],
): { state: OfficeStateName; detail: string } {
  if (!isTyping) {
    return { state: 'idle', detail: '' };
  }

  const lastRunningStep = [...steps].reverse().find(s => s.status === 'running');
  if (lastRunningStep) {
    const label = lastRunningStep.label;
    return { state: mapToolToState(label), detail: label };
  }

  const lastToolMsg = [...messages].reverse().find(
    m => m.role === 'tool' && m.toolInfo?.status === 'running'
  );
  if (lastToolMsg?.toolInfo) {
    const name = lastToolMsg.toolInfo.name;
    return { state: mapToolToState(name), detail: name };
  }

  return { state: 'writing', detail: 'AI 正在思考...' };
}

/**
 * 返回引用稳定的 OfficeState——只有 state 或 detail 值真正变化时才更新对象引用，
 * 避免 Context 频繁重渲染时产生不必要的 Phaser 事件推送。
 */
export function useOfficeState(): OfficeState {
  const { isTyping, steps, messages } = useChatSession();
  const prevRef = useRef<OfficeState>({ state: 'idle', detail: '' });

  const next = deriveState(isTyping, steps, messages);
  if (next.state !== prevRef.current.state || next.detail !== prevRef.current.detail) {
    prevRef.current = next;
  }
  return prevRef.current;
}
