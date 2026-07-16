import Link from 'next/link'
import { ArrowRight, Github } from 'lucide-react'
import { ArchitectureDiagram } from '@/components/ArchitectureDiagram'
import { TechStackStrip } from '@/components/TechStackStrip'
import { Card } from '@/components/ui/Card'
import { InterviewNote } from '@/components/InterviewNote'

export const metadata = {
  title: 'About This Project',
  description:
    'What Kovalyx is, why it exists, and how the Kafka-to-Supabase medallion pipeline behind this dashboard actually works.',
}

const TECH_STACK_TABLE: { layer: string; technologies: string }[] = [
  { layer: 'Ingestion (Bronze)', technologies: 'Apache Kafka 3.7, Python, Faker, MinIO' },
  { layer: 'Transform (Silver)', technologies: 'PySpark 3.5, Microsoft Presidio, Great Expectations 0.18' },
  { layer: 'Gold', technologies: 'dbt-core 1.8, Supabase PostgreSQL, Kimball star schema' },
  { layer: 'Orchestration', technologies: 'Apache Airflow 2.9' },
  { layer: 'Security', technologies: 'HashiCorp Vault 1.15, SASL/PLAIN Kafka auth, Postgres RLS' },
  { layer: 'Observability', technologies: 'Prometheus, Grafana, Loki, Promtail' },
  { layer: 'Frontend', technologies: 'Next.js 14, Vercel, Tailwind CSS, Recharts' },
  { layer: 'Infrastructure', technologies: 'Docker Compose, Nginx, Vercel, Supabase, GitHub Actions' },
]

const QUESTIONS: { q: string; a: string }[] = [
  {
    q: 'Where did the data come from?',
    a: 'A Kafka producer generates realistic retail events (orders, returns, inventory movements) with Faker, streamed live into the kovalyx.events topic. A batch CSV seed set covers historical backfill. Both land in the same Bronze object-store layer.',
  },
  {
    q: 'How did you move it?',
    a: 'Kafka Consumer → MinIO Bronze → PySpark Silver transform → Postgres staging loader → dbt marts → Supabase Gold. Every hop is orchestrated by Airflow on a fixed schedule, not triggered ad hoc.',
  },
  {
    q: 'Where did you store it, and why?',
    a: "MinIO (S3-compatible) for cheap, schema-less Bronze landing; Postgres for structured Silver/staging; Supabase Postgres for Gold, because the dashboard needs a queryable relational store with row-level security, not a data lake.",
  },
  {
    q: 'How did you model it?',
    a: 'dbt staging models clean and type raw loader output; mart models apply a Kimball star schema (fact tables for orders/returns/inventory snapshots, dimension tables for products/customers/dates) so the dashboard queries are simple aggregations, not ad hoc joins.',
  },
  {
    q: 'How did you ensure quality?',
    a: 'Great Expectations checkpoints run against every Silver batch before it is allowed to reach Postgres staging — null checks, referential checks, and value-range checks. Failed checkpoints block the load; results are logged and visible on the Pipeline Health page.',
  },
  {
    q: 'How did you make this production-like on a single VM?',
    a: 'Every credential is issued by HashiCorp Vault via least-privilege AppRole policies — nothing is hardcoded. PII (names, emails, phone numbers) is masked by Presidio NER + deterministic hashing at the Silver layer, before it can ever reach an analyst or a dashboard. Docker network isolation keeps each layer from talking to services it has no reason to reach. The whole pipeline is designed to run self-hosted on a single small VM via one `docker compose up` — the dashboard you\'re looking at is deployed separately, for free, on Vercel + Supabase.',
  },
]

export default function AboutPage() {
  return (
    <div className="space-y-10">
      <div>
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white">About This Project</h1>
        <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
          What Kovalyx is, why it exists, and how the pipeline behind this dashboard actually works.
        </p>
      </div>

      <section className="space-y-3">
        <h2 className="text-lg font-semibold text-gray-800 dark:text-gray-200">The Problem</h2>
        <p className="max-w-3xl text-sm leading-relaxed text-gray-600 dark:text-gray-400">
          Independent retailers generate real transaction data every day — POS systems, inventory feeds,
          customer orders — but the tools that turn that data into decisions (Snowflake, Databricks, Tableau,
          a dedicated data team) are built and priced for companies two orders of magnitude bigger. Kovalyx
          exists to close that gap: a complete, real medallion-architecture pipeline — ingestion through
          governed, PII-safe analytics marts — that runs on a single small VM and costs nothing but the
          hosting bill.
        </p>
      </section>

      <section className="space-y-3">
        <h2 className="text-lg font-semibold text-gray-800 dark:text-gray-200">What Kovalyx Does</h2>
        <ul className="max-w-3xl space-y-2 text-sm leading-relaxed text-gray-600 dark:text-gray-400">
          <li>
            <span className="font-medium text-gray-800 dark:text-gray-200">Real-time + batch ingestion</span> —
            Kafka-streamed live events and batch CSV drops land in an object-store Bronze layer together.
          </li>
          <li>
            <span className="font-medium text-gray-800 dark:text-gray-200">PII protection by construction</span>{' '}
            — every customer-identifying field is masked (Presidio NER + deterministic hashing) before Silver
            output ever exists, not as an afterthought at the reporting layer.
          </li>
          <li>
            <span className="font-medium text-gray-800 dark:text-gray-200">Data quality gates</span> — Great
            Expectations checkpoints block bad Silver output from ever reaching Gold.
          </li>
          <li>
            <span className="font-medium text-gray-800 dark:text-gray-200">One-command self-hosting</span> —
            the entire stack (Kafka, Spark, dbt, Airflow, Vault, Postgres, observability) runs from a single{' '}
            <code className="rounded bg-gray-100 px-1 py-0.5 text-xs dark:bg-gray-800">docker compose up</code>.
          </li>
          <li>
            <span className="font-medium text-gray-800 dark:text-gray-200">A live KPI dashboard</span> — GMV,
            cohort retention, and inventory alerts, queried directly from the governed Gold marts — this site.
          </li>
        </ul>
      </section>

      <section className="space-y-3">
        <h2 className="text-lg font-semibold text-gray-800 dark:text-gray-200">Architecture</h2>
        <ArchitectureDiagram />
        <InterviewNote>
          the Bronze/Silver/Gold split isn&apos;t just naming — each layer has a distinct contract (raw and
          replayable, cleaned and PII-safe, modeled and query-ready), and every arrow above is an Airflow task,
          not a manual step.
        </InterviewNote>
      </section>

      <section className="space-y-3">
        <h2 className="text-lg font-semibold text-gray-800 dark:text-gray-200">Tech Stack</h2>
        <TechStackStrip />
        <div className="mt-3 overflow-x-auto rounded-lg border border-gray-200 dark:border-gray-800">
          <table className="min-w-full divide-y divide-gray-200 text-sm dark:divide-gray-800">
            <tbody className="divide-y divide-gray-200 bg-white dark:divide-gray-800 dark:bg-gray-950">
              {TECH_STACK_TABLE.map((row) => (
                <tr key={row.layer}>
                  <td className="whitespace-nowrap px-4 py-2 font-medium text-gray-800 dark:text-gray-200">
                    {row.layer}
                  </td>
                  <td className="px-4 py-2 text-gray-500 dark:text-gray-400">{row.technologies}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="space-y-3">
        <h2 className="text-lg font-semibold text-gray-800 dark:text-gray-200">Security Design</h2>
        <ul className="max-w-3xl list-disc space-y-1.5 pl-5 text-sm leading-relaxed text-gray-600 dark:text-gray-400">
          <li>Every credential lives in HashiCorp Vault behind least-privilege AppRole policies — nothing is hardcoded in source.</li>
          <li>PII is masked at the Silver layer (Presidio + deterministic hashing) before it ever reaches Gold.</li>
          <li>Supabase Row Level Security scopes every Gold-layer role to exactly what it needs.</li>
          <li>Docker network isolation keeps Bronze/Silver/Gold services from talking to each other except where the pipeline actually requires it.</li>
        </ul>
      </section>

      <section className="space-y-3">
        <h2 className="text-lg font-semibold text-gray-800 dark:text-gray-200">Design Q&amp;A</h2>
        <div className="max-w-3xl space-y-2">
          {QUESTIONS.map((item) => (
            <details
              key={item.q}
              className="group rounded-lg border border-gray-200 bg-white p-3 dark:border-gray-800 dark:bg-gray-900"
            >
              <summary className="cursor-pointer text-sm font-medium text-gray-800 marker:text-kovalyx-goldText dark:text-gray-200 dark:marker:text-kovalyx-gold">
                {item.q}
              </summary>
              <p className="mt-2 text-sm leading-relaxed text-gray-600 dark:text-gray-400">{item.a}</p>
            </details>
          ))}
        </div>
      </section>

      <div className="flex flex-wrap gap-3 pt-2">
        <Link
          href="/pipeline"
          className="inline-flex items-center gap-2 rounded-md bg-kovalyx-gold px-4 py-2 text-sm font-medium text-gray-950 hover:opacity-90"
        >
          See it running <ArrowRight size={14} />
        </Link>
        <a
          href="https://github.com/zeciljain8197/Kovalyx"
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-2 rounded-md border border-gray-300 px-4 py-2 text-sm font-medium text-gray-700 hover:border-kovalyx-goldText hover:text-kovalyx-goldText dark:border-gray-700 dark:text-gray-300 dark:hover:border-kovalyx-gold dark:hover:text-kovalyx-gold"
        >
          <Github size={14} /> View source on GitHub
        </a>
      </div>
    </div>
  )
}
