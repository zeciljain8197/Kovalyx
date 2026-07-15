import { ReactNode } from 'react'
import { clsx } from 'clsx'

export interface CardProps {
  children: ReactNode
  className?: string
}

export function Card({ children, className }: CardProps) {
  return (
    <div
      className={clsx(
        'rounded-lg border border-gray-200 bg-white p-4 dark:border-gray-800 dark:bg-gray-900',
        className
      )}
    >
      {children}
    </div>
  )
}
