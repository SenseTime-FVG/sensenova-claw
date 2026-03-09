'use client';

import { FormEvent, KeyboardEvent, useState } from 'react';

export function InputArea({
  onSubmit,
}: {
  onSubmit: (content: string) => void;
}) {
  const [value, setValue] = useState('');

  const submit = (event: FormEvent) => {
    event.preventDefault();
    const content = value.trim();
    if (!content) return;
    onSubmit(content);
    setValue('');
  };

  const handleKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      const content = value.trim();
      if (content) {
        onSubmit(content);
        setValue('');
      }
    }
  };

  return (
    <form className="input-area" onSubmit={submit}>
      <textarea
        data-testid="chat-input"
        value={value}
        onChange={(event) => setValue(event.target.value)}
        onKeyDown={handleKeyDown}
        placeholder="输入你的问题... (Enter 发送, Shift+Enter 换行)"
        rows={3}
      />
      <button data-testid="send-button" type="submit">
        发送
      </button>
    </form>
  );
}
