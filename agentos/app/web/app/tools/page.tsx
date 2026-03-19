'use client';

import { useEffect, useState } from 'react';
import {
  Bell,
  Eye,
  EyeOff,
  KeyRound,
  Loader2,
  Search,
  Shield,
  ShieldAlert,
  ShieldCheck,
  TestTube2,
  Wrench,
} from 'lucide-react';

import { DashboardLayout } from '@/components/layout/DashboardLayout';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { useNotification } from '@/hooks/useNotification';
import { authFetch, API_BASE } from '@/lib/authFetch';

interface Tool {
  id: string;
  name: string;
  description: string;
  category: string;
  riskLevel: string;
  enabled: boolean;
  parameters: Record<string, unknown>;
  requiresApiKey: boolean;
  apiKeyConfigured: boolean;
}

interface ApiKeyStatus {
  configured: boolean;
  masked_key: string | null;
  docs_url: string;
  description: string;
  setup_guide: string[];
  example_format: string;
}

interface NotificationConfig {
  enabled: boolean;
  channels: string[];
  native: { enabled: boolean };
  browser: { enabled: boolean };
  electron: { enabled: boolean };
  session: { enabled: boolean };
}

const riskIcons: Record<string, React.ElementType> = {
  low: ShieldCheck,
  medium: Shield,
  high: ShieldAlert,
};

export default function ToolsPage() {
  const { permission, requestBrowserPermission } = useNotification();
  const [searchTerm, setSearchTerm] = useState('');
  const [tools, setTools] = useState<Tool[]>([]);
  const [loading, setLoading] = useState(true);
  const [expandedTools, setExpandedTools] = useState<Set<string>>(new Set());
  const [apiKeyStatus, setApiKeyStatus] = useState<Record<string, ApiKeyStatus>>({});
  const [apiKeyDrafts, setApiKeyDrafts] = useState<Record<string, string>>({});
  const [apiKeyVisibility, setApiKeyVisibility] = useState<Record<string, boolean>>({});
  const [apiKeyValidation, setApiKeyValidation] = useState<Record<string, { type: 'idle' | 'success' | 'error'; message: string }>>({});
  const [savingApiKey, setSavingApiKey] = useState<string | null>(null);
  const [notificationConfig, setNotificationConfig] = useState<NotificationConfig | null>(null);
  const [notificationMessage, setNotificationMessage] = useState('');
  const [notificationSaving, setNotificationSaving] = useState(false);

  const fetchTools = async () => {
    try {
      const response = await authFetch(`${API_BASE}/api/tools`);
      const data = await response.json();
      setTools(data);
    } catch {
      setTools([]);
    }
  };

  const fetchApiKeys = async () => {
    try {
      const response = await authFetch(`${API_BASE}/api/tools/api-keys`);
      const data = await response.json();
      setApiKeyStatus(data);
    } catch {
      setApiKeyStatus({});
    }
  };

  const fetchNotificationConfig = async () => {
    try {
      const response = await authFetch(`${API_BASE}/api/notifications/config`);
      const data = await response.json();
      setNotificationConfig(data);
    } catch {
      setNotificationConfig(null);
    }
  };

  useEffect(() => {
    Promise.all([fetchTools(), fetchApiKeys(), fetchNotificationConfig()]).finally(() => setLoading(false));
  }, []);

  const toggleEnabled = async (toolName: string, currentEnabled: boolean) => {
    const newEnabled = !currentEnabled;
    setTools((prev) => prev.map((tool) => (tool.name === toolName ? { ...tool, enabled: newEnabled } : tool)));
    try {
      await authFetch(`${API_BASE}/api/tools/${toolName}/enabled`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ enabled: newEnabled }),
      });
    } catch {
      setTools((prev) => prev.map((tool) => (tool.name === toolName ? { ...tool, enabled: currentEnabled } : tool)));
    }
  };

  const validateApiKey = async (toolName: string) => {
    setApiKeyValidation((prev) => ({
      ...prev,
      [toolName]: { type: 'idle', message: 'Validating...' },
    }));

    try {
      const response = await authFetch(`${API_BASE}/api/tools/api-keys/${toolName}/validate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ api_key: apiKeyDrafts[toolName] || null }),
      });
      const data = await response.json();
      setApiKeyValidation((prev) => ({
        ...prev,
        [toolName]: {
          type: data.valid ? 'success' : 'error',
          message: data.message || (data.valid ? 'Validation succeeded.' : 'Validation failed.'),
        },
      }));
    } catch (error) {
      setApiKeyValidation((prev) => ({
        ...prev,
        [toolName]: {
          type: 'error',
          message: error instanceof Error ? error.message : 'Validation failed.',
        },
      }));
    }
  };

  const saveApiKeys = async (toolName?: string) => {
    const payload = toolName
      ? { [toolName]: apiKeyDrafts[toolName] || '' }
      : Object.fromEntries(
          Object.entries(apiKeyDrafts).filter(([, value]) => value.trim() !== ''),
        );

    if (Object.keys(payload).length === 0) {
      return;
    }

    setSavingApiKey(toolName || 'all');
    try {
      const response = await authFetch(`${API_BASE}/api/tools/api-keys`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      const data = await response.json();
      setApiKeyStatus(data.api_keys || {});
      if (toolName) {
        setApiKeyDrafts((prev) => ({ ...prev, [toolName]: '' }));
      } else {
        setApiKeyDrafts({});
      }
      await fetchTools();
    } finally {
      setSavingApiKey(null);
    }
  };

  const saveNotificationConfig = async () => {
    if (!notificationConfig) {
      return;
    }
    setNotificationSaving(true);
    setNotificationMessage('');
    try {
      const response = await authFetch(`${API_BASE}/api/notifications/config`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(notificationConfig),
      });
      const data = await response.json();
      setNotificationConfig(data);
      setNotificationMessage('Notification preferences saved.');
    } catch (error) {
      setNotificationMessage(error instanceof Error ? error.message : 'Failed to save notification settings.');
    } finally {
      setNotificationSaving(false);
    }
  };

  const sendTestNotification = async () => {
    setNotificationMessage('');
    try {
      const response = await authFetch(`${API_BASE}/api/notifications/test`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          title: 'AgentOS test notification',
          body: 'The notification pipeline is active.',
          channels: notificationConfig?.channels || ['browser', 'session'],
        }),
      });
      const data = await response.json();
      setNotificationMessage(data.success ? 'Test notification sent.' : 'Test notification did not reach any enabled channel.');
    } catch (error) {
      setNotificationMessage(error instanceof Error ? error.message : 'Failed to send test notification.');
    }
  };

  const filteredTools = tools.filter((tool) =>
    tool.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
    tool.description.toLowerCase().includes(searchTerm.toLowerCase()),
  );

  const enabledCount = tools.filter((tool) => tool.enabled).length;
  const configuredKeyCount = Object.values(apiKeyStatus).filter((item) => item.configured).length;

  return (
    <DashboardLayout>
      <div className="flex-1 space-y-8 p-10 lg:p-12">
        <div className="flex items-center justify-between space-y-2">
          <h2 className="text-4xl font-extrabold tracking-tight text-foreground/90">Tools Workspace</h2>
        </div>

        <div className="grid gap-6 md:grid-cols-3">
          <Card className="border-border/60 shadow-lg">
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-3">
              <CardTitle className="text-sm font-bold uppercase tracking-wider text-muted-foreground">Functional Units</CardTitle>
              <Wrench className="h-5 w-5 text-primary" />
            </CardHeader>
            <CardContent>
              <div className="text-4xl font-black">{tools.length}</div>
              <p className="mt-2 text-sm text-muted-foreground">Registered tool modules</p>
            </CardContent>
          </Card>
          <Card className="border-border/60 shadow-lg">
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-3">
              <CardTitle className="text-sm font-bold uppercase tracking-wider text-muted-foreground">Active Safety</CardTitle>
              <ShieldCheck className="h-5 w-5 text-green-500" />
            </CardHeader>
            <CardContent>
              <div className="text-4xl font-black text-green-600 dark:text-green-500">{enabledCount}</div>
              <p className="mt-2 text-sm text-muted-foreground">Enabled tool entries</p>
            </CardContent>
          </Card>
          <Card className="border-border/60 shadow-lg">
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-3">
              <CardTitle className="text-sm font-bold uppercase tracking-wider text-muted-foreground">API Keys Ready</CardTitle>
              <KeyRound className="h-5 w-5 text-amber-500" />
            </CardHeader>
            <CardContent>
              <div className="text-4xl font-black text-amber-600 dark:text-amber-400">{configuredKeyCount}</div>
              <p className="mt-2 text-sm text-muted-foreground">Configured external tool credentials</p>
            </CardContent>
          </Card>
        </div>

        <Card className="overflow-hidden border-border/80 shadow-xl">
          <CardHeader className="border-b bg-muted/30 p-8">
            <CardTitle className="text-2xl font-bold">Tool Administration</CardTitle>
            <CardDescription className="mt-2 text-base">
              Review the registry, wire API keys, and tune notification safety defaults.
            </CardDescription>
          </CardHeader>
          <CardContent className="p-8">
            {loading ? (
              <div className="flex flex-col items-center justify-center gap-4 py-24">
                <Loader2 className="animate-spin text-primary" size={48} />
                <p className="text-sm font-bold uppercase tracking-[0.18em] text-muted-foreground">Hydrating tool workspace...</p>
              </div>
            ) : (
              <Tabs defaultValue="registry" className="gap-8">
                <TabsList variant="line" className="w-full justify-start overflow-x-auto rounded-none p-0">
                  <TabsTrigger value="registry" className="px-4 py-2 font-bold">Tool Registry</TabsTrigger>
                  <TabsTrigger value="api-keys" className="px-4 py-2 font-bold">API Keys</TabsTrigger>
                  <TabsTrigger value="safety" className="px-4 py-2 font-bold">Safety Configs</TabsTrigger>
                </TabsList>

                <TabsContent value="registry" className="space-y-6">
                  <div className="relative w-full md:w-96">
                    <Search className="absolute left-4 top-4 h-5 w-5 text-muted-foreground" />
                    <Input
                      type="text"
                      placeholder="Search tools..."
                      value={searchTerm}
                      onChange={(event) => setSearchTerm(event.target.value)}
                      className="rounded-2xl border-border/60 bg-background py-7 pl-12 text-base shadow-inner"
                    />
                  </div>

                  <div className="space-y-6">
                    {filteredTools.map((tool) => {
                      const RiskIcon = riskIcons[tool.riskLevel] || Shield;
                      const isExpanded = expandedTools.has(tool.id);
                      const keyStatus = apiKeyStatus[tool.name];

                      return (
                        <div key={tool.id} className="flex flex-col gap-6 rounded-2xl border border-border/60 bg-card p-8 shadow-sm sm:flex-row">
                          <div className="flex flex-1 items-start gap-6">
                            <div className="rounded-xl bg-primary/10 p-4">
                              <RiskIcon size={28} className="text-primary" />
                            </div>
                            <div className="flex-1 space-y-2">
                              <div className="flex flex-wrap items-center gap-3">
                                <h3 className="text-lg font-bold text-foreground">{tool.name}</h3>
                                <Badge variant={tool.riskLevel === 'high' ? 'destructive' : tool.riskLevel === 'medium' ? 'secondary' : 'default'}>
                                  {tool.riskLevel}
                                </Badge>
                                {tool.requiresApiKey && keyStatus?.configured && (
                                  <Badge className="bg-emerald-500/15 text-emerald-700 dark:text-emerald-300">
                                    API Key Configured
                                  </Badge>
                                )}
                                {tool.requiresApiKey && !keyStatus?.configured && (
                                  <Badge variant="destructive">API Key Required</Badge>
                                )}
                              </div>
                              <p className="text-base leading-relaxed text-muted-foreground">{tool.description}</p>

                              {Object.keys(tool.parameters).length > 0 && (
                                <button
                                  onClick={() => setExpandedTools((prev) => {
                                    const next = new Set(prev);
                                    if (next.has(tool.id)) {
                                      next.delete(tool.id);
                                    } else {
                                      next.add(tool.id);
                                    }
                                    return next;
                                  })}
                                  className="pt-2 text-sm font-bold text-primary hover:underline"
                                >
                                  {isExpanded ? 'Hide Parameters' : 'View Configuration Parameters'}
                                </button>
                              )}

                              {isExpanded && Object.keys(tool.parameters).length > 0 && (
                                <div className="mt-4 rounded-xl border border-border/40 bg-muted/50 p-6 font-mono text-sm">
                                  <pre className="whitespace-pre-wrap text-muted-foreground">
                                    {JSON.stringify(tool.parameters, null, 2)}
                                  </pre>
                                </div>
                              )}
                            </div>
                          </div>

                          <div className="flex items-start">
                            <label className="relative inline-flex cursor-pointer items-center">
                              <input
                                type="checkbox"
                                checked={tool.enabled}
                                onChange={() => toggleEnabled(tool.name, tool.enabled)}
                                className="peer sr-only"
                              />
                              <div className="pointer-events-none h-7 w-12 rounded-full bg-muted shadow-md after:absolute after:left-[2px] after:top-[2px] after:h-6 after:w-6 after:rounded-full after:bg-white after:transition-all after:content-[''] peer-checked:bg-primary peer-checked:after:translate-x-full" />
                            </label>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </TabsContent>

                <TabsContent value="api-keys" className="space-y-6">
                  {Object.entries(apiKeyStatus).map(([toolName, status]) => (
                    <Card key={toolName} className="border-border/60 shadow-sm">
                      <CardHeader className="space-y-3">
                        <div className="flex flex-wrap items-center justify-between gap-3">
                          <div>
                            <CardTitle className="text-xl font-bold">{toolName}</CardTitle>
                            <CardDescription className="mt-1 text-sm">{status.description}</CardDescription>
                          </div>
                          <Badge variant={status.configured ? 'default' : 'destructive'}>
                            {status.configured ? 'Configured' : 'Required'}
                          </Badge>
                        </div>
                      </CardHeader>
                      <CardContent className="space-y-5">
                        <details className="rounded-2xl border border-border/60 bg-muted/20 px-4 py-3">
                          <summary className="cursor-pointer text-sm font-bold text-foreground">
                            Setup Guide
                          </summary>
                          <div className="mt-4 space-y-3 text-sm text-muted-foreground">
                            <ul className="space-y-2">
                              {status.setup_guide.map((step) => (
                                <li key={step}>{step}</li>
                              ))}
                            </ul>
                            <p>
                              Docs: <a href={status.docs_url} target="_blank" rel="noreferrer" className="font-semibold text-primary underline underline-offset-4">{status.docs_url}</a>
                            </p>
                            <p>Example format: <code>{status.example_format}</code></p>
                          </div>
                        </details>

                        <div className="space-y-2">
                          <label className="text-sm font-bold text-foreground">API Key</label>
                          <div className="flex gap-2">
                            <Input
                              type={apiKeyVisibility[toolName] ? 'text' : 'password'}
                              value={apiKeyDrafts[toolName] || ''}
                              onChange={(event) => setApiKeyDrafts((prev) => ({ ...prev, [toolName]: event.target.value }))}
                              placeholder={status.masked_key || 'Paste a new API key'}
                            />
                            <Button
                              variant="outline"
                              size="icon"
                              onClick={() => setApiKeyVisibility((prev) => ({ ...prev, [toolName]: !prev[toolName] }))}
                            >
                              {apiKeyVisibility[toolName] ? <EyeOff size={16} /> : <Eye size={16} />}
                            </Button>
                          </div>
                        </div>

                        <div className="flex flex-wrap gap-3">
                          <Button variant="outline" className="gap-2" onClick={() => validateApiKey(toolName)}>
                            <TestTube2 size={16} />
                            Validate
                          </Button>
                          <Button
                            className="gap-2"
                            onClick={() => saveApiKeys(toolName)}
                            disabled={!apiKeyDrafts[toolName]?.trim() || savingApiKey === toolName}
                          >
                            {savingApiKey === toolName && <Loader2 size={16} className="animate-spin" />}
                            Save
                          </Button>
                        </div>

                        {apiKeyValidation[toolName]?.message && (
                          <div className={`rounded-2xl px-4 py-3 text-sm ${apiKeyValidation[toolName].type === 'success' ? 'border border-emerald-500/30 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300' : 'border border-rose-500/30 bg-rose-500/10 text-rose-700 dark:text-rose-300'}`}>
                            {apiKeyValidation[toolName].message}
                          </div>
                        )}
                      </CardContent>
                    </Card>
                  ))}

                  <div className="flex justify-end">
                    <Button onClick={() => saveApiKeys()} disabled={savingApiKey === 'all'}>
                      {savingApiKey === 'all' && <Loader2 size={16} className="mr-2 animate-spin" />}
                      Save All
                    </Button>
                  </div>
                </TabsContent>

                <TabsContent value="safety" className="space-y-6">
                  <Card className="border-border/60 shadow-sm">
                    <CardHeader>
                      <div className="flex items-center gap-3">
                        <Bell className="h-5 w-5 text-primary" />
                        <div>
                          <CardTitle className="text-xl font-bold">Notification Preferences</CardTitle>
                          <CardDescription className="mt-1 text-sm">
                            Choose which delivery channels are enabled for system notifications and cron outcomes.
                          </CardDescription>
                        </div>
                      </div>
                    </CardHeader>
                    <CardContent className="space-y-6">
                      <div className="flex items-center justify-between rounded-2xl border border-border/60 bg-muted/20 px-4 py-3">
                        <div>
                          <p className="font-bold text-foreground">Browser permission</p>
                          <p className="text-sm text-muted-foreground">Current permission: {permission}</p>
                        </div>
                        <Button variant="outline" onClick={requestBrowserPermission}>
                          Request Permission
                        </Button>
                      </div>

                      {notificationConfig && (
                        <>
                          <label className="flex items-center gap-3 rounded-2xl border border-border/60 px-4 py-3">
                            <input
                              type="checkbox"
                              checked={notificationConfig.enabled}
                              onChange={(event) => setNotificationConfig((prev) => prev ? { ...prev, enabled: event.target.checked } : prev)}
                              className="h-4 w-4 rounded border-input"
                            />
                            <div>
                              <p className="font-bold text-foreground">Notifications enabled</p>
                              <p className="text-sm text-muted-foreground">Master switch for server-side notification dispatch.</p>
                            </div>
                          </label>

                          <div className="grid gap-4 md:grid-cols-2">
                            {['browser', 'session', 'native', 'electron'].map((channel) => (
                              <label key={channel} className="flex items-center gap-3 rounded-2xl border border-border/60 px-4 py-3">
                                <input
                                  type="checkbox"
                                  checked={notificationConfig.channels.includes(channel)}
                                  onChange={(event) => {
                                    setNotificationConfig((prev) => {
                                      if (!prev) {
                                        return prev;
                                      }
                                      const nextChannels = event.target.checked
                                        ? [...prev.channels, channel]
                                        : prev.channels.filter((item) => item !== channel);
                                      return { ...prev, channels: Array.from(new Set(nextChannels)) };
                                    });
                                  }}
                                  className="h-4 w-4 rounded border-input"
                                />
                                <div>
                                  <p className="font-bold capitalize text-foreground">{channel}</p>
                                  <p className="text-sm text-muted-foreground">Enable the {channel} notification provider.</p>
                                </div>
                              </label>
                            ))}
                          </div>

                          <div className="flex flex-wrap gap-3">
                            <Button onClick={saveNotificationConfig} disabled={notificationSaving}>
                              {notificationSaving && <Loader2 size={16} className="mr-2 animate-spin" />}
                              Save Notification Settings
                            </Button>
                            <Button variant="outline" onClick={sendTestNotification}>
                              Send Test Notification
                            </Button>
                          </div>
                        </>
                      )}

                      {notificationMessage && (
                        <div className="rounded-2xl border border-border/60 bg-muted/20 px-4 py-3 text-sm text-foreground/80">
                          {notificationMessage}
                        </div>
                      )}
                    </CardContent>
                  </Card>
                </TabsContent>
              </Tabs>
            )}
          </CardContent>
        </Card>
      </div>
    </DashboardLayout>
  );
}
