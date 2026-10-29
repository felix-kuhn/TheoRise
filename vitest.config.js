import path from "node:path";
import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.js"],
    env: {
      VITE_BACKEND_URL: "http://127.0.0.1:9999",
      VITE_BACKEND_TOKEN: "test-token",
    },
  },
});
