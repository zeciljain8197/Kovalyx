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
 * supabase-js, so tier counts are computed here after a single
 * lightweight fetch of just (tier, total_spent).
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
    const { data, error } = await supabase
      .from('dim_customers')
      .select('tier, total_spent')

    if (error || !data) return empty

    const total_customers = data.length
    const avg_total_spent =
      total_customers > 0
        ? data.reduce((sum, r) => sum + Number(r.total_spent ?? 0), 0) / total_customers
        : 0

    return {
      total_customers,
      avg_total_spent,
      bronze_count: data.filter((r) => r.tier === 'bronze').length,
      silver_count: data.filter((r) => r.tier === 'silver').length,
      gold_count: data.filter((r) => r.tier === 'gold').length,
    }
  } catch {
    return empty
  }
}
