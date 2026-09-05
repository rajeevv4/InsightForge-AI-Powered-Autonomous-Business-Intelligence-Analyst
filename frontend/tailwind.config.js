/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        slate: {
          850: '#151F32',
          900: '#0F172A',
          950: '#0B0F19',
        },
        brand: {
          blue: '#38BDF8',
          emerald: '#10B981',
          amber: '#F59E0B',
          purple: '#8B5CF6'
        }
      }
    },
  },
  plugins: [],
}
