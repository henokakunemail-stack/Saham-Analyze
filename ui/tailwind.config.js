/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        background: '#090D16',
        surface: '#111827',
        surfaceHover: '#1F2937',
        borderMuted: '#1E293B',
        bullish: '#10B981',
        bearish: '#EF4444',
        accent: '#3B82F6'
      }
    },
  },
  plugins: [],
}
