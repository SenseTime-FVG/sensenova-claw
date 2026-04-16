'use client';

import { useEffect, useRef } from 'react';

interface SessionContextMenuProps {
  open: boolean;
  x: number;
  y: number;
  onClose: () => void;
  onRename: () => void;
  testId?: string;
}

export function SessionContextMenu({
  open,
  x,
  y,
  onClose,
  onRename,
  testId = 'session-context-menu',
}: SessionContextMenuProps) {
  const menuRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!open) return undefined;

    const handlePointerDown = (event: MouseEvent) => {
      if (!menuRef.current?.contains(event.target as Node)) {
        onClose();
      }
    };
    const handleEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        onClose();
      }
    };

    document.addEventListener('mousedown', handlePointerDown);
    document.addEventListener('keydown', handleEscape);
    return () => {
      document.removeEventListener('mousedown', handlePointerDown);
      document.removeEventListener('keydown', handleEscape);
    };
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div
      ref={menuRef}
      data-testid={testId}
      className="fixed z-[100] min-w-[140px] rounded-xl border border-border/80 bg-background/95 p-1 shadow-2xl backdrop-blur"
      style={{ left: x, top: y }}
    >
      <button
        type="button"
        data-testid={`${testId}-rename`}
        className="w-full rounded-lg px-3 py-2 text-left text-sm font-medium text-foreground transition-colors hover:bg-muted"
        onClick={() => {
          onRename();
          onClose();
        }}
      >
        重命名
      </button>
    </div>
  );
}
