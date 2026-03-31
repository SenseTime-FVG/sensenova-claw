'use client';

import { useEffect, useMemo, useRef, useState, type KeyboardEvent } from 'react';

type InteractionKind = 'question' | 'confirmation';

interface PendingInteractionBase {
  kind: InteractionKind;
  interactionId: string;
  sourceSessionId: string;
  timeout: number;
  createdAt: number;
}

export interface PendingQuestionInteraction extends PendingInteractionBase {
  kind: 'question';
  sourceAgentId: string;
  sourceAgentName: string;
  question: string;
  options: string[] | null;
  multiSelect: boolean;
}

export interface PendingConfirmationInteraction extends PendingInteractionBase {
  kind: 'confirmation';
  toolName: string;
  riskLevel: string;
  arguments: Record<string, unknown>;
  timeoutAction?: string;
}

export type PendingInteraction =
  | PendingQuestionInteraction
  | PendingConfirmationInteraction;

export interface InteractionDialogProps {
  open: boolean;
  interaction: PendingInteraction | null;
  submitting: boolean;
  wsConnected: boolean;
  onQuestionSubmit: (answer: string | string[]) => void;
  onQuestionCancel: () => void;
  onConfirmationSubmit: (approved: boolean) => void;
  onTimeout: () => void;
}

export function InteractionDialog({
  open,
  interaction,
  submitting,
  wsConnected,
  onQuestionSubmit,
  onQuestionCancel,
  onConfirmationSubmit,
  onTimeout,
}: InteractionDialogProps) {
  const [customInput, setCustomInput] = useState('');
  const [singleChoice, setSingleChoice] = useState('');
  const [multiChoices, setMultiChoices] = useState<string[]>([]);
  const [nowTs, setNowTs] = useState(Date.now());
  const timeoutNotifiedRef = useRef<string>('');

  useEffect(() => {
    if (!open || !interaction || interaction.kind !== 'question') return;
    setCustomInput('');
    setSingleChoice('');
    setMultiChoices([]);
  }, [open, interaction?.kind, interaction?.interactionId]);

  useEffect(() => {
    if (!open) return;
    const timer = window.setInterval(() => setNowTs(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [open]);

  const remainingSeconds = useMemo(() => {
    if (!interaction) return 0;
    const elapsed = Math.floor((nowTs - interaction.createdAt) / 1000);
    return Math.max(0, interaction.timeout - elapsed);
  }, [interaction, nowTs]);

  useEffect(() => {
    if (!open || !interaction) return;
    if (interaction.kind === 'confirmation') return;
    if (remainingSeconds > 0) return;
    const timeoutKey = `${interaction.kind}:${interaction.interactionId}`;
    if (timeoutNotifiedRef.current === timeoutKey) return;
    timeoutNotifiedRef.current = timeoutKey;
    onTimeout();
  }, [open, interaction, remainingSeconds, onTimeout]);

  const normalizedAnswer = useMemo(() => {
    if (!interaction || interaction.kind !== 'question') return null;
    const custom = customInput.trim();
    if (custom) return custom;

    if (interaction.options && interaction.options.length > 0) {
      if (interaction.multiSelect) {
        return multiChoices.length > 0 ? multiChoices : null;
      }
      return singleChoice || null;
    }

    return null;
  }, [customInput, interaction, multiChoices, singleChoice]);

  const questionConfirmDisabled = !normalizedAnswer
    || submitting
    || !wsConnected
    || remainingSeconds <= 0;
  const confirmationTimedOut = interaction?.kind === 'confirmation' && remainingSeconds <= 0;
  const confirmationAwaitingServer = interaction?.kind === 'confirmation'
    && remainingSeconds <= 0
    && interaction.timeoutAction !== 'block';
  const confirmationDisabled = submitting
    || !wsConnected
    || Boolean(confirmationAwaitingServer);

  const toggleMultiChoice = (opt: string) => {
    setMultiChoices((prev) => {
      if (prev.includes(opt)) {
        return prev.filter((v) => v !== opt);
      }
      return [...prev, opt];
    });
  };

  const submitAnswer = () => {
    if (!normalizedAnswer || questionConfirmDisabled) return;
    onQuestionSubmit(normalizedAnswer);
  };

  const handleCustomInputKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key !== 'Enter') return;
    if (e.shiftKey) return;
    e.preventDefault();
    submitAnswer();
  };

  if (!open || !interaction) return null;

  if (interaction.kind === 'confirmation') {
    return (
      <div className="fixed inset-0 z-[80] bg-black/60 flex items-center justify-center p-4">
        <div
          data-testid="tool-confirmation-dialog"
          className="w-full max-w-xl bg-card border border-border rounded-xl shadow-2xl"
        >
          <div className="px-4 py-3 border-b border-border flex items-center justify-between">
            <div className="text-sm font-semibold text-card-foreground">工具执行审批</div>
            <div className="text-xs text-muted-foreground">
              {confirmationAwaitingServer
                ? '等待服务端裁决'
                : remainingSeconds > 0
                  ? `剩余 ${remainingSeconds}s`
                  : '已超出建议等待时间'}
            </div>
          </div>
          <div className="p-4 space-y-4">
            <div className="text-xs text-primary">
              来源会话:
              {' '}
              <span data-testid="tool-confirm-source-session" className="font-mono">
                {interaction.sourceSessionId}
              </span>
            </div>
            <div className="text-sm text-card-foreground">
              工具:
              {' '}
              <span data-testid="tool-confirm-name" className="font-mono">{interaction.toolName}</span>
            </div>
            <div className="text-sm text-card-foreground">
              风险等级:
              {' '}
              <span data-testid="tool-confirm-risk" className="font-mono">{interaction.riskLevel}</span>
            </div>
            <div className="space-y-2">
              <div className="text-xs text-muted-foreground">参数</div>
              <pre
                data-testid="tool-confirm-arguments"
                className="text-[11px] text-card-foreground font-mono bg-muted border border-border rounded-md p-3 overflow-auto max-h-44 whitespace-pre-wrap break-all"
              >
                {JSON.stringify(interaction.arguments || {}, null, 2)}
              </pre>
            </div>
            {confirmationAwaitingServer && (
              <div className="rounded-md border border-[#d7ba7d]/40 bg-[#3c3c3c]/40 px-3 py-2 text-xs text-[#d7ba7d]">
                等待服务端确认超时处理结果
              </div>
            )}
            {confirmationTimedOut && interaction.timeoutAction === 'block' && (
              <div className="rounded-md border border-[#9cdcfe]/30 bg-[#3c3c3c]/40 px-3 py-2 text-xs text-[#9cdcfe]">
                已超出建议等待时间，仍可继续手动审批。
              </div>
            )}
            {!wsConnected && (
              <div className="text-xs text-destructive">连接已断开，暂时无法提交审批结果</div>
            )}
          </div>

          <div className="px-4 py-3 border-t border-border flex justify-end gap-2">
            <button
              data-testid="tool-confirm-reject"
              onClick={() => onConfirmationSubmit(false)}
              disabled={confirmationDisabled}
              className="px-3 py-1.5 text-sm rounded border border-border text-card-foreground hover:bg-muted disabled:opacity-50 disabled:cursor-not-allowed"
            >
              拒绝
            </button>
            <button
              data-testid="tool-confirm-approve"
              onClick={() => onConfirmationSubmit(true)}
              disabled={confirmationDisabled}
              className="px-3 py-1.5 text-sm rounded bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              批准
            </button>
          </div>
        </div>
      </div>
    );
  }

  const displaySourceAgent = String(
    interaction.sourceAgentName || interaction.sourceAgentId || 'default'
  ).trim() || 'default';

  return (
    <div className="fixed inset-0 z-[80] bg-black/60 flex items-center justify-center p-4">
      <div
        data-testid="ask-user-dialog"
        className="w-full max-w-xl bg-card border border-border rounded-xl shadow-2xl"
      >
        <div className="px-4 py-3 border-b border-border flex items-center justify-between">
          <div className="text-sm font-semibold text-card-foreground">Agent 需要你补充信息</div>
          <div className="text-xs text-muted-foreground">
            剩余 {remainingSeconds}s
          </div>
        </div>

        <div className="p-4 space-y-4">
          <div className="text-xs text-primary">
            来源 Agent:
            {' '}
            <span data-testid="ask-user-source-agent" className="font-mono">{displaySourceAgent}</span>
          </div>
          {interaction.sourceSessionId && (
            <div className="text-xs text-primary">
              来源会话:
              {' '}
              <span data-testid="ask-user-source-session" className="font-mono">
                {interaction.sourceSessionId}
              </span>
            </div>
          )}
          <p className="text-sm text-card-foreground whitespace-pre-wrap">{interaction.question}</p>

          {interaction.options && interaction.options.length > 0 && (
            <div className="space-y-2">
              <div className="text-xs text-muted-foreground">
                {interaction.multiSelect ? '可多选（也可直接输入自定义内容）' : '可单选（也可直接输入自定义内容）'}
              </div>
              <div className="space-y-2">
                {interaction.options.map((opt, idx) => (
                  <label
                    key={`${opt}_${idx}`}
                    className="flex items-center gap-2 text-sm text-card-foreground"
                    data-testid={`ask-user-option-${idx}`}
                  >
                    {interaction.multiSelect ? (
                      <input
                        type="checkbox"
                        checked={multiChoices.includes(opt)}
                        onChange={() => toggleMultiChoice(opt)}
                        className="accent-primary"
                        disabled={submitting || !wsConnected || remainingSeconds <= 0}
                      />
                    ) : (
                      <input
                        type="radio"
                        name="ask-user-single-choice"
                        checked={singleChoice == opt}
                        onChange={() => setSingleChoice(opt)}
                        className="accent-primary"
                        disabled={submitting || !wsConnected || remainingSeconds <= 0}
                      />
                    )}
                    <span>{opt}</span>
                  </label>
                ))}
              </div>
            </div>
          )}

          <div className="space-y-2">
            <div className="text-xs text-muted-foreground">自定义输入（优先级高于选项）</div>
            <textarea
              data-testid="ask-user-custom-input"
              value={customInput}
              onChange={(e) => setCustomInput(e.target.value)}
              placeholder="输入你的补充说明..."
              className="w-full resize-none rounded-lg border border-neutral-200 bg-white px-3 py-2 text-sm text-neutral-900 placeholder:text-neutral-500 focus:border-primary focus:outline-none disabled:text-neutral-500"
              rows={3}
              onKeyDown={handleCustomInputKeyDown}
              disabled={submitting || !wsConnected || remainingSeconds <= 0}
            />
            <div className="text-xs text-muted-foreground">提示：Enter 确认，Shift+Enter 换行</div>
          </div>

          {!wsConnected && (
            <div className="text-xs text-destructive">连接已断开，暂时无法提交回答</div>
          )}
        </div>

        <div className="px-4 py-3 border-t border-border flex justify-end gap-2">
          <button
            data-testid="ask-user-cancel"
            onClick={onQuestionCancel}
            disabled={submitting}
            className="px-3 py-1.5 text-sm rounded border border-border text-card-foreground hover:bg-muted disabled:opacity-50 disabled:cursor-not-allowed"
          >
            取消
          </button>
          <button
            data-testid="ask-user-confirm"
            onClick={submitAnswer}
            disabled={questionConfirmDisabled}
            className="px-3 py-1.5 text-sm rounded bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            确认
          </button>
        </div>
      </div>
    </div>
  );
}
