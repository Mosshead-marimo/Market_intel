import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  retries: process.env.CI ? 2 : 0,
  reporter: process.env.CI ? "github" : "list",
  webServer: {
    command: "corepack pnpm start",
    reuseExistingServer: !process.env.CI,
    url: "http://localhost:3000",
  },
  use: {
    baseURL: process.env.WEB_URL ?? "http://localhost:3000",
    trace: "retain-on-failure",
  },
});
