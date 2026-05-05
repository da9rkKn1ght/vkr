import type { Config } from "tailwindcss";

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        display: ['"Sora"', "sans-serif"],
        body: ['"DM Sans"', "sans-serif"],
      },
      colors: {
        ink: "#0E1A25",
        mist: "#E9F0F5",
        accent: "#1A9D8B",
        ember: "#F49D37",
      },
      boxShadow: {
        panel: "0 18px 45px rgba(16, 33, 51, 0.12)",
      },
    },
  },
  plugins: [],
} satisfies Config;
