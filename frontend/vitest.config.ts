import { defineConfig } from "vitest/config";

// Own config so the tests do not load the IIFE library build of vite.config.ts.
export default defineConfig({
  test: {
    include: ["src/**/*.test.ts"],
  },
});
