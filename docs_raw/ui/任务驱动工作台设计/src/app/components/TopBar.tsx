import { Search, Bell, Settings, User, Undo2, Redo2, Download, Share2 } from "lucide-react";
import { Input } from "./ui/input";
import { Button } from "./ui/button";
import { Badge } from "./ui/badge";

export function TopBar() {
  return (
    <header className="h-14 border-b bg-white px-4 flex items-center justify-between">
      {/* 左侧：AgentOS + 操作按钮 */}
      <div className="flex items-center gap-4">
        <h1 className="font-semibold">AgentOS</h1>
        
        {/* 操作按钮组 */}
        <div className="flex items-center gap-1 ml-2 pl-2 border-l">
          <Button variant="ghost" size="icon" title="撤销">
            <Undo2 className="w-4 h-4" />
          </Button>
          <Button variant="ghost" size="icon" title="重做">
            <Redo2 className="w-4 h-4" />
          </Button>
          <Button variant="ghost" size="icon" title="导出">
            <Download className="w-4 h-4" />
          </Button>
          <Button variant="ghost" size="icon" title="分享">
            <Share2 className="w-4 h-4" />
          </Button>
        </div>
      </div>

      {/* 中间：全局搜索 */}
      <div className="flex-1 max-w-2xl mx-8">
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
          <Input
            type="search"
            placeholder="全局搜索任务、文档、联系人..."
            className="pl-10 w-full"
          />
        </div>
      </div>

      {/* 右侧：状态和设置 */}
      <div className="flex items-center gap-3">
        <div className="flex items-center gap-2 px-3 py-1.5 rounded-md bg-green-50 border border-green-200">
          <div className="w-2 h-2 rounded-full bg-green-500"></div>
          <span className="text-sm text-green-700">Agent 运行中</span>
        </div>

        <Button variant="ghost" size="icon" className="relative">
          <Bell className="w-5 h-5" />
          <Badge className="absolute -top-1 -right-1 w-5 h-5 flex items-center justify-center p-0 text-xs">
            3
          </Badge>
        </Button>

        <Button variant="ghost" size="icon">
          <Settings className="w-5 h-5" />
        </Button>

        <Button variant="ghost" size="icon">
          <User className="w-5 h-5" />
        </Button>
      </div>
    </header>
  );
}