'use client';

import { useEffect, useRef } from 'react';

interface InlineSessionTitleEditorProps {
  value: string;
  onChange: (value: string) => void;
  onSubmit: () => void;
  onCancel: () => void;
  className?: string;
  testId?: string;
}

export function InlineSessionTitleEditor({
  value,
  onChange,
  onSubmit,
  onCancel,
  className,
  testId,
}: InlineSessionTitleEditorProps) {
  const inputRef = useRef<HTMLInputElement | null>(null);
  const skipBlurSubmitRef = useRef(false);

  useEffect(() => {
    inputRef.current?.focus();
    inputRef.current?.select();
  }, []);

  return (
    <input
      ref={inputRef}
      data-testid={testId}
      value={value}
      onChange={(event) => onChange(event.target.value)}
      onClick={(event) => event.stopPropagation()}
      onBlur={() => {
        if (skipBlurSubmitRef.current) {
          skipBlurSubmitRef.current = false;
          return;
        }
        onSubmit();
      }}
      onKeyDown={(event) => {
        if (event.key === 'Enter') {
          event.preventDefault();
          skipBlurSubmitRef.current = true;
          onSubmit();
          return;
        }
        if (event.key === 'Escape') {
          event.preventDefault();
          skipBlurSubmitRef.current = true;
          onCancel();
        }
      }}
      className={className}
    />
  );
}
