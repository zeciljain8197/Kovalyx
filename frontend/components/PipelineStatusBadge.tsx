import { getLastSuccessfulRun } from '@/lib/queries/pipeline'

export interface PipelineStatusBadgeProps {
  status?: 'success' | 'failed' | 'unknown'
  lastRun?: string
}

const DOT_CLASSES: Record<'success' | 'failed' | 'unknown', string> = {
  success: 'bg-green-500',
  failed: 'bg-red-500',
  unknown: 'bg-gray-500',
}

const LABELS: Record<'success' | 'failed' | 'unknown', string> = {
  success: 'Pipeline healthy',
  failed: 'Pipeline failed',
  unknown: 'No pipeline data',
}

export async function PipelineStatusBadge({ status, lastRun }: PipelineStatusBadgeProps) {
  let resolvedStatus: 'success' | 'failed' | 'unknown' = status ?? 'unknown'
  let resolvedLastRun = lastRun

  if (!status) {
    const run = await getLastSuccessfulRun()
    resolvedStatus = run ? 'success' : 'unknown'
    resolvedLastRun = run?.end_time ?? run?.start_time ?? undefined
  }

  return (
    <div className="inline-flex items-center gap-2 rounded-full border border-gray-200 bg-white px-3 py-1 text-xs text-gray-700 dark:border-gray-800 dark:bg-gray-900 dark:text-gray-300">
      <span className={`h-2 w-2 rounded-full ${DOT_CLASSES[resolvedStatus]}`} />
      <span>{LABELS[resolvedStatus]}</span>
      {resolvedLastRun && (
        <span className="text-gray-500">— {new Date(resolvedLastRun).toLocaleString()}</span>
      )}
    </div>
  )
}
