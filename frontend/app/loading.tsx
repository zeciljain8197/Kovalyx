export default function Loading() {
  return (
    <div className="space-y-6">
      <div className="h-8 w-48 animate-pulse rounded bg-gray-200 dark:bg-gray-800" />

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="h-24 animate-pulse rounded-lg border border-gray-200 bg-gray-100 dark:border-gray-800 dark:bg-gray-900" />
        ))}
      </div>

      <div className="h-72 animate-pulse rounded-lg border border-gray-200 bg-gray-100 dark:border-gray-800 dark:bg-gray-900" />

      <div className="h-48 animate-pulse rounded-lg border border-gray-200 bg-gray-100 dark:border-gray-800 dark:bg-gray-900" />
    </div>
  )
}
