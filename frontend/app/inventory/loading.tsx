export default function Loading() {
  return (
    <div className="space-y-6">
      <div className="h-8 w-56 animate-pulse rounded bg-gray-800" />

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="h-24 animate-pulse rounded-lg border border-gray-800 bg-gray-900" />
        ))}
      </div>

      <div className="overflow-hidden rounded-lg border border-gray-800">
        {Array.from({ length: 10 }).map((_, i) => (
          <div key={i} className="h-10 animate-pulse border-b border-gray-800 bg-gray-900 last:border-b-0" />
        ))}
      </div>
    </div>
  )
}
