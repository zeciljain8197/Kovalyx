import { createPublicClient } from '@/lib/supabase'

export interface DailySales {
  period_date: string
  total_gmv: number
  total_orders: number
  avg_order_value: number
}

export interface SalesByCategory {
  category: string
  total_gmv: number
  total_orders: number
  return_rate: number
}

export interface HomeKpis {
  todayGmv: number
  todayOrders: number
  todayAov: number
  activeSkuAlerts: number
  lastUpdated: string
}

/**
 * mart_sales_summary's grain is (period_date, category, subcategory), so
 * collapsing to one row per day is a GROUP BY period_date. supabase-js's
 * query builder has no general GROUP BY support (PostgREST aggregate
 * embedding would need a dedicated view/RPC, out of scope for this
 * session — see scripts/supabase_schema.sql's Session 5 migration
 * note), so rows are fetched filtered and aggregated here in JS.
 */
export async function getDailySalesTrend(days: number = 30): Promise<DailySales[]> {
  try {
    const supabase = createPublicClient()
    const since = new Date()
    since.setDate(since.getDate() - days)

    // Paginated for the same reason as getCustomerTierSummary() in
    // customers.ts: mart_sales_summary is already at 600+ rows, and the
    // 6-month range preset alone requests more rows than PostgREST's
    // default 1000-row cap would silently return.
    const PAGE_SIZE = 1000
    const data: { period_date: string; total_gmv: number; total_orders: number }[] = []
    for (let from = 0; ; from += PAGE_SIZE) {
      const { data: page, error } = await supabase
        .from('mart_sales_summary')
        .select('period_date, total_gmv, total_orders')
        .gte('period_date', since.toISOString().slice(0, 10))
        .order('period_date', { ascending: true })
        .range(from, from + PAGE_SIZE - 1)

      if (error) return []
      if (!page || page.length === 0) break
      data.push(...page)
      if (page.length < PAGE_SIZE) break
    }

    // avg_order_value is derived from the summed totals (a true weighted
    // average), not averaged across category rows — averaging per-category
    // avg_order_value values directly ignores each category's order volume
    // and produces a number nothing else on the page agrees with.
    const byDate = new Map<string, { total_gmv: number; total_orders: number }>()
    for (const row of data) {
      const existing = byDate.get(row.period_date)
      if (existing) {
        existing.total_gmv += Number(row.total_gmv ?? 0)
        existing.total_orders += Number(row.total_orders ?? 0)
      } else {
        byDate.set(row.period_date, {
          total_gmv: Number(row.total_gmv ?? 0),
          total_orders: Number(row.total_orders ?? 0),
        })
      }
    }
    return Array.from(byDate.entries())
      .map(([period_date, v]) => ({
        period_date,
        total_gmv: v.total_gmv,
        total_orders: v.total_orders,
        avg_order_value: v.total_orders > 0 ? v.total_gmv / v.total_orders : 0,
      }))
      .sort((a, b) => a.period_date.localeCompare(b.period_date))
  } catch {
    return []
  }
}

export async function getSalesByCategory(days: number = 30): Promise<SalesByCategory[]> {
  try {
    const supabase = createPublicClient()
    const since = new Date()
    since.setDate(since.getDate() - days)

    // Paginated — see getDailySalesTrend() above for why.
    const PAGE_SIZE = 1000
    const data: { category: string | null; total_gmv: number; total_orders: number; returned_orders: number }[] = []
    for (let from = 0; ; from += PAGE_SIZE) {
      const { data: page, error } = await supabase
        .from('mart_sales_summary')
        .select('category, total_gmv, total_orders, returned_orders')
        .gte('period_date', since.toISOString().slice(0, 10))
        .range(from, from + PAGE_SIZE - 1)

      if (error) return []
      if (!page || page.length === 0) break
      data.push(...page)
      if (page.length < PAGE_SIZE) break
    }

    // return_rate is derived from summed returned_orders/total_orders (a
    // true weighted rate), not averaged across daily rows — averaging the
    // per-row return_rate directly weights a 2-order day the same as a
    // 200-order day.
    const byCategory = new Map<string, { total_gmv: number; total_orders: number; returned_orders: number }>()
    for (const row of data) {
      const key = row.category ?? 'Unknown'
      const existing = byCategory.get(key)
      if (existing) {
        existing.total_gmv += Number(row.total_gmv ?? 0)
        existing.total_orders += Number(row.total_orders ?? 0)
        existing.returned_orders += Number(row.returned_orders ?? 0)
      } else {
        byCategory.set(key, {
          total_gmv: Number(row.total_gmv ?? 0),
          total_orders: Number(row.total_orders ?? 0),
          returned_orders: Number(row.returned_orders ?? 0),
        })
      }
    }

    return Array.from(byCategory.entries())
      .map(([category, v]) => ({
        category,
        total_gmv: v.total_gmv,
        total_orders: v.total_orders,
        return_rate: v.total_orders > 0 ? v.returned_orders / v.total_orders : 0,
      }))
      .sort((a, b) => b.total_gmv - a.total_gmv)
      .slice(0, 10)
  } catch {
    return []
  }
}

export async function getHomeKpis(): Promise<HomeKpis> {
  const zero: HomeKpis = {
    todayGmv: 0,
    todayOrders: 0,
    todayAov: 0,
    activeSkuAlerts: 0,
    lastUpdated: new Date().toISOString(),
  }
  try {
    const supabase = createPublicClient()

    // "Today" means the most recent day each mart actually has data for,
    // not the literal calendar date: the pipeline runs periodically
    // rather than continuously, and the two marts don't necessarily
    // share a latest date (e.g. sales summary stops at the last order
    // date, inventory snapshots at the last stock-check date) — filtering
    // on real "today" would show a misleading empty state between runs
    // even when real, recent data exists.
    const [latestSalesDate, latestSnapshotDate] = await Promise.all([
      supabase
        .from('mart_sales_summary')
        .select('period_date')
        .order('period_date', { ascending: false })
        .limit(1)
        .maybeSingle()
        .then((r) => r.data?.period_date ?? null),
      supabase
        .from('mart_inventory_alerts')
        .select('snapshot_date')
        .order('snapshot_date', { ascending: false })
        .limit(1)
        .maybeSingle()
        .then((r) => r.data?.snapshot_date ?? null),
    ])

    const [salesRes, alertsRes] = await Promise.all([
      latestSalesDate
        ? supabase
            .from('mart_sales_summary')
            .select('total_gmv, total_orders')
            .eq('period_date', latestSalesDate)
        : Promise.resolve({ data: [] }),
      latestSnapshotDate
        ? supabase
            .from('mart_inventory_alerts')
            .select('alert_level')
            .eq('snapshot_date', latestSnapshotDate)
            .in('alert_level', ['red', 'yellow'])
        : Promise.resolve({ data: [] }),
    ])

    const salesRows = salesRes.data ?? []
    const todayGmv = salesRows.reduce((sum, r) => sum + Number(r.total_gmv ?? 0), 0)
    const todayOrders = salesRows.reduce((sum, r) => sum + Number(r.total_orders ?? 0), 0)
    // True weighted AOV (matches the "Today's GMV ÷ today's orders"
    // subtitle on the homepage) — averaging each category row's own
    // avg_order_value ignored order volume per category and previously
    // produced a number that didn't match its own subtitle's claim.
    const todayAov = todayOrders > 0 ? todayGmv / todayOrders : 0

    return {
      todayGmv,
      todayOrders,
      todayAov,
      activeSkuAlerts: (alertsRes.data ?? []).length,
      lastUpdated: new Date().toISOString(),
    }
  } catch {
    return zero
  }
}
