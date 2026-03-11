'use client';

import { ReactNode } from 'react';
import { DashboardNav } from './DashboardNav';

interface DashboardLayoutProps {
  children: ReactNode;
}

export function DashboardLayout({ children }: DashboardLayoutProps) {
  return (
    <div className="flex h-screen bg-[#1e1e1e] text-[#cccccc]">
      <DashboardNav />
      <div className="flex-1 flex flex-col overflow-hidden">
        <div className="h-9 bg-[#323233] border-b border-[#2d2d30] flex items-center px-4">
          <span className="text-sm font-semibold text-[#cccccc]">AgentOS Dashboard</span>
        </div>
        <div className="flex-1 overflow-auto">
          {children}
        </div>
        <div className="h-6 bg-[#007acc] flex items-center px-4 text-xs text-white">
          <span>AgentOS v1.0.0</span>
          <span className="ml-auto">Ready</span>
        </div>
      </div>
    </div>
  );
}
