import type { NextConfig } from 'next'

const nextConfig: NextConfig = {
  experimental: {
    typedRoutes: true,
  },
  // All Supabase traffic goes through Next.js Server Components / Route
  // Handlers — no direct client-side calls to the external Supabase URL.
  // The NEXT_PUBLIC_ vars are still needed for the Supabase JS client
  // initialization, but the actual queries run server-side.
  env: {},
}

export default nextConfig
