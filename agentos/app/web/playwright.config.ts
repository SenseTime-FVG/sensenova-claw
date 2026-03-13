import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './e2e',
  timeout: 60000,
  retries: 0,
  use: {
    baseURL: 'http://localhost:3000',
    headless: true,
  },
  webServer: {
    command: 'cd .. && npm run dev',
    port: 3000,
    timeout: 120000,
    reuseExistingServer: true,
  },
});
