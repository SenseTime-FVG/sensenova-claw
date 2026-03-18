'use client';

import { useState, useCallback } from 'react';
import { Search, Sparkles, Globe, GitBranch } from 'lucide-react';
import { DashboardLayout } from '@/components/layout/DashboardLayout';
import { InstalledTab } from './components/InstalledTab';
import { MarketTab } from './components/MarketTab';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';

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
      if (activeFilter !== 'clawhub' && activeFilter !== 'anthropic') {
        setActiveFilter('all');
      }
    }
  }, [searchQuery, activeFilter]);

  const handleClearSearch = useCallback(() => {
    setSearchQuery('');
    setIsSearching(false);
  }, []);

  return (
    <DashboardLayout>
      <div className="flex-1 space-y-8 p-10 lg:p-12">
        <div className="flex items-center justify-between space-y-2">
          <h2 className="text-4xl font-extrabold tracking-tight text-foreground/90">Skills Engine</h2>
        </div>

        <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
          <Card className="shadow-lg border-border/60">
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-3">
              <CardTitle className="text-base font-bold text-muted-foreground uppercase tracking-wider">Market Connectivity</CardTitle>
              <Globe className="h-5 w-5 text-primary" />
            </CardHeader>
            <CardContent>
              <div className="text-3xl font-black text-green-500 flex items-center gap-2">
                <span className="w-2.5 h-2.5 rounded-full bg-green-500 animate-pulse" />
                Connected
              </div>
              <p className="text-sm font-medium text-muted-foreground mt-2">ClawHub & Anthropic Synced</p>
            </CardContent>
          </Card>
        </div>

        <Card className="shadow-xl border-border/80 overflow-hidden">
          <CardHeader className="bg-muted/30 border-b p-8">
            <CardTitle className="text-2xl font-bold">Skills Management</CardTitle>
            <CardDescription className="text-base mt-2">
              Browse, install, and manage skills from external markets or local bundles.
            </CardDescription>
            <div className="flex gap-4 mt-8">
              <div className="relative max-w-xl flex-1">
                <Search className="absolute left-3.5 top-3.5 h-5 w-5 text-muted-foreground" />
                <Input
                  type="text"
                  placeholder="Search skills (e.g. 'web search', 'python')..."
                  value={searchQuery}
                  onChange={e => {
                    setSearchQuery(e.target.value);
                    if (!e.target.value.trim()) setIsSearching(false);
                  }}
                  onKeyDown={e => e.key === 'Enter' && handleSearch()}
                  className="pl-11 py-6 text-base bg-background rounded-xl border-border/60 shadow-inner"
                />
              </div>
              <Button onClick={handleSearch} size="lg" className="rounded-xl px-8 font-bold">Search</Button>
            </div>
          </CardHeader>
          <CardContent className="p-0">
        <div className="flex flex-col md:flex-row min-h-[600px]">
          {/* Nested Sidebar */}
          <aside className="w-full md:w-64 lg:w-72 shrink-0 bg-muted/20 border-r border-border/40 p-6">
            <p className="text-[10px] font-black uppercase tracking-[0.2em] text-muted-foreground/70 mb-4 px-4">Categories</p>
            <nav className="flex space-x-2 md:flex-col md:space-x-0 md:space-y-2">
              <button
                onClick={() => { setActiveFilter('all'); setIsSearching(false); }}
                className={`flex items-center gap-3 font-bold justify-start w-full text-base px-5 py-3.5 rounded-xl transition-all ${
                  activeFilter === 'all'
                    ? "bg-primary text-primary-foreground shadow-lg shadow-primary/20"
                    : "text-muted-foreground hover:bg-muted hover:text-foreground"
                }`}
              >
                <Sparkles className="h-5 w-5" /> All Skills
              </button>
              <button
                onClick={() => { setActiveFilter('installed'); setIsSearching(false); }}
                className={`flex items-center gap-3 font-bold justify-start w-full text-base px-5 py-3.5 rounded-xl transition-all ${
                  activeFilter === 'installed'
                    ? "bg-primary text-primary-foreground shadow-lg shadow-primary/20"
                    : "text-muted-foreground hover:bg-muted hover:text-foreground"
                }`}
              >
                <GitBranch className="h-5 w-5" /> Installed
              </button>
              <div className="h-px bg-border/40 my-2 mx-4" />
              <p className="text-[10px] font-black uppercase tracking-[0.2em] text-muted-foreground/70 mb-2 mt-4 px-4">Marketplaces</p>
              <button
                onClick={() => { setActiveFilter('clawhub'); setIsSearching(false); }}
                className={`flex items-center gap-3 font-bold justify-start w-full text-base px-5 py-3.5 rounded-xl transition-all ${
                  activeFilter === 'clawhub'
                    ? "bg-primary text-primary-foreground shadow-lg shadow-primary/20"
                    : "text-muted-foreground hover:bg-muted hover:text-foreground"
                }`}
              >
                <Globe className="h-5 w-5" /> ClawHub
              </button>
              <button
                onClick={() => { setActiveFilter('anthropic'); setIsSearching(false); }}
                className={`flex items-center gap-3 font-bold justify-start w-full text-base px-5 py-3.5 rounded-xl transition-all ${
                  activeFilter === 'anthropic'
                    ? "bg-primary text-primary-foreground shadow-lg shadow-primary/20"
                    : "text-muted-foreground hover:bg-muted hover:text-foreground"
                }`}
              >
                <Globe className="h-5 w-5" /> Anthropic
              </button>
            </nav>
          </aside>

          {/* Main Content Area */}
          <div className="flex-1 p-8 lg:p-10 space-y-6">
             {activeFilter === 'all' && (
                isSearching ? (
                  <MarketTab
                    onInstalled={handleInstalled}
                    unifiedSearchMode
                    searchQuery={searchQuery}
                    sourceFilter="all"
                    onClearSearch={handleClearSearch}
                  />
                ) : (
                  <InstalledTab key={`all-${refreshKey}`} />
                )
             )}

             {activeFilter === 'installed' && (
                isSearching ? (
                  <MarketTab
                    onInstalled={handleInstalled}
                    unifiedSearchMode
                    searchQuery={searchQuery}
                    sourceFilter="installed"
                    onClearSearch={handleClearSearch}
                  />
                ) : (
                  <InstalledTab key={`installed-${refreshKey}`} categoryFilter="installed" />
                )
             )}

             {activeFilter === 'clawhub' && (
                isSearching ? (
                  <MarketTab
                    onInstalled={handleInstalled}
                    unifiedSearchMode
                    searchQuery={searchQuery}
                    sourceFilter="clawhub"
                    onClearSearch={handleClearSearch}
                  />
                ) : (
                  <MarketTab onInstalled={handleInstalled} defaultSource="clawhub" />
                )
             )}

             {activeFilter === 'anthropic' && (
                isSearching ? (
                  <MarketTab
                    onInstalled={handleInstalled}
                    unifiedSearchMode
                    searchQuery={searchQuery}
                    sourceFilter="anthropic"
                    onClearSearch={handleClearSearch}
                  />
                ) : (
                  <MarketTab onInstalled={handleInstalled} defaultSource="anthropic" />
                )
             )}
          </div>
        </div>
          </CardContent>
        </Card>
      </div>
    </DashboardLayout>
  );
}
