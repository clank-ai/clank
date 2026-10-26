// The agent panel's live state (design 0023 §3 and §5), built from the conversation stream's events: a `snapshot`
// replaces the conversation and its version; `message`, `part`, `delta` and `removed` change one thing each (a delta
// appends to its part's text as the model writes, a part replaces the part whole); `status` says whether the session
// works; `waiting` replaces the waits; `readout` is kept for the header and the foot; `session` names the session to
// open instead (the folder's newest changed). The version is the id of the last change applied, for `after` on
// reconnecting. A message the owner sends shows at once as pending (`sent`), ends when its text arrives as a message of
// the owner's (the mirror heard OpenCode), and is given back when the send fails (`failed`). `liveItems` draws the
// conversation's items, then the pending ones.

import {
  type Conversation,
  conversationItems,
  type Item,
  type PageMessage,
  type PagePart,
} from "./conversation";
import type { ServerEvent } from "./events";
import type { Readout } from "./readout";

/** A message sent and not yet heard back from the mirror. */
export interface Pending {
  id: string;
  text: string;
}

/** The live state. */
export interface Talk {
  conversation: Conversation | null;
  version: number;
  readout: Readout | null;
  pending: Pending[];
  reconnect: string | null;
}

export function emptyTalk(): Talk {
  return {
    conversation: null,
    version: 0,
    readout: null,
    pending: [],
    reconnect: null,
  };
}

/** The state after one event of the stream. */
export function applyEvent(talk: Talk, event: ServerEvent): Talk {
  const data = (event.data ?? {}) as Record<string, unknown>;
  const version = typeof event.id === "number" ? event.id : talk.version;
  switch (event.name) {
    case "snapshot": {
      const { version: given, ...conversation } =
        data as unknown as Conversation & { version?: number };
      const next = {
        ...talk,
        conversation,
        version: typeof given === "number" ? given : version,
      };
      return { ...next, pending: settled(next.pending, conversation) };
    }
    case "message":
      return settle(
        withMessages(talk, version, (messages) =>
          upsert(messages, data.message as PageMessage["info"]),
        ),
      );
    case "part": {
      const part = data.part as PagePart;
      return settle(
        withMessages(talk, version, (messages) =>
          messages.map((each) =>
            each.info.id === data.message
              ? { ...each, parts: placed(each.parts, part) }
              : each,
          ),
        ),
      );
    }
    case "delta":
      return withMessages(talk, version, (messages) =>
        messages.map((each) =>
          each.info.id === data.message
            ? {
                ...each,
                parts: appended(
                  each.parts,
                  String(data.part),
                  String(data.text ?? ""),
                ),
              }
            : each,
        ),
      );
    case "removed":
      return withMessages(talk, version, (messages) =>
        data.part
          ? messages.map((each) =>
              each.info.id === data.message
                ? {
                    ...each,
                    parts: each.parts.filter((part) => part.id !== data.part),
                  }
                : each,
            )
          : messages.filter((each) => each.info.id !== data.message),
      );
    case "status":
      return talk.conversation?.session
        ? {
            ...talk,
            version,
            conversation: {
              ...talk.conversation,
              session: {
                ...talk.conversation.session,
                busy: Boolean(data.busy),
              },
            },
          }
        : { ...talk, version };
    case "waiting":
      return talk.conversation
        ? {
            ...talk,
            version,
            conversation: {
              ...talk.conversation,
              waiting: data.waiting as Conversation["waiting"],
            },
          }
        : { ...talk, version };
    case "readout":
      return { ...talk, readout: (data.readout as Readout) ?? null };
    case "session":
      return { ...talk, reconnect: typeof data.id === "string" ? data.id : "" };
    default:
      return talk;
  }
}

/** A message the owner sent, shown at once. */
export function sent(talk: Talk, id: string, text: string): Talk {
  return { ...talk, pending: [...talk.pending, { id, text }] };
}

/** A send that failed: its text, to give back to the composer, and the state without it. */
export function failed(talk: Talk, id: string): [string, Talk] {
  const found = talk.pending.find((each) => each.id === id);
  return [
    found?.text ?? "",
    { ...talk, pending: talk.pending.filter((each) => each.id !== id) },
  ];
}

/** The conversation's items, then the pending messages as the owner's. */
export function liveItems(talk: Talk): Item[] {
  const items = talk.conversation
    ? conversationItems(talk.conversation.messages)
    : [];
  return [
    ...items,
    ...talk.pending.map((each) => ({
      kind: "owner" as const,
      id: each.id,
      text: each.text,
      pending: true,
    })),
  ];
}

function withMessages(
  talk: Talk,
  version: number,
  change: (messages: PageMessage[]) => PageMessage[],
): Talk {
  if (!talk.conversation) {
    return { ...talk, version };
  }
  return {
    ...talk,
    version,
    conversation: {
      ...talk.conversation,
      messages: change(talk.conversation.messages),
    },
  };
}

function upsert(
  messages: PageMessage[],
  info: PageMessage["info"],
): PageMessage[] {
  const found = messages.find((each) => each.info.id === info.id);
  const changed = found
    ? messages.map((each) =>
        each.info.id === info.id
          ? { ...each, info: { ...each.info, ...info } }
          : each,
      )
    : [...messages, { info, parts: [] }];
  return changed.sort(
    (a, b) =>
      (a.info.created ?? 0) - (b.info.created ?? 0) ||
      a.info.id.localeCompare(b.info.id),
  );
}

function placed(parts: PagePart[], part: PagePart): PagePart[] {
  const others = parts.filter((each) => each.id !== part.id);
  return [...others, part].sort((a, b) => a.id.localeCompare(b.id));
}

function appended(parts: PagePart[], id: string, text: string): PagePart[] {
  const found = parts.find((each) => each.id === id);
  if (!found) {
    return placed(parts, { id, type: "text", text, length: text.length });
  }
  const grown = `${found.text ?? ""}${text}`;
  return parts.map((each) =>
    each.id === id ? { ...each, text: grown, length: grown.length } : each,
  );
}

/** The pending messages still pending: those whose text no message of the owner's carries yet. */
function settled(
  pending: Pending[],
  conversation: Conversation | null,
): Pending[] {
  if (!conversation || !pending.length) {
    return pending;
  }
  const said = new Set(
    conversation.messages
      .filter((each) => each.info.role === "user")
      .map((each) =>
        each.parts
          .filter((part) => part.type === "text" && part.text)
          .map((part) => part.text)
          .join("\n\n"),
      ),
  );
  return pending.filter((each) => !said.has(each.text));
}

function settle(talk: Talk): Talk {
  return { ...talk, pending: settled(talk.pending, talk.conversation) };
}
