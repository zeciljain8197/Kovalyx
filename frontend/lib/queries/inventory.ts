import { createPublicClient } from '@/lib/supabase'

export interface InventoryAlert {
  product_id: string
  product_name: string
  category: string
  subcategory: string
  current_stock_level: number
  reorder_threshold: number
  days_of_stock_remaining: number | null
  alert_level: 'red' | 'yellow' | 'green'
  snapshot_date: string
}

export interface InventoryStats {
  total_skus: number
  red_alerts: number
  yellow_alerts: number
  green_skus: number
}

const ALERT_SORT_ORDER: Record<string, number> = { red: 1, yellow: 2, green: 3 }

export async function getInventoryAlerts(
  alertLevel?: 'red' | 'yellow' | 'green',
  category?: string,
  search?: string
): Promise<InventoryAlert[]> {
  try {
    const supabase = createPublicClient()
    let query = supabase
      .from('mart_inventory_alerts')
      .select(
        'product_id, product_name, category, subcategory, current_stock_level, reorder_threshold, days_of_stock_remaining, alert_level, snapshot_date'
      )

    if (alertLevel) query = query.eq('alert_level', alertLevel)
    if (category) query = query.eq('category', category)
    if (search) query = query.ilike('product_name', `%${search}%`)

    const { data, error } = await query
    if (error || !data) return []

    // CASE-based ordering (red -> yellow -> green, then days ascending
    // with nulls last) isn't expressible through PostgREST's .order(),
    // so it's applied here after the filtered fetch.
    return (data as InventoryAlert[]).sort((a, b) => {
      const levelDiff = (ALERT_SORT_ORDER[a.alert_level] ?? 4) - (ALERT_SORT_ORDER[b.alert_level] ?? 4)
      if (levelDiff !== 0) return levelDiff
      if (a.days_of_stock_remaining === null) return 1
      if (b.days_of_stock_remaining === null) return -1
      return a.days_of_stock_remaining - b.days_of_stock_remaining
    })
  } catch {
    return []
  }
}

export async function getInventoryStats(): Promise<InventoryStats> {
  const empty: InventoryStats = { total_skus: 0, red_alerts: 0, yellow_alerts: 0, green_skus: 0 }
  try {
    const supabase = createPublicClient()
    const { data, error } = await supabase.from('mart_inventory_alerts').select('alert_level')
    if (error || !data) return empty

    return {
      total_skus: data.length,
      red_alerts: data.filter((r) => r.alert_level === 'red').length,
      yellow_alerts: data.filter((r) => r.alert_level === 'yellow').length,
      green_skus: data.filter((r) => r.alert_level === 'green').length,
    }
  } catch {
    return empty
  }
}
