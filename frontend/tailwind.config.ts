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
          bronze: '#CD7F32',
          silver: '#C0C0C0',
          gold: '#FFD700',
          // Darker equivalents for text on light backgrounds — the raw
          // brand colors above (especially gold and silver) fail WCAG
          // contrast as text on white (gold ~1.6:1, silver worse; both
          // need 4.5:1). Use these via e.g.
          // `text-kovalyx-bronzeText dark:text-kovalyx-bronze` for any
          // *text* use of a tier/brand color; backgrounds/fills (chart
          // areas, active-nav tints, buttons with dark text on top) don't
          // have this problem and should keep using the bright variants.
          bronzeText: '#7C4A1E',
          silverText: '#57534E',
          goldText: '#8A6D00',
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
