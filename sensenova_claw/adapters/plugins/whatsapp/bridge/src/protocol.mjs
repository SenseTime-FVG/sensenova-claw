export function writeEvent(event) {
  process.stdout.write(`${JSON.stringify(event)}\n`);
}

export async function readCommands(onCommand) {
  process.stdin.setEncoding("utf8");
  let buffer = "";

  for await (const chunk of process.stdin) {
    buffer += chunk;

    while (true) {
      const newlineIndex = buffer.indexOf("\n");
      if (newlineIndex < 0) {
        break;
      }

      const line = buffer.slice(0, newlineIndex).trim();
      buffer = buffer.slice(newlineIndex + 1);
      if (!line) {
        continue;
      }

      let command;
      try {
        command = JSON.parse(line);
      } catch (error) {
        writeEvent({
          type: "error",
          payload: { message: `Invalid JSON command: ${String(error)}` },
        });
        continue;
      }

      await onCommand(command);
    }
  }
}

export function writeResponse(id, payload) {
  writeEvent({ type: "response", id, payload });
}
