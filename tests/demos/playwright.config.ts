import { fileURLToPath } from "node:url"
import { defineConfig } from "@playwright/test"

const web = process.env.DEMO_WEB_URL || "http://127.0.0.1:3100"
const api = process.env.DEMO_API_URL || "http://127.0.0.1:4100"
for (const value of [web, api]) {
  const url = new URL(value)
  if (!["127.0.0.1", "localhost", "[::1]"].includes(url.hostname) || !["http:", "https:"].includes(url.protocol) || url.username || url.password)
    throw new Error("Demo acceptance writes synthetic data: only explicit loopback services are allowed")
}
export default defineConfig({
  testDir: ".",
  testMatch: process.env.DEMO_LIVE_AI === "1" ? "ai-journeys.spec.ts" : process.env.DEMO_RECORD === "1" ? "journeys.spec.ts" : ["journeys.spec.ts", "learning-ui.spec.ts"],
  outputDir: fileURLToPath(new URL("../e2e/.runtime/learning-demos/results", import.meta.url)),
  reporter: "list",
  workers: 1,
  fullyParallel: false,
  retries: 0,
  timeout: 180_000,
  expect: { timeout: 15_000 },
  use: { baseURL: web, viewport: { width: 1440, height: 1000 }, screenshot: "only-on-failure", trace: "retain-on-failure", video: "off" },
})
