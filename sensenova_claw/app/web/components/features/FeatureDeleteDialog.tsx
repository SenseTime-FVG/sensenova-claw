'use client';

import { useEffect, useState } from 'react';
import { AlertTriangle } from 'lucide-react';
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { authFetch, API_BASE } from '@/lib/authFetch';
import { useCustomPages } from '@/hooks/useCustomPages';

interface FeatureDeleteDialogProps {
  open: boolean;
  featureId: string;
  featureName: string;
  onOpenChange: (open: boolean) => void;
  onDeleted?: () => void | Promise<void>;
}

export function FeatureDeleteDialog({
  open,
  featureId,
  featureName,
  onOpenChange,
  onDeleted,
}: FeatureDeleteDialogProps) {
  const { refresh: refreshCustomPages } = useCustomPages();
  const [deleteWorkspace, setDeleteWorkspace] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    if (!open) {
      setDeleteWorkspace(false);
      setError('');
      setSubmitting(false);
    }
  }, [open]);

  const handleDelete = async () => {
    setSubmitting(true);
    setError('');
    try {
      const query = deleteWorkspace ? '?delete_workspace=true' : '';
      const res = await authFetch(`${API_BASE}/api/custom-pages/${encodeURIComponent(featureId)}${query}`, {
        method: 'DELETE',
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        setError(data.detail || '删除功能失败');
        return;
      }
      await onDeleted?.();
      await refreshCustomPages();
      onOpenChange(false);
    } catch {
      setError('删除功能失败');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent data-testid="feature-delete-dialog">
        <DialogHeader>
          <DialogTitle>确认删除功能</DialogTitle>
          <DialogDescription>
            确定要删除功能“{featureName}”吗？该操作会移除功能入口。
          </DialogDescription>
        </DialogHeader>

        <div className="rounded-xl border border-destructive/20 bg-destructive/5 p-3 text-sm text-muted-foreground">
          <div className="mb-2 flex items-center gap-2 text-destructive">
            <AlertTriangle className="h-4 w-4" />
            <span className="font-medium">危险操作</span>
          </div>
          <p>如该功能绑定专属 agent，删除功能时会同步删除其专属 agent 配置。</p>
        </div>

        <label className="flex items-center gap-3 rounded-lg border border-border/70 px-3 py-3 text-sm">
          <input
            type="checkbox"
            className="h-4 w-4"
            checked={deleteWorkspace}
            onChange={(event) => setDeleteWorkspace(event.target.checked)}
            data-testid="feature-delete-workspace-toggle"
          />
          <span>删除对应的目录</span>
        </label>

        {error ? <p className="text-sm text-destructive">{error}</p> : null}

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={submitting}>
            取消
          </Button>
          <Button
            variant="destructive"
            onClick={handleDelete}
            disabled={submitting}
            data-testid="feature-delete-confirm"
          >
            {submitting ? '删除中...' : '删除功能'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
