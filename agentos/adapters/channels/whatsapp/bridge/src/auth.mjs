import fs from "node:fs/promises";

export async function ensureAuthDir(authDir) {
  await fs.mkdir(authDir, { recursive: true });
}
