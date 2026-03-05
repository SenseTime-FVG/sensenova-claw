'use client';

import { FormEvent, useState } from 'react';

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

  return (
    <form className="input-area" onSubmit={submit}>
      <textarea
        data-testid="chat-input"
        value={value}
        onChange={(event) => setValue(event.target.value)}
        placeholder="输入你的问题..."
        rows={3}
      />
      <button data-testid="send-button" type="submit">
        发送
      </button>
    </form>
  );
}
