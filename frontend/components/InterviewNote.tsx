import { ReactNode } from 'react'
import { Lightbulb } from 'lucide-react'

export interface InterviewNoteProps {
  children: ReactNode
}

export function InterviewNote({ children }: InterviewNoteProps) {
  return (
    <div className="flex gap-2 rounded-md border border-dashed border-kovalyx-goldText/40 bg-kovalyx-goldText/5 p-3 text-xs text-gray-600 dark:border-kovalyx-gold/40 dark:bg-kovalyx-gold/5 dark:text-gray-400">
      <Lightbulb size={14} className="mt-0.5 shrink-0 text-kovalyx-goldText dark:text-kovalyx-gold" />
      <p>
        <span className="font-semibold text-gray-800 dark:text-gray-200">Ask me about this: </span>
        {children}
      </p>
    </div>
  )
}
