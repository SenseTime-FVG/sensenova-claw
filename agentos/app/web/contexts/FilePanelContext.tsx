'use client';

import { createContext, useContext, useState, useCallback, type ReactNode } from 'react';

interface FilePanelState {
  focusPath: string | null;
  focusGeneration: number;
  openToPath: (path: string) => void;
}

const FilePanelContext = createContext<FilePanelState>({
  focusPath: null,
  focusGeneration: 0,
  openToPath: () => {},
});

export function FilePanelProvider({ children }: { children: ReactNode }) {
  const [focusPath, setFocusPath] = useState<string | null>(null);
  const [focusGeneration, setFocusGeneration] = useState(0);

  const openToPath = useCallback((path: string) => {
    setFocusPath(path);
    setFocusGeneration((g) => g + 1);
  }, []);

  return (
    <FilePanelContext.Provider value={{ focusPath, focusGeneration, openToPath }}>
      {children}
    </FilePanelContext.Provider>
  );
}

export function useFilePanel() {
  return useContext(FilePanelContext);
}
