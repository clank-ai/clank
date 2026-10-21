// The event stream's text read into messages (Server-Sent Events, decision 0017). A message ends at a blank line; it
// may arrive split across pieces, or several in one piece. A line starting with a colon is a comment (the service's
// keepalive) and is skipped. A kept event has its id; a live one (an operation's log line, who is connected) has none.

/**
 * One message of the event stream: its name (an event type, or the stream's own: `connected`, `reset`, `closing`), its
 * id when kept, its data.
 */
export interface ServerEvent {
  name: string;
  id: number | undefined;
  data: unknown;
}

/** Reads the stream's text piece by piece, returning each message once it is whole. */
export class EventReader {
  private buffer = "";

  /** Add a piece of the stream; returns the messages it completed. */
  push(piece: string): ServerEvent[] {
    this.buffer = (this.buffer + piece).replace(/\r\n/g, "\n");
    const messages: ServerEvent[] = [];
    let end = this.buffer.indexOf("\n\n");
    while (end >= 0) {
      const message = read(this.buffer.slice(0, end));
      if (message) {
        messages.push(message);
      }
      this.buffer = this.buffer.slice(end + 2);
      end = this.buffer.indexOf("\n\n");
    }
    return messages;
  }
}

function read(block: string): ServerEvent | undefined {
  const fields = new Map<string, string>();
  for (const line of block.split("\n")) {
    const colon = line.indexOf(":");
    if (!line || colon === 0) {
      continue;
    }
    const name = colon < 0 ? line : line.slice(0, colon);
    const value = colon < 0 ? "" : line.slice(colon + 1).replace(/^ /, "");
    fields.set(name, name === "data" && fields.has("data") ? `${fields.get("data")}\n${value}` : value);
  }
  const name = fields.get("event");
  if (!name) {
    return undefined;
  }
  const id = fields.get("id");
  return { name, id: id ? Number(id) : undefined, data: JSON.parse(fields.get("data") ?? "{}") as unknown };
}
