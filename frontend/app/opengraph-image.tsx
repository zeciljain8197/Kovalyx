import { ImageResponse } from 'next/og'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'

export const alt = 'Kovalyx — Real-time retail analytics pipeline'
export const size = { width: 1200, height: 630 }
export const contentType = 'image/png'

const TECH = ['Kafka', 'PySpark', 'Great Expectations', 'dbt', 'Airflow', 'Supabase', 'Next.js']

export default async function OgImage() {
  const logoBuffer = readFileSync(join(process.cwd(), 'public', 'logo_dark_theme.png'))
  const logoSrc = `data:image/png;base64,${logoBuffer.toString('base64')}`

  return new ImageResponse(
    (
      <div
        style={{
          width: '100%',
          height: '100%',
          display: 'flex',
          flexDirection: 'column',
          justifyContent: 'space-between',
          padding: '72px',
          backgroundColor: '#030712',
          backgroundImage: 'linear-gradient(135deg, #030712 0%, #0b1220 60%, #111827 100%)',
        }}
      >
        <div style={{ display: 'flex', flexDirection: 'column' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 20 }}>
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src={logoSrc} width={72} height={72} style={{ borderRadius: 14 }} alt="" />
            <div style={{ display: 'flex', fontSize: 88, fontWeight: 700, color: '#F0AA02' }}>
              Kovalyx
            </div>
          </div>
          <div
            style={{
              display: 'flex',
              marginTop: 32,
              fontSize: 34,
              lineHeight: 1.4,
              color: '#d1d5db',
              maxWidth: 920,
            }}
          >
            Real-time retail analytics, live and running — Kafka through PII-safe,
            governed Gold-layer marts.
          </div>
        </div>

        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 12 }}>
          {TECH.map((tech) => (
            <div
              key={tech}
              style={{
                display: 'flex',
                padding: '10px 22px',
                borderRadius: 999,
                border: '1px solid #374151',
                backgroundColor: 'rgba(255,255,255,0.03)',
                color: '#9ca3af',
                fontSize: 24,
              }}
            >
              {tech}
            </div>
          ))}
        </div>
      </div>
    ),
    { ...size }
  )
}
