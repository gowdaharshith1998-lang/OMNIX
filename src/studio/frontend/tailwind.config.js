/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        studio: {
          deep: "#06080c",
          panel: "#0d1118",
          line: "#1c2433",
          accent: "#3d9eff",
          muted: "#6b7a90",
        },
      },
    },
  },
  plugins: [],
};
