/** @type {import('next').NextConfig} */

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

const nextConfig = {
  reactStrictMode: true,
  async redirects() {
    return [
      {
        source: '/settings',
        destination: '/acp',
        permanent: false,
      },
    ];
  },
  // 代理 /api/* 和 /ws 到后端，解决 Cursor 端口转发问题
  async rewrites() {
    return [
      {
        source: '/api/:path*',
        destination: `${API_URL}/api/:path*`,
      },
      {
        source: '/ws',
        destination: `${API_URL}/ws`,
      },
      {
        source: '/health',
        destination: `${API_URL}/health`,
      },
    ];
  },
};

export default nextConfig;
