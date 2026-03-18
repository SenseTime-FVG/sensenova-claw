'use client';

import { useCallback, useEffect, useRef, useState } from 'react';

const WS_URL = process.env.NEXT_PUBLIC_WS_URL || 'ws://localhost:8000/ws';
const WS_RECONNECT_INTERVAL_MS = 1000;
const WS_MAX_RECONNECT_ATTEMPTS = 10;

export type TaskState = 'empty' | 'processing' | 'completed';

interface StepItem {
  label: string;
  status: 'done' | 'running' | 'pending';
}

interface TaskProgressItem {
  task: string;
  step: number;
  total: number;
  status: 'running' | 'completed';
}

interface CurrentTask {
  title: string;
  goal: string;
  stage: string;
  status: 'idle' | 'running' | 'completed' | 'error';
}

export interface UseWorkbenchSessionReturn {
  wsConnected: boolean;
  taskState: TaskState;
  currentTask: CurrentTask | null;
  steps: StepItem[];
  taskProgress: TaskProgressItem[];
  result: string | null;
  sendTask: (message: string) => void;
  reset: () => void;
}

export function useWorkbenchSession(): UseWorkbenchSessionReturn {
  const [wsConnected, setWsConnected] = useState(false);
  const [taskState, setTaskState] = useState<TaskState>('empty');
  const [currentTask, setCurrentTask] = useState<CurrentTask | null>(null);
  const [steps, setSteps] = useState<StepItem[]>([]);
  const [taskProgress, setTaskProgress] = useState<TaskProgressItem[]>([]);
  const [result, setResult] = useState<string | null>(null);

  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const reconnectAttemptsRef = useRef(0);
  const shouldReconnectRef = useRef(true);
  const sessionIdRef = useRef<string | null>(null);
  const pendingInputRef = useRef<string | null>(null);
  const toolStepMapRef = useRef<Map<string, number>>(new Map());

  const wsSend = useCallback((msg: Record<string, unknown>) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(msg));
    }
  }, []);

  const handleWsMessage = useCallback((data: Record<string, unknown>) => {
    const payload = (data.payload || {}) as Record<string, unknown>;

    switch (data.type) {
      case 'session_created': {
        const newSid = data.session_id as string;
        sessionIdRef.current = newSid;
        if (pendingInputRef.current) {
          wsSend({
            type: 'user_input',
            session_id: newSid,
            payload: { content: pendingInputRef.current, attachments: [], context_files: [] },
            timestamp: Date.now() / 1000,
          });
          pendingInputRef.current = null;
        }
        break;
      }
      case 'agent_thinking':
        setTaskState('processing');
        setCurrentTask((prev) => prev ? { ...prev, status: 'running', stage: '思考中' } : prev);
        break;
      case 'tool_execution': {
        const toolName = String(payload.tool_name || '');
        const toolCallId = String(payload.tool_call_id || '');
        setSteps((prev) => {
          const idx = prev.length;
          toolStepMapRef.current.set(toolCallId, idx);
          return [...prev, { label: `执行 ${toolName}`, status: 'running' as const }];
        });
        setTaskProgress((prev) => [...prev, {
          task: toolName,
          step: 0,
          total: 1,
          status: 'running' as const,
        }]);
        break;
      }
      case 'tool_result': {
        const toolCallId = String(payload.tool_call_id || '');
        const stepIdx = toolStepMapRef.current.get(toolCallId);
        if (stepIdx !== undefined) {
          setSteps((prev) => prev.map((s, i) =>
            i === stepIdx ? { ...s, status: 'done' as const } : s
          ));
        }
        setTaskProgress((prev) => {
          const toolName = String(payload.tool_name || '');
          const idx = prev.findIndex((t) => t.task === toolName && t.status === 'running');
          if (idx === -1) return prev;
          return prev.map((t, i) =>
            i === idx ? { ...t, step: 1, status: 'completed' as const } : t
          );
        });
        break;
      }
      case 'turn_completed': {
        const finalResponse = String(payload.final_response || '');
        if (finalResponse) {
          setResult(finalResponse);
        }
        setTaskState('completed');
        setCurrentTask((prev) => prev ? { ...prev, status: 'completed', stage: '已完成' } : prev);
        break;
      }
      case 'error': {
        const errMsg = String(payload.message || '未知错误');
        setResult(`错误：${errMsg}`);
        setCurrentTask((prev) => prev ? { ...prev, status: 'error', stage: '出错' } : prev);
        break;
      }
    }
  }, [wsSend]);

  const handleWsMessageRef = useRef(handleWsMessage);
  handleWsMessageRef.current = handleWsMessage;

  useEffect(() => {
    let cancelled = false;

    const scheduleReconnect = () => {
      if (cancelled || !shouldReconnectRef.current) return;
      if (reconnectAttemptsRef.current >= WS_MAX_RECONNECT_ATTEMPTS) return;
      if (reconnectTimerRef.current) clearTimeout(reconnectTimerRef.current);
      reconnectAttemptsRef.current += 1;
      reconnectTimerRef.current = setTimeout(connect, WS_RECONNECT_INTERVAL_MS);
    };

    const connect = () => {
      if (cancelled || !shouldReconnectRef.current) return;
      const cookieMatch = document.cookie.match(/(?:^|; )agentos_token=([^;]*)/);
      const token = cookieMatch ? decodeURIComponent(cookieMatch[1]) : null;
      const wsUrl = token ? `${WS_URL}?token=${encodeURIComponent(token)}` : WS_URL;

      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;

      ws.onopen = () => {
        if (cancelled || wsRef.current !== ws) return;
        setWsConnected(true);
        reconnectAttemptsRef.current = 0;
      };
      ws.onclose = () => {
        if (wsRef.current !== ws && wsRef.current !== null) return;
        if (wsRef.current === ws) wsRef.current = null;
        setWsConnected(false);
        scheduleReconnect();
      };
      ws.onerror = () => {
        if (wsRef.current !== ws) return;
        setWsConnected(false);
        if (ws.readyState === WebSocket.CONNECTING || ws.readyState === WebSocket.OPEN) {
          ws.close();
        }
      };
      ws.onmessage = (event) => {
        try { handleWsMessageRef.current(JSON.parse(event.data)); } catch {}
      };
    };

    shouldReconnectRef.current = true;
    const timer = setTimeout(connect, 50);

    return () => {
      cancelled = true;
      shouldReconnectRef.current = false;
      clearTimeout(timer);
      if (reconnectTimerRef.current) {
        clearTimeout(reconnectTimerRef.current);
        reconnectTimerRef.current = null;
      }
      if (wsRef.current) {
        const activeSocket = wsRef.current;
        wsRef.current = null;
        activeSocket.close();
      }
    };
  }, []);

  const sendTask = useCallback((message: string) => {
    if (!wsConnected) return;
    setTaskState('processing');
    setSteps([]);
    setTaskProgress([]);
    setResult(null);
    toolStepMapRef.current.clear();
    setCurrentTask({
      title: message.slice(0, 30) + (message.length > 30 ? '...' : ''),
      goal: message,
      stage: '初始化',
      status: 'running',
    });

    if (!sessionIdRef.current) {
      pendingInputRef.current = message;
      wsSend({
        type: 'create_session',
        payload: { agent_id: 'default', meta: { title: message.slice(0, 20) || '新任务' } },
        timestamp: Date.now() / 1000,
      });
    } else {
      wsSend({
        type: 'user_input',
        session_id: sessionIdRef.current,
        payload: { content: message, attachments: [], context_files: [] },
        timestamp: Date.now() / 1000,
      });
    }
  }, [wsConnected, wsSend]);

  const reset = useCallback(() => {
    setTaskState('empty');
    setCurrentTask(null);
    setSteps([]);
    setTaskProgress([]);
    setResult(null);
    toolStepMapRef.current.clear();
    sessionIdRef.current = null;
    pendingInputRef.current = null;
  }, []);

  return {
    wsConnected,
    taskState,
    currentTask,
    steps,
    taskProgress,
    result,
    sendTask,
    reset,
  };
}
