import { ImageResponse } from 'next/og'

export const alt = 'Kovalyx — Real-time retail analytics pipeline'
export const size = { width: 1200, height: 630 }
export const contentType = 'image/png'

const TECH = ['Kafka', 'PySpark', 'Great Expectations', 'dbt', 'Airflow', 'Supabase', 'Next.js']

export default async function OgImage() {
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
          <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
            <div
              style={{
                width: 14,
                height: 56,
                borderRadius: 4,
                backgroundColor: '#FFD700',
              }}
            />
            <div style={{ display: 'flex', fontSize: 88, fontWeight: 700, color: '#FFD700' }}>
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
            Self-hosted, real-time retail analytics pipeline — Kafka through PII-safe,
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
