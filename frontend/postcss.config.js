// Required by Next.js's built-in PostCSS pipeline to actually apply
// tailwind.config.ts — without this, Tailwind classes compile to nothing.
module.exports = {
  plugins: {
    tailwindcss: {},
    autoprefixer: {},
  },
}
