'use client';

import { useState } from 'react';
import { DashboardLayout } from '@/components/layout/DashboardLayout';
import { WorkbenchShell } from '@/components/workbench/WorkbenchShell';
import { Card } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Presentation, Plus, Search, Grid3X3, List } from 'lucide-react';

const presentations = [
  { id: 1, name: 'Q2产品发布会PPT', slides: 24, lastModified: '1小时前', owner: '我', gradient: 'from-blue-500 to-purple-600', status: 'editing' },
  { id: 2, name: '2024市场趋势分析', slides: 18, lastModified: '昨天', owner: '张经理', gradient: 'from-green-500 to-teal-600', status: 'completed' },
  { id: 3, name: '技术架构评审', slides: 32, lastModified: '3天前', owner: '李工程师', gradient: 'from-orange-500 to-red-600', status: 'completed' },
  { id: 4, name: '用户调研报告展示', slides: 15, lastModified: '1周前', owner: '设计团队', gradient: 'from-pink-500 to-rose-600', status: 'completed' },
  { id: 5, name: '团队OKR规划', slides: 12, lastModified: '2周前', owner: '王总监', gradient: 'from-indigo-500 to-blue-600', status: 'completed' },
  { id: 6, name: '竞品分析汇报', slides: 20, lastModified: '3周前', owner: '产品团队', gradient: 'from-yellow-500 to-orange-600', status: 'completed' },
];

export default function PPTPage() {
  const [viewMode, setViewMode] = useState<'grid' | 'list'>('grid');

  return (
    <DashboardLayout>
      <WorkbenchShell isRightCollapsed>
        <main className="flex-1 overflow-y-auto p-6">
          <div className="max-w-5xl mx-auto">
            <div className="flex items-center justify-between mb-6">
              <div>
                <h1 className="text-xl font-semibold text-foreground mb-1">PPT</h1>
                <p className="text-sm text-muted-foreground">管理和创建你的演示文稿</p>
              </div>
              <div className="flex items-center gap-3">
                <div className="relative">
                  <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
                  <Input placeholder="搜索PPT..." className="pl-9 w-48 bg-muted/50" />
                </div>
                <div className="flex items-center gap-0.5 border border-border rounded-lg p-0.5">
                  <Button variant={viewMode === 'grid' ? 'secondary' : 'ghost'} size="icon" className="w-7 h-7" onClick={() => setViewMode('grid')}>
                    <Grid3X3 className="w-3.5 h-3.5" />
                  </Button>
                  <Button variant={viewMode === 'list' ? 'secondary' : 'ghost'} size="icon" className="w-7 h-7" onClick={() => setViewMode('list')}>
                    <List className="w-3.5 h-3.5" />
                  </Button>
                </div>
                <Button className="gap-2" size="sm">
                  <Plus className="w-4 h-4" />
                  创建PPT
                </Button>
              </div>
            </div>

            {viewMode === 'grid' && (
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                {presentations.map((ppt) => (
                  <Card key={ppt.id} className="overflow-hidden hover:shadow-lg transition-shadow cursor-pointer group">
                    <div className={`h-32 bg-gradient-to-br ${ppt.gradient} relative`}>
                      {ppt.status === 'editing' && (
                        <Badge className="absolute bottom-2 left-2 bg-blue-500 text-[10px]">编辑中</Badge>
                      )}
                      <Presentation className="absolute bottom-2 right-2 w-6 h-6 text-white/60" />
                    </div>
                    <div className="p-3">
                      <h3 className="font-medium text-foreground mb-1 text-sm truncate">{ppt.name}</h3>
                      <div className="flex items-center justify-between text-xs text-muted-foreground">
                        <span>{ppt.slides} 张幻灯片</span>
                        <span>{ppt.lastModified}</span>
                      </div>
                    </div>
                  </Card>
                ))}
              </div>
            )}

            {viewMode === 'list' && (
              <div className="space-y-2">
                {presentations.map((ppt) => (
                  <Card key={ppt.id} className="p-4 hover:shadow-md transition-shadow cursor-pointer">
                    <div className="flex items-center gap-4">
                      <div className={`w-16 h-11 bg-gradient-to-br ${ppt.gradient} rounded flex items-center justify-center shrink-0`}>
                        <Presentation className="w-5 h-5 text-white/80" />
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 mb-0.5">
                          <h3 className="font-medium text-foreground text-sm">{ppt.name}</h3>
                          {ppt.status === 'editing' && <Badge variant="secondary" className="text-[10px]">编辑中</Badge>}
                        </div>
                        <div className="flex items-center gap-3 text-xs text-muted-foreground">
                          <span>{ppt.slides} 张幻灯片</span>
                          <span>{ppt.owner}</span>
                          <span>{ppt.lastModified}</span>
                        </div>
                      </div>
                    </div>
                  </Card>
                ))}
              </div>
            )}
          </div>
        </main>
      </WorkbenchShell>
    </DashboardLayout>
  );
}
