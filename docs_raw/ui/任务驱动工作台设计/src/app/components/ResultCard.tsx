import { Card } from "./ui/card";
import { Button } from "./ui/button";
import { Badge } from "./ui/badge";
import { Separator } from "./ui/separator";
import { CheckCircle2, ArrowRight } from "lucide-react";

interface ResultCardProps {
  summary: string;
  preview?: React.ReactNode;
  sources?: string[];
  nextActions?: { label: string; primary?: boolean; onClick?: () => void }[];
}

export function ResultCard({ summary, preview, sources, nextActions }: ResultCardProps) {
  return (
    <Card className="p-6 mb-4">
      {/* 结论摘要 */}
      <div className="flex items-start gap-3 mb-4">
        <CheckCircle2 className="w-5 h-5 text-green-600 mt-0.5 shrink-0" />
        <div>
          <h2 className="font-semibold mb-2">结论摘要</h2>
          <p className="text-gray-700">{summary}</p>
        </div>
      </div>

      {/* 预览/草稿 */}
      {preview && (
        <>
          <Separator className="my-4" />
          <div>
            <h3 className="font-semibold mb-3">预览</h3>
            <div className="bg-gray-50 rounded-lg p-4 border">{preview}</div>
          </div>
        </>
      )}

      {/* 依据/来源 */}
      {sources && sources.length > 0 && (
        <>
          <Separator className="my-4" />
          <div>
            <h3 className="font-semibold mb-2">依据来源</h3>
            <div className="space-y-1">
              {sources.map((source, index) => (
                <div key={index} className="text-sm text-gray-600 flex items-center gap-2">
                  <div className="w-1 h-1 rounded-full bg-gray-400"></div>
                  {source}
                </div>
              ))}
            </div>
          </div>
        </>
      )}

      {/* 下一步动作 */}
      {nextActions && nextActions.length > 0 && (
        <>
          <Separator className="my-4" />
          <div>
            <h3 className="font-semibold mb-3">下一步动作</h3>
            <div className="flex gap-2">
              {nextActions.map((action, index) => (
                <Button
                  key={index}
                  variant={action.primary ? "default" : "outline"}
                  onClick={action.onClick}
                  className="gap-2"
                >
                  {action.label}
                  {action.primary && <ArrowRight className="w-4 h-4" />}
                </Button>
              ))}
            </div>
          </div>
        </>
      )}
    </Card>
  );
}
