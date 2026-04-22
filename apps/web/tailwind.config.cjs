/** @type {import('tailwindcss').Config} */
// Tailwind palette is remapped onto the Workpad AI design tokens
// (see src/tokens.css). Legacy utility classes like text-slate-100,
// bg-chrome-950, text-sky-300 are rewritten to reference the shell /
// paper / accent CSS vars so the existing markup picks up the new
// editorial-journal look without touching every component.
module.exports = {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // Legacy chrome ramp -> shell surfaces
        chrome: {
          950: "var(--shell-0)",
          900: "var(--shell-1)",
          850: "var(--shell-2)",
          800: "var(--shell-3)",
        },
        // Slate ramp -> ink/shell. Light values are ink (text), dark
        // values are shell surfaces. This flips the polarity so the
        // previous "dark theme" classes read correctly on a light
        // app shell.
        slate: {
          50: "var(--ink-1)",
          100: "var(--ink-1)",
          200: "var(--ink-2)",
          300: "var(--ink-2)",
          400: "var(--ink-3)",
          500: "var(--ink-3)",
          600: "var(--ink-3)",
          700: "var(--shell-border-strong)",
          800: "var(--shell-2)",
          900: "var(--shell-1)",
          950: "var(--shell-0)",
        },
        // Sky / indigo -> the single product accent (ember orange #D85A1E)
        // Channel syntax ensures `bg-sky-500/15` etc. still apply alpha.
        sky: {
          50: "rgb(216 90 30 / 0.06)",
          100: "var(--accent-signal-soft)",
          200: "var(--accent-signal-press)",
          300: "rgb(216 90 30 / <alpha-value>)",
          400: "rgb(216 90 30 / <alpha-value>)",
          500: "rgb(216 90 30 / <alpha-value>)",
          600: "rgb(196 78 22 / <alpha-value>)",
          700: "rgb(174 67 15 / <alpha-value>)",
        },
        indigo: {
          400: "rgb(216 90 30 / <alpha-value>)",
          500: "rgb(216 90 30 / <alpha-value>)",
          600: "rgb(196 78 22 / <alpha-value>)",
          700: "rgb(174 67 15 / <alpha-value>)",
        },
        // Stone is used in a couple of "paper-like" code blocks. Map to paper.
        stone: {
          100: "var(--paper-1)",
          200: "var(--paper-1)",
          300: "var(--paper-border)",
          400: "var(--paper-border-strong)",
          900: "var(--paper-ink)",
        },
        // Citation-state palette — channel syntax for alpha modifiers.
        // Amber -> stale  (#B8701C = 184 112 28)
        amber: {
          50: "rgb(184 112 28 / 0.06)",
          100: "var(--state-stale-soft)",
          200: "var(--state-stale-ink)",
          300: "rgb(184 112 28 / <alpha-value>)",
          400: "rgb(184 112 28 / <alpha-value>)",
          500: "rgb(184 112 28 / <alpha-value>)",
          600: "var(--state-stale-ink)",
          700: "var(--state-stale-ink)",
        },
        // Rose -> missing (#B23B3B = 178 59 59)
        rose: {
          50: "rgb(178 59 59 / 0.06)",
          100: "var(--state-missing-soft)",
          200: "var(--state-missing-ink)",
          300: "rgb(178 59 59 / <alpha-value>)",
          400: "rgb(178 59 59 / <alpha-value>)",
          500: "rgb(178 59 59 / <alpha-value>)",
          600: "var(--state-missing-ink)",
          700: "var(--state-missing-ink)",
        },
        // Emerald/green -> live  (#2D7D4B = 45 125 75)
        emerald: {
          100: "var(--state-live-soft)",
          200: "rgb(45 125 75 / <alpha-value>)",
          300: "rgb(45 125 75 / <alpha-value>)",
          400: "rgb(45 125 75 / <alpha-value>)",
          500: "rgb(45 125 75 / <alpha-value>)",
          600: "var(--state-live-ink)",
        },
        green: {
          400: "rgb(45 125 75 / <alpha-value>)",
          500: "rgb(45 125 75 / <alpha-value>)",
        },
        // First-class new tokens for new code
        shell: {
          0: "var(--shell-0)",
          1: "var(--shell-1)",
          2: "var(--shell-2)",
          3: "var(--shell-3)",
          border: "var(--shell-border)",
          "border-strong": "var(--shell-border-strong)",
        },
        paper: {
          0: "var(--paper-0)",
          1: "var(--paper-1)",
          2: "var(--paper-2)",
          border: "var(--paper-border)",
          "border-strong": "var(--paper-border-strong)",
          ink: "var(--paper-ink)",
          "ink-2": "var(--paper-ink-2)",
          "ink-3": "var(--paper-ink-3)",
        },
        ink: {
          1: "var(--ink-1)",
          2: "var(--ink-2)",
          3: "var(--ink-3)",
          4: "var(--ink-4)",
        },
        signal: {
          DEFAULT: "var(--accent-signal)",
          hover: "var(--accent-signal-hover)",
          press: "var(--accent-signal-press)",
          soft: "var(--accent-signal-soft)",
          "soft-border": "var(--accent-signal-soft-border)",
          "soft-ink": "var(--accent-signal-soft-ink)",
          ink: "var(--accent-signal-ink)",
        },
        state: {
          live: "var(--state-live)",
          "live-soft": "var(--state-live-soft)",
          "live-ink": "var(--state-live-ink)",
          stale: "var(--state-stale)",
          "stale-soft": "var(--state-stale-soft)",
          "stale-ink": "var(--state-stale-ink)",
          missing: "var(--state-missing)",
          "missing-soft": "var(--state-missing-soft)",
          "missing-ink": "var(--state-missing-ink)",
        },
      },
      boxShadow: {
        panel: "var(--shadow-pop)",
        focus: "0 0 0 2px var(--accent-signal)",
      },
      fontFamily: {
        sans: [
          "Inter Tight",
          "Söhne",
          "Suisse Int'l",
          "ui-sans-serif",
          "system-ui",
          "-apple-system",
          "Segoe UI",
          "sans-serif",
        ],
        serif: [
          "Source Serif 4",
          "Charter",
          "Iowan Old Style",
          "Apple Garamond",
          "Georgia",
          "serif",
        ],
        mono: [
          "IBM Plex Mono",
          "SF Mono",
          "JetBrains Mono",
          "ui-monospace",
          "Menlo",
          "Consolas",
          "monospace",
        ],
      },
      backgroundImage: {
        "app-fade": "none",
      },
      borderRadius: {
        DEFAULT: "var(--r-2)",
        sm: "var(--r-1)",
        md: "var(--r-2)",
        lg: "var(--r-3)",
        xl: "var(--r-3)",
        "2xl": "var(--r-4)",
      },
    },
  },
  plugins: [],
};
