import { createPublicClient } from '@/lib/supabase'

export interface CohortRow {
  cohort_week: string
  weeks_since_acquisition: number
  customers_in_cohort: number
  active_customers: number
  retention_rate: number
}

export interface CustomerSummary {
  total_customers: number
  avg_total_spent: number
  bronze_count: number
  silver_count: number
  gold_count: number
}

export async function getCohortData(): Promise<CohortRow[]> {
  try {
    const supabase = createPublicClient()
    const { data, error } = await supabase
      .from('mart_customer_cohorts')
      .select('cohort_week, weeks_since_acquisition, customers_in_cohort, active_customers, retention_rate')
      .lte('weeks_since_acquisition', 12)
      .order('cohort_week', { ascending: false })
      .order('weeks_since_acquisition', { ascending: true })
      .limit(500)

    if (error || !data) return []
    return data as CohortRow[]
  } catch {
    return []
  }
}

/**
 * dim_customers has no server-side GROUP BY/FILTER support via
 * supabase-js, so tier counts are computed here after fetching every row
 * of (tier, total_spent). PostgREST caps any single response at 1000
 * rows by default regardless of table size — with 2000 customers, an
 * unpaginated .select() here silently returned only half of them (and
 * an average computed over that silent subset), so this pages through
 * with .range() until a short page confirms there's nothing left.
 */
export async function getCustomerTierSummary(): Promise<CustomerSummary> {
  const empty: CustomerSummary = {
    total_customers: 0,
    avg_total_spent: 0,
    bronze_count: 0,
    silver_count: 0,
    gold_count: 0,
  }
  try {
    const supabase = createPublicClient()
    const PAGE_SIZE = 1000
    const rows: { tier: string; total_spent: number | null }[] = []
    for (let from = 0; ; from += PAGE_SIZE) {
      const { data, error } = await supabase
        .from('dim_customers')
        .select('tier, total_spent')
        .range(from, from + PAGE_SIZE - 1)

      if (error) return empty
      if (!data || data.length === 0) break
      rows.push(...data)
      if (data.length < PAGE_SIZE) break
    }

    const total_customers = rows.length
    const avg_total_spent =
      total_customers > 0
        ? rows.reduce((sum, r) => sum + Number(r.total_spent ?? 0), 0) / total_customers
        : 0

    return {
      total_customers,
      avg_total_spent,
      bronze_count: rows.filter((r) => r.tier === 'bronze').length,
      silver_count: rows.filter((r) => r.tier === 'silver').length,
      gold_count: rows.filter((r) => r.tier === 'gold').length,
    }
  } catch {
    return empty
  }
}
