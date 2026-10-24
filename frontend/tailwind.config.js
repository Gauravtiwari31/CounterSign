/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // neutrals (slate) for text, surfaces and lines
        ink: { DEFAULT: "#0F172A", soft: "#475569", faint: "#64748B" },
        canvas: "#F8FAFC",
        line: "#E2E8F0",
        // primary actions and navigation
        brand: { 50: "#EFF6FF", 100: "#DBEAFE", 500: "#2563EB", 600: "#1D4ED8", 700: "#1E40AF", 900: "#0B1B3F" },
        // success states only (approved, supported, verified)
        leaf: { 50: "#ECFDF5", 100: "#D1FAE5", 500: "#059669", 600: "#047857", 700: "#065F46" },
      },
      fontFamily: { sans: ["Inter", "system-ui", "-apple-system", "Segoe UI", "sans-serif"] },
      boxShadow: {
        card: "0 1px 2px rgba(15, 23, 42, 0.04), 0 1px 3px rgba(15, 23, 42, 0.04)",
        pop: "0 12px 32px -8px rgba(15, 23, 42, 0.18)",
      },
    },
  },
  plugins: [],
};
