/** @type {import('next').NextConfig} */
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
};

export default nextConfig;
