'use client';

// WebSocket 事件 → 办公室状态映射
// 基于 ChatSessionContext 暴露的 isTyping / steps / messages 推导状态

import { useMemo } from 'react';
import { useChatSession } from '@/contexts/ChatSessionContext';
import type { OfficeStateName, OfficeState } from '@/components/office/types';

const SEARCH_TOOLS = ['serper_search', 'brave_search', 'baidu_search', 'tavily_search'];
const SYNC_TOOLS = ['send_message', 'create_agent'];

function mapToolToState(toolName: string): OfficeStateName {
  if (SEARCH_TOOLS.some(t => toolName.includes(t))) return 'researching';
  if (SYNC_TOOLS.some(t => toolName.includes(t))) return 'syncing';
  return 'executing';
}

export function useOfficeState(): OfficeState {
  const { isTyping, steps, messages } = useChatSession();

  return useMemo(() => {
    if (!isTyping) {
      return { state: 'idle' as OfficeStateName, detail: '' };
    }

    // 检查最近的 step 是否有工具调用
    const lastRunningStep = [...steps].reverse().find(s => s.status === 'running');
    if (lastRunningStep) {
      const label = lastRunningStep.label;
      const toolState = mapToolToState(label);
      return { state: toolState, detail: label };
    }

    // 检查最近的消息是否有工具信息
    const lastToolMsg = [...messages].reverse().find(
      m => m.role === 'tool' && m.toolInfo?.status === 'running'
    );
    if (lastToolMsg?.toolInfo) {
      const toolState = mapToolToState(lastToolMsg.toolInfo.name);
      return { state: toolState, detail: lastToolMsg.toolInfo.name };
    }

    // 默认：AI 在思考
    return { state: 'writing' as OfficeStateName, detail: 'AI 正在思考...' };
  }, [isTyping, steps, messages]);
}
