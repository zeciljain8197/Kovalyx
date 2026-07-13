import { createClient } from '@supabase/supabase-js'

/**
 * Public client — uses the anon key, subject to Postgres RLS.
 * Safe to use in Server Components and Route Handlers for marts.* data
 * (see scripts/supabase_schema.sql's Session 5 anon-role RLS migration).
 * DO NOT use for the audit schema — RLS blocks anon access there by
 * construction (anon is never granted USAGE on schema audit).
 */
export function createPublicClient() {
  return createClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!
  )
}

/**
 * Admin client — uses the service role key, bypasses RLS entirely.
 * USE ONLY in server-side code (Server Components, Route Handlers).
 * NEVER import this in a 'use client' component or forward its result
 * to the browser. Used exclusively for the /pipeline admin page's
 * audit-schema reads (see lib/queries/pipeline.ts).
 */
export function createAdminClient() {
  if (!process.env.SUPABASE_SERVICE_ROLE_KEY) {
    throw new Error(
      'SUPABASE_SERVICE_ROLE_KEY is not set. Admin client cannot be created.'
    )
  }
  return createClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.SUPABASE_SERVICE_ROLE_KEY,
    {
      auth: {
        autoRefreshToken: false,
        persistSession: false,
      },
    }
  )
}
