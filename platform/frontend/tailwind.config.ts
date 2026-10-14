import type { Config } from "tailwindcss";

// Renkler CSS değişkenlerinden gelir (globals.css) → açık/koyu tema tek yerde.
const v = (name: string) => `var(--${name})`;

export default {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        page: v("page"),
        surface: v("surface-1"),
        ink: { DEFAULT: v("text-primary"), 2: v("text-secondary"), muted: v("text-muted") },
        line: v("gridline"),
        brand: v("brand"),
        good: v("good-text"),
        critical: v("critical"),
      },
      fontFamily: { sans: ["system-ui", "-apple-system", "Segoe UI", "sans-serif"] },
    },
  },
  plugins: [],
} satisfies Config;
