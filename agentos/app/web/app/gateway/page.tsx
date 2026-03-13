'use client';

import { useState, useEffect } from 'react';
import { Search, Loader2 } from 'lucide-react';
import { DashboardLayout } from '@/components/layout/DashboardLayout';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

interface GatewayStats {
  totalChannels: number;
  activeChannels: number;
  totalConnections: number;
  totalSessions: number;
}

interface Channel {
  id: string;
  name: string;
  type: string;
  status: string;
  config: Record<string, unknown>;
}

export default function GatewayPage() {
  const [stats, setStats] = useState<GatewayStats | null>(null);
  const [channels, setChannels] = useState<Channel[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([
      fetch(`${API_BASE}/api/gateway/stats`).then(r => r.json()),
      fetch(`${API_BASE}/api/gateway/channels`).then(r => r.json()),
    ])
      .then(([statsData, channelsData]) => {
        setStats(statsData);
        setChannels(channelsData);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  const getStatusColor = (status: string) => {
    return status === 'connected'
      ? 'text-green-400 bg-green-400/20'
      : 'text-gray-400 bg-gray-400/20';
  };

  return (
    <DashboardLayout>
      <div className="h-full flex flex-col">
        <div className="bg-[#252526] border-b border-[#2d2d30] p-4">
          <h1 className="text-xl font-semibold text-[#cccccc] mb-4">Gateway & Channels</h1>

          {/* Gateway Stats */}
          {stats && (
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <div className="bg-[#1e1e1e] border border-[#2d2d30] rounded p-3">
                <div className="text-xs text-[#858585] mb-1">Total Channels</div>
                <div className="text-xl font-semibold text-[#cccccc]">{stats.totalChannels}</div>
              </div>
              <div className="bg-[#1e1e1e] border border-[#2d2d30] rounded p-3">
                <div className="text-xs text-[#858585] mb-1">Active</div>
                <div className="text-xl font-semibold text-green-400">{stats.activeChannels}</div>
              </div>
              <div className="bg-[#1e1e1e] border border-[#2d2d30] rounded p-3">
                <div className="text-xs text-[#858585] mb-1">Active Connections</div>
                <div className="text-xl font-semibold text-[#cccccc]">{stats.totalConnections}</div>
              </div>
              <div className="bg-[#1e1e1e] border border-[#2d2d30] rounded p-3">
                <div className="text-xs text-[#858585] mb-1">Total Sessions</div>
                <div className="text-xl font-semibold text-[#cccccc]">{stats.totalSessions}</div>
              </div>
            </div>
          )}
        </div>

        <div className="flex-1 overflow-auto p-4">
          {loading ? (
            <div className="flex items-center justify-center h-64">
              <Loader2 className="animate-spin text-[#858585]" size={32} />
            </div>
          ) : (
            <div className="space-y-2">
              {channels.map((channel) => (
                <div key={channel.id} className="bg-[#252526] border border-[#2d2d30] rounded p-3 hover:border-[#3e3e42] transition-colors">
                  <div className="flex items-center gap-3">
                    <div className="flex-1">
                      <div className="flex items-center gap-2 mb-1">
                        <h3 className="text-sm font-medium text-[#cccccc]">{channel.name}</h3>
                        <span className={`px-1.5 py-0.5 rounded text-xs capitalize ${getStatusColor(channel.status)}`}>
                          {channel.status}
                        </span>
                        <span className="px-1.5 py-0.5 rounded text-xs bg-[#3c3c3c] text-[#858585]">
                          {channel.type}
                        </span>
                      </div>
                    </div>
                    <div className={`w-2 h-2 rounded-full ${channel.status === 'connected' ? 'bg-green-500' : 'bg-gray-500'}`} />
                  </div>
                </div>
              ))}
              {channels.length === 0 && (
                <p className="text-sm text-[#858585] text-center py-8">No channels registered</p>
              )}
            </div>
          )}
        </div>
      </div>
    </DashboardLayout>
  );
}
