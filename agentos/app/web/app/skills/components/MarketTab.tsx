'use client';

import { useState, useCallback, useEffect } from 'react';
import { Search, Loader2, GitBranch, CheckCircle, XCircle, X } from 'lucide-react';
import { SkillCard } from './SkillCard';
import { SkillDetailModal } from './SkillDetailModal';

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
          <div className="flex items-center justify-center h-32">
            <Loader2 className="animate-spin text-[#858585]" size={24} />
          </div>
        ) : (
          <>
            {onClearSearch && (
              <div className="flex items-center justify-between">
                <span className="text-sm text-[#858585]">
                  搜索 &quot;{externalQuery}&quot;：本地 {filteredLocal.length} 个，远程 {filteredRemote.length} 个
                </span>
                <button
                  className="text-xs text-[#007acc] hover:underline"
                  onClick={onClearSearch}
                >
                  清除搜索
                </button>
              </div>
            )}

            {/* 本地匹配（已安装优先） */}
            {filteredLocal.length > 0 && (
              <div>
                <h3 className="text-sm font-medium text-[#858585] mb-2">已安装匹配</h3>
                <div className="space-y-2">
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
              <div>
                <h3 className="text-sm font-medium text-[#858585] mb-2">市场结果</h3>
                <div className="space-y-2">
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
              <div className="text-center text-[#858585] py-8">无搜索结果</div>
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
      <div className="flex items-center gap-2 bg-[#252526] rounded p-2 border border-[#2d2d30]">
        <GitBranch size={14} className="text-[#858585] shrink-0" />
        <input
          className="flex-1 bg-transparent text-sm text-[#cccccc] placeholder-[#858585] focus:outline-none"
          placeholder="从 Git URL 安装: https://github.com/user/skill-repo"
          value={gitUrl}
          onChange={e => setGitUrl(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && handleGitInstall()}
        />
        <button
          className="px-3 py-1 text-xs rounded bg-[#0e639c] text-white hover:bg-[#1177bb] disabled:opacity-50"
          onClick={handleGitInstall}
          disabled={gitInstalling || !gitUrl.trim()}
        >
          {gitInstalling ? '安装中...' : '安装'}
        </button>
      </div>

      {/* 搜索框 */}
      <div className="flex items-center gap-2">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-[#858585]" size={16} />
          <input
            className="w-full bg-[#3c3c3c] border border-[#2d2d30] rounded pl-9 pr-3 py-2 text-sm text-[#cccccc] placeholder-[#858585] focus:border-[#007acc] focus:outline-none"
            placeholder={`在 ${activeSource === 'clawhub' ? 'ClawHub' : 'Anthropic'} 搜索 skills...`}
            value={query}
            onChange={e => setQuery(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && doSearch(activeSource, query, 1)}
          />
        </div>
        <button
          className="px-4 py-2 text-sm rounded bg-[#0e639c] text-white hover:bg-[#1177bb]"
          onClick={() => doSearch(activeSource, query, 1)}
        >
          搜索
        </button>
      </div>

      {/* 搜索结果 */}
      {loading ? (
        <div className="flex items-center justify-center h-32">
          <Loader2 className="animate-spin text-[#858585]" size={24} />
        </div>
      ) : results.length > 0 ? (
        <div className="space-y-2">
          <div className="text-xs text-[#858585]">共 {total} 个结果</div>
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
          {total > 20 && (
            <div className="flex justify-center gap-2 pt-2">
              <button
                className="px-3 py-1 text-xs rounded bg-[#3c3c3c] text-[#cccccc] disabled:opacity-30"
                disabled={page <= 1}
                onClick={() => doSearch(activeSource, query, page - 1)}
              >
                上一页
              </button>
              <span className="text-xs text-[#858585] py-1">第 {page} 页</span>
              <button
                className="px-3 py-1 text-xs rounded bg-[#3c3c3c] text-[#cccccc] disabled:opacity-30"
                disabled={page * 20 >= total}
                onClick={() => doSearch(activeSource, query, page + 1)}
              >
                下一页
              </button>
            </div>
          )}
        </div>
      ) : query ? (
        <div className="text-center text-[#858585] py-8">无搜索结果，请尝试其他关键词</div>
      ) : null}

      {/* 浏览列表（无搜索时显示） */}
      {!query && results.length === 0 && (
        browseLoading ? (
          <div className="flex items-center justify-center h-32">
            <Loader2 className="animate-spin text-[#858585]" size={24} />
            <span className="ml-2 text-sm text-[#858585]">正在加载 {activeSource === 'clawhub' ? 'ClawHub' : 'Anthropic'} skills...</span>
          </div>
        ) : browseResults.length > 0 ? (
          <div className="space-y-2">
            <div className="text-xs text-[#858585]">
              {activeSource === 'clawhub' ? 'ClawHub' : 'Anthropic'} 市场 · 共 {browseTotal} 个 skills
            </div>
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
            {browseTotal > 20 && (
              <div className="flex justify-center gap-2 pt-2">
                <button
                  className="px-3 py-1 text-xs rounded bg-[#3c3c3c] text-[#cccccc] disabled:opacity-30"
                  disabled={browsePage <= 1}
                  onClick={() => doBrowse(activeSource, browsePage - 1)}
                >
                  上一页
                </button>
                <span className="text-xs text-[#858585] py-1">第 {browsePage} 页</span>
                <button
                  className="px-3 py-1 text-xs rounded bg-[#3c3c3c] text-[#cccccc] disabled:opacity-30"
                  disabled={browsePage * 20 >= browseTotal}
                  onClick={() => doBrowse(activeSource, browsePage + 1)}
                >
                  下一页
                </button>
              </div>
            )}
          </div>
        ) : browseLoaded ? (
          <div className="text-center text-[#858585] py-8">
            暂时无法加载 {activeSource === 'clawhub' ? 'ClawHub' : 'Anthropic'} 市场列表，请尝试搜索
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
    <div className="fixed top-4 right-4 z-50 space-y-2 max-w-sm">
      {toasts.map(toast => (
        <div
          key={toast.id}
          className={`flex items-center gap-2 px-4 py-3 rounded-lg shadow-lg border text-sm ${
            toast.type === 'loading'
              ? 'bg-[#252526] border-[#007acc] text-[#cccccc]'
              : toast.type === 'success'
                ? 'bg-[#252526] border-green-600 text-green-400'
                : 'bg-[#252526] border-red-600 text-red-400'
          }`}
        >
          {toast.type === 'loading' && <Loader2 size={16} className="animate-spin text-[#007acc] shrink-0" />}
          {toast.type === 'success' && <CheckCircle size={16} className="text-green-400 shrink-0" />}
          {toast.type === 'error' && <XCircle size={16} className="text-red-400 shrink-0" />}
          <span className="flex-1 min-w-0 truncate">{toast.message}</span>
          {toast.type !== 'loading' && (
            <button onClick={() => removeToast(toast.id)} className="text-[#858585] hover:text-[#cccccc] shrink-0">
              <X size={14} />
            </button>
          )}
        </div>
      ))}
    </div>
  );
}
