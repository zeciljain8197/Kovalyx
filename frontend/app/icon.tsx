import { ImageResponse } from 'next/og'

export const size = { width: 64, height: 64 }
export const contentType = 'image/png'

export default function Icon() {
  return new ImageResponse(
    (
      <div
        style={{
          width: '100%',
          height: '100%',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          backgroundColor: '#030712',
          borderRadius: 12,
        }}
      >
        <div style={{ display: 'flex', fontSize: 40, fontWeight: 700, color: '#FFD700' }}>K</div>
      </div>
    ),
    { ...size }
  )
}
