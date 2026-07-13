import { Lock } from 'lucide-react'
import { getLastSuccessfulRun, getPiiAuditSummary, getRecentGeResults, getRecentPipelineRuns } from '@/lib/queries/pipeline'
import { KpiCard } from '@/components/KpiCard'
import { Card } from '@/components/ui/Card'
import { Badge } from '@/components/ui/Badge'
import { Table } from '@/components/ui/Table'

export const revalidate = 60

function formatDate(value: string | null): string {
  if (!value) return '—'
  return new Date(value).toLocaleString()
}

function formatDuration(start: string, end: string | null): string {
  if (!end) return '—'
  const seconds = (new Date(end).getTime() - new Date(start).getTime()) / 1000
  if (seconds < 60) return `${seconds.toFixed(0)}s`
  return `${(seconds / 60).toFixed(1)}m`
}

function statusBadgeVariant(status: string): 'success' | 'danger' | 'info' {
  if (status === 'success') return 'success'
  if (status === 'failed') return 'danger'
  return 'info'
}

export default async function PipelinePage() {
  const [lastRun, geResults, piiSummary, runHistory] = await Promise.all([
    getLastSuccessfulRun(),
    getRecentGeResults(20),
    getPiiAuditSummary(),
    getRecentPipelineRuns(50),
  ])

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-2">
        <h1 className="text-2xl font-bold text-white">Pipeline Health</h1>
        <Badge variant="info">
          <Lock size={10} className="mr-1 inline" /> Admin
        </Badge>
      </div>

      <Card>
        <h2 className="mb-3 text-sm font-semibold text-gray-400">Last Successful Run</h2>
        {lastRun ? (
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
            <div>
              <p className="text-xs text-gray-500">Run ID</p>
              <p className="truncate text-sm text-gray-200">{lastRun.run_id}</p>
            </div>
            <div>
              <p className="text-xs text-gray-500">Completed</p>
              <p className="text-sm text-gray-200">{formatDate(lastRun.end_time)}</p>
            </div>
            <div>
              <p className="text-xs text-gray-500">Records Processed</p>
              <p className="text-sm text-gray-200">{lastRun.records_processed ?? 0}</p>
            </div>
            <div>
              <p className="text-xs text-gray-500">PII Events Masked</p>
              <p className="text-sm text-gray-200">{lastRun.pii_events_masked ?? 0}</p>
            </div>
            <div>
              <p className="text-xs text-gray-500">GE Passed</p>
              <Badge variant={lastRun.ge_passed ? 'success' : 'danger'}>
                {lastRun.ge_passed ? 'Passed' : 'Failed'}
              </Badge>
            </div>
          </div>
        ) : (
          <p className="text-sm text-gray-500">No successful runs recorded yet.</p>
        )}
      </Card>

      <div>
        <h2 className="mb-3 text-lg font-semibold text-gray-200">Great Expectations Results</h2>
        <Table
          headers={['Checkpoint', 'Success', 'Evaluated', 'Successful', 'Failed', 'Run Time']}
          rows={geResults.map((r) => [
            r.checkpoint_name,
            <Badge key={r.result_id} variant={r.success ? 'success' : 'danger'}>
              {r.success ? 'Pass' : 'Fail'}
            </Badge>,
            String(r.evaluated_expectations),
            String(r.successful_expectations),
            String(r.failed_expectations),
            formatDate(r.run_time),
          ])}
          emptyMessage="No Great Expectations results recorded yet."
        />
      </div>

      <div>
        <h2 className="mb-3 text-lg font-semibold text-gray-200">PII Masking Summary</h2>
        <Table
          headers={['Field', 'Total Masked Events', 'Last Seen']}
          rows={piiSummary.map((p) => [p.field_name, String(p.count), formatDate(p.last_seen)])}
          emptyMessage="No PII masking events recorded yet."
        />
        <p className="mt-2 text-xs text-gray-500">
          Only metadata is logged. Original PII values are never stored.
        </p>
      </div>

      <div>
        <KpiCard title="Recent Runs Shown" value={runHistory.length} subtitle="Most recent first" />
        <div className="mt-3">
          <Table
            headers={['DAG', 'Task', 'Status', 'Start Time', 'Duration', 'Processed', 'Failed']}
            rows={runHistory.map((r) => [
              r.dag_id,
              r.task_id,
              <Badge key={`${r.run_id}-${r.task_id}`} variant={statusBadgeVariant(r.status)}>
                {r.status}
              </Badge>,
              formatDate(r.start_time),
              formatDuration(r.start_time, r.end_time),
              String(r.records_processed ?? 0),
              String(r.records_failed ?? 0),
            ])}
            emptyMessage="No pipeline runs recorded yet."
          />
        </div>
      </div>
    </div>
  )
}
