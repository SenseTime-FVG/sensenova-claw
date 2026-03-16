/**
 * 带认证的 fetch 封装
 * 自动添加 Authorization header
 */

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export interface AuthFetchOptions extends RequestInit {
  skipAuth?: boolean; // 跳过认证（用于登录等公开端点）
}

/**
 * 带认证的 fetch 请求
 */
export async function authFetch(
  url: string,
  options: AuthFetchOptions = {}
): Promise<Response> {
  const { skipAuth, headers, ...restOptions } = options;

  // 获取 token
  const token = !skipAuth ? localStorage.getItem('access_token') : null;

  // 构造 headers
  const authHeaders: HeadersInit = {
    ...headers,
  };

  if (token && !skipAuth) {
    authHeaders['Authorization'] = `Bearer ${token}`;
  }

  // 发送请求
  const response = await fetch(url, {
    ...restOptions,
    headers: authHeaders,
  });

  // 如果返回 401，token 可能过期，跳转到登录页
  if (response.status === 401 && !skipAuth) {
    // 清除 token
    localStorage.removeItem('access_token');
    localStorage.removeItem('refresh_token');
    // 跳转到登录页
    window.location.href = '/login';
  }

  return response;
}

/**
 * GET 请求
 */
export async function authGet<T = any>(url: string, options?: AuthFetchOptions): Promise<T> {
  const response = await authFetch(url, { ...options, method: 'GET' });
  return response.json();
}

/**
 * POST 请求
 */
export async function authPost<T = any>(
  url: string,
  body?: any,
  options?: AuthFetchOptions
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

export { API_BASE };
