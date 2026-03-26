/**
 * 带认证的 fetch 封装（基于 cookie）
 */

const API_BASE = process.env.NEXT_PUBLIC_API_URL || '';
const COOKIE_NAME = 'sensenova_claw_token';

/** 从 document.cookie 读取指定 cookie */
function getCookie(name: string): string | null {
  if (typeof document === 'undefined') return null;
  const match = document.cookie.match(new RegExp(`(?:^|; )${name}=([^;]*)`));
  return match ? decodeURIComponent(match[1]) : null;
}

/**
 * 带认证的 fetch 请求（通过 cookie + Authorization header）
 */
export async function authFetch(
  url: string,
  options: RequestInit = {}
): Promise<Response> {
  const { headers, ...restOptions } = options;

  // 读取 cookie 中的 token，同时放到 Authorization header（跨端口 cookie 可能不携带）
  const token = getCookie(COOKIE_NAME);
  const authHeaders: HeadersInit = {
    ...headers,
  };

  if (token) {
    (authHeaders as Record<string, string>)['Authorization'] = `Bearer ${token}`;
  }

  const response = await fetch(url, {
    ...restOptions,
    headers: authHeaders,
    credentials: 'include',
  });

  // 401 → 跳转到登录页
  if (response.status === 401) {
    window.location.href = '/login';
    throw new Error('Authentication expired, redirecting to login');
  }

  return response;
}

/**
 * GET 请求
 */
export async function authGet<T = any>(url: string, options?: RequestInit): Promise<T> {
  const response = await authFetch(url, { ...options, method: 'GET' });
  return response.json();
}

/**
 * POST 请求
 */
export async function authPost<T = any>(
  url: string,
  body?: any,
  options?: RequestInit
): Promise<T> {
  const response = await authFetch(url, {
    ...options,
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...options?.headers,
    },
    body: body ? JSON.stringify(body) : undefined,
  });
  return response.json();
}

/**
 * PUT 请求
 */
export async function authPut<T = any>(
  url: string,
  body?: any,
  options?: RequestInit
): Promise<T> {
  const response = await authFetch(url, {
    ...options,
    method: 'PUT',
    headers: {
      'Content-Type': 'application/json',
      ...options?.headers,
    },
    body: body ? JSON.stringify(body) : undefined,
  });
  return response.json();
}

/**
 * DELETE 请求
 */
export async function authDelete<T = any>(
  url: string,
  options?: RequestInit
): Promise<T> {
  const response = await authFetch(url, {
    ...options,
    method: 'DELETE',
  });
  return response.json();
}

export { API_BASE };
