import { existsSync } from 'node:fs';

import { defineConfig } from '@playwright/test';

const systemChromePaths = [
  process.env.PLAYWRIGHT_CHROME_EXECUTABLE,
  '/usr/bin/google-chrome',
  '/usr/bin/google-chrome-stable',
  '/usr/bin/chromium',
  '/usr/bin/chromium-browser',
].filter((value): value is string => Boolean(value));

const chromeExecutablePath = systemChromePaths.find((path) => existsSync(path));

export default defineConfig({
  testDir: './e2e',
  timeout: 60000,
  retries: 0,
  use: {
    baseURL: 'http://127.0.0.1:3000',
    headless: true,
    launchOptions: chromeExecutablePath
      ? {
          executablePath: chromeExecutablePath,
        }
      : undefined,
  },
  webServer: {
    command: 'npm run dev',
    port: 3000,
    timeout: 120000,
    reuseExistingServer: false,
  },
});
