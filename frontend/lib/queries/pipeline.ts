// SERVER-ONLY — uses the service role key via createAdminClient().
// Do not import this file in a 'use client' component.
// Only import it in Server Components or Route Handlers.
import { createAdminClient } from '@/lib/supabase'

export interface PipelineRun {
  run_id: string
  dag_id: string
  task_id: string
  triggered_by: string
  start_time: string
  end_time: string | null
  records_processed: number | null
  records_failed: number | null
  ge_passed: boolean | null
  pii_events_masked: number | null
  status: 'success' | 'failed' | 'running'
}

export interface GeResult {
  result_id: string
  run_id: string
  checkpoint_name: string
  suite_name: string
  success: boolean
  evaluated_expectations: number
  successful_expectations: number
  failed_expectations: number
  run_time: string
}

export interface PiiAuditEntry {
  record_id: string
  event_id: string
  field_name: string
  masking_action: string
  original_length: number | null
  pipeline_run_id: string
  masked_at: string
}

// audit.ge_validation_results' real columns (scripts/supabase_schema.sql,
// Session 1 + the Session 2 checkpoint_name migration) are id /
// pipeline_run_id / expectation_suite_name / unsuccessful_expectations /
// result_detail — not the result_id / run_id / suite_name /
// failed_expectations names this session's GeResult interface uses.
// Aliased in the .select() below so every caller works against the
// clean interface names without needing to know the underlying schema.
const GE_RESULT_SELECT =
  'result_id:id, run_id:pipeline_run_id, checkpoint_name, suite_name:expectation_suite_name, success, evaluated_expectations, successful_expectations, failed_expectations:unsuccessful_expectations, run_time'

export async function getRecentPipelineRuns(limit: number = 50): Promise<PipelineRun[]> {
  try {
    const supabase = createAdminClient()
    const { data, error } = await supabase
      .from('kovalyx_pipeline_audit_log')
      .select('run_id, dag_id, task_id, triggered_by, start_time, end_time, records_processed, records_failed, ge_passed, pii_events_masked, status')
      .order('start_time', { ascending: false })
      .limit(limit)

    if (error || !data) return []
    return data as PipelineRun[]
  } catch {
    return []
  }
}

export async function getLastSuccessfulRun(): Promise<PipelineRun | null> {
  try {
    const supabase = createAdminClient()
    const { data, error } = await supabase
      .from('kovalyx_pipeline_audit_log')
      .select('run_id, dag_id, task_id, triggered_by, start_time, end_time, records_processed, records_failed, ge_passed, pii_events_masked, status')
      .eq('dag_id', 'kovalyx_medallion_pipeline')
      .eq('status', 'success')
      .order('end_time', { ascending: false })
      .limit(1)

    if (error || !data || data.length === 0) return null
    return data[0] as PipelineRun
  } catch {
    return null
  }
}

export async function getGeResultsForRun(runId: string): Promise<GeResult[]> {
  try {
    const supabase = createAdminClient()
    const { data, error } = await supabase
      .from('ge_validation_results')
      .select(GE_RESULT_SELECT)
      .eq('pipeline_run_id', runId)
      .order('run_time', { ascending: true })

    if (error || !data) return []
    return data as unknown as GeResult[]
  } catch {
    return []
  }
}

export async function getRecentGeResults(limit: number = 20): Promise<GeResult[]> {
  try {
    const supabase = createAdminClient()
    const { data, error } = await supabase
      .from('ge_validation_results')
      .select(GE_RESULT_SELECT)
      .order('run_time', { ascending: false })
      .limit(limit)

    if (error || !data) return []
    return data as unknown as GeResult[]
  } catch {
    return []
  }
}

export async function getPiiAuditSummary(): Promise<{ field_name: string; count: number; last_seen: string }[]> {
  try {
    const supabase = createAdminClient()
    const { data, error } = await supabase
      .from('kovalyx_pii_audit_log')
      .select('field_name, masked_at')

    if (error || !data) return []

    const byField = new Map<string, { count: number; last_seen: string }>()
    for (const row of data) {
      const existing = byField.get(row.field_name)
      if (existing) {
        existing.count += 1
        if (row.masked_at > existing.last_seen) existing.last_seen = row.masked_at
      } else {
        byField.set(row.field_name, { count: 1, last_seen: row.masked_at })
      }
    }

    return Array.from(byField.entries())
      .map(([field_name, v]) => ({ field_name, count: v.count, last_seen: v.last_seen }))
      .sort((a, b) => b.count - a.count)
  } catch {
    return []
  }
}

export async function getRecentPiiEvents(limit: number = 100): Promise<PiiAuditEntry[]> {
  try {
    const supabase = createAdminClient()
    const { data, error } = await supabase
      .from('kovalyx_pii_audit_log')
      .select('record_id, event_id, field_name, masking_action, original_length, pipeline_run_id, masked_at')
      .order('masked_at', { ascending: false })
      .limit(limit)

    if (error || !data) return []
    return data as PiiAuditEntry[]
  } catch {
    return []
  }
}
