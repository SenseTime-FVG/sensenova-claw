'use client';

import { useUIContext } from '@/contexts/UIContext';

export function ActivityBar() {
  const { sidebarView, setSidebarView } = useUIContext();
  return (
    <aside className="activitybar">
      <button
        type="button"
        className={sidebarView === 'history' ? 'active' : ''}
        onClick={() => setSidebarView('history')}
      >
        历史
      </button>
      <button
        type="button"
        className={sidebarView === 'explorer' ? 'active' : ''}
        onClick={() => setSidebarView('explorer')}
      >
        文件
      </button>
    </aside>
  );
}
