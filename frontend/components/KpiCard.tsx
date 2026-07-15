import { ReactNode } from 'react'
import { clsx } from 'clsx'
import { ArrowDown, ArrowUp } from 'lucide-react'
import { Card } from '@/components/ui/Card'

export type KpiCardVariant = 'default' | 'warning' | 'danger' | 'success'

export interface KpiCardProps {
  title: string
  value: string | number
  subtitle?: string
  trend?: { value: number; label: string }
  variant?: KpiCardVariant
}

const VARIANT_VALUE_CLASSES: Record<KpiCardVariant, string> = {
  default: 'text-gray-900 dark:text-white',
  warning: 'text-yellow-600 dark:text-yellow-400',
  danger: 'text-red-600 dark:text-red-400',
  success: 'text-green-600 dark:text-green-400',
}

const VARIANT_BORDER_CLASSES: Record<KpiCardVariant, string> = {
  default: '',
  warning: 'border-l-4 border-l-yellow-500',
  danger: 'border-l-4 border-l-red-500',
  success: 'border-l-4 border-l-green-500',
}

export function KpiCard({ title, value, subtitle, trend, variant = 'default' }: KpiCardProps): ReactNode {
  return (
    <Card className={clsx(VARIANT_BORDER_CLASSES[variant])}>
      <p className="text-sm text-gray-500 dark:text-gray-400">{title}</p>
      <p className={clsx('mt-1 text-2xl font-bold', VARIANT_VALUE_CLASSES[variant])}>{value}</p>
      {subtitle && <p className="mt-1 text-xs text-gray-500 dark:text-gray-500">{subtitle}</p>}
      {trend && (
        <div
          className={clsx(
            'mt-2 flex items-center gap-1 text-xs font-medium',
            trend.value >= 0 ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'
          )}
        >
          {trend.value >= 0 ? <ArrowUp size={12} /> : <ArrowDown size={12} />}
          <span>{Math.abs(trend.value)}%</span>
          <span className="text-gray-500">{trend.label}</span>
        </div>
      )}
    </Card>
  )
}
