import fs from "node:fs/promises";

export async function ensureAuthDir(authDir) {
  await fs.mkdir(authDir, { recursive: true });
}

export async function resetAuthDir(authDir) {
  await fs.rm(authDir, { recursive: true, force: true });
  await fs.mkdir(authDir, { recursive: true });
}
