'use client';

// WebSocket 事件 → 办公室状态映射
// 基于 ChatSessionContext 暴露的全局活动状态 + 当前会话的 steps/messages 推导状态
// 只要有任意 agent 在工作就显示工作界面

import { useRef } from 'react';
import { useMessages, useEventDispatcher } from '@/contexts/ws';
import type { OfficeStateName, OfficeState } from '@/components/office/types';

const SEARCH_TOOLS = ['serper_search', 'brave_search', 'baidu_search', 'tavily_search'];
const SYNC_TOOLS = ['send_message', 'create_agent'];

function mapToolToState(toolName: string): OfficeStateName {
  if (SEARCH_TOOLS.some(t => toolName.includes(t))) return 'researching';
  if (SYNC_TOOLS.some(t => toolName.includes(t))) return 'syncing';
  return 'executing';
}

function deriveState(
  anyWorking: boolean,
  globalLastToolName: string,
  isTyping: boolean,
  steps: { label: string; status: string }[],
  messages: { role: string; toolInfo?: { name: string; status: string } }[],
): { state: OfficeStateName; detail: string } {
  // 当前会话有详细信息时优先使用
  if (isTyping) {
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

  // 当前会话空闲，但其他会话有 agent 在工作
  if (anyWorking) {
    if (globalLastToolName) {
      return { state: mapToolToState(globalLastToolName), detail: globalLastToolName };
    }
    return { state: 'writing', detail: 'Agent 工作中...' };
  }

  return { state: 'idle', detail: '' };
}

/**
 * 返回引用稳定的 OfficeState——只有 state 或 detail 值真正变化时才更新对象引用，
 * 避免 Context 频繁重渲染时产生不必要的 Phaser 事件推送。
 *
 * 改进：只要有任意 agent 在工作（跨会话），就显示工作状态。
 */
export function useOfficeState(): OfficeState {
  const { isTyping, steps, messages } = useMessages();
  const { globalActivity } = useEventDispatcher();
  const prevRef = useRef<OfficeState>({ state: 'idle', detail: '' });

  const next = deriveState(globalActivity.anyWorking, globalActivity.lastToolName, isTyping, steps, messages);
  if (next.state !== prevRef.current.state || next.detail !== prevRef.current.detail) {
    prevRef.current = next;
  }
  return prevRef.current;
}
