'use client';

import { AlertTriangle, Search, Loader2 } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';

interface SkillCardProps {
  name: string;
  description: string;
  category?: string;
  source?: string;
  version?: string | null;
  enabled?: boolean;
  hasUpdate?: boolean;
  downloads?: number | null;
  author?: string | null;
  installed?: boolean;
  installing?: boolean;
  dependencies?: Record<string, boolean> | null;
  allDepsMet?: boolean;
  onToggle?: (enabled: boolean) => void;
  onUninstall?: () => void;
  onUpdate?: () => void;
  onInstall?: () => void;
  onClick?: () => void;
}

const categoryConfig: Record<string, { label: string; variant: "default" | "secondary" | "destructive" | "outline" }> = {
  builtin:   { label: 'Built-in', variant: 'default' },
  workspace: { label: 'Workspace', variant: 'secondary' },
  installed: { label: 'Installed', variant: 'outline' },
  clawhub:   { label: 'ClawHub', variant: 'default' },
  anthropic: { label: 'Anthropic', variant: 'secondary' },
  git:       { label: 'Git', variant: 'outline' },
};

export function SkillCard({
  name, description, category, source, version, enabled, hasUpdate,
  downloads, author, installed, installing, dependencies, allDepsMet,
  onToggle, onUninstall, onUpdate, onInstall, onClick,
}: SkillCardProps) {
  const displayCategory = category || source || 'local';
  const config = categoryConfig[displayCategory] || { label: displayCategory, variant: 'secondary' };

  return (
    <Card 
      className="hover:border-primary/50 transition-colors cursor-pointer shadow-sm group"
      onClick={onClick}
    >
      <CardContent className="p-4 flex items-start gap-4">
        <div className="flex-1 min-w-0 flex flex-col justify-center">
          <div className="flex items-center gap-2 mb-1">
            <span className="font-semibold text-foreground truncate">{name}</span>
            <Badge variant={config.variant as any} className="text-[10px] h-5 uppercase px-1.5">{config.label}</Badge>
            {version && (
              <span className="text-[10px] text-muted-foreground font-mono bg-muted px-1 rounded">v{version}</span>
            )}
            {dependencies && allDepsMet === false && (
              <span className="text-[10px] text-destructive flex items-center gap-0.5 font-medium ml-1" title="Missing dependencies">
                <AlertTriangle size={12} /> Missing Deps
              </span>
            )}
            {hasUpdate && (
              <Badge variant="default" className="text-[10px] h-5 bg-blue-500 hover:bg-blue-600">Update Available</Badge>
            )}
          </div>
          <p className="text-sm text-muted-foreground line-clamp-2 mt-1">{description}</p>
          {(author || downloads != null) && (
            <div className="flex items-center gap-3 mt-2 text-xs text-muted-foreground/80">
              {author && <span className="font-medium">by {author}</span>}
              {downloads != null && <span>{downloads.toLocaleString()} downloads</span>}
            </div>
          )}
        </div>
        
        <div className="flex items-center gap-2 flex-shrink-0" onClick={e => e.stopPropagation()}>
          {onToggle && (
            <label className="relative inline-flex items-center cursor-pointer ml-2">
              <input
                type="checkbox"
                checked={enabled}
                onChange={() => onToggle(!enabled)}
                className="sr-only peer"
              />
              <div className="w-9 h-5 bg-muted peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-4 after:w-4 after:transition-all peer-checked:bg-primary pointer-events-none shadow-inner" />
            </label>
          )}
          {hasUpdate && onUpdate && (
            <Button size="sm" variant="default" onClick={onUpdate} className="h-7 text-xs px-2">
              Update
            </Button>
          )}
          {installing && (
            <span className="text-xs text-primary flex items-center gap-1 font-medium bg-primary/10 px-2 py-1 rounded">
              <Loader2 className="w-3 h-3 animate-spin" />
              Installing...
            </span>
          )}
          {onInstall && !installed && !installing && (
            <Button size="sm" onClick={onInstall} className="h-7 text-xs px-3">
              Install
            </Button>
          )}
          {installed && !installing && !onToggle && (
            <Badge variant="outline" className="text-green-500 border-green-500/30 bg-green-500/10">Installed</Badge>
          )}
          {onUninstall && displayCategory === 'installed' && (
            <Button size="sm" variant="destructive" onClick={onUninstall} className="h-7 text-xs px-2 opacity-0 group-hover:opacity-100 transition-opacity ml-2">
              Uninstall
            </Button>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
