import Link from 'next/link'
import { Compass } from 'lucide-react'

export default function NotFound() {
  return (
    <div className="flex h-full flex-col items-center justify-center gap-4 text-center">
      <Compass className="h-12 w-12 text-kovalyx-blueText dark:text-kovalyx-blue" />
      <h1 className="text-xl font-bold text-gray-900 dark:text-white">Page not found</h1>
      <p className="max-w-md text-sm text-gray-500 dark:text-gray-400">
        This page doesn&apos;t exist. Head back to the dashboard to see the pipeline in action.
      </p>
      <Link
        href="/"
        className="rounded-md bg-kovalyx-blue px-4 py-2 text-sm font-medium text-white hover:opacity-90"
      >
        Back to dashboard
      </Link>
    </div>
  )
}
