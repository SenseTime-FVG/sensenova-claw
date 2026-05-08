#!/usr/bin/env node
import { getOAuthApiKey, loginOpenAICodex } from "@mariozechner/pi-ai/oauth";
import { spawn } from "node:child_process";

const PROVIDER = "openai-codex";
const ORIGINATOR = "sensenova-claw";
const LOCAL_MANUAL_FALLBACK_DELAY_MS = 15_000;
const LOCAL_MANUAL_FALLBACK_GRACE_MS = 1_000;
const OPENAI_AUTH_PROBE_URL =
  "https://auth.openai.com/oauth/authorize?response_type=code&client_id=sensenova-claw-preflight&redirect_uri=http%3A%2F%2Flocalhost%3A1455%2Fauth%2Fcallback&scope=openid+profile+email";
const TLS_CERT_ERROR_CODES = new Set([
  "UNABLE_TO_GET_ISSUER_CERT_LOCALLY",
  "UNABLE_TO_VERIFY_LEAF_SIGNATURE",
  "CERT_HAS_EXPIRED",
  "DEPTH_ZERO_SELF_SIGNED_CERT",
  "SELF_SIGNED_CERT_IN_CHAIN",
  "ERR_TLS_CERT_ALTNAME_INVALID",
]);
const TLS_CERT_ERROR_PATTERNS = [
  /unable to get local issuer certificate/i,
  /unable to verify the first certificate/i,
  /self[- ]signed certificate/i,
  /certificate has expired/i,
];

function readStdin() {
  return new Promise((resolve, reject) => {
    let data = "";
    process.stdin.setEncoding("utf8");
    process.stdin.on("data", (chunk) => {
      data += chunk;
    });
    process.stdin.on("end", () => resolve(data));
    process.stdin.on("error", reject);
  });
}

function writeCredential(credential) {
  const payload = {
    ...credential,
    provider: credential.provider ?? PROVIDER,
  };
  process.stdout.write(`${JSON.stringify(payload)}\n`);
}

function openUrl(url) {
  const command =
    process.platform === "darwin" ? "open" : process.platform === "win32" ? "cmd" : "xdg-open";
  const args = process.platform === "win32" ? ["/c", "start", "", url] : [url];
  const child = spawn(command, args, {
    detached: true,
    stdio: "ignore",
  });
  child.unref();
}

function prompt(message) {
  process.stderr.write(`${message}\n> `);
  return new Promise((resolve) => {
    process.stdin.resume();
    process.stdin.setEncoding("utf8");
    process.stdin.once("data", (chunk) => {
      resolve(String(chunk).trim());
    });
  });
}

function waitForDelayOrLoginSettle(delayMs, waitForLoginToSettle) {
  return new Promise((resolve) => {
    let finished = false;
    let timeoutHandle;
    const finish = (outcome) => {
      if (finished) return;
      finished = true;
      clearTimeout(timeoutHandle);
      resolve(outcome);
    };
    timeoutHandle = setTimeout(() => finish("delay"), delayMs);
    waitForLoginToSettle.then(
      () => finish("settled"),
      () => finish("settled"),
    );
  });
}

function neverSettles() {
  return new Promise(() => undefined);
}

function classifyPreflightFailure(error) {
  const code =
    typeof error?.cause?.code === "string"
      ? error.cause.code
      : typeof error?.code === "string"
        ? error.code
        : undefined;
  const message =
    typeof error?.cause?.message === "string"
      ? error.cause.message
      : error instanceof Error
        ? error.message
        : String(error);
  const tlsCert =
    (code ? TLS_CERT_ERROR_CODES.has(code) : false) ||
    TLS_CERT_ERROR_PATTERNS.some((pattern) => pattern.test(message));
  return { code, message, kind: tlsCert ? "tls-cert" : "network" };
}

async function runOpenAIOAuthTlsPreflight() {
  try {
    await fetch(OPENAI_AUTH_PROBE_URL, {
      method: "GET",
      redirect: "manual",
      signal: AbortSignal.timeout(5000),
    });
    return { ok: true };
  } catch (error) {
    return { ok: false, ...classifyPreflightFailure(error) };
  }
}

function formatTlsPreflightFix(result) {
  if (result.kind !== "tls-cert") {
    return [
      "OpenAI OAuth prerequisites check failed due to a network error before the browser flow.",
      `Cause: ${result.message}`,
      "Verify DNS/firewall/proxy access to auth.openai.com and retry.",
    ].join("\n");
  }
  return [
    "OpenAI OAuth prerequisites check failed: Node/OpenSSL cannot validate TLS certificates.",
    `Cause: ${result.code ? `${result.code} (${result.message})` : result.message}`,
    "",
    "Fix (Homebrew Node/OpenSSL):",
    "- brew postinstall ca-certificates",
    "- brew postinstall openssl@3",
    "- Retry the OAuth login flow.",
  ].join("\n");
}

function createManualCodeInputHandler({ isRemote, hasBrowserAuthStarted, waitForLoginToSettle }) {
  if (isRemote) {
    return async () => await prompt("Paste the authorization code or full redirect URL:");
  }
  return async () => {
    if (!hasBrowserAuthStarted()) {
      process.stderr.write("Local OAuth callback was unavailable. Paste the redirect URL to continue.\n");
      return await prompt("Paste the authorization code or full redirect URL:");
    }
    const outcome = await waitForDelayOrLoginSettle(
      LOCAL_MANUAL_FALLBACK_DELAY_MS,
      waitForLoginToSettle,
    );
    if (outcome === "settled") {
      return await neverSettles();
    }
    const settledDuringGraceWindow = await waitForDelayOrLoginSettle(
      LOCAL_MANUAL_FALLBACK_GRACE_MS,
      waitForLoginToSettle,
    );
    if (settledDuringGraceWindow === "settled") {
      return await neverSettles();
    }
    process.stderr.write("Browser callback did not finish. Paste the redirect URL to continue.\n");
    return await prompt("Paste the authorization code or full redirect URL:");
  };
}

async function login(isRemote) {
  const preflight = await runOpenAIOAuthTlsPreflight();
  if (!preflight.ok && preflight.kind === "tls-cert") {
    throw new Error(formatTlsPreflightFix(preflight));
  }

  let browserAuthStarted = false;
  let markLoginSettled;
  const waitForLoginToSettle = new Promise((resolve) => {
    markLoginSettled = resolve;
  });
  try {
    const credential = await loginOpenAICodex({
      originator: ORIGINATOR,
      onAuth: async ({ url }) => {
        browserAuthStarted = true;
        if (isRemote) {
          process.stderr.write(`Open this URL in your local browser:\n\n${url}\n\n`);
          return;
        }
        openUrl(url);
        process.stderr.write(`Open: ${url}\n`);
      },
      onPrompt: async ({ message }) => await prompt(message),
      onManualCodeInput: createManualCodeInputHandler({
        isRemote,
        hasBrowserAuthStarted: () => browserAuthStarted,
        waitForLoginToSettle,
      }),
      onProgress: (message) => {
        process.stderr.write(`${message}\n`);
      },
    });
    if (!credential) {
      throw new Error("OpenAI Codex OAuth login returned no credential");
    }
    writeCredential(credential);
  } finally {
    if (markLoginSettled) {
      markLoginSettled();
    }
  }
}

async function refresh() {
  const raw = await readStdin();
  const credential = JSON.parse(raw || "{}");
  const result = await getOAuthApiKey(PROVIDER, {
    [PROVIDER]: {
      ...credential,
      provider: PROVIDER,
    },
  });
  const refreshed = result?.newCredentials
    ? { ...credential, ...result.newCredentials, provider: PROVIDER }
    : credential;
  writeCredential(refreshed);
}

async function main() {
  const [command, ...args] = process.argv.slice(2);
  if (command === "login") {
    await login(args.includes("--remote"));
    return;
  }
  if (command === "refresh") {
    await refresh();
    return;
  }
  throw new Error(`Unknown command: ${command || ""}`);
}

main().catch((error) => {
  process.stderr.write(`${error instanceof Error ? error.message : String(error)}\n`);
  process.exit(1);
});
