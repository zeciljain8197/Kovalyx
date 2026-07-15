const TECHNOLOGIES = [
  'Kafka',
  'PySpark',
  'Presidio',
  'Great Expectations',
  'dbt',
  'Airflow',
  'Supabase',
  'Next.js',
  'Vercel',
]

export function TechStackStrip() {
  return (
    <div className="flex flex-wrap items-center gap-2">
      {TECHNOLOGIES.map((tech) => (
        <span
          key={tech}
          className="rounded-full border border-gray-200 bg-gray-100 px-2.5 py-1 text-xs font-medium text-gray-600 dark:border-gray-800 dark:bg-gray-900 dark:text-gray-400"
        >
          {tech}
        </span>
      ))}
    </div>
  )
}
