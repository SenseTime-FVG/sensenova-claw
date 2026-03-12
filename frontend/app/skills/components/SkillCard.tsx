'use client';

interface SkillCardProps {
  name: string;
  description: string;
  source?: string;
  version?: string | null;
  enabled?: boolean;
  hasUpdate?: boolean;
  downloads?: number | null;
  author?: string | null;
  installed?: boolean;
  installing?: boolean;
  onToggle?: (enabled: boolean) => void;
  onUninstall?: () => void;
  onUpdate?: () => void;
  onInstall?: () => void;
  onClick?: () => void;
}

const sourceColors: Record<string, string> = {
  clawhub: 'bg-purple-600',
  anthropic: 'bg-orange-600',
  git: 'bg-gray-600',
  local: 'bg-blue-600',
  builtin: 'bg-green-600',
};

export function SkillCard({
  name, description, source, version, enabled, hasUpdate,
  downloads, author, installed, installing,
  onToggle, onUninstall, onUpdate, onInstall, onClick,
}: SkillCardProps) {
  return (
    <div
      className="bg-[#252526] border border-[#2d2d30] rounded p-3 hover:border-[#3e3e42] transition-colors cursor-pointer"
      onClick={onClick}
    >
      <div className="flex items-start gap-3">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <span className="text-[#cccccc] font-medium truncate">{name}</span>
            {source && (
              <span className={`text-[10px] text-white px-1.5 py-0.5 rounded ${sourceColors[source] || 'bg-gray-600'}`}>
                {source}
              </span>
            )}
            {version && (
              <span className="text-[10px] text-[#858585]">v{version}</span>
            )}
          </div>
          <p className="text-sm text-[#858585] line-clamp-2">{description}</p>
          {(author || downloads != null) && (
            <div className="flex items-center gap-3 mt-1 text-xs text-[#6b6b6b]">
              {author && <span>by {author}</span>}
              {downloads != null && <span>{downloads.toLocaleString()} downloads</span>}
            </div>
          )}
        </div>
        <div className="flex items-center gap-2 flex-shrink-0" onClick={e => e.stopPropagation()}>
          {onToggle && (
            <button
              className={`text-xs px-2 py-1 rounded ${enabled ? 'bg-green-700 text-green-100' : 'bg-[#3c3c3c] text-[#858585]'}`}
              onClick={() => onToggle(!enabled)}
            >
              {enabled ? '启用' : '禁用'}
            </button>
          )}
          {hasUpdate && onUpdate && (
            <button
              className="text-xs px-2 py-1 rounded bg-[#0e639c] text-white hover:bg-[#1177bb]"
              onClick={onUpdate}
            >
              更新
            </button>
          )}
          {onUninstall && source !== 'local' && source !== 'builtin' && (
            <button
              className="text-xs px-2 py-1 rounded bg-[#3c3c3c] text-[#858585] hover:bg-red-800 hover:text-red-100"
              onClick={onUninstall}
            >
              卸载
            </button>
          )}
          {installing && (
            <span className="text-xs text-[#007acc] flex items-center gap-1">
              <span className="w-3 h-3 border-2 border-[#007acc] border-t-transparent rounded-full animate-spin" />
              安装中...
            </span>
          )}
          {onInstall && !installed && !installing && (
            <button
              className="text-xs px-2 py-1 rounded bg-[#0e639c] text-white hover:bg-[#1177bb]"
              onClick={onInstall}
            >
              安装
            </button>
          )}
          {installed && !installing && (
            <span className="text-xs text-green-400">已安装</span>
          )}
        </div>
      </div>
    </div>
  );
}
