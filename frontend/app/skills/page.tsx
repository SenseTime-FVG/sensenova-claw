'use client';

import { useState, useCallback } from 'react';
import { Sparkles, Package } from 'lucide-react';
import { DashboardLayout } from '@/components/layout/DashboardLayout';
import { InstalledTab } from './components/InstalledTab';
import { MarketTab } from './components/MarketTab';

type Tab = 'installed' | 'market';

export default function SkillsPage() {
  const [activeTab, setActiveTab] = useState<Tab>('installed');
  const [refreshKey, setRefreshKey] = useState(0);

  const handleInstalled = useCallback(() => {
    setRefreshKey(k => k + 1);
  }, []);

  return (
    <DashboardLayout>
      <div className="h-full flex flex-col">
        {/* Header */}
        <div className="bg-[#252526] border-b border-[#2d2d30] p-4">
          <h1 className="text-xl font-semibold text-[#cccccc] mb-3">Skills 管理</h1>
          <div className="flex gap-1">
            <button
              className={`flex items-center gap-1.5 px-3 py-1.5 text-sm rounded transition-colors ${
                activeTab === 'installed'
                  ? 'bg-[#0e639c] text-white'
                  : 'text-[#858585] hover:text-[#cccccc] hover:bg-[#3c3c3c]'
              }`}
              onClick={() => setActiveTab('installed')}
            >
              <Sparkles size={14} /> 已安装
            </button>
            <button
              className={`flex items-center gap-1.5 px-3 py-1.5 text-sm rounded transition-colors ${
                activeTab === 'market'
                  ? 'bg-[#0e639c] text-white'
                  : 'text-[#858585] hover:text-[#cccccc] hover:bg-[#3c3c3c]'
              }`}
              onClick={() => setActiveTab('market')}
            >
              <Package size={14} /> 市场浏览
            </button>
          </div>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-auto p-4">
          {activeTab === 'installed' ? (
            <InstalledTab key={refreshKey} />
          ) : (
            <MarketTab onInstalled={handleInstalled} />
          )}
        </div>
      </div>
    </DashboardLayout>
  );
}
