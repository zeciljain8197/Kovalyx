import { ReactNode } from 'react'
import { clsx } from 'clsx'

export type BadgeVariant = 'success' | 'danger' | 'warning' | 'info' | 'default'

export interface BadgeProps {
  variant?: BadgeVariant
  children: ReactNode
  className?: string
}

const VARIANT_CLASSES: Record<BadgeVariant, string> = {
  success: 'bg-green-900/50 text-green-400 border-green-800',
  danger: 'bg-red-900/50 text-red-400 border-red-800',
  warning: 'bg-yellow-900/50 text-yellow-400 border-yellow-800',
  info: 'bg-blue-900/50 text-blue-400 border-blue-800',
  default: 'bg-gray-800 text-gray-300 border-gray-700',
}

export function Badge({ variant = 'default', children, className }: BadgeProps) {
  return (
    <span
      className={clsx(
        'inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-medium',
        VARIANT_CLASSES[variant],
        className
      )}
    >
      {children}
    </span>
  )
}
