'use client';

import { useState, useCallback } from 'react';
import { Search, Sparkles, Globe, GitBranch } from 'lucide-react';
import { DashboardLayout } from '@/components/layout/DashboardLayout';
import { InstalledTab } from './components/InstalledTab';
import { MarketTab } from './components/MarketTab';

type FilterTab = 'all' | 'installed' | 'clawhub' | 'anthropic';

export default function SkillsPage() {
  const [activeFilter, setActiveFilter] = useState<FilterTab>('all');
  const [searchQuery, setSearchQuery] = useState('');
  const [isSearching, setIsSearching] = useState(false);
  const [refreshKey, setRefreshKey] = useState(0);

  const handleInstalled = useCallback(() => {
    setRefreshKey(k => k + 1);
  }, []);

  const handleSearch = useCallback(() => {
    if (searchQuery.trim()) {
      setIsSearching(true);
    }
  }, [searchQuery]);

  const handleClearSearch = useCallback(() => {
    setSearchQuery('');
    setIsSearching(false);
  }, []);

  const tabs: { key: FilterTab; label: string; icon: React.ReactNode }[] = [
    { key: 'all', label: '全部', icon: <Sparkles size={14} /> },
    { key: 'installed', label: '已安装', icon: <Sparkles size={14} /> },
    { key: 'clawhub', label: 'ClawHub', icon: <Globe size={14} /> },
    { key: 'anthropic', label: 'Anthropic', icon: <Globe size={14} /> },
  ];

  return (
    <DashboardLayout>
      <div className="h-full flex flex-col">
        {/* Header */}
        <div className="bg-[#252526] border-b border-[#2d2d30] p-4">
          <h1 className="text-xl font-semibold text-[#cccccc] mb-3">Skills 管理</h1>

          {/* 搜索栏 + Git URL */}
          <div className="flex items-center gap-2 mb-3">
            <div className="relative flex-1">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-[#858585]" size={16} />
              <input
                className="w-full bg-[#3c3c3c] border border-[#2d2d30] rounded pl-9 pr-3 py-2 text-sm text-[#cccccc] placeholder-[#858585] focus:border-[#007acc] focus:outline-none"
                placeholder="搜索 skills..."
                value={searchQuery}
                onChange={e => {
                  setSearchQuery(e.target.value);
                  if (!e.target.value.trim()) {
                    setIsSearching(false);
                  }
                }}
                onKeyDown={e => e.key === 'Enter' && handleSearch()}
              />
            </div>
            <button
              className="px-4 py-2 text-sm rounded bg-[#0e639c] text-white hover:bg-[#1177bb]"
              onClick={handleSearch}
            >
              搜索
            </button>
          </div>

          {/* Filter Tabs */}
          <div className="flex gap-1">
            {tabs.map(tab => (
              <button
                key={tab.key}
                className={`flex items-center gap-1.5 px-3 py-1.5 text-sm rounded transition-colors ${
                  activeFilter === tab.key
                    ? 'bg-[#0e639c] text-white'
                    : 'text-[#858585] hover:text-[#cccccc] hover:bg-[#3c3c3c]'
                }`}
                onClick={() => {
                  setActiveFilter(tab.key);
                  if (!isSearching && (tab.key === 'clawhub' || tab.key === 'anthropic')) {
                    // 切到市场 tab 时不自动搜索
                  }
                }}
              >
                {tab.icon} {tab.label}
              </button>
            ))}
          </div>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-auto p-4">
          {isSearching ? (
            <MarketTab
              onInstalled={handleInstalled}
              unifiedSearchMode
              searchQuery={searchQuery}
              sourceFilter={activeFilter}
              onClearSearch={handleClearSearch}
            />
          ) : activeFilter === 'clawhub' || activeFilter === 'anthropic' ? (
            <MarketTab
              onInstalled={handleInstalled}
              defaultSource={activeFilter}
            />
          ) : (
            <InstalledTab
              key={refreshKey}
              categoryFilter={activeFilter === 'installed' ? 'installed' : undefined}
            />
          )}
        </div>
      </div>
    </DashboardLayout>
  );
}
