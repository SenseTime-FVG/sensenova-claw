"use client";

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/contexts/AuthContext';

export default function LoginPage() {
  const [token, setToken] = useState('');
  const [error, setError] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const router = useRouter();
  const { verifyToken } = useAuth();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setIsLoading(true);

    try {
      const valid = await verifyToken(token.trim());
      if (valid) {
        router.push('/');
      } else {
        setError('Token 无效，请检查终端输出的 token');
      }
    } catch (err: any) {
      setError(err?.message || '验证失败，请确认后端服务已启动');
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50">
      <div className="max-w-md w-full space-y-8 p-8 bg-white rounded-lg shadow-md">
        <div>
          <h2 className="text-center text-3xl font-extrabold text-gray-900">
            Sensenova-Claw
          </h2>
          <p className="mt-2 text-center text-sm text-gray-600">
            请输入服务启动时生成的 Token
          </p>
        </div>

        <form className="mt-8 space-y-6" onSubmit={handleSubmit}>
          {error && (
            <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded">
              {error}
            </div>
          )}

          <div>
            <label htmlFor="token" className="block text-sm font-medium text-gray-700">
              Token
            </label>
            <input
              id="token"
              name="token"
              type="text"
              required
              autoFocus
              value={token}
              onChange={(e) => setToken(e.target.value)}
              className="mt-1 block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500 font-mono text-sm"
              placeholder="粘贴终端中的 token..."
            />
          </div>

          <div>
            <button
              type="submit"
              disabled={isLoading || !token.trim()}
              className="w-full flex justify-center py-2 px-4 border border-transparent rounded-md shadow-sm text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500 disabled:bg-gray-400 disabled:cursor-not-allowed"
            >
              {isLoading ? '验证中...' : '验证 Token'}
            </button>
          </div>

          <div className="text-sm text-center text-gray-500 space-y-1">
            <p>Token 在终端启动日志中，形如：</p>
            <code className="text-xs bg-gray-100 px-2 py-1 rounded">
              http://localhost:3000/?token=xxx
            </code>
          </div>
        </form>
      </div>
    </div>
  );
}
