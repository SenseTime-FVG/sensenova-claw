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
}

interface Toast {
  id: number;
  type: 'loading' | 'success' | 'error';
  message: string;
}

const SOURCES = ['clawhub', 'anthropic'] as const;

let toastId = 0;

export function MarketTab({ onInstalled }: { onInstalled: () => void }) {
  const [activeSource, setActiveSource] = useState<string>('clawhub');
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
        updateToast(tid, 'success', `${data.skill_name || id} 安装成功`);
        onInstalled();
        doSearch(activeSource, query, page);
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
        updateToast(tid, 'success', `${data.skill_name || 'Skill'} 安装成功`);
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

  return (
    <div className="space-y-4">
      {/* Toast 通知 */}
      {toasts.length > 0 && (
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
      )}

      {/* 来源切换 */}
      <div className="flex gap-1 bg-[#252526] rounded p-1">
        {SOURCES.map(src => (
          <button
            key={src}
            className={`px-3 py-1.5 text-sm rounded transition-colors ${
              activeSource === src
                ? 'bg-[#0e639c] text-white'
                : 'text-[#858585] hover:text-[#cccccc]'
            }`}
            onClick={() => { setActiveSource(src); setResults([]); }}
          >
            {src === 'clawhub' ? 'ClawHub' : 'Anthropic'}
          </button>
        ))}
        <button
          className={`px-3 py-1.5 text-sm rounded transition-colors flex items-center gap-1 ${
            activeSource === 'git'
              ? 'bg-[#0e639c] text-white'
              : 'text-[#858585] hover:text-[#cccccc]'
          }`}
          onClick={() => { setActiveSource('git'); setResults([]); }}
        >
          <GitBranch size={14} /> Git URL
        </button>
      </div>

      {/* Git URL 输入 */}
      {activeSource === 'git' ? (
        <div className="flex items-center gap-2">
          <input
            className="flex-1 bg-[#3c3c3c] border border-[#2d2d30] rounded px-3 py-2 text-sm text-[#cccccc] placeholder-[#858585] focus:border-[#007acc] focus:outline-none"
            placeholder="https://github.com/user/skill-repo"
            value={gitUrl}
            onChange={e => setGitUrl(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && handleGitInstall()}
          />
          <button
            className="px-4 py-2 text-sm rounded bg-[#0e639c] text-white hover:bg-[#1177bb] disabled:opacity-50"
            onClick={handleGitInstall}
            disabled={gitInstalling || !gitUrl.trim()}
          >
            {gitInstalling ? '安装中...' : '安装'}
          </button>
        </div>
      ) : (
        <>
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

          {/* 结果 */}
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
                  source={skill.source}
                  version={skill.version}
                  downloads={skill.downloads}
                  author={skill.author}
                  installing={installingIds.has(skill.id)}
                  onInstall={installingIds.has(skill.id) ? undefined : () => handleInstall(skill.source, skill.id)}
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
          ) : (
            <div className="text-center text-[#858585] py-8">输入关键词搜索 skills</div>
          )}
        </>
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
