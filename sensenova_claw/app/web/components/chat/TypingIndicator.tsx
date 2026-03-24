'use client';

import { Bot } from 'lucide-react';

export function TypingIndicator() {
  return (
    <div className="flex gap-4 max-w-4xl mx-auto my-6">
      <div className="w-10 h-10 rounded-full bg-primary flex items-center justify-center shrink-0 shadow-md">
        <Bot size={20} className="text-primary-foreground animate-pulse" />
      </div>
      <div className="flex items-center gap-2 pt-4">
        <div className="w-2 h-2 bg-primary/40 rounded-full animate-bounce" style={{ animationDelay: '0s' }} />
        <div className="w-2 h-2 bg-primary/40 rounded-full animate-bounce" style={{ animationDelay: '0.15s' }} />
        <div className="w-2 h-2 bg-primary/40 rounded-full animate-bounce" style={{ animationDelay: '0.3s' }} />
      </div>
    </div>
  );
}
