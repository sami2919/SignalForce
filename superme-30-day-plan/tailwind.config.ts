import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{js,ts,jsx,tsx,mdx}"],
  theme: {
    extend: {
      colors: {
        ink: "#171717",
        muted: "#5f6368",
        paper: "#fbfaf7",
        line: "#e4e0d8",
        soft: "#f3f0ea",
        accent: "#245c4f",
      },
      fontFamily: {
        sans: ["Inter", "ui-sans-serif", "system-ui", "sans-serif"],
      },
      boxShadow: {
        memo: "0 1px 2px rgba(23, 23, 23, 0.04)",
      },
    },
  },
  plugins: [],
};

export default config;
