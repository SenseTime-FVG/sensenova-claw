'use client';

import { useEffect, useState } from 'react';
import { X, FileText, Folder, CheckCircle, XCircle, AlertTriangle } from 'lucide-react';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

interface SkillDetailModalProps {
  source: string;
  skillId: string;
  onClose: () => void;
  onInstall?: () => void;
  onUninstall?: () => void;
  installed?: boolean;
}

interface DetailData {
  name: string;
  description: string;
  version?: string;
  author?: string;
  skill_md_preview: string;
  files: string[];
  installed: boolean;
  updated_at?: string;
  dependencies?: string[];
  readme?: string;
}

const categoryConfig: Record<string, { label: string; color: string }> = {
  clawhub:   { label: 'ClawHub',  color: 'bg-violet-600' },
  anthropic: { label: 'Anthropic', color: 'bg-orange-600' },
  git:       { label: 'Git',      color: 'bg-gray-600' },
  local:     { label: '本地',     color: 'bg-blue-600' },
};

export function SkillDetailModal({
  source, skillId, onClose, onInstall, onUninstall, installed,
}: SkillDetailModalProps) {
  const [detail, setDetail] = useState<DetailData | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch(`${API_BASE}/api/skills/market/detail?source=${source}&id=${encodeURIComponent(skillId)}`)
      .then(r => r.json())
      .then(setDetail)
      .catch(() => setDetail(null))
      .finally(() => setLoading(false));
  }, [source, skillId]);

  const srcConfig = categoryConfig[source] || { label: source, color: 'bg-gray-600' };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50" onClick={onClose}>
      <div
        className="bg-[#1e1e1e] border border-[#2d2d30] rounded-lg w-[640px] max-h-[80vh] flex flex-col"
        onClick={e => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-[#2d2d30]">
          <div>
            <h2 className="text-lg font-semibold text-[#cccccc]">{detail?.name || skillId}</h2>
            <div className="flex items-center gap-2 mt-1 text-xs text-[#858585]">
              {detail?.author && <span>by {detail.author}</span>}
              {detail?.version && <span>v{detail.version}</span>}
              <span className={`text-[10px] text-white px-1.5 py-0.5 rounded ${srcConfig.color}`}>
                {srcConfig.label}
              </span>
              {detail?.updated_at && (
                <span>更新于 {new Date(detail.updated_at).toLocaleDateString()}</span>
              )}
            </div>
          </div>
          <button onClick={onClose} className="text-[#858585] hover:text-[#cccccc]">
            <X size={20} />
          </button>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-auto p-4 space-y-4">
          {loading ? (
            <div className="text-center text-[#858585] py-8">加载中...</div>
          ) : detail ? (
            <>
              <p className="text-sm text-[#cccccc]">{detail.description}</p>

              {/* 依赖状态 */}
              {detail.dependencies && detail.dependencies.length > 0 && (
                <div>
                  <h3 className="text-sm font-medium text-[#858585] mb-2 flex items-center gap-1">
                    <AlertTriangle size={14} /> 依赖
                  </h3>
                  <div className="bg-[#252526] rounded p-2 text-xs space-y-1">
                    {detail.dependencies.map(dep => (
                      <div key={dep} className="flex items-center gap-1.5 text-[#cccccc]">
                        <span className="text-[#858585]">{dep}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* SKILL.md 预览 */}
              <div>
                <h3 className="text-sm font-medium text-[#858585] mb-2 flex items-center gap-1">
                  <FileText size={14} /> SKILL.md
                </h3>
                <pre className="bg-[#252526] rounded p-3 text-xs text-[#cccccc] overflow-auto max-h-60 whitespace-pre-wrap">
                  {detail.skill_md_preview}
                </pre>
              </div>

              {/* 文件列表 */}
              {detail.files && detail.files.length > 0 && (
                <div>
                  <h3 className="text-sm font-medium text-[#858585] mb-2 flex items-center gap-1">
                    <Folder size={14} /> 文件列表
                  </h3>
                  <div className="bg-[#252526] rounded p-2 text-xs text-[#858585] space-y-1">
                    {detail.files.map(f => <div key={f}>{f}</div>)}
                  </div>
                </div>
              )}
            </>
          ) : (
            <div className="text-center text-red-400 py-8">加载失败</div>
          )}
        </div>

        {/* Footer */}
        <div className="flex justify-end gap-2 p-4 border-t border-[#2d2d30]">
          {onInstall && !installed && !(detail?.installed) && (
            <button
              className="px-4 py-2 text-sm rounded bg-[#0e639c] text-white hover:bg-[#1177bb]"
              onClick={onInstall}
            >
              安装
            </button>
          )}
          {onUninstall && (installed || detail?.installed) && (
            <button
              className="px-4 py-2 text-sm rounded bg-red-800 text-white hover:bg-red-700"
              onClick={onUninstall}
            >
              卸载
            </button>
          )}
          <button
            className="px-4 py-2 text-sm rounded bg-[#3c3c3c] text-[#cccccc] hover:bg-[#4c4c4c]"
            onClick={onClose}
          >
            关闭
          </button>
        </div>
      </div>
    </div>
  );
}
