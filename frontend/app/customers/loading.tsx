export default function Loading() {
  return (
    <div className="space-y-6">
      <div className="h-8 w-64 animate-pulse rounded bg-gray-800" />

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        {Array.from({ length: 3 }).map((_, i) => (
          <div key={i} className="h-20 animate-pulse rounded-lg border border-gray-800 bg-gray-900" />
        ))}
      </div>

      <div className="h-96 animate-pulse rounded-lg border border-gray-800 bg-gray-900" />
    </div>
  )
}
