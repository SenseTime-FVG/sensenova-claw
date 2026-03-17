'use client';

import { useEffect, useMemo, useState } from 'react';

export interface QuestionDialogProps {
  open: boolean;
  questionId: string;
  question: string;
  options: string[] | null;
  multiSelect: boolean;
  timeout: number;
  createdAt: number;
  submitting: boolean;
  wsConnected: boolean;
  onSubmit: (answer: string | string[]) => void;
  onCancel: () => void;
}

export function QuestionDialog({
  open,
  questionId,
  question,
  options,
  multiSelect,
  timeout,
  createdAt,
  submitting,
  wsConnected,
  onSubmit,
  onCancel,
}: QuestionDialogProps) {
  const [customInput, setCustomInput] = useState('');
  const [singleChoice, setSingleChoice] = useState('');
  const [multiChoices, setMultiChoices] = useState<string[]>([]);
  const [nowTs, setNowTs] = useState(Date.now());

  useEffect(() => {
    if (!open) return;
    setCustomInput('');
    setSingleChoice('');
    setMultiChoices([]);
  }, [open, questionId]);

  useEffect(() => {
    if (!open) return;
    const timer = window.setInterval(() => setNowTs(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [open]);

  const remainingSeconds = useMemo(() => {
    const elapsed = Math.floor((nowTs - createdAt) / 1000);
    return Math.max(0, timeout - elapsed);
  }, [createdAt, nowTs, timeout]);

  const normalizedAnswer = useMemo(() => {
    const custom = customInput.trim();
    if (custom) return custom;

    if (options && options.length > 0) {
      if (multiSelect) {
        return multiChoices.length > 0 ? multiChoices : null;
      }
      return singleChoice || null;
    }

    return null;
  }, [customInput, options, multiChoices, multiSelect, singleChoice]);

  const confirmDisabled = !normalizedAnswer || submitting || !wsConnected || remainingSeconds <= 0;

  const toggleMultiChoice = (opt: string) => {
    setMultiChoices((prev) => {
      if (prev.includes(opt)) {
        return prev.filter((v) => v !== opt);
      }
      return [...prev, opt];
    });
  };

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-[80] bg-black/60 flex items-center justify-center p-4">
      <div
        data-testid="ask-user-dialog"
        className="w-full max-w-xl bg-[#1e1e1e] border border-[#2d2d30] rounded-xl shadow-2xl"
      >
        <div className="px-4 py-3 border-b border-[#2d2d30] flex items-center justify-between">
          <div className="text-sm font-semibold text-[#cccccc]">Agent 需要你补充信息</div>
          <div className="text-xs text-[#858585]">
            剩余 {remainingSeconds}s
          </div>
        </div>

        <div className="p-4 space-y-4">
          <p className="text-sm text-[#cccccc] whitespace-pre-wrap">{question}</p>

          {options && options.length > 0 && (
            <div className="space-y-2">
              <div className="text-xs text-[#858585]">
                {multiSelect ? '可多选（也可直接输入自定义内容）' : '可单选（也可直接输入自定义内容）'}
              </div>
              <div className="space-y-2">
                {options.map((opt, idx) => (
                  <label
                    key={`${opt}_${idx}`}
                    className="flex items-center gap-2 text-sm text-[#cccccc]"
                    data-testid={`ask-user-option-${idx}`}
                  >
                    {multiSelect ? (
                      <input
                        type="checkbox"
                        checked={multiChoices.includes(opt)}
                        onChange={() => toggleMultiChoice(opt)}
                        className="accent-[#0e639c]"
                        disabled={submitting || !wsConnected || remainingSeconds <= 0}
                      />
                    ) : (
                      <input
                        type="radio"
                        name="ask-user-single-choice"
                        checked={singleChoice === opt}
                        onChange={() => setSingleChoice(opt)}
                        className="accent-[#0e639c]"
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
            <div className="text-xs text-[#858585]">自定义输入（优先级高于选项）</div>
            <textarea
              data-testid="ask-user-custom-input"
              value={customInput}
              onChange={(e) => setCustomInput(e.target.value)}
              placeholder="输入你的补充说明..."
              className="w-full bg-[#252526] border border-[#3c3c3c] rounded-lg px-3 py-2 text-sm text-[#cccccc] placeholder-[#858585] focus:outline-none focus:border-[#0e639c] resize-none"
              rows={3}
              disabled={submitting || !wsConnected || remainingSeconds <= 0}
            />
          </div>

          {!wsConnected && (
            <div className="text-xs text-red-400">连接已断开，暂时无法提交回答</div>
          )}
        </div>

        <div className="px-4 py-3 border-t border-[#2d2d30] flex justify-end gap-2">
          <button
            data-testid="ask-user-cancel"
            onClick={onCancel}
            disabled={submitting}
            className="px-3 py-1.5 text-sm rounded border border-[#3c3c3c] text-[#cccccc] hover:bg-[#2d2d30] disabled:opacity-50 disabled:cursor-not-allowed"
          >
            取消
          </button>
          <button
            data-testid="ask-user-confirm"
            onClick={() => normalizedAnswer && onSubmit(normalizedAnswer)}
            disabled={confirmDisabled}
            className="px-3 py-1.5 text-sm rounded bg-[#0e639c] text-white hover:bg-[#1177bb] disabled:opacity-50 disabled:cursor-not-allowed"
          >
            确认
          </button>
        </div>
      </div>
    </div>
  );
}
