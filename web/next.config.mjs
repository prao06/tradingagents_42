/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Lint is enforced separately; don't fail the Vercel build on it.
  eslint: { ignoreDuringBuilds: true },
};

export default nextConfig;
