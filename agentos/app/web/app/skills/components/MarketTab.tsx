'use client';

import { useState, useCallback, useEffect } from 'react';
import { Search, Loader2, GitBranch, CheckCircle, XCircle, X } from 'lucide-react';
import { SkillCard } from './SkillCard';
import { SkillDetailModal } from './SkillDetailModal';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

interface MarketSkill {
  id: string;
  name: string;
  description: string;
  author: string | null;
  version: string | null;
  downloads: number | null;
  source: string;
  category?: string;
  installed?: boolean;
  enabled?: boolean;
}

interface Toast {
  id: number;
  type: 'loading' | 'success' | 'error';
  message: string;
}

let toastId = 0;

interface MarketTabProps {
  onInstalled: () => void;
  // 统一搜索模式
  unifiedSearchMode?: boolean;
  searchQuery?: string;
  sourceFilter?: string;
  onClearSearch?: () => void;
  // 传统市场浏览模式
  defaultSource?: string;
}

export function MarketTab({
  onInstalled,
  unifiedSearchMode,
  searchQuery: externalQuery,
  sourceFilter,
  onClearSearch,
  defaultSource,
}: MarketTabProps) {
  const activeSource = defaultSource || 'clawhub';
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<MarketSkill[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(false);
  const [gitUrl, setGitUrl] = useState('');
  const [gitInstalling, setGitInstalling] = useState(false);
  const [detailModal, setDetailModal] = useState<{ source: string; id: string } | null>(null);
  const [installingIds, setInstallingIds] = useState<Set<string>>(new Set());
  const [toasts, setToasts] = useState<Toast[]>([]);

  // 统一搜索结果
  const [localResults, setLocalResults] = useState<MarketSkill[]>([]);
  const [remoteResults, setRemoteResults] = useState<MarketSkill[]>([]);
  
  // 浏览模式（无搜索时的默认列表）
  const [browseResults, setBrowseResults] = useState<MarketSkill[]>([]);
  const [browseTotal, setBrowseTotal] = useState(0);
  const [browseLoading, setBrowseLoading] = useState(false);
  const [browsePage, setBrowsePage] = useState(1);
  const [browseLoaded, setBrowseLoaded] = useState(false);
  const [browseSource, setBrowseSource] = useState<string>('');

  // 自动清除 success/error toast
  useEffect(() => {
    const timer = setInterval(() => {
      setToasts(prev => prev.filter(t => t.type === 'loading'));
    }, 5000);
    return () => clearInterval(timer);
  }, []);

  const addToast = (type: Toast['type'], message: string): number => {
    const id = ++toastId;
    setToasts(prev => [...prev, { id, type, message }]);
    return id;
  };

  const updateToast = (id: number, type: Toast['type'], message: string) => {
    setToasts(prev => prev.map(t => t.id === id ? { ...t, type, message } : t));
  };

  const removeToast = (id: number) => {
    setToasts(prev => prev.filter(t => t.id !== id));
  };

  // 统一搜索
  const doUnifiedSearch = useCallback(async (q: string, sources: string) => {
    if (!q.trim()) return;
    setLoading(true);
    try {
      const res = await fetch(
        `${API_BASE}/api/skills/search?q=${encodeURIComponent(q)}&sources=${sources}`
      );
      const data = await res.json();
      setLocalResults(data.local_results || []);
      setRemoteResults(data.remote_results || []);
    } catch {
      setLocalResults([]);
      setRemoteResults([]);
    } finally {
      setLoading(false);
    }
  }, []);

  // 统一搜索模式下，外部 query 变化时触发搜索
  useEffect(() => {
    if (unifiedSearchMode && externalQuery?.trim()) {
      const sources = sourceFilter === 'all' || !sourceFilter ? 'all' : sourceFilter;
      doUnifiedSearch(externalQuery, sources);
    }
  }, [unifiedSearchMode, externalQuery, sourceFilter, doUnifiedSearch]);

  // 浏览模式：自动加载市场列表
  const doBrowse = useCallback(async (src: string, p: number) => {
    setBrowseLoading(true);
    try {
      const res = await fetch(
        `${API_BASE}/api/skills/market/browse?source=${src}&page=${p}&page_size=20`
      );
      const data = await res.json();
      setBrowseResults(data.items || []);
      setBrowseTotal(data.total || 0);
      setBrowsePage(p);
      setBrowseLoaded(true);
      setBrowseSource(src);
    } catch {
      setBrowseResults([]);
      setBrowseLoaded(true);
      setBrowseSource(src);
    } finally {
      setBrowseLoading(false);
    }
  }, []);

  // source 切换或首次打开时自动加载
  useEffect(() => {
    if (!unifiedSearchMode && activeSource !== browseSource) {
      setResults([]);
      setQuery('');
      doBrowse(activeSource, 1);
    }
  }, [unifiedSearchMode, activeSource, browseSource, doBrowse]);

  // 传统市场搜索
  const doSearch = useCallback(async (src: string, q: string, p: number) => {
    if (!q.trim()) return;
    setLoading(true);
    try {
      const res = await fetch(
        `${API_BASE}/api/skills/market/search?source=${src}&q=${encodeURIComponent(q)}&page=${p}&page_size=20`
      );
      const data = await res.json();
      setResults(data.items || []);
      setTotal(data.total || 0);
      setPage(p);
    } catch {
      setResults([]);
    } finally {
      setLoading(false);
    }
  }, []);

  const handleInstall = async (source: string, id: string) => {
    if (installingIds.has(id)) return;
    setInstallingIds(prev => new Set(prev).add(id));

    const tid = addToast('loading', `正在安装 ${id}，下载中...`);

    try {
      const res = await fetch(`${API_BASE}/api/skills/install`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ source, id }),
      });
      if (res.ok) {
        const data = await res.json();
        // 依赖检查
        if (data.all_deps_met === false && data.dependencies) {
          const missing = Object.entries(data.dependencies)
            .filter(([, ok]) => !ok)
            .map(([name]) => name);
          updateToast(tid, 'success', `${data.skill_name || id} 安装成功，但缺少依赖: ${missing.join(', ')}`);
        } else {
          updateToast(tid, 'success', `${data.skill_name || id} 安装成功，已自动启用`);
        }
        onInstalled();
        if (unifiedSearchMode && externalQuery) {
          doUnifiedSearch(externalQuery, sourceFilter === 'all' || !sourceFilter ? 'all' : sourceFilter);
        } else if (query) {
          doSearch(activeSource, query, page);
        } else {
          doBrowse(activeSource, browsePage);
        }
      } else {
        const err = await res.json();
        updateToast(tid, 'error', `安装失败: ${err?.detail?.error || '未知错误'}`);
      }
    } catch (e: any) {
      updateToast(tid, 'error', `安装失败: ${e?.message || '网络错误'}`);
    } finally {
      setInstallingIds(prev => {
        const next = new Set(prev);
        next.delete(id);
        return next;
      });
    }
  };

  const handleGitInstall = async () => {
    if (!gitUrl.trim()) return;
    setGitInstalling(true);
    const tid = addToast('loading', `正在从 Git 安装，克隆中...`);
    try {
      const res = await fetch(`${API_BASE}/api/skills/install`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ source: 'git', repo_url: gitUrl }),
      });
      if (res.ok) {
        const data = await res.json();
        if (data.all_deps_met === false && data.dependencies) {
          const missing = Object.entries(data.dependencies)
            .filter(([, ok]) => !ok)
            .map(([name]) => name);
          updateToast(tid, 'success', `${data.skill_name || 'Skill'} 安装成功，但缺少依赖: ${missing.join(', ')}`);
        } else {
          updateToast(tid, 'success', `${data.skill_name || 'Skill'} 安装成功，已自动启用`);
        }
        setGitUrl('');
        onInstalled();
      } else {
        const err = await res.json();
        updateToast(tid, 'error', `安装失败: ${err?.detail?.error || '未知错误'}`);
      }
    } catch (e: any) {
      updateToast(tid, 'error', `安装失败: ${e?.message || '网络错误'}`);
    } finally {
      setGitInstalling(false);
    }
  };

  // --- 统一搜索模式渲染 ---
  if (unifiedSearchMode) {
    // 按 sourceFilter 过滤
    let filteredLocal = localResults;
    let filteredRemote = remoteResults;
    if (sourceFilter && sourceFilter !== 'all') {
      if (sourceFilter === 'installed') {
        filteredRemote = [];
      } else if (sourceFilter === 'clawhub' || sourceFilter === 'anthropic') {
        filteredLocal = [];
        filteredRemote = remoteResults.filter(r => r.category === sourceFilter || r.source === sourceFilter);
      }
    }

    return (
      <div className="space-y-4">
        {/* Toast 通知 */}
        <ToastContainer toasts={toasts} removeToast={removeToast} />

        {loading ? (
          <div className="flex items-center justify-center py-12">
            <Loader2 className="animate-spin text-muted-foreground" size={32} />
          </div>
        ) : (
          <>
            {onClearSearch && (
              <div className="flex items-center justify-between">
                <span className="text-sm text-muted-foreground">
                  Search "{externalQuery}": Local {filteredLocal.length}, Remote {filteredRemote.length}
                </span>
                <Button variant="link" size="sm" onClick={onClearSearch}>
                  Clear Query
                </Button>
              </div>
            )}

            {/* 本地匹配（已安装优先） */}
            {filteredLocal.length > 0 && (
              <div>
                <h3 className="text-sm font-semibold text-muted-foreground mb-3 pb-2 border-b">Installed Matches</h3>
                <div className="grid gap-3 grid-cols-1 md:grid-cols-2 lg:grid-cols-3">
                  {filteredLocal.map(skill => (
                    <SkillCard
                      key={skill.id}
                      name={skill.name}
                      description={skill.description}
                      category={skill.category}
                      source={skill.source}
                      version={skill.version}
                      installed
                      enabled={skill.enabled}
                    />
                  ))}
                </div>
              </div>
            )}

            {/* 远程结果 */}
            {filteredRemote.length > 0 && (
              <div className="pt-4">
                <h3 className="text-sm font-semibold text-muted-foreground mb-3 pb-2 border-b">Market Results</h3>
                <div className="grid gap-3 grid-cols-1 md:grid-cols-2 lg:grid-cols-3">
                  {filteredRemote.map(skill => (
                    <SkillCard
                      key={skill.id}
                      name={skill.name}
                      description={skill.description}
                      category={skill.category || skill.source}
                      source={skill.source}
                      version={skill.version}
                      downloads={skill.downloads}
                      author={skill.author}
                      installed={skill.installed}
                      installing={installingIds.has(skill.id)}
                      onInstall={skill.installed || installingIds.has(skill.id) ? undefined : () => handleInstall(skill.source, skill.id)}
                      onClick={() => setDetailModal({ source: skill.source, id: skill.id })}
                    />
                  ))}
                </div>
              </div>
            )}

            {filteredLocal.length === 0 && filteredRemote.length === 0 && (
              <div className="text-center text-muted-foreground py-12 border border-dashed rounded-lg bg-muted/10">No Search Results Found</div>
            )}
          </>
        )}

        {detailModal && (
          <SkillDetailModal
            source={detailModal.source}
            skillId={detailModal.id}
            onClose={() => setDetailModal(null)}
            onInstall={() => {
              handleInstall(detailModal.source, detailModal.id);
              setDetailModal(null);
            }}
          />
        )}
      </div>
    );
  }

  // --- 传统市场浏览模式渲染 ---
  return (
    <div className="space-y-4">
      {/* Toast 通知 */}
      <ToastContainer toasts={toasts} removeToast={removeToast} />

      {/* Git URL 输入 */}
      <div className="flex items-center gap-2 bg-muted/50 rounded-lg p-3 border border-border mt-4">
        <GitBranch size={16} className="text-muted-foreground shrink-0" />
        <Input
          className="flex-1 bg-transparent border-0 focus-visible:ring-0 px-0 h-auto shadow-none"
          placeholder="Install from Git URL: https://github.com/user/skill-repo"
          value={gitUrl}
          onChange={e => setGitUrl(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && handleGitInstall()}
        />
        <Button
          size="sm"
          onClick={handleGitInstall}
          disabled={gitInstalling || !gitUrl.trim()}
        >
          {gitInstalling ? 'Installing...' : 'Install'}
        </Button>
      </div>

      {/* 搜索框 */}
      <div className="flex items-center gap-4 mt-6">
        <div className="relative flex-1 max-w-md">
          <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
          <Input
            className="pl-8 bg-background"
            placeholder={`Search ${activeSource === 'clawhub' ? 'ClawHub' : 'Anthropic'} market...`}
            value={query}
            onChange={e => setQuery(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && doSearch(activeSource, query, 1)}
          />
        </div>
        <Button variant="secondary" onClick={() => doSearch(activeSource, query, 1)}>
          Search Market
        </Button>
      </div>

      {/* 搜索结果 */}
      {loading ? (
        <div className="flex items-center justify-center py-12">
          <Loader2 className="animate-spin text-muted-foreground" size={32} />
        </div>
      ) : results.length > 0 ? (
        <div className="space-y-3">
          <div className="text-xs text-muted-foreground pb-2 border-b">Displaying {total} results</div>
          <div className="grid gap-3 grid-cols-1 md:grid-cols-2 lg:grid-cols-3">
            {results.map(skill => (
              <SkillCard
                key={skill.id}
                name={skill.name}
                description={skill.description}
                category={activeSource}
                source={skill.source}
                version={skill.version}
                downloads={skill.downloads}
                author={skill.author}
                installed={skill.installed}
                installing={installingIds.has(skill.id)}
                onInstall={skill.installed || installingIds.has(skill.id) ? undefined : () => handleInstall(skill.source, skill.id)}
                onClick={() => setDetailModal({ source: skill.source, id: skill.id })}
              />
            ))}
          </div>
          {total > 20 && (
            <div className="flex justify-center gap-2 pt-6">
              <Button
                variant="outline"
                size="sm"
                disabled={page <= 1}
                onClick={() => doSearch(activeSource, query, page - 1)}
              >
                Previous
              </Button>
              <span className="text-sm text-muted-foreground flex items-center px-4">Page {page}</span>
              <Button
                variant="outline"
                size="sm"
                disabled={page * 20 >= total}
                onClick={() => doSearch(activeSource, query, page + 1)}
              >
                Next
              </Button>
            </div>
          )}
        </div>
      ) : query ? (
        <div className="text-center text-muted-foreground py-12 border border-dashed rounded-lg bg-muted/10">No market results found.</div>
      ) : null}

      {/* 浏览列表（无搜索时显示） */}
      {!query && results.length === 0 && (
        browseLoading ? (
          <div className="flex items-center justify-center py-12">
            <Loader2 className="animate-spin text-muted-foreground" size={32} />
            <span className="ml-3 text-sm text-muted-foreground">Loading {activeSource === 'clawhub' ? 'ClawHub' : 'Anthropic'} market...</span>
          </div>
        ) : browseResults.length > 0 ? (
          <div className="space-y-3">
            <div className="text-xs text-muted-foreground pb-2 border-b">
              {activeSource === 'clawhub' ? 'ClawHub' : 'Anthropic'} Market · {browseTotal} Skills
            </div>
            <div className="grid gap-3 grid-cols-1 md:grid-cols-2 lg:grid-cols-3">
              {browseResults.map(skill => (
                <SkillCard
                  key={skill.id}
                  name={skill.name}
                  description={skill.description}
                  category={activeSource}
                  source={skill.source || activeSource}
                  version={skill.version}
                  downloads={skill.downloads}
                  author={skill.author}
                  installed={skill.installed}
                  installing={installingIds.has(skill.id)}
                  onInstall={skill.installed || installingIds.has(skill.id) ? undefined : () => handleInstall(activeSource, skill.id)}
                  onClick={() => setDetailModal({ source: activeSource, id: skill.id })}
                />
              ))}
            </div>
            {browseTotal > 20 && (
              <div className="flex justify-center gap-2 pt-6">
                <Button
                  variant="outline"
                  size="sm"
                  disabled={browsePage <= 1}
                  onClick={() => doBrowse(activeSource, browsePage - 1)}
                >
                  Previous
                </Button>
                <span className="text-sm text-muted-foreground flex items-center px-4">Page {browsePage}</span>
                <Button
                  variant="outline"
                  size="sm"
                  disabled={browsePage * 20 >= browseTotal}
                  onClick={() => doBrowse(activeSource, browsePage + 1)}
                >
                  Next
                </Button>
              </div>
            )}
          </div>
        ) : browseLoaded ? (
          <div className="text-center text-muted-foreground py-12 border border-dashed rounded-lg bg-muted/10">
            Market is unavailable right now. Try searching above!
          </div>
        ) : null
      )}

      {/* 详情弹窗 */}
      {detailModal && (
        <SkillDetailModal
          source={detailModal.source}
          skillId={detailModal.id}
          onClose={() => setDetailModal(null)}
          onInstall={() => {
            handleInstall(detailModal.source, detailModal.id);
            setDetailModal(null);
          }}
        />
      )}
    </div>
  );
}

// 独立的 Toast 容器组件
function ToastContainer({ toasts, removeToast }: { toasts: Toast[]; removeToast: (id: number) => void }) {
  if (toasts.length === 0) return null;
  return (
    <div className="fixed top-20 right-8 z-50 space-y-2 max-w-sm">
      {toasts.map(toast => (
        <div
          key={toast.id}
          className={`flex items-center gap-3 px-4 py-3 rounded-lg shadow-xl border text-sm bg-card transition-all ${
            toast.type === 'loading'
              ? 'border-primary text-foreground'
              : toast.type === 'success'
                ? 'border-green-600 text-green-500'
                : 'border-destructive text-destructive'
          }`}
        >
          {toast.type === 'loading' && <Loader2 size={16} className="animate-spin text-primary shrink-0" />}
          {toast.type === 'success' && <CheckCircle size={16} className="text-green-500 shrink-0" />}
          {toast.type === 'error' && <XCircle size={16} className="text-destructive shrink-0" />}
          <span className="flex-1 min-w-0 font-medium">{toast.message}</span>
          {toast.type !== 'loading' && (
            <button onClick={() => removeToast(toast.id)} className="text-muted-foreground hover:text-foreground shrink-0 rounded-full hover:bg-muted p-1 transition-colors">
              <X size={14} />
            </button>
          )}
        </div>
      ))}
    </div>
  );
}
