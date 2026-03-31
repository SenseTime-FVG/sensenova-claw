'use client';

import { useState, useEffect, useCallback } from 'react';
import { Loader2, Globe, Settings, RefreshCw } from 'lucide-react';
import { useRouter } from 'next/navigation';
import { DashboardLayout } from '@/components/layout/DashboardLayout';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { authFetch, API_BASE } from '@/lib/authFetch';

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
  error?: string;
  config: Record<string, unknown>;
}

interface WhatsAppStatus {
  enabled: boolean;
  authorized: boolean;
  state: string;
}

export default function GatewayPage() {
  const router = useRouter();
  const [stats, setStats] = useState<GatewayStats | null>(null);
  const [channels, setChannels] = useState<Channel[]>([]);
  const [whatsappStatus, setWhatsAppStatus] = useState<WhatsAppStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const loadGatewayData = useCallback(async () => {
    const [statsData, channelsData, whatsappStatusData] = await Promise.all([
      authFetch(`${API_BASE}/api/gateway/stats`).then(r => r.json()),
      authFetch(`${API_BASE}/api/gateway/channels`).then(r => r.json()),
      authFetch(`${API_BASE}/api/gateway/whatsapp/status`).then(r => r.json()).catch(() => null),
    ]);
    setStats(statsData);
    setChannels(channelsData);
    setWhatsAppStatus(whatsappStatusData);
  }, []);

  const refreshGatewayData = useCallback(async () => {
    setRefreshing(true);
    try {
      await loadGatewayData();
    } finally {
      setRefreshing(false);
    }
  }, [loadGatewayData]);

  useEffect(() => {
    let cancelled = false;

    const load = async () => {
      try {
        await loadGatewayData();
      } catch {
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    };

    void load();

    const handleVisibilityRefresh = () => {
      if (document.visibilityState === 'visible') {
        void loadGatewayData().catch(() => {});
      }
    };

    const handleWindowFocus = () => {
      void loadGatewayData().catch(() => {});
    };

    document.addEventListener('visibilitychange', handleVisibilityRefresh);
    window.addEventListener('focus', handleWindowFocus);

    return () => {
      cancelled = true;
      document.removeEventListener('visibilitychange', handleVisibilityRefresh);
      window.removeEventListener('focus', handleWindowFocus);
    };
  }, [loadGatewayData]);

  function getChannelPresentation(channel: Channel) {
    if (channel.id === 'whatsapp' && whatsappStatus?.enabled && !whatsappStatus.authorized) {
      return {
        status: 'unauthorized',
        accentClass: 'bg-red-500/40',
        dotClass: 'bg-red-500 shadow-[0_0_10px_rgba(239,68,68,0.6)]',
        badgeClass: 'bg-red-500 text-white shadow-sm',
      };
    }

    if (channel.status === 'connecting') {
      return {
        status: channel.status,
        accentClass: 'bg-amber-500/40',
        dotClass: 'bg-amber-500 shadow-[0_0_10px_rgba(245,158,11,0.6)]',
        badgeClass: 'bg-amber-500 text-white shadow-sm',
      };
    }

    if (channel.status === 'failed') {
      return {
        status: channel.status,
        accentClass: 'bg-red-500/40',
        dotClass: 'bg-red-500 shadow-[0_0_10px_rgba(239,68,68,0.6)]',
        badgeClass: 'bg-red-500 text-white shadow-sm',
      };
    }

    const connected = channel.status === 'connected';
    return {
      status: channel.status,
      accentClass: connected ? 'bg-green-500/40' : 'bg-muted-foreground/20',
      dotClass: connected ? 'bg-green-500 shadow-[0_0_10px_rgba(34,197,94,0.6)]' : 'bg-muted-foreground/40',
      badgeClass: connected ? 'bg-green-500 text-white shadow-sm' : '',
    };
  }

  return (
    <DashboardLayout>
      <div className="flex-1 space-y-8 p-10 lg:p-12">
        <div className="flex items-center justify-between space-y-2">
          <h2 className="text-4xl font-extrabold tracking-tight text-foreground/90">Gateway & Channels</h2>
          <Button variant="outline" size="sm" onClick={refreshGatewayData} disabled={loading || refreshing} data-testid="gateway-refresh-button">
            {refreshing ? <Loader2 className="w-4 h-4 animate-spin" /> : <RefreshCw className="w-4 h-4" />}
            <span className="ml-1">刷新</span>
          </Button>
        </div>

        <div className="flex flex-col md:flex-row gap-8 mt-10">
          {/* Nested Sidebar */}
          <aside className="w-full md:w-64 lg:w-72 shrink-0">
            <nav className="flex space-x-2 md:flex-col md:space-x-0 md:space-y-2">
               <p className="text-[10px] font-black uppercase tracking-[0.2em] text-muted-foreground/70 mb-2 px-4">Traffic</p>
               <button className="flex items-center gap-3 font-bold justify-start w-full text-base px-5 py-3.5 rounded-xl transition-all border border-transparent bg-primary text-primary-foreground shadow-lg shadow-primary/20">
                  <Globe className="h-5 w-5" /> Live Channels
               </button>
               <button className="flex items-center gap-3 font-bold justify-start w-full text-base px-5 py-3.5 rounded-xl transition-all border border-transparent text-muted-foreground hover:bg-muted hover:text-foreground opacity-60">
                  <Settings className="h-5 w-5" /> Global Settings
               </button>
            </nav>
          </aside>

          {/* Main Content Area */}
          <div className="flex-1 space-y-8">
            {/* Gateway Stats */}
            {stats && (
              <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-4">
                <Card className="shadow-lg border-border/60">
                  <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-3">
                    <CardTitle className="text-sm font-bold text-muted-foreground uppercase tracking-wider">Total Channels</CardTitle>
                    <Globe className="h-5 w-5 text-primary" />
                  </CardHeader>
                  <CardContent>
                    <div className="text-4xl font-black">{stats.totalChannels}</div>
                    <p className="text-sm font-medium text-muted-foreground mt-2">Configured routes</p>
                  </CardContent>
                </Card>
                <Card className="shadow-lg border-border/60">
                  <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-3">
                    <CardTitle className="text-sm font-bold text-muted-foreground uppercase tracking-wider">Active Channels</CardTitle>
                    <div className="w-3 h-3 rounded-full bg-green-500 animate-pulse" />
                  </CardHeader>
                  <CardContent>
                    <div className="text-4xl font-black text-green-600 dark:text-green-500">{stats.activeChannels}</div>
                    <p className="text-sm font-medium text-muted-foreground mt-2">Heathy & connected</p>
                  </CardContent>
                </Card>
                <Card className="shadow-lg border-border/60">
                  <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-3">
                    <CardTitle className="text-sm font-bold text-muted-foreground uppercase tracking-wider">Active Connections</CardTitle>
                  </CardHeader>
                  <CardContent>
                    <div className="text-4xl font-black">{stats.totalConnections}</div>
                    <p className="text-sm font-medium text-muted-foreground mt-2">Current client links</p>
                  </CardContent>
                </Card>
                <Card className="shadow-lg border-border/60">
                  <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-3">
                    <CardTitle className="text-sm font-bold text-muted-foreground uppercase tracking-wider">Total Sessions</CardTitle>
                  </CardHeader>
                  <CardContent>
                    <div className="text-4xl font-black">{stats.totalSessions}</div>
                    <p className="text-sm font-medium text-muted-foreground mt-2">All-time throughput</p>
                  </CardContent>
                </Card>
              </div>
            )}

            <Card className="shadow-xl border-border/80 overflow-hidden">
              <CardHeader className="bg-muted/30 border-b p-8">
                <CardTitle className="text-2xl font-bold">Channel Registry</CardTitle>
                <CardDescription className="text-base mt-2">View and manage active communication channels across the gateway.</CardDescription>
              </CardHeader>
              <CardContent className="p-8">
                {loading ? (
                  <div className="flex flex-col items-center justify-center py-24 gap-4">
                    <Loader2 className="animate-spin text-primary" size={48} />
                    <p className="text-sm font-bold text-muted-foreground uppercase tracking-widest">Hydrating gateway stats...</p>
                  </div>
                ) : (
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                    {channels.map((channel) => {
                      const presentation = getChannelPresentation(channel);
                      const showAuthorizeButton = channel.id === 'whatsapp' && whatsappStatus?.enabled && !whatsappStatus.authorized;
                      return (
                        <div key={channel.id} className="flex flex-col p-8 border border-border/60 rounded-2xl bg-card hover:bg-muted/30 transition-all shadow-sm group relative overflow-hidden">
                          <div className={`absolute top-0 right-0 w-2 h-full ${presentation.accentClass}`} />
                          <div className="flex-1">
                            <div className="flex flex-col mb-4">
                              <div className="flex items-center justify-between mb-2">
                                <h3 className="text-xl font-bold text-foreground group-hover:text-primary transition-colors">{channel.name}</h3>
                                <span className={`w-3 h-3 rounded-full ${presentation.dotClass}`} />
                              </div>
                              <div className="flex items-center gap-2">
                                <Badge
                                  variant={presentation.status === 'connected' ? 'default' : 'secondary'}
                                  className={`px-2.5 py-1 text-[10px] font-black uppercase tracking-wider ${presentation.badgeClass}`}>
                                  {presentation.status}
                                </Badge>
                                <Badge variant="outline" className="capitalize px-2.5 py-1 text-[10px] font-black uppercase tracking-wider text-muted-foreground/60">
                                  {channel.type}
                                </Badge>
                              </div>
                            </div>
                            <p className="text-xs font-mono text-muted-foreground/50 truncate">ID: {channel.id}</p>
                            {channel.error ? (
                              <p className="mt-3 text-sm font-medium text-red-600 dark:text-red-400">
                                {channel.error}
                              </p>
                            ) : null}
                            {showAuthorizeButton ? (
                              <div className="mt-6">
                                <Button onClick={() => router.push('/gateway/whatsapp')}>授权</Button>
                              </div>
                            ) : null}
                          </div>
                        </div>
                      );
                    })}
                    {channels.length === 0 && (
                      <div className="col-span-full py-24 border border-dashed rounded-2xl text-center text-muted-foreground bg-muted/5">
                        <p className="text-lg font-bold opacity-30 uppercase tracking-widest">No active channels registered</p>
                      </div>
                    )}
                  </div>
                )}
              </CardContent>
            </Card>
          </div>
        </div>
      </div>
    </DashboardLayout>
  );
}
