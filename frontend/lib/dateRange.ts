export type RangePreset = '7d' | '30d' | '90d' | '6mo'

export const RANGE_PRESETS: { value: RangePreset; label: string }[] = [
  { value: '7d', label: '7D' },
  { value: '30d', label: '30D' },
  { value: '90d', label: '90D' },
  { value: '6mo', label: '6M' },
]

const DEFAULT_RANGE: RangePreset = '30d'

export function parseRangeParam(range: string | string[] | undefined): RangePreset {
  const value = Array.isArray(range) ? range[0] : range
  if (value === '7d' || value === '30d' || value === '90d' || value === '6mo') return value
  return DEFAULT_RANGE
}

export function rangeToDays(range: RangePreset): number {
  switch (range) {
    case '7d':
      return 7
    case '30d':
      return 30
    case '90d':
      return 90
    case '6mo':
      return 180
  }
}

export function rangeToMonths(range: RangePreset): number {
  switch (range) {
    case '7d':
    case '30d':
      return 1
    case '90d':
      return 3
    case '6mo':
      return 6
  }
}
