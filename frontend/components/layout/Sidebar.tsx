'use client';

import { useUIContext } from '@/contexts/UIContext';

export function Sidebar() {
  const { sidebarView } = useUIContext();
  return (
    <aside className="sidebar">
      <h3>{sidebarView === 'history' ? '会话历史' : '文件浏览器'}</h3>
      <p>{sidebarView === 'history' ? 'v0.1 暂提供基础会话视图。' : 'v0.1 暂提供占位文件树。'}</p>
    </aside>
  );
}
