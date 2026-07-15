import {
  Send,
  Waypoints,
  Database,
  ShieldCheck,
  CheckCircle2,
  Server,
  Layers,
  Cloud,
  LayoutDashboard,
  BarChart3,
  Workflow,
  KeyRound,
  ArrowRight,
  ArrowDown,
} from 'lucide-react'
import { Card } from '@/components/ui/Card'

interface Stage {
  icon: typeof Send
  label: string
  detail: string
}

const STAGES: Stage[] = [
  { icon: Send, label: 'Kafka Producer', detail: 'Faker-generated live events' },
  { icon: Waypoints, label: 'Kafka', detail: 'kovalyx.events topic' },
  { icon: Database, label: 'Bronze (MinIO)', detail: 'Raw landing zone' },
  { icon: ShieldCheck, label: 'PySpark + Presidio', detail: 'Silver transform, PII masking' },
  { icon: CheckCircle2, label: 'Great Expectations', detail: 'Quality gates' },
  { icon: Server, label: 'Postgres Loader', detail: 'Staging schema' },
  { icon: Layers, label: 'dbt', detail: 'Staging → marts' },
  { icon: Cloud, label: 'Supabase (Gold)', detail: 'Governed analytics marts' },
]

const OUTPUTS: Stage[] = [
  { icon: LayoutDashboard, label: 'Next.js Dashboard', detail: 'This site, on Vercel' },
  { icon: BarChart3, label: 'Streamlit', detail: 'Internal ops/audit monitor' },
]

function Connector() {
  return (
    <>
      <ArrowDown className="my-1 shrink-0 text-gray-300 dark:text-gray-700 lg:hidden" size={18} />
      <ArrowRight className="mx-1 hidden shrink-0 text-gray-300 dark:text-gray-700 lg:block" size={18} />
    </>
  )
}

function StageCard({ stage }: { stage: Stage }) {
  const Icon = stage.icon
  return (
    <Card className="flex w-full shrink-0 flex-col items-center gap-1 p-3 text-center lg:w-36">
      <Icon size={22} className="text-kovalyx-goldText dark:text-kovalyx-gold" />
      <p className="text-xs font-semibold text-gray-800 dark:text-gray-200">{stage.label}</p>
      <p className="text-[11px] leading-tight text-gray-500 dark:text-gray-500">{stage.detail}</p>
    </Card>
  )
}

export function ArchitectureDiagram() {
  return (
    <div className="space-y-4">
      <div className="flex flex-col items-stretch lg:flex-row lg:flex-wrap lg:items-center">
        {STAGES.map((stage, i) => (
          <div key={stage.label} className="flex flex-col items-center lg:flex-row">
            <StageCard stage={stage} />
            {i < STAGES.length - 1 && <Connector />}
          </div>
        ))}
      </div>

      <div className="flex flex-col items-center gap-1 lg:flex-row lg:justify-center">
        <ArrowDown className="text-gray-300 dark:text-gray-700" size={18} />
      </div>

      <div className="flex flex-col items-stretch justify-center gap-2 lg:flex-row">
        {OUTPUTS.map((stage) => (
          <StageCard key={stage.label} stage={stage} />
        ))}
      </div>

      <Card className="flex items-center justify-center gap-3 bg-gray-50 py-3 dark:bg-gray-900/50">
        <Workflow size={18} className="text-kovalyx-goldText dark:text-kovalyx-gold" />
        <p className="text-xs text-gray-600 dark:text-gray-400">
          <span className="font-semibold text-gray-800 dark:text-gray-200">Apache Airflow</span> orchestrates
          every stage above on a 2-hour schedule — producer through dbt.
        </p>
      </Card>

      <div className="flex items-center justify-center gap-2 text-xs text-gray-500 dark:text-gray-500">
        <KeyRound size={14} />
        <span>HashiCorp Vault issues short-lived credentials to the Silver transform, Loader, and dbt — nothing is hardcoded in source.</span>
      </div>
    </div>
  )
}
