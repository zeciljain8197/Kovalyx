import { createPublicClient } from '@/lib/supabase'

export interface ReturnTrend {
  period_date: string
  year: number
  month: number
  total_orders: number
  returned_orders: number
  return_rate: number
}

export interface ReturnsByCategory {
  category: string
  total_orders: number
  returned_orders: number
  return_rate: number
}

export interface TopReturnedProduct {
  product_name: string
  category: string
  return_rate: number
  returned_orders: number
  // Not in the original deliverable spec for this interface, but the
  // Returns Analysis page's "Top Returned Products" table needs a
  // month-over-month indicator, and mart_return_rates already carries
  // this column at the same (period_date, product_id) row grain this
  // query reads — pulling it in here is simpler and more correct than
  // a second round-trip.
  return_rate_change: number | null
}

/**
 * mart_return_rates is grained at (period_date, product_id), so
 * collapsing to one row per period is a GROUP BY — done here in JS for
 * the same reason as lib/queries/sales.ts (no general GROUP BY through
 * supabase-js's query builder).
 */
export async function getReturnTrends(months: number = 6): Promise<ReturnTrend[]> {
  try {
    const supabase = createPublicClient()
    const since = new Date()
    since.setMonth(since.getMonth() - months)

    // Paginated — same PostgREST 1000-row default cap already fixed
    // elsewhere (see customers.ts's getCustomerTierSummary()).
    const PAGE_SIZE = 1000
    const data: { period_date: string; year: number; month: number; total_orders: number; returned_orders: number }[] = []
    for (let from = 0; ; from += PAGE_SIZE) {
      const { data: page, error } = await supabase
        .from('mart_return_rates')
        .select('period_date, year, month, total_orders, returned_orders')
        .gte('period_date', since.toISOString().slice(0, 10))
        .order('period_date', { ascending: true })
        .range(from, from + PAGE_SIZE - 1)

      if (error) return []
      if (!page || page.length === 0) break
      data.push(...page)
      if (page.length < PAGE_SIZE) break
    }

    // return_rate is derived from summed returned_orders/total_orders (a
    // true weighted rate) — averaging each product's own return_rate
    // directly weighted a 1-order product the same as a 100-order one,
    // and disagreed with the "Total Returned Orders" KPI shown next to it.
    const byPeriod = new Map<string, { year: number; month: number; total_orders: number; returned_orders: number }>()
    for (const row of data) {
      const existing = byPeriod.get(row.period_date)
      if (existing) {
        existing.total_orders += Number(row.total_orders ?? 0)
        existing.returned_orders += Number(row.returned_orders ?? 0)
      } else {
        byPeriod.set(row.period_date, {
          year: row.year,
          month: row.month,
          total_orders: Number(row.total_orders ?? 0),
          returned_orders: Number(row.returned_orders ?? 0),
        })
      }
    }

    return Array.from(byPeriod.entries())
      .map(([period_date, v]) => ({
        period_date,
        year: v.year,
        month: v.month,
        total_orders: v.total_orders,
        returned_orders: v.returned_orders,
        return_rate: v.total_orders > 0 ? v.returned_orders / v.total_orders : 0,
      }))
      .sort((a, b) => a.period_date.localeCompare(b.period_date))
  } catch {
    return []
  }
}

export async function getReturnsByCategory(days: number = 90): Promise<ReturnsByCategory[]> {
  try {
    const supabase = createPublicClient()
    const since = new Date()
    since.setDate(since.getDate() - days)

    // Paginated — see getReturnTrends() above for why.
    const PAGE_SIZE = 1000
    const data: { category: string | null; total_orders: number; returned_orders: number }[] = []
    for (let from = 0; ; from += PAGE_SIZE) {
      const { data: page, error } = await supabase
        .from('mart_return_rates')
        .select('category, total_orders, returned_orders')
        .gte('period_date', since.toISOString().slice(0, 10))
        .range(from, from + PAGE_SIZE - 1)

      if (error) return []
      if (!page || page.length === 0) break
      data.push(...page)
      if (page.length < PAGE_SIZE) break
    }

    // Weighted rate (returned_orders/total_orders), not an average of
    // per-product rates — same fix as getReturnTrends() above.
    const byCategory = new Map<string, { total_orders: number; returned_orders: number }>()
    for (const row of data) {
      const key = row.category ?? 'Unknown'
      const existing = byCategory.get(key)
      if (existing) {
        existing.total_orders += Number(row.total_orders ?? 0)
        existing.returned_orders += Number(row.returned_orders ?? 0)
      } else {
        byCategory.set(key, {
          total_orders: Number(row.total_orders ?? 0),
          returned_orders: Number(row.returned_orders ?? 0),
        })
      }
    }

    return Array.from(byCategory.entries())
      .map(([category, v]) => ({
        category,
        total_orders: v.total_orders,
        returned_orders: v.returned_orders,
        return_rate: v.total_orders > 0 ? v.returned_orders / v.total_orders : 0,
      }))
      .sort((a, b) => b.return_rate - a.return_rate)
  } catch {
    return []
  }
}

export async function getTopReturnedProducts(limit: number = 10): Promise<TopReturnedProduct[]> {
  try {
    const supabase = createPublicClient()

    const { data: latest, error: latestError } = await supabase
      .from('mart_return_rates')
      .select('period_date')
      .order('period_date', { ascending: false })
      .limit(1)

    if (latestError || !latest || latest.length === 0) return []
    const mostRecentPeriod = latest[0].period_date

    const { data, error } = await supabase
      .from('mart_return_rates')
      .select('product_name, category, return_rate, returned_orders, return_rate_change')
      .eq('period_date', mostRecentPeriod)
      .order('return_rate', { ascending: false })
      .limit(limit)

    if (error || !data) return []
    return data as TopReturnedProduct[]
  } catch {
    return []
  }
}
