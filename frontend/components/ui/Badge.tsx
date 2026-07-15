import { ReactNode } from 'react'
import { clsx } from 'clsx'

export type BadgeVariant = 'success' | 'danger' | 'warning' | 'info' | 'default'

export interface BadgeProps {
  variant?: BadgeVariant
  children: ReactNode
  className?: string
}

const VARIANT_CLASSES: Record<BadgeVariant, string> = {
  success: 'bg-green-100 text-green-800 border-green-300 dark:bg-green-900/50 dark:text-green-400 dark:border-green-800',
  danger: 'bg-red-100 text-red-800 border-red-300 dark:bg-red-900/50 dark:text-red-400 dark:border-red-800',
  warning: 'bg-yellow-100 text-yellow-800 border-yellow-300 dark:bg-yellow-900/50 dark:text-yellow-400 dark:border-yellow-800',
  info: 'bg-blue-100 text-blue-800 border-blue-300 dark:bg-blue-900/50 dark:text-blue-400 dark:border-blue-800',
  default: 'bg-gray-100 text-gray-700 border-gray-300 dark:bg-gray-800 dark:text-gray-300 dark:border-gray-700',
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
