import type { Config } from "tailwindcss";

export default {
  darkMode: "class",
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        sans: ["Aptos", "Segoe UI Variable", "Helvetica Neue", "sans-serif"],
        display: ["Aptos Display", "Segoe UI Variable Display", "Helvetica Neue", "sans-serif"],
        mono: ["JetBrains Mono", "Cascadia Code", "SFMono-Regular", "monospace"]
      },
      colors: {
        ink: {
          50: "#f6f8f9",
          100: "#e8edf0",
          500: "#5d6f78",
          700: "#31424a",
          900: "#14252d"
        },
        harbor: {
          400: "#16a3b8",
          500: "#0f8fa3",
          700: "#0b6574"
        },
        brass: {
          300: "#f2ca72",
          500: "#c9912f",
          700: "#8c5f1d"
        }
      },
      boxShadow: {
        soft: "0 20px 60px rgba(20, 37, 45, 0.12)"
      }
    }
  },
  plugins: []
} satisfies Config;
