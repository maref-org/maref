import { defineConfig } from "vitest/config";
import path from "path";

export default defineConfig({
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  test: {
    globals: true,
    environment: "jsdom",
    setupFiles: ["./tests/setup.ts"],
    css: false,
    // tests/e2e 为 Playwright 规格（@playwright/test 未在 devDependencies 中）。
    exclude: ["**/node_modules/**", "**/dist/**", "**/.git/**", "tests/e2e/**"],
  },
});
