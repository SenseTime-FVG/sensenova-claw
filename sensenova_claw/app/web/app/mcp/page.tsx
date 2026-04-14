'use client';

import { useEffect, useMemo, useState } from 'react';
import {
  Boxes,
  Braces,
  Cable,
  Globe,
  Loader2,
  Plus,
  RefreshCw,
  Save,
  TerminalSquare,
  Trash2,
  Upload,
} from 'lucide-react';

import { DashboardLayout } from '@/components/layout/DashboardLayout';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { authFetch, API_BASE } from '@/lib/authFetch';

type TransportType = 'stdio' | 'sse' | 'streamable-http';

type KeyValueRow = {
  id: string;
  key: string;
  value: string;
};

type McpServerDraft = {
  id: string;
  name: string;
  transport: TransportType;
  command: string;
  args: string[];
  env: KeyValueRow[];
  cwd: string;
  url: string;
  headers: KeyValueRow[];
  timeout: number;
};

type McpApiServer = Omit<McpServerDraft, 'id'>;

const emptyPair = (): KeyValueRow => ({ id: crypto.randomUUID(), key: '', value: '' });

const emptyServer = (): McpServerDraft => ({
  id: crypto.randomUUID(),
  name: '',
  transport: 'stdio',
  command: '',
  args: [],
  env: [],
  cwd: '',
  url: '',
  headers: [],
  timeout: 15,
});

function toDraft(server: Partial<McpApiServer>): McpServerDraft {
  return {
    id: crypto.randomUUID(),
    name: server.name || '',
    transport: (server.transport as TransportType) || 'stdio',
    command: server.command || '',
    args: Array.isArray(server.args) ? server.args.map(String) : [],
    env: Array.isArray(server.env) ? server.env.map((row) => ({ ...row, id: crypto.randomUUID() })) : [],
    cwd: server.cwd || '',
    url: server.url || '',
    headers: Array.isArray(server.headers) ? server.headers.map((row) => ({ ...row, id: crypto.randomUUID() })) : [],
    timeout: Number(server.timeout || 15),
  };
}

function normalizeKeyValueRows(rows: KeyValueRow[]): Array<{ key: string; value: string }> {
  return rows
    .map((row) => ({ key: row.key.trim(), value: row.value }))
    .filter((row) => row.key.length > 0);
}

function toPayload(servers: McpServerDraft[]) {
  return {
    servers: servers.map((server) => ({
      name: server.name.trim(),
      transport: server.transport,
      command: server.command.trim(),
      args: server.args.map((arg) => arg.trim()).filter(Boolean),
      env: normalizeKeyValueRows(server.env),
      cwd: server.cwd.trim(),
      url: server.url.trim(),
      headers: normalizeKeyValueRows(server.headers),
      timeout: Number(server.timeout || 15),
    })),
  };
}

function parseImportJson(raw: string): Partial<McpApiServer>[] {
  const parsed = JSON.parse(raw);
  const servers = parsed?.mcpServers;
  if (!servers || typeof servers !== 'object' || Array.isArray(servers)) {
    throw new Error('JSON 中缺少 mcpServers 对象');
  }

  return Object.entries(servers).map(([name, value]) => {
    const server = value as Record<string, unknown>;
    const transport = String(server.transport || (server.command ? 'stdio' : 'sse')) as TransportType;
    const args = Array.isArray(server.args) ? server.args.map(String) : [];
    const env = server.env && typeof server.env === 'object' && !Array.isArray(server.env)
      ? Object.entries(server.env as Record<string, unknown>).map(([key, item]) => ({ key, value: String(item ?? '') }))
      : [];
    const headers = server.headers && typeof server.headers === 'object' && !Array.isArray(server.headers)
      ? Object.entries(server.headers as Record<string, unknown>).map(([key, item]) => ({ key, value: String(item ?? '') }))
      : [];
    return {
      name,
      transport,
      command: String(server.command || ''),
      args,
      env,
      cwd: String(server.cwd || ''),
      url: String(server.url || ''),
      headers,
      timeout: Number(server.timeout || 15),
    };
  });
}

function validateServers(servers: McpServerDraft[]): string | null {
  const names = new Set<string>();
  for (const server of servers) {
    const name = server.name.trim();
    if (!name) return 'Server 名称不能为空';
    if (names.has(name)) return `Server 名称重复: ${name}`;
    names.add(name);
    if (server.timeout <= 0) return `Server ${name} 的 timeout 必须大于 0`;
    if (server.transport === 'stdio' && !server.command.trim()) return `Server ${name} 缺少 command`;
    if (server.transport !== 'stdio' && !server.url.trim()) return `Server ${name} 缺少 url`;
  }
  return null;
}

export default function McpPage() {
  const [servers, setServers] = useState<McpServerDraft[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState('');
  const [showImportDialog, setShowImportDialog] = useState(false);
  const [importDraft, setImportDraft] = useState('');
  const [importError, setImportError] = useState('');

  const loadServers = async (silent = false) => {
    if (!silent) setRefreshing(true);
    try {
      const response = await authFetch(`${API_BASE}/api/mcp/servers`);
      const data = await response.json();
      setServers(Array.isArray(data.servers) ? data.servers.map((item: McpApiServer) => toDraft(item)) : []);
      setMessage('');
    } catch {
      setMessage('读取 MCP 配置失败');
      setServers([]);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  useEffect(() => {
    void loadServers(true);
  }, []);

  const stats = useMemo(() => {
    const stdioCount = servers.filter((server) => server.transport === 'stdio').length;
    const httpCount = servers.length - stdioCount;
    const headerCount = servers.reduce((sum, server) => sum + normalizeKeyValueRows(server.headers).length, 0);
    return { stdioCount, httpCount, headerCount };
  }, [servers]);

  const updateServer = (id: string, updater: (server: McpServerDraft) => McpServerDraft) => {
    setServers((prev) => prev.map((server) => (server.id === id ? updater(server) : server)));
  };

  const updatePairRows = (
    serverId: string,
    field: 'env' | 'headers',
    rowId: string,
    key: 'key' | 'value',
    value: string,
  ) => {
    updateServer(serverId, (server) => ({
      ...server,
      [field]: server[field].map((row) => (row.id === rowId ? { ...row, [key]: value } : row)),
    }));
  };

  const addPairRow = (serverId: string, field: 'env' | 'headers') => {
    updateServer(serverId, (server) => ({
      ...server,
      [field]: [...server[field], emptyPair()],
    }));
  };

  const removePairRow = (serverId: string, field: 'env' | 'headers', rowId: string) => {
    updateServer(serverId, (server) => ({
      ...server,
      [field]: server[field].filter((row) => row.id !== rowId),
    }));
  };

  const addServer = () => {
    setServers((prev) => [emptyServer(), ...prev]);
    setMessage('');
  };

  const removeServer = (id: string) => {
    setServers((prev) => prev.filter((server) => server.id !== id));
  };

  const saveAll = async () => {
    const validationError = validateServers(servers);
    if (validationError) {
      setMessage(validationError);
      return;
    }
    setSaving(true);
    setMessage('');
    try {
      const payload = toPayload(servers);
      const response = await authFetch(`${API_BASE}/api/mcp/servers`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      const data = await response.json();
      setServers(Array.isArray(data.servers) ? data.servers.map((item: McpApiServer) => toDraft(item)) : []);
      setMessage('MCP 配置已保存');
    } catch (error) {
      setMessage(error instanceof Error ? error.message : '保存 MCP 配置失败');
    } finally {
      setSaving(false);
    }
  };

  const applyImport = () => {
    try {
      const imported = parseImportJson(importDraft);
      setServers((prev) => {
        const merged = [...prev];
        for (const server of imported) {
          const next = toDraft(server);
          const existingIndex = merged.findIndex((item) => item.name.trim() === next.name.trim());
          if (existingIndex >= 0) {
            merged[existingIndex] = next;
          } else {
            merged.unshift(next);
          }
        }
        return merged;
      });
      setShowImportDialog(false);
      setImportDraft('');
      setImportError('');
      setMessage('JSON 导入成功，请点击 Save All 持久化');
    } catch (error) {
      setImportError(error instanceof Error ? error.message : 'JSON 导入失败');
    }
  };

  return (
    <DashboardLayout>
      <div className="flex-1 space-y-8 p-10 lg:p-12">
        <div className="flex items-center justify-between gap-4">
          <div>
            <h2 className="text-4xl font-extrabold tracking-tight text-foreground/90">MCP Registry</h2>
            <p className="mt-2 text-sm text-muted-foreground">Manage global MCP servers and import standard `mcpServers` JSON snippets.</p>
          </div>
          <div className="flex items-center gap-2">
            <Button variant="outline" onClick={() => setShowImportDialog(true)}>
              <Upload className="mr-2 h-4 w-4" />
              Import JSON
            </Button>
            <Button variant="outline" onClick={() => void loadServers()} disabled={loading || refreshing}>
              {refreshing ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <RefreshCw className="mr-2 h-4 w-4" />}
              Refresh
            </Button>
            <Button onClick={saveAll} disabled={loading || saving}>
              {saving ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Save className="mr-2 h-4 w-4" />}
              Save All
            </Button>
          </div>
        </div>

        <div className="grid gap-6 md:grid-cols-2 xl:grid-cols-4">
          <Card className="border-border/60 shadow-lg">
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-3">
              <CardTitle className="text-sm font-bold uppercase tracking-wider text-muted-foreground">Servers</CardTitle>
              <Boxes className="h-5 w-5 text-primary" />
            </CardHeader>
            <CardContent>
              <div className="text-4xl font-black">{servers.length}</div>
              <p className="mt-2 text-sm text-muted-foreground">Configured MCP endpoints</p>
            </CardContent>
          </Card>
          <Card className="border-border/60 shadow-lg">
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-3">
              <CardTitle className="text-sm font-bold uppercase tracking-wider text-muted-foreground">Stdio</CardTitle>
              <TerminalSquare className="h-5 w-5 text-primary" />
            </CardHeader>
            <CardContent>
              <div className="text-4xl font-black">{stats.stdioCount}</div>
              <p className="mt-2 text-sm text-muted-foreground">Local process servers</p>
            </CardContent>
          </Card>
          <Card className="border-border/60 shadow-lg">
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-3">
              <CardTitle className="text-sm font-bold uppercase tracking-wider text-muted-foreground">HTTP</CardTitle>
              <Globe className="h-5 w-5 text-primary" />
            </CardHeader>
            <CardContent>
              <div className="text-4xl font-black">{stats.httpCount}</div>
              <p className="mt-2 text-sm text-muted-foreground">SSE + streamable-http</p>
            </CardContent>
          </Card>
          <Card className="border-border/60 shadow-lg">
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-3">
              <CardTitle className="text-sm font-bold uppercase tracking-wider text-muted-foreground">Headers</CardTitle>
              <Cable className="h-5 w-5 text-primary" />
            </CardHeader>
            <CardContent>
              <div className="text-4xl font-black">{stats.headerCount}</div>
              <p className="mt-2 text-sm text-muted-foreground">Configured HTTP headers</p>
            </CardContent>
          </Card>
        </div>

        <Card className="shadow-xl border-border/80 overflow-hidden">
          <CardHeader className="bg-muted/30 border-b p-8">
            <div className="flex items-center justify-between gap-4">
              <div>
                <CardTitle className="text-2xl font-bold">Server Registry</CardTitle>
                <CardDescription className="mt-2 text-base">Edit global `mcp.servers` and persist them back to `config.yml`.</CardDescription>
              </div>
              <Button variant="outline" onClick={addServer}>
                <Plus className="mr-2 h-4 w-4" />
                Add Server
              </Button>
            </div>
          </CardHeader>
          <CardContent className="p-8">
            {message ? (
              <div className="mb-6 rounded-xl border border-border/60 bg-muted/30 px-4 py-3 text-sm text-foreground/80">
                {message}
              </div>
            ) : null}

            {loading ? (
              <div className="flex flex-col items-center justify-center gap-4 py-24">
                <Loader2 className="h-10 w-10 animate-spin text-primary" />
                <p className="text-sm font-bold uppercase tracking-widest text-muted-foreground">Loading MCP servers…</p>
              </div>
            ) : servers.length === 0 ? (
              <div className="rounded-2xl border border-dashed border-border/60 bg-muted/10 px-8 py-20 text-center">
                <p className="text-lg font-bold uppercase tracking-widest text-muted-foreground/60">No MCP servers configured</p>
                <p className="mt-3 text-sm text-muted-foreground">Use “Add Server” or “Import JSON” to create your first MCP entry.</p>
              </div>
            ) : (
              <div className="space-y-6">
                {servers.map((server) => (
                  <div key={server.id} className="rounded-2xl border border-border/60 bg-card p-6 shadow-sm">
                    <div className="mb-5 flex items-start justify-between gap-4">
                      <div className="space-y-1">
                        <div className="flex items-center gap-3">
                          <h3 className="text-xl font-bold">{server.name || 'New MCP Server'}</h3>
                          <span className="rounded-full border border-border/60 px-2.5 py-1 text-[10px] font-black uppercase tracking-wider text-muted-foreground">
                            {server.transport}
                          </span>
                        </div>
                        <p className="text-xs text-muted-foreground">
                          {server.transport === 'stdio'
                            ? (server.command || 'No command set')
                            : (server.url || 'No URL set')}
                        </p>
                      </div>
                      <Button variant="ghost" size="sm" onClick={() => removeServer(server.id)}>
                        <Trash2 className="h-4 w-4" />
                      </Button>
                    </div>

                    <div className="grid gap-4 md:grid-cols-3">
                      <div className="space-y-2">
                        <label className="text-xs font-black uppercase tracking-wider text-muted-foreground">Name</label>
                        <Input value={server.name} onChange={(e) => updateServer(server.id, (item) => ({ ...item, name: e.target.value }))} />
                      </div>
                      <div className="space-y-2">
                        <label className="text-xs font-black uppercase tracking-wider text-muted-foreground">Transport</label>
                        <select
                          className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                          value={server.transport}
                          onChange={(e) => updateServer(server.id, (item) => ({ ...item, transport: e.target.value as TransportType }))}
                        >
                          <option value="stdio">stdio</option>
                          <option value="sse">sse</option>
                          <option value="streamable-http">streamable-http</option>
                        </select>
                      </div>
                      <div className="space-y-2">
                        <label className="text-xs font-black uppercase tracking-wider text-muted-foreground">Timeout</label>
                        <Input
                          type="number"
                          value={server.timeout}
                          onChange={(e) => updateServer(server.id, (item) => ({ ...item, timeout: Number(e.target.value || 0) }))}
                        />
                      </div>
                    </div>

                    {server.transport === 'stdio' ? (
                      <div className="mt-5 space-y-4">
                        <div className="grid gap-4 md:grid-cols-2">
                          <div className="space-y-2">
                            <label className="text-xs font-black uppercase tracking-wider text-muted-foreground">Command</label>
                            <Input
                              data-testid={`mcp-command-${server.name || server.id}`}
                              value={server.command}
                              onChange={(e) => updateServer(server.id, (item) => ({ ...item, command: e.target.value }))}
                            />
                          </div>
                          <div className="space-y-2">
                            <label className="text-xs font-black uppercase tracking-wider text-muted-foreground">Working Dir</label>
                            <Input value={server.cwd} onChange={(e) => updateServer(server.id, (item) => ({ ...item, cwd: e.target.value }))} />
                          </div>
                        </div>
                        <div className="space-y-2">
                          <label className="text-xs font-black uppercase tracking-wider text-muted-foreground">Args</label>
                          <textarea
                            value={server.args.join('\n')}
                            onChange={(e) => updateServer(server.id, (item) => ({ ...item, args: e.target.value.split('\n').map((arg) => arg.trim()).filter(Boolean) }))}
                            rows={4}
                            className="w-full rounded-xl border border-input bg-background px-4 py-3 text-sm outline-none focus:border-primary/50"
                          />
                          <p className="text-xs text-muted-foreground">One argument per line. Example: `@browsermcp/mcp@latest`</p>
                        </div>
                        <div className="space-y-3">
                          <div className="flex items-center justify-between">
                            <label className="text-xs font-black uppercase tracking-wider text-muted-foreground">Env</label>
                            <Button variant="outline" size="sm" onClick={() => addPairRow(server.id, 'env')}>Add Row</Button>
                          </div>
                          <div className="space-y-2">
                            {server.env.map((row) => (
                              <div key={row.id} className="grid gap-2 md:grid-cols-[1fr_1fr_auto]">
                                <Input value={row.key} placeholder="KEY" onChange={(e) => updatePairRows(server.id, 'env', row.id, 'key', e.target.value)} />
                                <Input value={row.value} placeholder="value" onChange={(e) => updatePairRows(server.id, 'env', row.id, 'value', e.target.value)} />
                                <Button variant="ghost" size="sm" onClick={() => removePairRow(server.id, 'env', row.id)}>
                                  <Trash2 className="h-4 w-4" />
                                </Button>
                              </div>
                            ))}
                          </div>
                        </div>
                      </div>
                    ) : (
                      <div className="mt-5 space-y-4">
                        <div className="space-y-2">
                          <label className="text-xs font-black uppercase tracking-wider text-muted-foreground">URL</label>
                          <Input value={server.url} onChange={(e) => updateServer(server.id, (item) => ({ ...item, url: e.target.value }))} />
                        </div>
                        <div className="space-y-3">
                          <div className="flex items-center justify-between">
                            <label className="text-xs font-black uppercase tracking-wider text-muted-foreground">Headers</label>
                            <Button variant="outline" size="sm" onClick={() => addPairRow(server.id, 'headers')}>Add Row</Button>
                          </div>
                          <div className="space-y-2">
                            {server.headers.map((row) => (
                              <div key={row.id} className="grid gap-2 md:grid-cols-[1fr_1fr_auto]">
                                <Input value={row.key} placeholder="Header" onChange={(e) => updatePairRows(server.id, 'headers', row.id, 'key', e.target.value)} />
                                <Input value={row.value} placeholder="Value" onChange={(e) => updatePairRows(server.id, 'headers', row.id, 'value', e.target.value)} />
                                <Button variant="ghost" size="sm" onClick={() => removePairRow(server.id, 'headers', row.id)}>
                                  <Trash2 className="h-4 w-4" />
                                </Button>
                              </div>
                            ))}
                          </div>
                        </div>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        <Dialog open={showImportDialog} onOpenChange={setShowImportDialog}>
          <DialogContent className="max-w-3xl">
            <DialogHeader>
              <DialogTitle className="flex items-center gap-2">
                <Braces className="h-5 w-5" />
                Import MCP JSON
              </DialogTitle>
              <DialogDescription>
                Paste a standard MCP snippet containing the `mcpServers` object. Imported servers will update the local draft first.
              </DialogDescription>
            </DialogHeader>
            <div className="space-y-4">
              <textarea
                data-testid="mcp-import-textarea"
                value={importDraft}
                onChange={(e) => {
                  setImportDraft(e.target.value);
                  setImportError('');
                }}
                rows={14}
                className="w-full rounded-xl border border-input bg-background px-4 py-3 font-mono text-sm outline-none focus:border-primary/50"
                placeholder={`{\n  "mcpServers": {\n    "sample-server": {\n      "command": "<your-command>",\n      "args": ["<arg-1>", "<arg-2>"],\n      "env": {\n        "API_KEY": "<your-api-key>"\n      }\n    }\n  }\n}`}
              />
              {importError ? (
                <div className="rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-600 dark:text-red-300">
                  {importError}
                </div>
              ) : null}
              <div className="flex justify-end gap-2">
                <Button variant="outline" onClick={() => setShowImportDialog(false)}>Cancel</Button>
                <Button onClick={applyImport}>Import</Button>
              </div>
            </div>
          </DialogContent>
        </Dialog>
      </div>
    </DashboardLayout>
  );
}
