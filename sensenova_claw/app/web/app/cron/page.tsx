'use client';

import { Fragment, useEffect, useState } from 'react';
import { CalendarClock, Clock3, Loader2, Pencil, Play, Plus, RefreshCw, Trash2 } from 'lucide-react';

import { DashboardLayout } from '@/components/layout/DashboardLayout';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { useNotification } from '@/hooks/useNotification';
import { authFetch, API_BASE } from '@/lib/authFetch';

type ScheduleType = 'at' | 'every' | 'cron';
type WakeMode = 'now' | 'next-heartbeat';

interface CronJob {
  id: string;
  name: string;
  description: string;
  schedule_type: ScheduleType;
  schedule_value: string;
  timezone: string | null;
  text: string;
  enabled: boolean;
  wake_mode: WakeMode;
  delete_after_run: boolean | null;
  next_run_at_ms: number | null;
  last_run_at_ms: number | null;
  last_run_status: string | null;
  last_error: string | null;
  last_duration_ms: number | null;
  delivery: {
    mode: 'none' | 'announce';
    channel_id: string | null;
    to: string | null;
    session_id: string | null;
    notification_channels: string[];
  } | null;
}

interface CronRun {
  id: number;
  started_at_ms: number;
  ended_at_ms: number | null;
  status: string;
  error: string | null;
  duration_ms: number | null;
}

interface CronFormState {
  name: string;
  description: string;
  scheduleType: ScheduleType;
  atValue: string;
  intervalValue: string;
  intervalUnit: 'seconds' | 'minutes' | 'hours';
  cronValue: string;
  timezone: string;
  text: string;
  wakeMode: WakeMode;
  deleteAfterRun: boolean;
  sendToSession: boolean;
  deliverySessionId: string;
  notifyBrowser: boolean;
  notifyNative: boolean;
}

const emptyForm: CronFormState = {
  name: '',
  description: '',
  scheduleType: 'cron',
  atValue: '',
  intervalValue: '60',
  intervalUnit: 'minutes',
  cronValue: '0 9 * * *',
  timezone: 'Asia/Shanghai',
  text: '',
  wakeMode: 'now',
  deleteAfterRun: false,
  sendToSession: false,
  deliverySessionId: '',
  notifyBrowser: false,
  notifyNative: false,
};

function formatTimestamp(timestampMs: number | null): string {
  if (!timestampMs) {
    return '-';
  }
  return new Date(timestampMs).toLocaleString();
}

function formatDuration(durationMs: number | null): string {
  if (durationMs == null) {
    return '-';
  }
  if (durationMs < 1000) {
    return `${durationMs} ms`;
  }
  return `${(durationMs / 1000).toFixed(1)} s`;
}

function formatInterval(msString: string): { value: string; unit: 'seconds' | 'minutes' | 'hours' } {
  const value = Number(msString || 0);
  if (value > 0 && value % 3600000 === 0) {
    return { value: String(value / 3600000), unit: 'hours' };
  }
  if (value > 0 && value % 60000 === 0) {
    return { value: String(value / 60000), unit: 'minutes' };
  }
  return { value: String(Math.max(1, Math.floor(value / 1000) || 60)), unit: 'seconds' };
}

function toDatetimeLocal(isoString: string): string {
  const date = new Date(isoString);
  if (Number.isNaN(date.getTime())) {
    return '';
  }
  const offsetMs = date.getTimezoneOffset() * 60000;
  return new Date(date.getTime() - offsetMs).toISOString().slice(0, 16);
}

function humanizeSchedule(job: CronJob): string {
  if (job.schedule_type === 'at') {
    return `One-time • ${formatTimestamp(Date.parse(job.schedule_value))}`;
  }
  if (job.schedule_type === 'every') {
    const interval = formatInterval(job.schedule_value);
    return `Every ${interval.value} ${interval.unit}`;
  }
  const tz = job.timezone || 'UTC';
  return `Cron • ${job.schedule_value} • ${tz}`;
}

function describeDelivery(job: CronJob): string {
  const parts: string[] = [];
  if (job.delivery?.session_id) {
    parts.push(`Session ${job.delivery.session_id}`);
  }
  for (const channel of job.delivery?.notification_channels || []) {
    parts.push(channel === 'native' ? 'Native notification' : 'Browser notification');
  }
  return parts.length > 0 ? parts.join(' • ') : 'No reminder delivery targets';
}

function buildPayload(form: CronFormState) {
  let scheduleValue = form.cronValue;
  if (form.scheduleType === 'at') {
    scheduleValue = new Date(form.atValue).toISOString();
  }
  if (form.scheduleType === 'every') {
    const multiplier = form.intervalUnit === 'hours' ? 3600000 : form.intervalUnit === 'minutes' ? 60000 : 1000;
    scheduleValue = String(Math.max(1, Number(form.intervalValue || 1)) * multiplier);
  }

  return {
    name: form.name.trim(),
    description: form.description.trim(),
    schedule_type: form.scheduleType,
    schedule_value: scheduleValue,
    timezone: form.scheduleType === 'cron' ? form.timezone.trim() || null : null,
    text: form.text.trim(),
    session_target: 'main',
    wake_mode: form.wakeMode,
    delete_after_run: form.scheduleType === 'at' ? form.deleteAfterRun : false,
    delivery_session_id: form.sendToSession ? form.deliverySessionId.trim() : null,
    notification_channels: [
      ...(form.notifyBrowser ? ['browser'] : []),
      ...(form.notifyNative ? ['native'] : []),
    ],
  };
}

export default function CronPage() {
  const { pushNotification } = useNotification();
  const [jobs, setJobs] = useState<CronJob[]>([]);
  const [loading, setLoading] = useState(true);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [editingJob, setEditingJob] = useState<CronJob | null>(null);
  const [form, setForm] = useState<CronFormState>(emptyForm);
  const [expandedJobId, setExpandedJobId] = useState<string | null>(null);
  const [runLoadingId, setRunLoadingId] = useState<string | null>(null);
  const [triggeringJobId, setTriggeringJobId] = useState<string | null>(null);
  const [runsByJobId, setRunsByJobId] = useState<Record<string, CronRun[]>>({});
  const [errorMessage, setErrorMessage] = useState('');

  const fetchJobs = async () => {
    setLoading(true);
    setErrorMessage('');
    try {
      const response = await authFetch(`${API_BASE}/api/cron/jobs`);
      const data = await response.json();
      setJobs(data.jobs || []);
    } catch (error) {
      setJobs([]);
      setErrorMessage(error instanceof Error ? error.message : 'Failed to load cron jobs.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchJobs();
  }, []);

  const openCreateDialog = () => {
    setEditingJob(null);
    setForm(emptyForm);
    setDialogOpen(true);
  };

  const openEditDialog = (job: CronJob) => {
    const interval = formatInterval(job.schedule_value);
    setEditingJob(job);
    setForm({
      name: job.name || '',
      description: job.description || '',
      scheduleType: job.schedule_type,
      atValue: job.schedule_type === 'at' ? toDatetimeLocal(job.schedule_value) : '',
      intervalValue: interval.value,
      intervalUnit: interval.unit,
      cronValue: job.schedule_type === 'cron' ? job.schedule_value : '0 9 * * *',
      timezone: job.timezone || 'Asia/Shanghai',
      text: job.text || '',
      wakeMode: job.wake_mode || 'now',
      deleteAfterRun: Boolean(job.delete_after_run),
      sendToSession: Boolean(job.delivery?.session_id),
      deliverySessionId: job.delivery?.session_id || '',
      notifyBrowser: Boolean(job.delivery?.notification_channels?.includes('browser')),
      notifyNative: Boolean(job.delivery?.notification_channels?.includes('native')),
    });
    setDialogOpen(true);
  };

  const saveJob = async () => {
    if (!form.name.trim()) {
      setErrorMessage('Job name is required.');
      return;
    }
    if (!form.text.trim()) {
      setErrorMessage('Message text is required.');
      return;
    }
    if (form.scheduleType === 'at' && !form.atValue) {
      setErrorMessage('Select a run time for the one-time schedule.');
      return;
    }
    if (form.sendToSession && !form.deliverySessionId.trim()) {
      setErrorMessage('Provide a session ID when session delivery is enabled.');
      return;
    }

    setSaving(true);
    setErrorMessage('');
    try {
      const payload = buildPayload(form);
      const url = editingJob
        ? `${API_BASE}/api/cron/jobs/${editingJob.id}`
        : `${API_BASE}/api/cron/jobs`;
      const method = editingJob ? 'PUT' : 'POST';

      await authFetch(url, {
        method,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });

      setDialogOpen(false);
      setEditingJob(null);
      setForm(emptyForm);
      await fetchJobs();
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : 'Failed to save cron job.');
    } finally {
      setSaving(false);
    }
  };

  const toggleEnabled = async (job: CronJob) => {
    await authFetch(`${API_BASE}/api/cron/jobs/${job.id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ enabled: !job.enabled }),
    });
    await fetchJobs();
  };

  const deleteJob = async (job: CronJob) => {
    const confirmed = window.confirm(`Delete cron job "${job.name}"?`);
    if (!confirmed) {
      return;
    }
    await authFetch(`${API_BASE}/api/cron/jobs/${job.id}`, { method: 'DELETE' });
    await fetchJobs();
  };

  const fetchRuns = async (jobId: string) => {
    setRunLoadingId(jobId);
    try {
      const response = await authFetch(`${API_BASE}/api/cron/jobs/${jobId}/runs?limit=10`);
      const data = await response.json();
      setRunsByJobId((prev) => ({ ...prev, [jobId]: data.runs || [] }));
    } finally {
      setRunLoadingId(null);
    }
  };

  const toggleRuns = async (jobId: string) => {
    if (expandedJobId === jobId) {
      setExpandedJobId(null);
      return;
    }

    setExpandedJobId(jobId);
    if (runsByJobId[jobId]) {
      return;
    }

    await fetchRuns(jobId);
  };

  const triggerJob = async (job: CronJob) => {
    setTriggeringJobId(job.id);
    try {
      const response = await authFetch(`${API_BASE}/api/cron/jobs/${job.id}/trigger`, {
        method: 'POST',
      });
      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.detail || 'Failed to trigger cron job.');
      }

      await fetchJobs();
      if (data.deleted) {
        setExpandedJobId((current) => (current === job.id ? null : current));
        setRunsByJobId((prev) => {
          const next = { ...prev };
          delete next[job.id];
          return next;
        });
      } else if (expandedJobId === job.id) {
        await fetchRuns(job.id);
      }

      pushNotification({
        title: 'Cron job triggered',
        body: `Triggered "${job.name}".`,
        level: 'success',
        source: 'cron',
      }, {
        toast: true,
        browser: false,
      });
    } catch (error) {
      pushNotification({
        title: 'Failed to trigger cron job',
        body: error instanceof Error ? error.message : 'Failed to trigger cron job.',
        level: 'error',
        source: 'cron',
      }, {
        toast: true,
        browser: false,
      });
    } finally {
      setTriggeringJobId(null);
    }
  };

  const totalJobs = jobs.length;
  const activeJobs = jobs.filter((job) => job.enabled).length;
  const lastRunJob = [...jobs]
    .filter((job) => job.last_run_at_ms)
    .sort((left, right) => (right.last_run_at_ms || 0) - (left.last_run_at_ms || 0))[0];

  return (
    <DashboardLayout>
      <div className="flex-1 space-y-8 p-10 lg:p-12">
        <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
          <div>
            <h2 className="text-4xl font-extrabold tracking-tight text-foreground/90">Cron Control</h2>
            <p className="mt-2 text-base text-muted-foreground">
              Manage scheduled reminders and background wakeups from the dashboard.
            </p>
          </div>
          <div className="flex gap-3">
            <Button variant="outline" size="lg" className="gap-2 rounded-xl" onClick={fetchJobs}>
              <RefreshCw size={16} />
              Refresh
            </Button>
            <Button size="lg" className="gap-2 rounded-xl" onClick={openCreateDialog}>
              <Plus size={16} />
              Create Job
            </Button>
          </div>
        </div>

        <div className="grid gap-6 md:grid-cols-3">
          <Card className="border-border/60 shadow-lg">
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-3">
              <CardTitle className="text-sm font-bold uppercase tracking-wider text-muted-foreground">Total Jobs</CardTitle>
              <CalendarClock className="h-5 w-5 text-primary" />
            </CardHeader>
            <CardContent>
              <div className="text-4xl font-black">{totalJobs}</div>
              <p className="mt-2 text-sm text-muted-foreground">Persisted scheduler entries</p>
            </CardContent>
          </Card>
          <Card className="border-border/60 shadow-lg">
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-3">
              <CardTitle className="text-sm font-bold uppercase tracking-wider text-muted-foreground">Active</CardTitle>
              <Clock3 className="h-5 w-5 text-emerald-500" />
            </CardHeader>
            <CardContent>
              <div className="text-4xl font-black text-emerald-600 dark:text-emerald-400">{activeJobs}</div>
              <p className="mt-2 text-sm text-muted-foreground">Enabled jobs ready to run</p>
            </CardContent>
          </Card>
          <Card className="border-border/60 shadow-lg">
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-3">
              <CardTitle className="text-sm font-bold uppercase tracking-wider text-muted-foreground">Last Run</CardTitle>
              <RefreshCw className="h-5 w-5 text-amber-500" />
            </CardHeader>
            <CardContent>
              <div className="text-lg font-black">
                {lastRunJob?.last_run_status ? lastRunJob.last_run_status.toUpperCase() : 'NO RUNS'}
              </div>
              <p className="mt-2 text-sm text-muted-foreground">
                {lastRunJob ? `${lastRunJob.name} • ${formatTimestamp(lastRunJob.last_run_at_ms)}` : 'No execution history yet.'}
              </p>
            </CardContent>
          </Card>
        </div>

        <Card className="overflow-hidden border-border/80 shadow-xl">
          <CardHeader className="border-b bg-muted/30 p-8">
            <CardTitle className="text-2xl font-bold">Scheduled Jobs</CardTitle>
            <CardDescription className="text-base">
              Review schedules, delivery state, and recent execution history.
            </CardDescription>
          </CardHeader>
          <CardContent className="p-0">
            {loading ? (
              <div className="flex flex-col items-center justify-center gap-4 py-24">
                <Loader2 className="animate-spin text-primary" size={48} />
                <p className="text-sm font-bold uppercase tracking-[0.18em] text-muted-foreground">Loading scheduler state...</p>
              </div>
            ) : jobs.length === 0 ? (
              <div className="py-24 text-center text-muted-foreground">
                <p className="text-lg font-bold uppercase tracking-[0.18em] opacity-40">No cron jobs configured</p>
              </div>
            ) : (
              <div className="overflow-x-auto">
                <Table>
                  <TableHeader className="bg-muted/50">
                    <TableRow className="hover:bg-transparent">
                      <TableHead className="pl-8">Name</TableHead>
                      <TableHead>Schedule</TableHead>
                      <TableHead>Status</TableHead>
                      <TableHead>Next Run</TableHead>
                      <TableHead>Last Run</TableHead>
                      <TableHead>Last Status</TableHead>
                      <TableHead className="pr-8 text-right">Actions</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {jobs.map((job) => (
                      <Fragment key={job.id}>
                        <TableRow className="border-b border-border/40">
                          <TableCell className="pl-8 align-top">
                            <div>
                              <p className="font-bold text-foreground">{job.name}</p>
                              <p className="mt-1 max-w-md text-sm text-muted-foreground">{job.description || job.text}</p>
                            </div>
                          </TableCell>
                          <TableCell className="align-top">
                            <div className="space-y-1">
                              <p className="font-medium text-foreground">{humanizeSchedule(job)}</p>
                              <p className="text-xs uppercase tracking-[0.16em] text-muted-foreground">
                                Wake: {job.wake_mode}
                              </p>
                              <p className="text-xs text-muted-foreground">
                                Delivery: {describeDelivery(job)}
                              </p>
                            </div>
                          </TableCell>
                          <TableCell className="align-top">
                            <Badge variant={job.enabled ? 'default' : 'secondary'}>
                              {job.enabled ? 'Enabled' : 'Disabled'}
                            </Badge>
                          </TableCell>
                          <TableCell className="align-top text-sm text-muted-foreground">
                            {formatTimestamp(job.next_run_at_ms)}
                          </TableCell>
                          <TableCell className="align-top text-sm text-muted-foreground">
                            {formatTimestamp(job.last_run_at_ms)}
                          </TableCell>
                          <TableCell className="align-top">
                            {job.last_run_status ? (
                              <Badge variant={job.last_run_status === 'error' ? 'destructive' : 'secondary'}>
                                {job.last_run_status}
                              </Badge>
                            ) : (
                              <span className="text-sm text-muted-foreground">-</span>
                            )}
                          </TableCell>
                          <TableCell className="pr-8 align-top">
                            <div className="flex flex-wrap justify-end gap-2">
                              <Button
                                variant="outline"
                                size="sm"
                                onClick={() => triggerJob(job)}
                                disabled={triggeringJobId === job.id}
                                className="gap-2"
                              >
                                {triggeringJobId === job.id ? (
                                  <Loader2 size={14} className="animate-spin" />
                                ) : (
                                  <Play size={14} />
                                )}
                                Run Now
                              </Button>
                              <Button variant="outline" size="sm" onClick={() => toggleRuns(job.id)}>
                                History
                              </Button>
                              <Button variant="outline" size="sm" onClick={() => openEditDialog(job)}>
                                <Pencil size={14} />
                              </Button>
                              <Button variant="outline" size="sm" onClick={() => toggleEnabled(job)}>
                                {job.enabled ? 'Disable' : 'Enable'}
                              </Button>
                              <Button variant="destructive" size="sm" onClick={() => deleteJob(job)}>
                                <Trash2 size={14} />
                              </Button>
                            </div>
                          </TableCell>
                        </TableRow>
                        {expandedJobId === job.id && (
                          <TableRow className="bg-muted/15">
                            <TableCell colSpan={7} className="px-8 py-6">
                              {runLoadingId === job.id ? (
                                <div className="flex items-center gap-3 text-muted-foreground">
                                  <Loader2 className="animate-spin" size={16} />
                                  Loading run history...
                                </div>
                              ) : (runsByJobId[job.id] || []).length === 0 ? (
                                <p className="text-sm text-muted-foreground">No execution history for this job.</p>
                              ) : (
                                <div className="overflow-x-auto rounded-2xl border border-border/60 bg-background">
                                  <Table>
                                    <TableHeader>
                                      <TableRow>
                                        <TableHead>Started At</TableHead>
                                        <TableHead>Duration</TableHead>
                                        <TableHead>Status</TableHead>
                                        <TableHead>Error</TableHead>
                                      </TableRow>
                                    </TableHeader>
                                    <TableBody>
                                      {(runsByJobId[job.id] || []).map((run) => (
                                        <TableRow key={run.id}>
                                          <TableCell>{formatTimestamp(run.started_at_ms)}</TableCell>
                                          <TableCell>{formatDuration(run.duration_ms)}</TableCell>
                                          <TableCell>
                                            <Badge variant={run.status === 'error' ? 'destructive' : 'secondary'}>
                                              {run.status}
                                            </Badge>
                                          </TableCell>
                                          <TableCell className="max-w-xl text-sm text-muted-foreground">
                                            {run.error || '-'}
                                          </TableCell>
                                        </TableRow>
                                      ))}
                                    </TableBody>
                                  </Table>
                                </div>
                              )}
                            </TableCell>
                          </TableRow>
                        )}
                      </Fragment>
                    ))}
                  </TableBody>
                </Table>
              </div>
            )}
          </CardContent>
        </Card>

        <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
          <DialogContent className="max-h-[90vh] overflow-y-auto overflow-x-hidden rounded-3xl p-0 sm:max-w-4xl lg:max-w-5xl">
            <DialogHeader className="border-b px-8 py-6">
              <DialogTitle className="text-2xl font-bold">
                {editingJob ? 'Edit Cron Job' : 'Create Cron Job'}
              </DialogTitle>
              <DialogDescription className="text-base">
                Configure the schedule, delivery message, and wake mode for this task.
              </DialogDescription>
            </DialogHeader>

            <div className="space-y-6 px-8 py-6">
              <div className="grid gap-4 md:grid-cols-2">
                <div className="space-y-2">
                  <label className="text-sm font-bold text-foreground">Name</label>
                  <Input
                    value={form.name}
                    onChange={(event) => setForm((prev) => ({ ...prev, name: event.target.value }))}
                    placeholder="Daily report reminder"
                  />
                </div>
                <div className="space-y-2">
                  <label className="text-sm font-bold text-foreground">Wake Mode</label>
                  <select
                    value={form.wakeMode}
                    onChange={(event) => setForm((prev) => ({ ...prev, wakeMode: event.target.value as WakeMode }))}
                    className="h-10 w-full rounded-xl border border-input bg-background px-3 text-sm"
                  >
                    <option value="now">Wake now</option>
                    <option value="next-heartbeat">Wait for next heartbeat</option>
                  </select>
                </div>
              </div>

              <div className="space-y-2">
                <label className="text-sm font-bold text-foreground">Description</label>
                <textarea
                  value={form.description}
                  onChange={(event) => setForm((prev) => ({ ...prev, description: event.target.value }))}
                  placeholder="Why this job exists."
                  className="min-h-24 w-full rounded-2xl border border-input bg-background px-4 py-3 text-sm"
                />
              </div>

              <div className="grid gap-4 md:grid-cols-[220px,1fr]">
                <div className="space-y-2">
                  <label className="text-sm font-bold text-foreground">Schedule Type</label>
                  <select
                    value={form.scheduleType}
                    onChange={(event) => setForm((prev) => ({ ...prev, scheduleType: event.target.value as ScheduleType }))}
                    className="h-10 w-full rounded-xl border border-input bg-background px-3 text-sm"
                  >
                    <option value="at">One-time</option>
                    <option value="every">Interval</option>
                    <option value="cron">Cron expression</option>
                  </select>
                </div>

                {form.scheduleType === 'at' && (
                  <div className="space-y-2">
                    <label className="text-sm font-bold text-foreground">Run At</label>
                    <input
                      type="datetime-local"
                      value={form.atValue}
                      onChange={(event) => setForm((prev) => ({ ...prev, atValue: event.target.value }))}
                      className="h-10 w-full rounded-xl border border-input bg-background px-3 text-sm"
                    />
                  </div>
                )}

                {form.scheduleType === 'every' && (
                  <div className="grid gap-4 md:grid-cols-[1fr,180px]">
                    <div className="space-y-2">
                      <label className="text-sm font-bold text-foreground">Interval</label>
                      <Input
                        type="number"
                        min={1}
                        value={form.intervalValue}
                        onChange={(event) => setForm((prev) => ({ ...prev, intervalValue: event.target.value }))}
                      />
                    </div>
                    <div className="space-y-2">
                      <label className="text-sm font-bold text-foreground">Unit</label>
                      <select
                        value={form.intervalUnit}
                        onChange={(event) => setForm((prev) => ({ ...prev, intervalUnit: event.target.value as CronFormState['intervalUnit'] }))}
                        className="h-10 w-full rounded-xl border border-input bg-background px-3 text-sm"
                      >
                        <option value="seconds">Seconds</option>
                        <option value="minutes">Minutes</option>
                        <option value="hours">Hours</option>
                      </select>
                    </div>
                  </div>
                )}

                {form.scheduleType === 'cron' && (
                  <div className="grid gap-4 md:grid-cols-[1fr,220px]">
                    <div className="space-y-2">
                      <label className="text-sm font-bold text-foreground">Cron Expression</label>
                      <Input
                        value={form.cronValue}
                        onChange={(event) => setForm((prev) => ({ ...prev, cronValue: event.target.value }))}
                        placeholder="0 9 * * *"
                      />
                    </div>
                    <div className="space-y-2">
                      <label className="text-sm font-bold text-foreground">Timezone</label>
                      <Input
                        value={form.timezone}
                        onChange={(event) => setForm((prev) => ({ ...prev, timezone: event.target.value }))}
                        placeholder="Asia/Shanghai"
                      />
                    </div>
                  </div>
                )}
              </div>

              <div className="space-y-2">
                <label className="text-sm font-bold text-foreground">Message</label>
                <textarea
                  value={form.text}
                  onChange={(event) => setForm((prev) => ({ ...prev, text: event.target.value }))}
                  placeholder="Please check the daily reports."
                  className="min-h-28 w-full rounded-2xl border border-input bg-background px-4 py-3 text-sm"
                />
              </div>

              <div className="space-y-4 rounded-3xl border border-border/60 bg-muted/20 p-5">
                <div>
                  <p className="text-sm font-bold text-foreground">Reminder Delivery</p>
                  <p className="mt-1 text-sm text-muted-foreground">
                    Choose where the reminder itself should appear when the cron job fires.
                  </p>
                </div>

                <label className="flex items-center gap-3 text-sm">
                  <input
                    type="checkbox"
                    checked={form.sendToSession}
                    onChange={(event) => setForm((prev) => ({ ...prev, sendToSession: event.target.checked }))}
                    className="h-4 w-4 rounded border-input"
                  />
                  Send the reminder into a specific chat session
                </label>

                {form.sendToSession && (
                  <div className="space-y-2">
                    <label className="text-sm font-bold text-foreground">Session ID</label>
                    <Input
                      value={form.deliverySessionId}
                      onChange={(event) => setForm((prev) => ({ ...prev, deliverySessionId: event.target.value }))}
                      placeholder="sess_xxxxxxxxxxxx"
                    />
                  </div>
                )}

                <div className="grid gap-3 md:grid-cols-2">
                  <label className="flex items-center gap-3 rounded-2xl border border-border/60 bg-background px-4 py-3 text-sm">
                    <input
                      type="checkbox"
                      checked={form.notifyBrowser}
                      onChange={(event) => setForm((prev) => ({ ...prev, notifyBrowser: event.target.checked }))}
                      className="h-4 w-4 rounded border-input"
                    />
                    Send a browser notification
                  </label>
                  <label className="flex items-center gap-3 rounded-2xl border border-border/60 bg-background px-4 py-3 text-sm">
                    <input
                      type="checkbox"
                      checked={form.notifyNative}
                      onChange={(event) => setForm((prev) => ({ ...prev, notifyNative: event.target.checked }))}
                      className="h-4 w-4 rounded border-input"
                    />
                    Send a backend native desktop notification
                  </label>
                </div>
              </div>

              {form.scheduleType === 'at' && (
                <label className="flex items-center gap-3 rounded-2xl border border-border/60 bg-muted/20 px-4 py-3 text-sm">
                  <input
                    type="checkbox"
                    checked={form.deleteAfterRun}
                    onChange={(event) => setForm((prev) => ({ ...prev, deleteAfterRun: event.target.checked }))}
                    className="h-4 w-4 rounded border-input"
                  />
                  Delete the job automatically after the one-time run completes.
                </label>
              )}

              {errorMessage && (
                <div className="rounded-2xl border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive">
                  {errorMessage}
                </div>
              )}
            </div>

            <DialogFooter className="rounded-b-3xl px-8 py-4">
              <Button variant="outline" onClick={() => setDialogOpen(false)}>
                Cancel
              </Button>
              <Button onClick={saveJob} disabled={saving} className="gap-2">
                {saving && <Loader2 size={16} className="animate-spin" />}
                {editingJob ? 'Update Job' : 'Create Job'}
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </div>
    </DashboardLayout>
  );
}
