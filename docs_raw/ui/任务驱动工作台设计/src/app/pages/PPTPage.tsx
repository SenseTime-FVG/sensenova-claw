import { useState } from "react";
import { WorkbenchLayout } from "../components/WorkbenchLayout";
import { Card } from "../components/ui/card";
import { Badge } from "../components/ui/badge";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Presentation, Plus, Search, Grid3X3, List, MoreVertical } from "lucide-react";

export default function PPTPage() {
  const [viewMode, setViewMode] = useState<"grid" | "list">("grid");

  const presentations = [
    {
      id: 1,
      name: "Q2产品发布会PPT",
      slides: 24,
      lastModified: "1小时前",
      owner: "我",
      thumbnail: "bg-gradient-to-br from-blue-500 to-purple-600",
      status: "editing",
    },
    {
      id: 2,
      name: "2024市场趋势分析",
      slides: 18,
      lastModified: "昨天",
      owner: "张经理",
      thumbnail: "bg-gradient-to-br from-green-500 to-teal-600",
      status: "completed",
    },
    {
      id: 3,
      name: "技术架构评审",
      slides: 32,
      lastModified: "3天前",
      owner: "李工程师",
      thumbnail: "bg-gradient-to-br from-orange-500 to-red-600",
      status: "completed",
    },
    {
      id: 4,
      name: "用户调研报告展示",
      slides: 15,
      lastModified: "1周前",
      owner: "设计团队",
      thumbnail: "bg-gradient-to-br from-pink-500 to-rose-600",
      status: "completed",
    },
    {
      id: 5,
      name: "团队OKR规划",
      slides: 12,
      lastModified: "2周前",
      owner: "王总监",
      thumbnail: "bg-gradient-to-br from-indigo-500 to-blue-600",
      status: "completed",
    },
    {
      id: 6,
      name: "竞品分析汇报",
      slides: 20,
      lastModified: "3周前",
      owner: "产品团队",
      thumbnail: "bg-gradient-to-br from-yellow-500 to-orange-600",
      status: "completed",
    },
  ];

  return (
    <WorkbenchLayout isCollapsed={true}>
      <main className="flex-1 overflow-y-auto p-6">
        <div className="max-w-6xl mx-auto">
          {/* Header */}
          <div className="flex items-center justify-between mb-6">
            <div>
              <h1 className="text-2xl font-semibold mb-1">PPT</h1>
              <p className="text-sm text-gray-600">
                管理和创建你的演示文稿
              </p>
            </div>
            <div className="flex items-center gap-3">
              <div className="relative">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
                <Input
                  placeholder="搜索PPT..."
                  className="pl-9 w-64"
                />
              </div>
              <div className="flex items-center gap-1 border rounded-lg p-1">
                <Button
                  variant={viewMode === "grid" ? "secondary" : "ghost"}
                  size="icon"
                  className="w-8 h-8"
                  onClick={() => setViewMode("grid")}
                >
                  <Grid3X3 className="w-4 h-4" />
                </Button>
                <Button
                  variant={viewMode === "list" ? "secondary" : "ghost"}
                  size="icon"
                  className="w-8 h-8"
                  onClick={() => setViewMode("list")}
                >
                  <List className="w-4 h-4" />
                </Button>
              </div>
              <Button className="gap-2">
                <Plus className="w-4 h-4" />
                创建PPT
              </Button>
            </div>
          </div>

          {/* Grid View */}
          {viewMode === "grid" && (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {presentations.map((ppt) => (
                <Card
                  key={ppt.id}
                  className="overflow-hidden hover:shadow-lg transition-shadow cursor-pointer group"
                >
                  {/* Thumbnail */}
                  <div className={`h-40 ${ppt.thumbnail} relative`}>
                    <div className="absolute inset-0 bg-black/10 group-hover:bg-black/0 transition-colors"></div>
                    <div className="absolute top-3 right-3">
                      <Button
                        variant="secondary"
                        size="icon"
                        className="w-8 h-8 opacity-0 group-hover:opacity-100 transition-opacity"
                      >
                        <MoreVertical className="w-4 h-4" />
                      </Button>
                    </div>
                    {ppt.status === "editing" && (
                      <Badge className="absolute bottom-3 left-3 bg-blue-500">
                        编辑中
                      </Badge>
                    )}
                    <div className="absolute bottom-3 right-3">
                      <Presentation className="w-8 h-8 text-white/80" />
                    </div>
                  </div>

                  {/* Info */}
                  <div className="p-4">
                    <h3 className="font-medium mb-2 line-clamp-1">
                      {ppt.name}
                    </h3>
                    <div className="flex items-center justify-between text-sm text-gray-600">
                      <span>{ppt.slides} 张幻灯片</span>
                      <span>•</span>
                      <span className="truncate">{ppt.owner}</span>
                    </div>
                    <div className="text-xs text-gray-500 mt-1">
                      {ppt.lastModified}
                    </div>
                  </div>
                </Card>
              ))}
            </div>
          )}

          {/* List View */}
          {viewMode === "list" && (
            <div className="space-y-2">
              {presentations.map((ppt) => (
                <Card
                  key={ppt.id}
                  className="p-4 hover:shadow-md transition-shadow cursor-pointer group"
                >
                  <div className="flex items-center gap-4">
                    {/* Thumbnail */}
                    <div
                      className={`w-20 h-14 ${ppt.thumbnail} rounded flex items-center justify-center shrink-0`}
                    >
                      <Presentation className="w-6 h-6 text-white/80" />
                    </div>

                    {/* Info */}
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-1">
                        <h3 className="font-medium">{ppt.name}</h3>
                        {ppt.status === "editing" && (
                          <Badge variant="secondary" className="text-xs">
                            编辑中
                          </Badge>
                        )}
                      </div>
                      <div className="flex items-center gap-3 text-sm text-gray-600">
                        <span>{ppt.slides} 张幻灯片</span>
                        <span>•</span>
                        <span>由 {ppt.owner} 修改</span>
                        <span>•</span>
                        <span>{ppt.lastModified}</span>
                      </div>
                    </div>

                    {/* Actions */}
                    <Button
                      variant="ghost"
                      size="icon"
                      className="opacity-0 group-hover:opacity-100 transition-opacity"
                    >
                      <MoreVertical className="w-4 h-4" />
                    </Button>
                  </div>
                </Card>
              ))}
            </div>
          )}
        </div>
      </main>
    </WorkbenchLayout>
  );
}
