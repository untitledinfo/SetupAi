import type { Config } from "tailwindcss";

const config: Config = {
  darkMode: "class",
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
    "./lib/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        ink: {
          950: "#05070B",
          900: "#0A0E14",
          800: "#0F1621",
          700: "#131A26",
          600: "#1B2434",
          500: "#25314459",
        },
        steel: {
          400: "#8592A6",
          300: "#A9B4C4",
          200: "#C8D3E0",
          100: "#E4EAF2",
        },
        volt: {
          700: "#1454B8",
          600: "#1C6BE0",
          500: "#2F8FFF",
          400: "#5BA8FF",
          300: "#8FC4FF",
        },
        signal: {
          amber: "#FFB020",
          green: "#37D399",
          red: "#FF5C5C",
        },
      },
      fontFamily: {
        display: ["var(--font-display)", "sans-serif"],
        body: ["var(--font-body)", "sans-serif"],
        mono: ["var(--font-mono)", "monospace"],
      },
      boxShadow: {
        glow: "0 0 0 1px rgba(47,143,255,0.25), 0 0 24px rgba(47,143,255,0.18)",
        "glow-sm": "0 0 0 1px rgba(47,143,255,0.2), 0 0 10px rgba(47,143,255,0.14)",
      },
      backgroundImage: {
        circuit:
          "radial-gradient(circle at 1px 1px, rgba(143,196,255,0.08) 1px, transparent 0)",
      },
      keyframes: {
        pulseGlow: {
          "0%, 100%": { opacity: "0.5" },
          "50%": { opacity: "1" },
        },
        scan: {
          "0%": { backgroundPosition: "0% 0%" },
          "100%": { backgroundPosition: "0% 200%" },
        },
      },
      animation: {
        pulseGlow: "pulseGlow 2.2s ease-in-out infinite",
        scan: "scan 3s linear infinite",
      },
    },
  },
  plugins: [],
};

export default config;
