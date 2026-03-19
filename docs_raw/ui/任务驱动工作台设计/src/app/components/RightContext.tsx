import { useState } from "react";
import { ChevronDown, ChevronRight, ExternalLink, FileText, Globe } from "lucide-react";
import { Card } from "./ui/card";
import { cn } from "./ui/utils";

interface ThoughtTrace {
  steps: string[];
}

interface Source {
  name: string;
  type: "file" | "web";
  url?: string;
}

interface Parameter {
  label: string;
  value: string;
}

interface TaskProgress {
  task: string;
  step: number;
  total: number;
  status: "running" | "completed";
}

interface RightContextProps {
  thoughtTrace?: ThoughtTrace;
  sources?: Source[];
  parameters?: Parameter[];
  taskProgress?: TaskProgress[];
  isCollapsed?: boolean;
  deepWorkLink?: string;
}

export function RightContext({
  thoughtTrace,
  sources,
  parameters,
  taskProgress,
  isCollapsed = true,
  deepWorkLink,
}: RightContextProps) {
  const [expanded, setExpanded] = useState(!isCollapsed);

  return (
    <aside className="w-80 border-l bg-gray-50 flex flex-col overflow-y-auto">
      <div className="p-4">
        {/* Header - AI 深度工作区 */}
        <div className="mb-4">
          <button
            onClick={() => setExpanded(!expanded)}
            className="flex items-center justify-between w-full text-left"
          >
            <div>
              <h2 className="font-semibold text-gray-900">AI 深度工作区</h2>
              <p className="text-sm text-gray-500">默认收起，按需展开</p>
            </div>
            {expanded ? (
              <ChevronDown className="w-5 h-5 text-gray-500" />
            ) : (
              <ChevronRight className="w-5 h-5 text-gray-500" />
            )}
          </button>
          
          {/* 跳转链接 */}
          {deepWorkLink && (
            <a
              href={deepWorkLink}
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center gap-1 text-sm text-blue-600 hover:text-blue-700 mt-2"
            >
              查看完整工作流
              <ExternalLink className="w-3 h-3" />
            </a>
          )}
        </div>

        {/* Content - 只在展开时显示 */}
        {expanded && (
          <div className="space-y-3">
            {/* Thought Trace Panel */}
            {thoughtTrace && (
              <Card className="p-4 bg-white">
                <h3 className="font-semibold mb-3 text-sm">Thought Trace</h3>
                <div className="space-y-2">
                  {thoughtTrace.steps.map((step, index) => (
                    <div key={index} className="flex items-center gap-2">
                      <div
                        className={cn(
                          "w-2 h-2 rounded-full shrink-0",
                          index === thoughtTrace.steps.length - 1
                            ? "bg-blue-600"
                            : "bg-gray-300"
                        )}
                      ></div>
                      <span
                        className={cn(
                          "text-sm",
                          index === thoughtTrace.steps.length - 1
                            ? "text-gray-900 font-medium"
                            : "text-gray-600"
                        )}
                      >
                        {step}
                      </span>
                    </div>
                  ))}
                </div>
              </Card>
            )}

            {/* Sources Panel */}
            {sources && sources.length > 0 && (
              <Card className="p-4 bg-white">
                <h3 className="font-semibold mb-3 text-sm">Sources</h3>
                <div className="space-y-2">
                  {sources.map((source, index) => (
                    <div key={index} className="flex items-start gap-2 text-sm">
                      {source.type === "file" ? (
                        <FileText className="w-4 h-4 text-gray-500 shrink-0 mt-0.5" />
                      ) : (
                        <Globe className="w-4 h-4 text-blue-500 shrink-0 mt-0.5" />
                      )}
                      <div className="flex-1 min-w-0">
                        {source.url ? (
                          <a
                            href={source.url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="text-blue-600 hover:text-blue-700 hover:underline truncate block"
                          >
                            {source.name}
                          </a>
                        ) : (
                          <span className="text-gray-700 truncate block">
                            {source.name}
                          </span>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              </Card>
            )}

            {/* 参数 */}
            {parameters && parameters.length > 0 && (
              <Card className="p-4 bg-white">
                <h3 className="font-semibold mb-3 text-sm">参数</h3>
                <div className="text-sm text-gray-700 space-y-1">
                  {parameters.map((param, index) => (
                    <div key={index}>
                      {param.label} / {param.value}
                    </div>
                  ))}
                </div>
              </Card>
            )}

            {/* 多步任务进度 Panel */}
            {taskProgress && taskProgress.length > 0 && (
              <Card className="p-4 bg-white">
                <h3 className="font-semibold mb-3 text-sm">多步任务进度</h3>
                <div className="space-y-3">
                  {taskProgress.map((task, index) => (
                    <div key={index} className="flex items-center gap-3">
                      <div
                        className={cn(
                          "w-3 h-3 rounded-full shrink-0",
                          task.status === "completed" ? "bg-gray-400" : "bg-green-500"
                        )}
                      ></div>
                      <div className="flex-1 min-w-0">
                        <p className="text-sm text-gray-900 truncate">{task.task}</p>
                      </div>
                      <span className="text-sm text-orange-500 shrink-0">
                        {task.step}/{task.total}
                      </span>
                    </div>
                  ))}
                </div>
              </Card>
            )}
          </div>
        )}
      </div>
    </aside>
  );
}
