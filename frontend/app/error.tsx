'use client'

import { useEffect } from 'react'
import Link from 'next/link'
import { AlertTriangle } from 'lucide-react'

export default function Error({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  useEffect(() => {
    // eslint-disable-next-line no-console
    console.error(error)
  }, [error])

  return (
    <div className="flex h-full flex-col items-center justify-center gap-4 text-center">
      <AlertTriangle className="h-12 w-12 text-red-500" />
      <h1 className="text-xl font-bold text-white">Something went wrong</h1>
      {process.env.NODE_ENV === 'development' && (
        <p className="max-w-md text-sm text-gray-500">{error.message}</p>
      )}
      <div className="flex gap-3">
        <button
          type="button"
          onClick={reset}
          className="rounded-md bg-kovalyx-gold px-4 py-2 text-sm font-medium text-gray-950 hover:opacity-90"
        >
          Try again
        </button>
        <Link
          href="/pipeline"
          className="rounded-md border border-gray-700 px-4 py-2 text-sm font-medium text-gray-300 hover:border-kovalyx-gold hover:text-kovalyx-gold"
        >
          Check pipeline status
        </Link>
      </div>
    </div>
  )
}
