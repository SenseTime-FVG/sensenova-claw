import { ensureAuthDir, resetAuthDir } from "./auth.mjs";

const DEFAULT_BAILEYS_VERSION = [2, 3000, 1];
const DEFAULT_BAILEYS_VERSION_FETCH_TIMEOUT_MS = 3000;

function createSilentLogger() {
  const logger = {
    trace() {},
    debug() {},
    info() {},
    warn() {},
    error() {},
    fatal() {},
    child() {
      return logger;
    },
  };
  return logger;
}

function formatDisconnectError(error) {
  if (!error) {
    return "connection closed";
  }

  const parts = [];
  const message = error?.message || String(error);
  if (message) {
    parts.push(message);
  }

  const statusCode = error?.output?.statusCode;
  if (statusCode != null) {
    parts.push(`statusCode=${statusCode}`);
  }

  const payload = error?.data ?? error?.output?.payload;
  if (payload && typeof payload === "object") {
    try {
      parts.push(`payload=${JSON.stringify(payload)}`);
    } catch {
      // ignore
    }
  }

  return parts.join(" | ");
}

function isQrRefsTimeout(error) {
  const message = error?.message || "";
  const payloadMessage = error?.data?.message ?? error?.output?.payload?.message ?? "";
  return String(message).includes("QR refs attempts ended") || String(payloadMessage).includes("QR refs attempts ended");
}

function isGroupJid(jid) {
  return typeof jid === "string" && jid.endsWith("@g.us");
}

async function resolveBaileysVersion(fetchLatestBaileysVersion, emitDebug, timeoutMs) {
  try {
    const result = await Promise.race([
      fetchLatestBaileysVersion(),
      new Promise((_, reject) => {
        setTimeout(() => reject(new Error("fetchLatestBaileysVersion timeout")), timeoutMs);
      }),
    ]);
    if (Array.isArray(result?.version) && result.version.length > 0) {
      return result.version;
    }
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    emitDebug(`fetchLatestBaileysVersion fallback: ${message}`);
  }
  return DEFAULT_BAILEYS_VERSION;
}

async function resolveOutboundTarget(sock, target) {
  if (typeof target !== "string" || !target.endsWith("@lid")) {
    return target;
  }
  const resolved = await sock?.signalRepository?.lidMapping?.getPNForLID?.(target);
  const selfLid = sock?._agentosSelfLid ?? sock?.user?.lid ?? null;
  const selfJid = sock?._agentosSelfJid ?? sock?.user?.id ?? null;
  if (!resolved && normalizeJidUser(target) === normalizeJidUser(selfLid) && selfJid) {
    return selfJid;
  }
  return resolved || target;
}

function describeMessageShape(message) {
  const rootKeys = message && typeof message === "object" ? Object.keys(message).slice(0, 12) : [];
  let normalizedKeys = [];
  let extractedKeys = [];
  try {
    const normalized = unwrapMessage(message, null);
    if (normalized && typeof normalized === "object") {
      normalizedKeys = Object.keys(normalized).slice(0, 12);
    }
  } catch {
    // ignore
  }
  try {
    const extracted = extractMessageNode(message, null);
    if (extracted && typeof extracted === "object") {
      extractedKeys = Object.keys(extracted).slice(0, 12);
    }
  } catch {
    // ignore
  }
  const extended =
    (message && typeof message === "object" ? message.extendedTextMessage : null)
    || (normalizedKeys.length > 0 ? unwrapMessage(message, null)?.extendedTextMessage : null);
  const extendedKeys =
    extended && typeof extended === "object" ? Object.keys(extended).slice(0, 12) : [];
  return `root_keys=${rootKeys.join(",") || "-"} normalized_keys=${normalizedKeys.join(",") || "-"} extracted_keys=${extractedKeys.join(",") || "-"} extended_keys=${extendedKeys.join(",") || "-"}`;
}

function normalizeJidUser(jid) {
  if (typeof jid !== "string" || !jid) {
    return "";
  }
  return jid.split("@", 1)[0].split(":", 1)[0];
}

function isSelfChatMessage(item, selfJid, selfLid) {
  if (!item?.key?.fromMe) {
    return false;
  }
  const selfUser = normalizeJidUser(selfJid);
  const selfLidUser = normalizeJidUser(selfLid);
  const remoteUser = normalizeJidUser(item?.key?.remoteJid);
  const participantUser = normalizeJidUser(item?.key?.participant);
  if (!selfUser || !remoteUser) {
    return false;
  }
  if (remoteUser !== selfUser) {
    if (selfLidUser && remoteUser === selfLidUser && !participantUser) {
      return true;
    }
    return false;
  }
  return !participantUser || participantUser === selfUser;
}

function extractMessageNode(message, baileysHelpers) {
  if (!message) {
    return null;
  }
  const extracted = baileysHelpers?.extractMessageContent?.(message);
  return extracted && typeof extracted === "object" ? extracted : null;
}

function extractCandidateText(candidate) {
  if (!candidate || typeof candidate !== "object") {
    return "";
  }
  const extended = candidate.extendedTextMessage;
  const raw = [
    candidate.conversation,
    extended?.text,
    extended?.matchedText,
    extended?.canonicalUrl,
    extended?.description,
    extended?.title,
    candidate?.imageMessage?.caption,
    candidate?.videoMessage?.caption,
    candidate?.documentMessage?.caption,
  ].find((value) => typeof value === "string" && value.trim());
  return typeof raw === "string" ? raw.trim() : "";
}

function extractText(message, baileysHelpers) {
  const normalized = unwrapMessage(message, baileysHelpers);
  if (!normalized) {
    return "";
  }
  const extracted = extractMessageNode(normalized, baileysHelpers);
  const candidates = [normalized, extracted && extracted !== normalized ? extracted : null];
  for (const candidate of candidates) {
    if (!candidate) {
      continue;
    }
    const text = extractCandidateText(candidate);
    if (text) {
      return text;
    }
  }
  return (
    ""
  );
}

function unwrapMessage(message, baileysHelpers) {
  const normalized = baileysHelpers?.normalizeMessageContent?.(message);
  if (normalized && typeof normalized === "object") {
    return normalized;
  }
  let current = message ?? null;
  while (current && typeof current === "object") {
    if (current.protocolMessage?.editedMessage?.message) {
      current = current.protocolMessage.editedMessage.message;
      continue;
    }
    if (current.ephemeralMessage?.message) {
      current = current.ephemeralMessage.message;
      continue;
    }
    if (current.viewOnceMessage?.message) {
      current = current.viewOnceMessage.message;
      continue;
    }
    if (current.viewOnceMessageV2?.message) {
      current = current.viewOnceMessageV2.message;
      continue;
    }
    if (current.viewOnceMessageV2Extension?.message) {
      current = current.viewOnceMessageV2Extension.message;
      continue;
    }
    if (current.documentWithCaptionMessage?.message) {
      current = current.documentWithCaptionMessage.message;
      continue;
    }
    if (current.editedMessage?.message) {
      current = current.editedMessage.message;
      continue;
    }
    if (current.deviceSentMessage?.message) {
      current = current.deviceSentMessage.message;
      continue;
    }
    break;
  }
  return current;
}

export class WhatsAppRuntime {
  constructor({
    emit,
    loadBaileys = () => import("@whiskeysockets/baileys"),
    ensureAuthDir: ensureAuthDirFn = ensureAuthDir,
    resetAuthDir: resetAuthDirFn = resetAuthDir,
    restartDelayMs = 300,
    reconnectDelayMs = 1000,
    maxReconnectAttempts = 3,
    versionFetchTimeoutMs = DEFAULT_BAILEYS_VERSION_FETCH_TIMEOUT_MS,
  }) {
    this._emit = emit;
    this._loadBaileys = loadBaileys;
    this._ensureAuthDir = ensureAuthDirFn;
    this._resetAuthDir = resetAuthDirFn;
    this._restartDelayMs = restartDelayMs;
    this._reconnectDelayMs = reconnectDelayMs;
    this._maxReconnectAttempts = maxReconnectAttempts;
    this._versionFetchTimeoutMs = versionFetchTimeoutMs;
    this._sock = null;
    this._authDir = null;
    this._isRecoveringAuth = false;
    this._isRestarting = false;
    this._isReconnecting = false;
    this._isRefreshingQr = false;
    this._reconnectAttempts = 0;
    this._recentOutboundMessageIds = new Map();
    this._status = {
      state: "idle",
      connected: false,
      jid: null,
      phone: null,
      lastError: null,
      lastQr: null,
      lastStatusCode: null,
      lastEvent: null,
      lastEventAt: null,
      debugMessage: null,
    };
    this._typingIndicator = "composing";
  }

  async start(authDir, options = {}) {
    this._authDir = authDir;
    this._typingIndicator = options.typingIndicator === "none" ? "none" : "composing";
    await this._ensureAuthDir(authDir);
    this._emitDebug(`start called with authDir=${authDir} typingIndicator=${this._typingIndicator}`);

    const baileys = await this._loadBaileys();
    const {
      extractMessageContent,
      fetchLatestBaileysVersion,
      makeCacheableSignalKeyStore,
      makeWASocket,
      normalizeMessageContent,
      useMultiFileAuthState,
    } = baileys;
    this._baileysHelpers = {
      extractMessageContent,
      normalizeMessageContent,
    };
    this._emitDebug("baileys imported");

    const { state, saveCreds } = await useMultiFileAuthState(authDir);
    this._emitDebug("auth state loaded");
    const version = await resolveBaileysVersion(
      fetchLatestBaileysVersion,
      (message) => this._emitDebug(message),
      this._versionFetchTimeoutMs,
    );
    const logger = createSilentLogger();

    this._sock = makeWASocket({
      auth: {
        creds: state.creds,
        keys: makeCacheableSignalKeyStore(state.keys, logger),
      },
      version,
      logger,
      printQRInTerminal: false,
      syncFullHistory: false,
      markOnlineOnConnect: false,
      browser: ["openclaw", "cli", "agentos"],
    });
    this._sock._agentosSelfJid = state?.creds?.me?.id ?? null;
    this._sock._agentosSelfLid = state?.creds?.me?.lid ?? null;
    this._emitDebug("socket created");

    this._status.state = "connecting";
    this._status.lastEvent = "start";
    this._status.lastEventAt = Date.now() / 1000;
    this._status.debugMessage = "socket created, waiting for connection.update";
    this._emit({
      type: "status",
      payload: { ...this._status },
    });

    this._sock.ev.on("creds.update", saveCreds);
    this._sock.ev.on("connection.update", (update) => {
      this._emitDebug(`connection.update: ${JSON.stringify({
        connection: update.connection ?? null,
        hasQr: Boolean(update.qr),
        isNewLogin: Boolean(update.isNewLogin),
        receivedPendingNotifications: Boolean(update.receivedPendingNotifications),
      })}`);

      if (update.qr) {
        this._status.lastQr = update.qr;
        void this._emitQr(update.qr);
      }

      if (update.connection === "open") {
        this._reconnectAttempts = 0;
        const jid = this._sock.user?.id ?? null;
        this._status = {
          ...this._status,
          state: "ready",
          connected: true,
          jid,
          phone: jid ? `+${String(jid).split("@", 1)[0].split(":", 1)[0]}` : null,
          lastError: null,
          lastStatusCode: null,
          lastEvent: "open",
          lastEventAt: Date.now() / 1000,
          debugMessage: "connection open",
        };
        this._emit({
          type: "ready",
          payload: {
            jid: this._status.jid,
            phone: this._status.phone,
          },
        });
        this._emit({
          type: "status",
          payload: { ...this._status },
        });
      } else if (update.connection === "close") {
        const statusCode = update.lastDisconnect?.error?.output?.statusCode;
        this._status = {
          ...this._status,
          state: "closed",
          connected: false,
          lastError: formatDisconnectError(update.lastDisconnect?.error),
          lastStatusCode: statusCode ?? null,
          lastEvent: "close",
          lastEventAt: Date.now() / 1000,
          debugMessage: "connection closed before ready",
        };
        this._emit({
          type: "status",
          payload: { ...this._status },
        });
        this._emit({
          type: "error",
          payload: {
            message: this._status.lastError,
            status_code: statusCode ?? null,
            debug_message: "connection closed before ready",
          },
        });

        if (statusCode === 515 && !this._isRestarting) {
          void this._restartAfterPairing();
          return;
        }

        if (statusCode === 408 && isQrRefsTimeout(update.lastDisconnect?.error) && !this._isRefreshingQr) {
          void this._refreshQrAfterTimeout();
          return;
        }

        if (statusCode === 408 && !this._isReconnecting) {
          void this._reconnectAfterTimeout();
          return;
        }

        if ((statusCode === 401 || statusCode === 405) && !this._isRecoveringAuth) {
          void this._recoverFromInvalidSession(statusCode);
        }
      }
    });

    this._sock.ev.on("messages.upsert", ({ messages, type }) => {
      this._emitDebug(
        `messages.upsert received: type=${type ?? "unknown"} count=${Array.isArray(messages) ? messages.length : 0}`,
      );
      for (const item of messages ?? []) {
        const messageId = item?.key?.id ?? "";
        if (messageId && this._recentOutboundMessageIds.has(messageId)) {
          this._recentOutboundMessageIds.delete(messageId);
          this._emitDebug(
            `messages.upsert ignored: outbound_echo message_id=${messageId} remote_jid=${item?.key?.remoteJid ?? "unknown"}`,
          );
          continue;
        }
        const isSelfChat = isSelfChatMessage(
          item,
          this._sock?.user?.id ?? null,
          this._sock?.user?.lid ?? null,
        );
        if (!item?.message || (item.key?.fromMe && !isSelfChat)) {
          this._emitDebug(
            `messages.upsert ignored: empty_or_self message_id=${messageId || "unknown"} remote_jid=${item?.key?.remoteJid ?? "unknown"} from_me=${Boolean(item?.key?.fromMe)}`,
          );
          continue;
        }

        const text = extractText(item.message, this._baileysHelpers);
        if (!text) {
          const protocolType = item?.message?.protocolMessage?.type ?? null;
          this._emitDebug(
            `messages.upsert ignored: no text content for message_id=${item.key?.id ?? "unknown"} remote_jid=${item.key?.remoteJid ?? "unknown"} protocol_type=${protocolType ?? "-"} ${describeMessageShape(item.message)}`,
          );
          continue;
        }

        const chatJid = item.key?.remoteJid ?? "";
        const participant = item.key?.participant ?? chatJid;
        this._emitDebug(
          `messages.upsert accepted: message_id=${item.key?.id ?? "unknown"} remote_jid=${chatJid} participant=${participant}`,
        );
        this._emit({
          type: "message",
          payload: {
            text,
            chat_jid: chatJid,
            chat_type: isGroupJid(chatJid) ? "group" : "p2p",
            sender_jid: participant,
            message_id: item.key?.id ?? "",
            push_name: item.pushName ?? null,
          },
        });
      }
    });
    this._sock.ev.on("messaging-history.set", (payload) => {
      this._emitDebug(
        `messaging-history.set received: chats=${payload?.chats?.length ?? 0} contacts=${payload?.contacts?.length ?? 0} messages=${payload?.messages?.length ?? 0} isLatest=${Boolean(payload?.isLatest)}`,
      );
    });
  }

  async _emitQr(qrText) {
    let dataUrl = null;
    try {
      const QRCode = (await import("qrcode")).default;
      dataUrl = await QRCode.toDataURL(qrText, {
        margin: 1,
        width: 320,
      });
    } catch (error) {
      this._status.lastError = error instanceof Error ? error.message : String(error);
    }

    this._emit({
      type: "qr",
      payload: {
        text: qrText,
        ascii: null,
        data_url: dataUrl,
        debug_message: "qr received from connection.update",
      },
    });
  }

  _emitDebug(message) {
    this._status.lastEvent = "debug";
    this._status.lastEventAt = Date.now() / 1000;
    this._status.debugMessage = message;
    this._emit({
      type: "debug",
      payload: { message },
    });
  }

  async sendText(target, text) {
    if (!this._sock) {
      throw new Error("WhatsApp runtime not started");
    }
    const resolvedTarget = await resolveOutboundTarget(this._sock, target);
    if (this._typingIndicator !== "none") {
      await this._sock.sendPresenceUpdate?.("composing", resolvedTarget);
    }
    const result = await this._sock.sendMessage(resolvedTarget, { text });
    const outboundId = result?.key?.id ?? null;
    if (outboundId) {
      this._recentOutboundMessageIds.set(outboundId, Date.now());
      const cleanupTimer = setTimeout(() => {
        this._recentOutboundMessageIds.delete(outboundId);
      }, 60_000);
      cleanupTimer.unref?.();
    }
    return {
      success: true,
      message_id: outboundId,
      target: resolvedTarget,
    };
  }

  getStatus() {
    return { ...this._status };
  }

  async logout() {
    if (!this._sock) {
      return { success: true, logged_out: false };
    }
    await this._sock.logout();
    this._status = {
      ...this._status,
      state: "logged_out",
      connected: false,
    };
    return { success: true, logged_out: true };
  }

  async stop() {
    if (this._sock?.ws) {
      try {
        this._sock.ws.close();
      } catch {
        // ignore
      }
    }
    this._sock = null;
    this._status = {
      ...this._status,
      state: "stopped",
      connected: false,
    };
  }

  async _recoverFromInvalidSession(statusCode) {
    if (!this._authDir) {
      return;
    }

    this._isRecoveringAuth = true;
    this._emit({
      type: "status",
      payload: {
        ...this._status,
        state: "recovering_auth",
        connected: false,
      },
    });
    this._emit({
      type: "error",
      payload: {
        message: `Session rejected by WhatsApp (statusCode=${statusCode}), clearing auth cache and retrying login.`,
      },
    });

    try {
      await this.stop();
      await this._resetAuthDir(this._authDir);
      this._status = {
        state: "idle",
        connected: false,
        jid: null,
        phone: null,
        lastError: null,
        lastQr: null,
      };
      await this.start(this._authDir);
    } catch (error) {
      this._status = {
        ...this._status,
        state: "closed",
        connected: false,
        lastError: `Auth recovery failed: ${error instanceof Error ? error.message : String(error)}`,
      };
      this._emit({
        type: "status",
        payload: { ...this._status },
      });
      this._emit({
        type: "error",
        payload: { message: this._status.lastError },
      });
    } finally {
      this._isRecoveringAuth = false;
    }
  }

  async _restartAfterPairing() {
    if (!this._authDir) {
      return;
    }

    this._isRestarting = true;
    this._emit({
      type: "status",
      payload: {
        ...this._status,
        state: "restarting",
        connected: false,
        debugMessage: "restart required after pairing, recreating socket",
      },
    });
    this._emit({
      type: "error",
      payload: {
        message: "WhatsApp asked for a restart after pairing (statusCode=515), recreating socket.",
      },
    });

    try {
      if (this._sock?.ws) {
        try {
          this._sock.ws.close();
        } catch {
          // ignore
        }
      }
      this._sock = null;
      await new Promise((resolve) => setTimeout(resolve, this._restartDelayMs));
      await this.start(this._authDir);
    } finally {
      this._isRestarting = false;
    }
  }

  async _reconnectAfterTimeout() {
    if (!this._authDir) {
      return;
    }
    if (this._reconnectAttempts >= this._maxReconnectAttempts) {
      this._status = {
        ...this._status,
        state: "reconnect_exhausted",
        connected: false,
        lastError: `WhatsApp reconnect exhausted after ${this._reconnectAttempts} attempts.`,
        lastEvent: "reconnect_exhausted",
        lastEventAt: Date.now() / 1000,
        debugMessage: "connection closed before ready",
      };
      this._emit({
        type: "status",
        payload: { ...this._status },
      });
      this._emit({
        type: "error",
        payload: {
          message: this._status.lastError,
        },
      });
      return;
    }

    this._isReconnecting = true;
    this._reconnectAttempts += 1;
    this._emit({
      type: "status",
      payload: {
        ...this._status,
        state: "reconnecting",
        connected: false,
        debugMessage: `connection timed out, reconnecting (${this._reconnectAttempts}/${this._maxReconnectAttempts})`,
      },
    });
    this._emit({
      type: "error",
      payload: {
        message: `WhatsApp connection timed out (statusCode=408), reconnecting (${this._reconnectAttempts}/${this._maxReconnectAttempts}).`,
      },
    });

    try {
      if (this._sock?.ws) {
        try {
          this._sock.ws.close();
        } catch {
          // ignore
        }
      }
      this._sock = null;
      await new Promise((resolve) => setTimeout(resolve, this._reconnectDelayMs));
      await this.start(this._authDir);
    } finally {
      this._isReconnecting = false;
    }
  }

  async _refreshQrAfterTimeout() {
    if (!this._authDir) {
      return;
    }

    this._isRefreshingQr = true;
    this._emit({
      type: "status",
      payload: {
        ...this._status,
        state: "refreshing_qr",
        connected: false,
        debugMessage: "qr expired, restarting login flow",
      },
    });
    this._emit({
      type: "error",
      payload: {
        message: "WhatsApp QR expired, refreshing login flow.",
      },
    });

    try {
      if (this._sock?.ws) {
        try {
          this._sock.ws.close();
        } catch {
          // ignore
        }
      }
      this._sock = null;
      await new Promise((resolve) => setTimeout(resolve, this._restartDelayMs));
      await this.start(this._authDir);
    } finally {
      this._isRefreshingQr = false;
    }
  }
}
