/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        primary: "#ffff00",
        surface: "#16161a",
        background: "#0a0a0c",
        border: "#27272a",
        "text-dim": "#a1a1aa",
      },
      fontFamily: {
        sans: ['Inter', '-apple-system', 'sans-serif'],
        love: ['"Love Light"', 'cursive'],
      },
    },
  },
  plugins: [],
}
