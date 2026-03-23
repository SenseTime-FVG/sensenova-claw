'use client';

import { useEffect, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { Loader2, RefreshCw, Smartphone } from 'lucide-react';
import { DashboardLayout } from '@/components/layout/DashboardLayout';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { API_BASE, authFetch } from '@/lib/authFetch';

interface WhatsAppStatus {
  enabled: boolean;
  authorized: boolean;
  state: string;
  phone: string | null;
  lastQr: string | null;
  lastQrDataUrl: string | null;
  lastError: string | null;
}

const POLL_MS = 2000;

export default function WhatsAppGatewayPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [status, setStatus] = useState<WhatsAppStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const returnTo = searchParams.get('returnTo') || '/chat';

  useEffect(() => {
    let cancelled = false;

    const load = async () => {
      try {
        const response = await authFetch(`${API_BASE}/api/gateway/whatsapp/status`);
        const data = await response.json();
        if (!cancelled) {
          setStatus(data);
          if (data.enabled && data.authorized) {
            router.replace(returnTo);
          }
        }
      } catch {
        if (!cancelled) {
          setStatus(null);
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    };

    void load();
    const timer = window.setInterval(() => {
      void load();
    }, POLL_MS);

    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [router, returnTo]);

  return (
    <DashboardLayout>
      <div className="flex-1 p-8 lg:p-12">
        <div className="max-w-4xl mx-auto space-y-8">
          <div className="space-y-3">
            <p className="text-xs font-black uppercase tracking-[0.25em] text-muted-foreground/60">Gateway / WhatsApp</p>
            <h1 className="text-4xl font-black tracking-tight">WhatsApp Login</h1>
            <p className="text-muted-foreground text-base">
              当 WhatsApp 插件已启用但尚未授权时，系统会强制跳转到此页面。扫码完成并进入
              <code className="mx-1">ready</code>
              状态后会自动放行。
            </p>
          </div>

          <Card className="shadow-xl border-border/70">
            <CardHeader className="space-y-4">
              <div className="flex items-center justify-between gap-4">
                <div>
                  <CardTitle className="text-2xl font-bold">设备授权状态</CardTitle>
                  <CardDescription className="mt-2">页面每 2 秒自动刷新一次状态。</CardDescription>
                </div>
                <Button variant="outline" onClick={() => window.location.reload()}>
                  <RefreshCw className="w-4 h-4 mr-2" />
                  刷新
                </Button>
              </div>
            </CardHeader>
            <CardContent className="grid gap-6 lg:grid-cols-[1.1fr_0.9fr]">
              <div className="space-y-4">
                {loading ? (
                  <div className="min-h-[360px] flex flex-col items-center justify-center border rounded-2xl bg-muted/20">
                    <Loader2 className="w-10 h-10 animate-spin text-primary" />
                    <p className="mt-4 text-sm text-muted-foreground">正在读取 WhatsApp 状态...</p>
                  </div>
                ) : status?.lastQrDataUrl ? (
                  <div className="border rounded-2xl p-6 bg-white flex flex-col items-center justify-center min-h-[360px]">
                    <img src={status.lastQrDataUrl} alt="WhatsApp QR" className="w-full max-w-[320px] h-auto" />
                    <p className="mt-4 text-sm text-slate-600">使用手机 WhatsApp 扫描此二维码完成授权。</p>
                  </div>
                ) : (
                  <div className="min-h-[360px] flex flex-col items-center justify-center border rounded-2xl bg-muted/20 text-center px-8">
                    <Smartphone className="w-10 h-10 text-primary" />
                    <p className="mt-4 font-semibold">二维码暂未生成</p>
                    <p className="mt-2 text-sm text-muted-foreground">
                      当前状态为
                      <code className="mx-1">{status?.state || 'unknown'}</code>
                      ，请确认 sidecar 已启动且插件已启用。
                    </p>
                  </div>
                )}
              </div>

              <div className="space-y-4">
                <div className="rounded-2xl border p-5 bg-card">
                  <p className="text-xs font-black uppercase tracking-[0.2em] text-muted-foreground/70">Current State</p>
                  <div className="mt-3 flex items-center gap-3">
                    <Badge variant={status?.authorized ? 'default' : 'secondary'} className="uppercase tracking-wider px-3 py-1">
                      {status?.state || 'unknown'}
                    </Badge>
                    {status?.authorized ? (
                      <Badge variant="outline" className="uppercase tracking-wider px-3 py-1">Authorized</Badge>
                    ) : null}
                  </div>
                  <div className="mt-4 space-y-2 text-sm">
                    <div>启用状态：{status?.enabled ? '已启用' : '未启用'}</div>
                    <div>授权状态：{status?.authorized ? '已授权' : '未授权'}</div>
                    <div>手机号：{status?.phone || '未知'}</div>
                  </div>
                </div>

                {status?.lastQr && !status?.lastQrDataUrl ? (
                  <div className="rounded-2xl border p-5 bg-muted/20">
                    <p className="text-xs font-black uppercase tracking-[0.2em] text-muted-foreground/70">QR Raw Text</p>
                    <pre className="mt-3 text-xs whitespace-pre-wrap break-all">{status.lastQr}</pre>
                  </div>
                ) : null}

                <div className="rounded-2xl border p-5 bg-muted/20 text-sm text-muted-foreground">
                  完成扫码后，页面会自动放行并跳回
                  <code className="mx-1">{returnTo}</code>。
                </div>
              </div>
            </CardContent>
          </Card>
        </div>
      </div>
    </DashboardLayout>
  );
}
