'use client';

import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Separator } from '@/components/ui/separator';
import { CheckCircle2, ArrowRight } from 'lucide-react';

interface ResultCardProps {
  summary: string;
  preview?: React.ReactNode;
  sources?: string[];
  nextActions?: { label: string; primary?: boolean; onClick?: () => void }[];
}

export function ResultCard({ summary, preview, sources, nextActions }: ResultCardProps) {
  return (
    <Card className="p-6 mb-4">
      <div className="flex items-start gap-3 mb-4">
        <CheckCircle2 className="w-5 h-5 text-green-500 mt-0.5 shrink-0" />
        <div>
          <h2 className="font-semibold text-foreground mb-2">结论摘要</h2>
          <p className="text-foreground/80 text-sm">{summary}</p>
        </div>
      </div>

      {preview && (
        <>
          <Separator className="my-4" />
          <div>
            <h3 className="font-semibold text-foreground mb-3 text-sm">预览</h3>
            <div className="bg-muted/50 rounded-lg p-4 border border-border">{preview}</div>
          </div>
        </>
      )}

      {sources && sources.length > 0 && (
        <>
          <Separator className="my-4" />
          <div>
            <h3 className="font-semibold text-foreground mb-2 text-sm">依据来源</h3>
            <div className="space-y-1">
              {sources.map((source, index) => (
                <div key={index} className="text-xs text-muted-foreground flex items-center gap-2">
                  <div className="w-1 h-1 rounded-full bg-muted-foreground/40" />
                  {source}
                </div>
              ))}
            </div>
          </div>
        </>
      )}

      {nextActions && nextActions.length > 0 && (
        <>
          <Separator className="my-4" />
          <div>
            <h3 className="font-semibold text-foreground mb-3 text-sm">下一步动作</h3>
            <div className="flex gap-2">
              {nextActions.map((action, index) => (
                <Button
                  key={index}
                  variant={action.primary ? 'default' : 'outline'}
                  size="sm"
                  onClick={action.onClick}
                  className="gap-1.5"
                >
                  {action.label}
                  {action.primary && <ArrowRight className="w-3.5 h-3.5" />}
                </Button>
              ))}
            </div>
          </div>
        </>
      )}
    </Card>
  );
}
