/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        chrome: {
          950: "#090b10",
          900: "#10131a",
          850: "#161a22",
          800: "#1d2430",
        },
      },
      boxShadow: {
        panel: "0 24px 64px rgba(0, 0, 0, 0.38)",
        focus: "0 0 0 1px rgba(129, 140, 248, 0.4), 0 0 0 8px rgba(59, 130, 246, 0.08)",
      },
      fontFamily: {
        sans: ["Sohne", "Avenir Next", "Segoe UI", "sans-serif"],
        mono: ["IBM Plex Mono", "SFMono-Regular", "monospace"],
      },
      backgroundImage: {
        "app-fade":
          "radial-gradient(circle at top, rgba(91, 124, 250, 0.15), transparent 28%), radial-gradient(circle at right, rgba(34, 197, 94, 0.09), transparent 24%)",
      },
    },
  },
  plugins: [],
};

