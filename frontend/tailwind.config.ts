import type { Config } from "tailwindcss";

export default {
  darkMode: "class",
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        sans: ["Sabic", "SabicRegular", "Arial", "sans-serif"],
        display: ["SabicHeadline", "SabicHeadlineRegular", "Sabic", "Arial", "sans-serif"],
        mono: ["Cascadia Code", "SFMono-Regular", "Consolas", "monospace"]
      },
      colors: {
        ink: {
          50: "#f6f6f6",
          100: "#e6e6e6",
          500: "#939598",
          700: "#4d4d4d",
          900: "#041e42"
        },
        harbor: {
          400: "#46b4e6",
          500: "#009fdf",
          700: "#008cc8"
        },
        brass: {
          300: "#ffe678",
          500: "#ffcd00",
          700: "#f99d1c"
        }
      },
      boxShadow: {
        soft: "0 20px 60px rgba(4, 30, 66, 0.14)"
      }
    }
  },
  plugins: []
} satisfies Config;
