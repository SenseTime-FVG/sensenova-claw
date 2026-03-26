import { clsx, type ClassValue } from "clsx"
import { twMerge } from "tailwind-merge"
import { authFetch, API_BASE } from "./authFetch";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

export function isJsonLike(value: unknown): boolean {
  if (typeof value === 'object' && value !== null) {
    return true;
  }
  if (typeof value !== 'string') {
    return false;
  }
  try {
    JSON.parse(value);
    return true;
  } catch {
    return false;
  }
}

export function stringifyContent(value: unknown): string {
  if (typeof value === 'string') {
    return value;
  }
  if (value == null) {
    return '';
  }
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

export function previewText(content: string, maxLength: number): string {
  if (content.length <= maxLength) {
    return content;
  }
  return `${content.slice(0, maxLength)}...`;
}

/* ── workdir Root Cache ── */
let _workdirRootCache: string | null | undefined;
export async function fetchWorkdirRoot(): Promise<string | null> {
  if (_workdirRootCache !== undefined) return _workdirRootCache as string | null;
  let result: string | null = null;
  try {
    const res = await authFetch(`${API_BASE}/api/files/roots`);
    if (res.ok) {
      const data = await res.json();
      const entry = (data.roots || []).find((r: { name: string }) => r.name === 'Agent 工作区');
      result = entry?.path ?? null;
    }
  } catch { /* ignore */ }
  _workdirRootCache = result;
  return result;
}
