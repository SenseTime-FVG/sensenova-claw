'use client';

import { useMemo, useState, type KeyboardEvent } from 'react';
import { Send } from 'lucide-react';

import { cn } from '@/lib/utils';

export interface AskUserResponseFormValue {
  question: string;
  options: string[] | null;
  multiSelect: boolean;
}

interface AskUserResponseFormProps {
  value: AskUserResponseFormValue;
  pending?: boolean;
  resolved?: boolean;
  pendingText?: string;
  className?: string;
  testIdPrefix?: string;
  onSubmit: (answer: string) => void;
  onCancel?: () => void;
}

export function AskUserResponseForm({
  value,
  pending = false,
  resolved = false,
  pendingText = '已提交回复，等待服务端确认最终结果。',
  className,
  testIdPrefix = 'ask-user-shared',
  onSubmit,
  onCancel,
}: AskUserResponseFormProps) {
  const [customInput, setCustomInput] = useState('');
  const [singleChoice, setSingleChoice] = useState('');
  const [multiChoices, setMultiChoices] = useState<string[]>([]);

  const normalizedAnswer = useMemo(() => {
    const custom = customInput.trim();
    if (custom) return custom;
    if (value.options && value.options.length > 0) {
      if (value.multiSelect) {
        return multiChoices.length > 0 ? multiChoices.join(', ') : '';
      }
      return singleChoice;
    }
    return '';
  }, [customInput, multiChoices, singleChoice, value.multiSelect, value.options]);

  const disabled = pending || resolved;

  const toggleMultiChoice = (option: string) => {
    setMultiChoices((prev) => (
      prev.includes(option)
        ? prev.filter((item) => item !== option)
        : [...prev, option]
    ));
  };

  const submit = () => {
    if (!normalizedAnswer || disabled) return;
    onSubmit(normalizedAnswer);
  };

  const handleKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key !== 'Enter' || event.shiftKey) return;
    event.preventDefault();
    submit();
  };

  return (
    <div className={cn('space-y-3', className)}>
      <p className="text-xs leading-relaxed text-foreground/80 whitespace-pre-wrap">
        {value.question}
      </p>

      {value.options && value.options.length > 0 && (
        <div className="space-y-1.5">
          <div className="text-[11px] text-muted-foreground">
            {value.multiSelect ? '可多选' : '可单选'}
          </div>
          <div className="space-y-1">
            {value.options.map((option, index) => (
              <label
                key={`${option}_${index}`}
                className="flex items-center gap-2 text-xs text-foreground/80 cursor-pointer hover:text-foreground transition-colors"
              >
                {value.multiSelect ? (
                  <input
                    type="checkbox"
                    checked={multiChoices.includes(option)}
                    onChange={() => toggleMultiChoice(option)}
                    disabled={disabled}
                    className="h-3.5 w-3.5 accent-sky-500"
                  />
                ) : (
                  <input
                    type="radio"
                    name={`${testIdPrefix}-choice`}
                    checked={singleChoice === option}
                    onChange={() => setSingleChoice(option)}
                    disabled={disabled}
                    className="h-3.5 w-3.5 accent-sky-500"
                  />
                )}
                <span>{option}</span>
              </label>
            ))}
          </div>
        </div>
      )}

      <div className="space-y-1.5">
        <div className="text-[11px] text-muted-foreground">
          {value.options && value.options.length > 0 ? '自定义输入（优先级高于选项）' : '请输入回复'}
        </div>
        <textarea
          data-testid={`${testIdPrefix}-custom-input`}
          value={customInput}
          onChange={(event) => setCustomInput(event.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="输入你的回复..."
          rows={2}
          disabled={disabled}
          className="w-full resize-none rounded-lg border border-neutral-200 bg-white px-3 py-1.5 text-xs text-foreground placeholder-muted-foreground/50 focus:border-sky-400 focus:outline-none disabled:cursor-not-allowed disabled:bg-neutral-100"
        />
      </div>

      {pending && (
        <div
          data-testid={`${testIdPrefix}-pending`}
          className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-[11px] text-amber-700"
        >
          {pendingText}
        </div>
      )}

      {!resolved && (
        <div className="flex gap-2">
          {onCancel && (
            <button
              type="button"
              onClick={onCancel}
              disabled={disabled}
              className="rounded-lg border border-neutral-200 bg-white px-3 py-1.5 text-xs font-medium text-neutral-600 transition-colors hover:bg-neutral-50 disabled:cursor-not-allowed disabled:opacity-50"
            >
              取消
            </button>
          )}
          <button
            data-testid={`${testIdPrefix}-confirm`}
            type="button"
            onClick={submit}
            disabled={!normalizedAnswer || disabled}
            className={cn(
              'flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-xs font-semibold transition-all',
              !normalizedAnswer || disabled
                ? 'cursor-not-allowed border-neutral-200 bg-neutral-100 text-neutral-400'
                : 'border-sky-300 bg-sky-500 text-white shadow-sm shadow-sky-200 hover:bg-sky-600',
            )}
          >
            <Send size={12} />
            确认
          </button>
        </div>
      )}
    </div>
  );
}
