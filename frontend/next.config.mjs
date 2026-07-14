// next.config.ts isn't supported until Next.js 15 — this project pins
// 14.2.5 (package.json), so the config has to be plain JS/ESM instead.
/** @type {import('next').NextConfig} */
const nextConfig = {
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
