import { getLastSuccessfulRun, getPiiAuditSummary, getRecentGeResults, getRecentPipelineRuns } from '@/lib/queries/pipeline'
import { KpiCard } from '@/components/KpiCard'
import { Card } from '@/components/ui/Card'
import { Badge } from '@/components/ui/Badge'
import { Table } from '@/components/ui/Table'
import { InterviewNote } from '@/components/InterviewNote'

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

  const gePassedCount = geResults.filter((r) => r.success).length
  const piiFieldsMasked = piiSummary.length
  const piiEventsTotal = piiSummary.reduce((sum, p) => sum + p.count, 0)

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Pipeline Health</h1>
        <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
          Live run history, data-quality checks, and PII audit trail — proof this is a real, running system, not a mockup.
        </p>
      </div>

      <div>
        <h2 className="mb-3 text-sm font-semibold text-gray-500 dark:text-gray-400">Last Successful Run</h2>
        {lastRun ? (
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
            <KpiCard title="Run ID" value={lastRun.run_id.slice(0, 8)} subtitle="Airflow DAG run identifier" />
            <KpiCard title="Completed" value={formatDate(lastRun.end_time)} subtitle="Most recent successful run" />
            <KpiCard
              title="Records Processed"
              value={lastRun.records_processed ?? 0}
              subtitle="Rows loaded to the Gold layer"
            />
            <KpiCard
              title="GE Passed"
              value={lastRun.ge_passed ? 'Passed' : 'Failed'}
              subtitle="Great Expectations checkpoint status"
              variant={lastRun.ge_passed ? 'success' : 'danger'}
            />
          </div>
        ) : (
          <Card>
            <p className="text-sm text-gray-500">No successful runs recorded yet.</p>
          </Card>
        )}
      </div>

      <div>
        <h2 className="mb-3 text-lg font-semibold text-gray-800 dark:text-gray-200">Great Expectations Results</h2>
        <div className="mb-3 grid grid-cols-1 gap-4 sm:grid-cols-2">
          <KpiCard
            title="Checkpoints Passing"
            value={`${gePassedCount}/${geResults.length}`}
            subtitle="Data-quality checks run by Great Expectations after each Silver-layer transform"
            variant={gePassedCount === geResults.length && geResults.length > 0 ? 'success' : 'warning'}
          />
        </div>
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
        <div className="mt-3">
          <InterviewNote>
            these checkpoints run against every Silver-layer batch before it&apos;s allowed into Postgres
            staging — a failed checkpoint blocks the load rather than letting bad data reach Gold silently.
          </InterviewNote>
        </div>
      </div>

      <div>
        <h2 className="mb-3 text-lg font-semibold text-gray-800 dark:text-gray-200">PII Masking Summary</h2>
        <div className="mb-3 grid grid-cols-1 gap-4 sm:grid-cols-2">
          <KpiCard
            title="PII Fields Actively Masked"
            value={piiFieldsMasked}
            subtitle="Distinct fields redacted by the PySpark + Presidio Silver-layer transform"
          />
          <KpiCard
            title="Total Masking Events"
            value={piiEventsTotal}
            subtitle="Only metadata is logged — original PII values are never stored"
          />
        </div>
        <Table
          headers={['Field', 'Total Masked Events', 'Last Seen']}
          rows={piiSummary.map((p) => [p.field_name, String(p.count), formatDate(p.last_seen)])}
          emptyMessage="No PII masking events recorded yet."
        />
        <div className="mt-3">
          <InterviewNote>
            PII is masked (Presidio NER + deterministic hashing) at the Silver layer, before it can ever reach
            Gold or a dashboard. Only masking metadata is logged here — the original values are never stored,
            anywhere.
          </InterviewNote>
        </div>
      </div>

      <div>
        <h2 className="mb-3 text-lg font-semibold text-gray-800 dark:text-gray-200">Recent Runs</h2>
        <KpiCard title="Recent Runs Shown" value={runHistory.length} subtitle="Most recent first, across all DAG tasks" />
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
