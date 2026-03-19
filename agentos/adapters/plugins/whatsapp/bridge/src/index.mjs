import { writeEvent, readCommands, writeResponse } from "./protocol.mjs";
import { WhatsAppRuntime } from "./runtime.mjs";

const runtime = new WhatsAppRuntime({
  emit: (event) => writeEvent(event),
});

async function handleCommand(command) {
  const { id, type, payload = {} } = command;

  try {
    if (type === "start") {
      await runtime.start(payload.authDir, {
        typingIndicator: payload.typingIndicator,
      });
      writeResponse(id, { success: true });
      return;
    }

    if (type === "send_text") {
      writeResponse(id, await runtime.sendText(payload.target, payload.text));
      return;
    }

    if (type === "status") {
      writeResponse(id, runtime.getStatus());
      return;
    }

    if (type === "logout") {
      writeResponse(id, await runtime.logout());
      return;
    }

    if (type === "stop") {
      await runtime.stop();
      writeResponse(id, { success: true });
      process.exit(0);
    }

    writeResponse(id, { success: false, error: `Unsupported command: ${type}` });
  } catch (error) {
    writeResponse(id, {
      success: false,
      error: error instanceof Error ? error.message : String(error),
    });
    writeEvent({
      type: "error",
      payload: {
        message: error instanceof Error ? error.message : String(error),
      },
    });
  }
}

writeEvent({ type: "status", payload: { state: "booting", connected: false } });
readCommands(handleCommand).catch((error) => {
  writeEvent({
    type: "error",
    payload: { message: error instanceof Error ? error.message : String(error) },
  });
  process.exit(1);
});
