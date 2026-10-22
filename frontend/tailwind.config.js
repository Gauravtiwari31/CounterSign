/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: { DEFAULT: "#17201B", soft: "#4B5650", faint: "#7A847E" },
        leaf: { 50: "#EEF6F1", 100: "#D9ECE0", 500: "#2F6B4F", 600: "#265A42", 700: "#1D4734" },
        paper: "#FAF8F3",
      },
      fontFamily: { sans: ["Inter", "system-ui", "sans-serif"], serif: ["Fraunces", "Georgia", "serif"] },
    },
  },
  plugins: [],
};
