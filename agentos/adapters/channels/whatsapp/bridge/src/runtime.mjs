import { ensureAuthDir } from "./auth.mjs";

function isGroupJid(jid) {
  return typeof jid === "string" && jid.endsWith("@g.us");
}

function extractText(message) {
  return (
    message?.conversation ??
    message?.extendedTextMessage?.text ??
    message?.imageMessage?.caption ??
    message?.videoMessage?.caption ??
    ""
  );
}

export class WhatsAppRuntime {
  constructor({ emit }) {
    this._emit = emit;
    this._sock = null;
    this._status = {
      state: "idle",
      connected: false,
      jid: null,
      phone: null,
      lastError: null,
      lastQr: null,
    };
  }

  async start(authDir) {
    await ensureAuthDir(authDir);

    const baileys = await import("@whiskeysockets/baileys");
    const { makeWASocket, useMultiFileAuthState } = baileys;

    const { state, saveCreds } = await useMultiFileAuthState(authDir);

    this._sock = makeWASocket({
      auth: state,
      printQRInTerminal: false,
      syncFullHistory: false,
      markOnlineOnConnect: false,
      browser: ["AgentOS", "Chrome", "1.0"],
    });

    this._status.state = "connecting";
    this._emit({
      type: "status",
      payload: { ...this._status },
    });

    this._sock.ev.on("creds.update", saveCreds);
    this._sock.ev.on("connection.update", (update) => {
      if (update.qr) {
        this._status.lastQr = update.qr;
        this._emit({
          type: "qr",
          payload: { text: update.qr, ascii: null },
        });
      }

      if (update.connection === "open") {
        const jid = this._sock.user?.id ?? null;
        this._status = {
          ...this._status,
          state: "ready",
          connected: true,
          jid,
          phone: jid ? `+${String(jid).split("@", 1)[0].split(":", 1)[0]}` : null,
          lastError: null,
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
        this._status = {
          ...this._status,
          state: "closed",
          connected: false,
          lastError: update.lastDisconnect?.error?.message ?? "connection closed",
        };
        this._emit({
          type: "status",
          payload: { ...this._status },
        });
        this._emit({
          type: "error",
          payload: { message: this._status.lastError },
        });
      }
    });

    this._sock.ev.on("messages.upsert", ({ messages }) => {
      for (const item of messages ?? []) {
        if (!item?.message || item.key?.fromMe) {
          continue;
        }

        const text = extractText(item.message);
        if (!text) {
          continue;
        }

        const chatJid = item.key?.remoteJid ?? "";
        const participant = item.key?.participant ?? chatJid;
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
  }

  async sendText(target, text) {
    if (!this._sock) {
      throw new Error("WhatsApp runtime not started");
    }
    const result = await this._sock.sendMessage(target, { text });
    return {
      success: true,
      message_id: result?.key?.id ?? null,
      target,
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
}
