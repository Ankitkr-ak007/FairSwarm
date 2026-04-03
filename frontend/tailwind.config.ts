import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        primary: "#0066FF",
        secondary: "#00D4FF",
        accent: "#00FF88",
        danger: "#FF3B3B",
        warning: "#FFAA00",
        background: "#040B14",
        surface: "#0A1628",
        card: "#0F1F38",
        border: "#1A3050",
      },
      fontFamily: {
        sans: ["Space Grotesk", "sans-serif"],
      },
      keyframes: {
        "pulse-glow": {
          "0%, 100%": { opacity: "1", transform: "scale(1)" },
          "50%": { opacity: "0.8", transform: "scale(1.05)", filter: "brightness(1.5)" },
        },
        "scan-line": {
          "0%": { transform: "translateY(-100%)" },
          "100%": { transform: "translateY(100vh)" },
        },
      },
      animation: {
        "pulse-glow": "pulse-glow 2s cubic-bezier(0.4, 0, 0.6, 1) infinite",
        "scan-line": "scan-line 3s linear infinite",
      },
    },
  },
  plugins: [],
};
export default config;
