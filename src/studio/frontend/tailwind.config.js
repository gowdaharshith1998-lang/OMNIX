/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        sans: [
          "Outfit",
          "ui-sans-serif",
          "system-ui",
          "sans-serif",
        ],
        display: ['"Syne"', "sans-serif"],
        mono: ['"JetBrains Mono"', "ui-monospace", "monospace"],
        omnix: {
          sans: "var(--omnix-font-sans)",
          display: "var(--omnix-font-display)",
          mono: "var(--omnix-font-mono)",
        },
      },
      colors: {
        omnix: {
          bg: "var(--omnix-bg-primary)",
          "glass-bg": "var(--omnix-glass-bg)",
          "text-primary": "var(--omnix-text-primary)",
          "text-muted": "var(--omnix-text-muted)",
          "text-dim": "var(--omnix-text-dim)",
          "text-sep": "var(--omnix-text-sep)",
          "accent-indigo": "var(--omnix-accent-indigo)",
          cyan: "var(--omnix-neon-cyan)",
          panel: "var(--omnix-sb-surface)",
          "sb-border": "var(--omnix-sb-border)",
          "sb-text": "var(--omnix-sb-text)",
          "sb-muted": "var(--omnix-sb-muted)",
          "sb-accent": "var(--omnix-sb-accent)",
          stat: "var(--omnix-stat-mono)",
          "stat-dm": "var(--omnix-stat-dark-matter)",
          "stat-ent": "var(--omnix-stat-entangled)",
          "xray-label": "var(--omnix-xray-label)",
        },
        studio: {
          deep: "#020615",
          panel: "rgba(10, 15, 26, 0.8)",
          line: "rgba(99, 102, 241, 0.2)",
          accent: "#6366f1",
          muted: "#94a3b8",
        },
      },
      boxShadow: {
        "omnix-glow": "0 0 18px rgba(99, 102, 241, 0.2)",
        "omnix-glass": "0 0 40px rgba(59, 130, 246, 0.06), inset 0 1px 0 rgba(255, 255, 255, 0.04)",
        "omnix-glow-cyan": "0 0 20px rgba(99, 102, 241, 0.22)",
      },
    },
  },
  plugins: [],
};
