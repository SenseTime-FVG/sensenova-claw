'use client';

import { useState, useCallback } from 'react';

export function useResizablePreview(initialHeight: number = 350, minHeight: number = 180) {
  const [previewHeight, setPreviewHeight] = useState(initialHeight);

  const onPreviewResize = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    const startY = e.clientY;
    const startH = previewHeight;

    const onMove = (ev: MouseEvent) => {
      const delta = startY - ev.clientY;
      const maxHeight = window.innerHeight * 0.8;
      setPreviewHeight(Math.max(minHeight, Math.min(maxHeight, startH + delta)));
    };

    const onUp = () => {
      document.removeEventListener('mousemove', onMove);
      document.removeEventListener('mouseup', onUp);
    };

    document.addEventListener('mousemove', onMove);
    document.addEventListener('mouseup', onUp);
  }, [previewHeight, minHeight]);

  return {
    previewHeight,
    setPreviewHeight,
    onPreviewResize,
  };
}
