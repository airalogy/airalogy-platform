import { defineConfig } from "@playwright/test"

export default defineConfig({
  testDir: ".",
  testMatch: "preview.spec.ts",
  outputDir: "../../test-results/agent-preview",
  workers: 1,
  use: { baseURL: "http://127.0.0.1:3109", screenshot: "only-on-failure" },
  webServer: {
    command: "python3 tools/airalogy_agent.py preview",
    cwd: "../..",
    url: "http://127.0.0.1:3109/agent-preview.html",
    reuseExistingServer: true,
  },
})
