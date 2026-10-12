/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        sans: ["IBM Plex Sans", "system-ui", "sans-serif"],
        mono: ["IBM Plex Mono", "ui-monospace", "monospace"],
      },
      colors: {
        ink: {
          DEFAULT: "#0d0d0f",
          2: "#16161a",
          3: "#1e1e23",
        },
        rule: "#2a2a31",
        paper: "#e8e6e1",
        muted: "#8a8a94",
        signal: "#d8763a",
        verify: "#5f8f6a",
        fault: "#b5503f",
      },
      fontSize: {
        micro: ["10.5px", { lineHeight: "1.4", letterSpacing: "0.04em" }],
      },
    },
  },
  plugins: [],
}
