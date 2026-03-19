import test from "node:test";
import assert from "node:assert/strict";

import { WhatsAppRuntime } from "../src/runtime.mjs";

function createFakeEmitter() {
  const handlers = new Map();
  return {
    on(event, handler) {
      handlers.set(event, handler);
    },
    emit(event, payload) {
      const handler = handlers.get(event);
      if (handler) {
        handler(payload);
      }
    },
  };
}

test("start uses openclaw-compatible Baileys auth options", async () => {
  const calls = {
    fetchLatestBaileysVersion: 0,
    makeCacheableSignalKeyStore: 0,
  };
  let capturedSocketOptions = null;
  const fakeSocket = {
    ev: createFakeEmitter(),
    ws: { close() {} },
    user: null,
  };

  const runtime = new WhatsAppRuntime({
    emit: () => {},
    loadBaileys: async () => ({
      makeWASocket(options) {
        capturedSocketOptions = options;
        return fakeSocket;
      },
      useMultiFileAuthState: async () => ({
        state: {
          creds: { me: "creds" },
          keys: { me: "keys" },
        },
        saveCreds: async () => {},
      }),
      fetchLatestBaileysVersion: async () => {
        calls.fetchLatestBaileysVersion += 1;
        return { version: [2, 3000, 1] };
      },
      makeCacheableSignalKeyStore(keys) {
        calls.makeCacheableSignalKeyStore += 1;
        return { wrappedKeys: keys };
      },
    }),
  });

  await runtime.start("/tmp/agentos-whatsapp-runtime-test");

  assert.equal(calls.fetchLatestBaileysVersion, 1);
  assert.equal(calls.makeCacheableSignalKeyStore, 1);
  assert.deepEqual(capturedSocketOptions.auth, {
    creds: { me: "creds" },
    keys: { wrappedKeys: { me: "keys" } },
  });
  assert.deepEqual(capturedSocketOptions.version, [2, 3000, 1]);
  assert.deepEqual(capturedSocketOptions.browser, ["openclaw", "cli", "agentos"]);
});

test("statusCode 515 restarts socket without clearing auth dir", async () => {
  const events = [];
  let makeSocketCalls = 0;
  let resetAuthDirCalls = 0;
  const sockets = [];

  const runtime = new WhatsAppRuntime({
    emit: (event) => {
      events.push(event);
    },
    ensureAuthDir: async () => {},
    resetAuthDir: async () => {
      resetAuthDirCalls += 1;
    },
    restartDelayMs: 0,
    reconnectDelayMs: 0,
    loadBaileys: async () => ({
      makeWASocket() {
        makeSocketCalls += 1;
        const socket = {
          ev: createFakeEmitter(),
          ws: { close() {} },
          user: null,
        };
        sockets.push(socket);
        return socket;
      },
      useMultiFileAuthState: async () => ({
        state: {
          creds: {},
          keys: {},
        },
        saveCreds: async () => {},
      }),
      fetchLatestBaileysVersion: async () => ({ version: [2, 3000, 1] }),
      makeCacheableSignalKeyStore(keys) {
        return keys;
      },
    }),
  });

  await runtime.start("/tmp/agentos-whatsapp-runtime-test");
  sockets[0].ev.emit("connection.update", {
    connection: "close",
    lastDisconnect: {
      error: {
        message: "Stream Errored (restart required)",
        output: { statusCode: 515, payload: { tag: "stream:error" } },
      },
    },
  });
  await new Promise((resolve) => setTimeout(resolve, 0));

  assert.equal(makeSocketCalls, 2);
  assert.equal(resetAuthDirCalls, 0);
  assert.equal(events.some((event) => event.type === "status" && event.payload.state === "restarting"), true);
});

test("messages.upsert extracts text from ephemeral wrapper", async () => {
  const events = [];
  const sockets = [];

  const runtime = new WhatsAppRuntime({
    emit: (event) => {
      events.push(event);
    },
    ensureAuthDir: async () => {},
    loadBaileys: async () => ({
      makeWASocket() {
        const socket = {
          ev: createFakeEmitter(),
          ws: { close() {} },
          user: null,
        };
        sockets.push(socket);
        return socket;
      },
      useMultiFileAuthState: async () => ({
        state: {
          creds: {},
          keys: {},
        },
        saveCreds: async () => {},
      }),
      fetchLatestBaileysVersion: async () => ({ version: [2, 3000, 1] }),
      makeCacheableSignalKeyStore(keys) {
        return keys;
      },
    }),
  });

  await runtime.start("/tmp/agentos-whatsapp-runtime-test");
  sockets[0].ev.emit("messages.upsert", {
    type: "notify",
    messages: [
      {
        key: {
          fromMe: false,
          remoteJid: "15550000001@s.whatsapp.net",
          id: "wamid-ephemeral-1",
        },
        message: {
          ephemeralMessage: {
            message: {
              extendedTextMessage: {
                text: "hello from ephemeral",
              },
            },
          },
        },
      },
    ],
  });

  const messageEvent = events.find((event) => event.type === "message");
  assert.ok(messageEvent);
  assert.equal(messageEvent.payload.text, "hello from ephemeral");
  assert.equal(
    events.some(
      (event) =>
        event.type === "debug"
        && String(event.payload?.message ?? "").includes("messages.upsert received: type=notify count=1"),
    ),
    true,
  );
});

test("messages.upsert uses Baileys normalizeMessageContent helpers for text extraction", async () => {
  const events = [];
  const sockets = [];

  const runtime = new WhatsAppRuntime({
    emit: (event) => {
      events.push(event);
    },
    ensureAuthDir: async () => {},
    loadBaileys: async () => ({
      makeWASocket() {
        const socket = {
          ev: createFakeEmitter(),
          ws: { close() {} },
          user: null,
        };
        sockets.push(socket);
        return socket;
      },
      useMultiFileAuthState: async () => ({
        state: {
          creds: {},
          keys: {},
        },
        saveCreds: async () => {},
      }),
      fetchLatestBaileysVersion: async () => ({ version: [2, 3000, 1] }),
      makeCacheableSignalKeyStore(keys) {
        return keys;
      },
      normalizeMessageContent(message) {
        if (message?.futureMessage?.message) {
          return message.futureMessage.message;
        }
        return message;
      },
      extractMessageContent(message) {
        return message?.wrappedTextMessage?.message ?? null;
      },
    }),
  });

  await runtime.start("/tmp/agentos-whatsapp-runtime-test");
  sockets[0].ev.emit("messages.upsert", {
    type: "notify",
    messages: [
      {
        key: {
          fromMe: false,
          remoteJid: "15550000001@s.whatsapp.net",
          id: "wamid-helper-1",
        },
        message: {
          futureMessage: {
            message: {
              wrappedTextMessage: {
                message: {
                  extendedTextMessage: {
                    text: "hello from helper extraction",
                  },
                },
              },
            },
          },
        },
      },
    ],
  });

  const messageEvent = events.find((event) => event.type === "message");
  assert.ok(messageEvent);
  assert.equal(messageEvent.payload.text, "hello from helper extraction");
});

test("messages.upsert falls back to extendedTextMessage matchedText", async () => {
  const events = [];
  const sockets = [];

  const runtime = new WhatsAppRuntime({
    emit: (event) => {
      events.push(event);
    },
    ensureAuthDir: async () => {},
    loadBaileys: async () => ({
      makeWASocket() {
        const socket = {
          ev: createFakeEmitter(),
          ws: { close() {} },
          user: null,
        };
        sockets.push(socket);
        return socket;
      },
      useMultiFileAuthState: async () => ({
        state: {
          creds: {},
          keys: {},
        },
        saveCreds: async () => {},
      }),
      fetchLatestBaileysVersion: async () => ({ version: [2, 3000, 1] }),
      makeCacheableSignalKeyStore(keys) {
        return keys;
      },
      normalizeMessageContent(message) {
        return message;
      },
      extractMessageContent(message) {
        return message;
      },
    }),
  });

  await runtime.start("/tmp/agentos-whatsapp-runtime-test");
  sockets[0].ev.emit("messages.upsert", {
    type: "notify",
    messages: [
      {
        key: {
          fromMe: false,
          remoteJid: "15550000001@s.whatsapp.net",
          id: "wamid-matched-1",
        },
        message: {
          extendedTextMessage: {
            matchedText: "hello from matched text",
          },
        },
      },
    ],
  });

  const messageEvent = events.find((event) => event.type === "message");
  assert.ok(messageEvent);
  assert.equal(messageEvent.payload.text, "hello from matched text");
});

test("messages.upsert accepts self chat messages from current account", async () => {
  const events = [];
  const sockets = [];

  const runtime = new WhatsAppRuntime({
    emit: (event) => {
      events.push(event);
    },
    ensureAuthDir: async () => {},
    loadBaileys: async () => ({
      makeWASocket() {
        const socket = {
          ev: createFakeEmitter(),
          ws: { close() {} },
          user: { id: "85293432086:1@s.whatsapp.net", lid: "121672866726017@lid" },
        };
        sockets.push(socket);
        return socket;
      },
      useMultiFileAuthState: async () => ({
        state: {
          creds: {},
          keys: {},
        },
        saveCreds: async () => {},
      }),
      fetchLatestBaileysVersion: async () => ({ version: [2, 3000, 1] }),
      makeCacheableSignalKeyStore(keys) {
        return keys;
      },
    }),
  });

  await runtime.start("/tmp/agentos-whatsapp-runtime-test");
  sockets[0].ev.emit("messages.upsert", {
    type: "notify",
    messages: [
      {
        key: {
          fromMe: true,
          remoteJid: "85293432086@s.whatsapp.net",
          id: "wamid-self-1",
        },
        message: {
          conversation: "hello from self chat",
        },
      },
    ],
  });

  const messageEvent = events.find((event) => event.type === "message");
  assert.ok(messageEvent);
  assert.equal(messageEvent.payload.text, "hello from self chat");
});

test("messages.upsert accepts self chat messages on lid conversations", async () => {
  const events = [];
  const sockets = [];

  const runtime = new WhatsAppRuntime({
    emit: (event) => {
      events.push(event);
    },
    ensureAuthDir: async () => {},
    loadBaileys: async () => ({
      makeWASocket() {
        const socket = {
          ev: createFakeEmitter(),
          ws: { close() {} },
          user: { id: "85293432086:1@s.whatsapp.net", lid: "121672866726017@lid" },
        };
        sockets.push(socket);
        return socket;
      },
      useMultiFileAuthState: async () => ({
        state: {
          creds: {},
          keys: {},
        },
        saveCreds: async () => {},
      }),
      fetchLatestBaileysVersion: async () => ({ version: [2, 3000, 1] }),
      makeCacheableSignalKeyStore(keys) {
        return keys;
      },
    }),
  });

  await runtime.start("/tmp/agentos-whatsapp-runtime-test");
  sockets[0].ev.emit("messages.upsert", {
    type: "notify",
    messages: [
      {
        key: {
          fromMe: true,
          remoteJid: "121672866726017@lid",
          id: "wamid-self-lid-1",
        },
        message: {
          conversation: "hello from self lid chat",
        },
      },
    ],
  });

  const messageEvent = events.find((event) => event.type === "message");
  assert.ok(messageEvent);
  assert.equal(messageEvent.payload.text, "hello from self lid chat");
});

test("messages.upsert still ignores non-self from_me messages", async () => {
  const events = [];
  const sockets = [];

  const runtime = new WhatsAppRuntime({
    emit: (event) => {
      events.push(event);
    },
    ensureAuthDir: async () => {},
    loadBaileys: async () => ({
      makeWASocket() {
        const socket = {
          ev: createFakeEmitter(),
          ws: { close() {} },
          user: { id: "85293432086:1@s.whatsapp.net" },
        };
        sockets.push(socket);
        return socket;
      },
      useMultiFileAuthState: async () => ({
        state: {
          creds: {},
          keys: {},
        },
        saveCreds: async () => {},
      }),
      fetchLatestBaileysVersion: async () => ({ version: [2, 3000, 1] }),
      makeCacheableSignalKeyStore(keys) {
        return keys;
      },
    }),
  });

  await runtime.start("/tmp/agentos-whatsapp-runtime-test");
  sockets[0].ev.emit("messages.upsert", {
    type: "notify",
    messages: [
      {
        key: {
          fromMe: true,
          remoteJid: "999999999999999@lid",
          id: "wamid-self-ignored-1",
        },
        message: {
          conversation: "should stay ignored",
        },
      },
    ],
  });

  const messageEvent = events.find((event) => event.type === "message");
  assert.equal(messageEvent, undefined);
});

test("messages.upsert ignores recent outbound echo in self chat", async () => {
  const events = [];
  const sockets = [];

  const runtime = new WhatsAppRuntime({
    emit: (event) => {
      events.push(event);
    },
    ensureAuthDir: async () => {},
    loadBaileys: async () => ({
      makeWASocket() {
        const socket = {
          ev: createFakeEmitter(),
          ws: { close() {} },
          user: { id: "85293432086:1@s.whatsapp.net", lid: "121672866726017@lid" },
          async sendMessage() {
            return { key: { id: "wamid-outbound-1" } };
          },
        };
        sockets.push(socket);
        return socket;
      },
      useMultiFileAuthState: async () => ({
        state: {
          creds: {},
          keys: {},
        },
        saveCreds: async () => {},
      }),
      fetchLatestBaileysVersion: async () => ({ version: [2, 3000, 1] }),
      makeCacheableSignalKeyStore(keys) {
        return keys;
      },
    }),
  });

  await runtime.start("/tmp/agentos-whatsapp-runtime-test");
  await runtime.sendText("121672866726017@lid", "reply from bot");
  sockets[0].ev.emit("messages.upsert", {
    type: "notify",
    messages: [
      {
        key: {
          fromMe: true,
          remoteJid: "121672866726017@lid",
          id: "wamid-outbound-1",
        },
        message: {
          conversation: "reply from bot",
        },
      },
    ],
  });

  const messageEvent = events.find((event) => event.type === "message");
  assert.equal(messageEvent, undefined);
});

test("statusCode 408 reconnects socket without clearing auth dir", async () => {
  const events = [];
  let makeSocketCalls = 0;
  let resetAuthDirCalls = 0;
  const sockets = [];

  const runtime = new WhatsAppRuntime({
    emit: (event) => {
      events.push(event);
    },
    ensureAuthDir: async () => {},
    resetAuthDir: async () => {
      resetAuthDirCalls += 1;
    },
    restartDelayMs: 0,
    reconnectDelayMs: 0,
    loadBaileys: async () => ({
      makeWASocket() {
        makeSocketCalls += 1;
        const socket = {
          ev: createFakeEmitter(),
          ws: { close() {} },
          user: null,
        };
        sockets.push(socket);
        return socket;
      },
      useMultiFileAuthState: async () => ({
        state: {
          creds: {},
          keys: {},
        },
        saveCreds: async () => {},
      }),
      fetchLatestBaileysVersion: async () => ({ version: [2, 3000, 1] }),
      makeCacheableSignalKeyStore(keys) {
        return keys;
      },
    }),
  });

  await runtime.start("/tmp/agentos-whatsapp-runtime-test");
  sockets[0].ev.emit("connection.update", {
    connection: "close",
    lastDisconnect: {
      error: {
        message: "WebSocket Error (Opening handshake has timed out)",
        output: { statusCode: 408, payload: {} },
      },
    },
  });
  await new Promise((resolve) => setTimeout(resolve, 0));

  assert.equal(makeSocketCalls, 2);
  assert.equal(resetAuthDirCalls, 0);
  assert.equal(events.some((event) => event.type === "status" && event.payload.state === "reconnecting"), true);
});

test("qr refs timeout restarts login socket without consuming reconnect budget", async () => {
  const events = [];
  let makeSocketCalls = 0;
  const sockets = [];

  const runtime = new WhatsAppRuntime({
    emit: (event) => {
      events.push(event);
    },
    ensureAuthDir: async () => {},
    restartDelayMs: 0,
    reconnectDelayMs: 0,
    maxReconnectAttempts: 1,
    loadBaileys: async () => ({
      makeWASocket() {
        makeSocketCalls += 1;
        const socket = {
          ev: createFakeEmitter(),
          ws: { close() {} },
          user: null,
        };
        sockets.push(socket);
        return socket;
      },
      useMultiFileAuthState: async () => ({
        state: {
          creds: {},
          keys: {},
        },
        saveCreds: async () => {},
      }),
      fetchLatestBaileysVersion: async () => ({ version: [2, 3000, 1] }),
      makeCacheableSignalKeyStore(keys) {
        return keys;
      },
    }),
  });

  await runtime.start("/tmp/agentos-whatsapp-runtime-test");
  sockets[0].ev.emit("connection.update", {
    connection: "close",
    lastDisconnect: {
      error: {
        message: "QR refs attempts ended",
        output: {
          statusCode: 408,
          payload: { statusCode: 408, error: "Request Time-out", message: "QR refs attempts ended" },
        },
      },
    },
  });
  await new Promise((resolve) => setTimeout(resolve, 0));

  assert.equal(makeSocketCalls, 2);
  assert.equal(events.some((event) => event.type === "status" && event.payload.state === "refreshing_qr"), true);
  assert.equal(runtime._reconnectAttempts, 0);
});

test("sendText resolves lid target to pn jid before sending", async () => {
  const sent = [];
  const runtime = new WhatsAppRuntime({
    emit: () => {},
    ensureAuthDir: async () => {},
    loadBaileys: async () => ({
      makeWASocket() {
        return {
          ev: createFakeEmitter(),
          ws: { close() {} },
          user: { id: "85293432086:1@s.whatsapp.net", lid: "121672866726017@lid" },
          signalRepository: {
            lidMapping: {
              async getPNForLID(jid) {
                if (jid === "121672866726017@lid") {
                  return "85293432086:49@s.whatsapp.net";
                }
                return null;
              },
            },
          },
          async sendMessage(target, payload) {
            sent.push({ target, payload });
            return { key: { id: "wamid-send-lid-1" } };
          },
        };
      },
      useMultiFileAuthState: async () => ({
        state: {
          creds: {},
          keys: {},
        },
        saveCreds: async () => {},
      }),
      fetchLatestBaileysVersion: async () => ({ version: [2, 3000, 1] }),
      makeCacheableSignalKeyStore(keys) {
        return keys;
      },
      normalizeMessageContent(message) {
        return message;
      },
      extractMessageContent(message) {
        return message;
      },
    }),
  });

  await runtime.start("/tmp/agentos-whatsapp-runtime-test");
  const result = await runtime.sendText("121672866726017@lid", "hello lid target");

  assert.equal(result.success, true);
  assert.equal(sent.length, 1);
  assert.equal(sent[0].target, "85293432086:49@s.whatsapp.net");
  assert.deepEqual(sent[0].payload, { text: "hello lid target" });
});

test("sendText falls back to self jid when target is self lid", async () => {
  const sent = [];
  const runtime = new WhatsAppRuntime({
    emit: () => {},
    ensureAuthDir: async () => {},
    loadBaileys: async () => ({
      makeWASocket() {
        return {
          ev: createFakeEmitter(),
          ws: { close() {} },
          user: { id: "85293432086:1@s.whatsapp.net", lid: "121672866726017:6@lid" },
          signalRepository: {
            lidMapping: {
              async getPNForLID() {
                return null;
              },
            },
          },
          async sendMessage(target, payload) {
            sent.push({ target, payload });
            return { key: { id: "wamid-send-self-lid-1" } };
          },
        };
      },
      useMultiFileAuthState: async () => ({
        state: {
          creds: {},
          keys: {},
        },
        saveCreds: async () => {},
      }),
      fetchLatestBaileysVersion: async () => ({ version: [2, 3000, 1] }),
      makeCacheableSignalKeyStore(keys) {
        return keys;
      },
      normalizeMessageContent(message) {
        return message;
      },
      extractMessageContent(message) {
        return message;
      },
    }),
  });

  await runtime.start("/tmp/agentos-whatsapp-runtime-test");
  const result = await runtime.sendText("121672866726017@lid", "hello self lid target");

  assert.equal(result.success, true);
  assert.equal(sent.length, 1);
  assert.equal(sent[0].target, "85293432086:1@s.whatsapp.net");
  assert.deepEqual(sent[0].payload, { text: "hello self lid target" });
});
