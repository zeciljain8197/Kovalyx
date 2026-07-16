import type { Config } from 'tailwindcss'

const config: Config = {
  darkMode: 'class',
  content: [
    './pages/**/*.{ts,tsx}',
    './components/**/*.{ts,tsx}',
    './app/**/*.{ts,tsx}',
  ],
  theme: {
    extend: {
      colors: {
        kovalyx: {
          // Customer loyalty tier colors (Customer Intelligence page) —
          // a separate concept from the brand palette below, kept
          // unchanged.
          bronze: '#CD7F32',
          silver: '#C0C0C0',
          bronzeText: '#7C4A1E',
          silverText: '#57534E',

          // Brand palette, sampled directly from the logo's gradient
          // (public/logo_dark_theme.png) — it isn't decorative, it maps
          // onto the medallion architecture itself: blue = ingestion,
          // teal = transform/quality, gold = the Gold layer. Gold stays
          // the "brand mark" color (wordmark, success/premium states,
          // GMV — literally Gold-layer data); blue is the primary
          // actionable color (links, buttons, active nav, selections);
          // teal is a secondary accent, mainly in the architecture
          // diagram's transform stage.
          gold: '#F0AA02',
          goldText: '#8A5E00',
          // #0075FB is the exact sampled logo blue; nudged one step
          // darker so white text sitting on a solid blue fill (buttons,
          // active pills) clears 4.5:1 — the raw sample was 4.25:1.
          blue: '#006EE8',
          blueText: '#0B5FCC',
          teal: '#00A9B0',
          tealText: '#067579',
        },
      },
      fontFamily: {
        sans: ['var(--font-inter)'],
        mono: ['var(--font-mono)'],
      },
    },
  },
  plugins: [],
}

export default config
