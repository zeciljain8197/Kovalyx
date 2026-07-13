import { ReactNode } from 'react'
import { clsx } from 'clsx'

export interface CardProps {
  children: ReactNode
  className?: string
}

export function Card({ children, className }: CardProps) {
  return (
    <div className={clsx('rounded-lg border border-gray-800 bg-gray-900 p-4', className)}>
      {children}
    </div>
  )
}
