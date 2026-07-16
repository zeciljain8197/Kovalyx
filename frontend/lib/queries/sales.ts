import { createPublicClient } from '@/lib/supabase'

export interface DailySales {
  period_date: string
  total_gmv: number
  total_orders: number
  avg_order_value: number
  unique_customers: number
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

    const { data, error } = await supabase
      .from('mart_sales_summary')
      .select('period_date, total_gmv, total_orders, avg_order_value, unique_customers')
      .gte('period_date', since.toISOString().slice(0, 10))
      .order('period_date', { ascending: true })

    if (error || !data) return []

    const byDate = new Map<string, DailySales>()
    for (const row of data) {
      const existing = byDate.get(row.period_date)
      if (existing) {
        existing.total_gmv += Number(row.total_gmv ?? 0)
        existing.total_orders += Number(row.total_orders ?? 0)
        existing.unique_customers += Number(row.unique_customers ?? 0)
        existing.avg_order_value =
          (existing.avg_order_value + Number(row.avg_order_value ?? 0)) / 2
      } else {
        byDate.set(row.period_date, {
          period_date: row.period_date,
          total_gmv: Number(row.total_gmv ?? 0),
          total_orders: Number(row.total_orders ?? 0),
          avg_order_value: Number(row.avg_order_value ?? 0),
          unique_customers: Number(row.unique_customers ?? 0),
        })
      }
    }
    return Array.from(byDate.values()).sort((a, b) => a.period_date.localeCompare(b.period_date))
  } catch {
    return []
  }
}

export async function getSalesByCategory(days: number = 30): Promise<SalesByCategory[]> {
  try {
    const supabase = createPublicClient()
    const since = new Date()
    since.setDate(since.getDate() - days)

    const { data, error } = await supabase
      .from('mart_sales_summary')
      .select('category, total_gmv, total_orders, return_rate')
      .gte('period_date', since.toISOString().slice(0, 10))

    if (error || !data) return []

    const byCategory = new Map<string, { total_gmv: number; total_orders: number; returnRateSum: number; n: number }>()
    for (const row of data) {
      const key = row.category ?? 'Unknown'
      const existing = byCategory.get(key)
      if (existing) {
        existing.total_gmv += Number(row.total_gmv ?? 0)
        existing.total_orders += Number(row.total_orders ?? 0)
        existing.returnRateSum += Number(row.return_rate ?? 0)
        existing.n += 1
      } else {
        byCategory.set(key, {
          total_gmv: Number(row.total_gmv ?? 0),
          total_orders: Number(row.total_orders ?? 0),
          returnRateSum: Number(row.return_rate ?? 0),
          n: 1,
        })
      }
    }

    return Array.from(byCategory.entries())
      .map(([category, v]) => ({
        category,
        total_gmv: v.total_gmv,
        total_orders: v.total_orders,
        return_rate: v.n > 0 ? v.returnRateSum / v.n : 0,
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
            .select('total_gmv, total_orders, avg_order_value')
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
    const todayAov = salesRows.length > 0
      ? salesRows.reduce((sum, r) => sum + Number(r.avg_order_value ?? 0), 0) / salesRows.length
      : 0

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
