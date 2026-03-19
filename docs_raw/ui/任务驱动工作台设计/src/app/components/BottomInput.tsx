import { useState } from "react";
import { Send, Paperclip, Mail, Calendar, FileText, BarChart } from "lucide-react";
import { Button } from "./ui/button";
import { Textarea } from "./ui/textarea";
import { useDrop } from "react-dnd";
import { Badge } from "./ui/badge";

interface BottomInputProps {
  onSubmit?: (message: string) => void;
}

const quickActions = [
  { id: "email", label: "写邮件", icon: Mail },
  { id: "meeting", label: "安排会议", icon: Calendar },
  { id: "summary", label: "总结文档", icon: FileText },
  { id: "report", label: "生成周报", icon: BarChart },
];

export function BottomInput({ onSubmit }: BottomInputProps) {
  const [message, setMessage] = useState("");
  const [droppedFiles, setDroppedFiles] = useState<
    { name: string; path: string; type: string }[]
  >([]);

  const [{ isOver }, drop] = useDrop(() => ({
    accept: "FILE",
    drop: (item: { name: string; path: string; type: string }) => {
      setDroppedFiles((prev) => [...prev, item]);
    },
    collect: (monitor) => ({
      isOver: monitor.isOver(),
    }),
  }));

  const handleSubmit = () => {
    if (message.trim() || droppedFiles.length > 0) {
      const finalMessage = droppedFiles.length > 0
        ? `${message}\n\n附件：${droppedFiles.map((f) => f.name).join(", ")}`
        : message;
      onSubmit?.(finalMessage);
      setMessage("");
      setDroppedFiles([]);
    }
  };

  const handleQuickAction = (actionId: string) => {
    const action = quickActions.find((a) => a.id === actionId);
    if (action) {
      onSubmit?.(action.label);
    }
  };

  const removeFile = (index: number) => {
    setDroppedFiles((prev) => prev.filter((_, i) => i !== index));
  };

  return (
    <div className="border-t bg-white">
      {/* 快捷意图 */}
      <div className="px-4 pt-3 pb-2 border-b">
        <div className="flex gap-2">
          {quickActions.map((action) => {
            const Icon = action.icon;
            return (
              <Button
                key={action.id}
                variant="outline"
                size="sm"
                onClick={() => handleQuickAction(action.id)}
                className="gap-2"
              >
                <Icon className="w-4 h-4" />
                {action.label}
              </Button>
            );
          })}
        </div>
      </div>

      {/* 输入区 */}
      <div ref={drop} className={`p-4 ${isOver ? "bg-blue-50" : ""}`}>
        {/* 已拖入的文件 */}
        {droppedFiles.length > 0 && (
          <div className="mb-3 flex flex-wrap gap-2">
            {droppedFiles.map((file, index) => (
              <Badge
                key={index}
                variant="secondary"
                className="gap-2 pr-1 cursor-pointer"
                onClick={() => removeFile(index)}
              >
                <FileText className="w-3 h-3" />
                {file.name}
                <span className="ml-1 text-xs hover:text-red-600">×</span>
              </Badge>
            ))}
          </div>
        )}

        <div className="flex gap-3">
          <Button variant="ghost" size="icon" className="shrink-0">
            <Paperclip className="w-5 h-5" />
          </Button>
          <Textarea
            value={message}
            onChange={(e) => setMessage(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                handleSubmit();
              }
            }}
            placeholder="描述你需要完成的任务，或拖入文件..."
            className="min-h-[60px] resize-none"
          />
          <Button
            onClick={handleSubmit}
            size="icon"
            className="shrink-0 w-14 h-14"
            disabled={!message.trim() && droppedFiles.length === 0}
          >
            <Send className="w-5 h-5" />
          </Button>
        </div>
        <p className="text-xs text-gray-500 mt-2 px-12">
          按 Enter 发送，Shift + Enter 换行
        </p>
      </div>
    </div>
  );
}