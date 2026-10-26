// Design 0002 §2.7 and §2.14: the extension's client sends the local token and names itself `vscode` on every call,
// a request that starts an operation carries its request key, the API's error shape becomes a `ClankError` with the
// service's own words, and a service that does not answer is `NotRunning`.

import assert from "node:assert/strict";
import { test } from "node:test";

import { ClankClient, ClankError, NotRunning } from "../src/core/client";

interface Call {
  url: string;
  init: RequestInit;
}

function answering(status: number, body: unknown, calls: Call[]): typeof fetch {
  return async (url: string | URL | Request, init?: RequestInit) => {
    calls.push({ url: String(url), init: init ?? {} });
    return new Response(JSON.stringify(body), {
      status,
      headers: { "Content-Type": "application/json" },
    });
  };
}

test("every call carries the token and names the client vscode", async () => {
  const calls: Call[] = [];
  const client = new ClankClient(
    "http://127.0.0.1:7720",
    "the-token",
    answering(200, [], calls),
  );
  assert.deepEqual(await client.get("questions"), []);
  const headers = calls[0]!.init.headers as Record<string, string>;
  assert.equal(calls[0]!.url, "http://127.0.0.1:7720/api/v1/questions");
  assert.equal(headers["Authorization"], "Bearer the-token");
  assert.equal(headers["X-Clank-Client"], "vscode");
});

test("a request that starts an operation carries its request key and its body", async () => {
  const calls: Call[] = [];
  const client = new ClankClient(
    "http://127.0.0.1:7720",
    "t",
    answering(200, { id: "op-1" }, calls),
  );
  await client.post("docker/start", undefined, "press-1");
  await client.post("questions/q-1/answer", { option: "stop" });
  const first = calls[0]!.init.headers as Record<string, string>;
  assert.equal(first["X-Clank-Request-Key"], "press-1");
  assert.equal(calls[1]!.init.body, JSON.stringify({ option: "stop" }));
});

test("the API's error shape becomes a ClankError with the service's own words", async () => {
  const refusal = {
    error: {
      code: "refused",
      message: "q-1 was already answered by you (console)",
      where: {},
    },
  };
  const client = new ClankClient(
    "http://127.0.0.1:7720",
    "t",
    answering(409, refusal, []),
  );
  await assert.rejects(
    client.post("questions/q-1/answer", { option: "stop" }),
    (error: unknown) => {
      assert.ok(error instanceof ClankError);
      assert.equal(error.message, "q-1 was already answered by you (console)");
      assert.equal(error.status, 409);
      return true;
    },
  );
});

test("a service that does not answer is NotRunning", async () => {
  const refused: typeof fetch = async () => {
    throw new TypeError("fetch failed");
  };
  const client = new ClankClient("http://127.0.0.1:7720", "t", refused);
  await assert.rejects(client.get("service"), NotRunning);
});

test("a stream route's messages come as they arrive, split or joined across the pieces read", async () => {
  const calls: string[] = [];
  const pieces = [
    'event: connected\ndata: {}\n\nid: 7\nevent: snapshot\ndata: {"session": nu',
    'll}\n\n: keepalive\n\nid: 8\nevent: delta\ndata: {"text": "a"}\n\n',
  ];
  const fetcher = async (url: string | URL | Request): Promise<Response> => {
    calls.push(String(url));
    const encoder = new TextEncoder();
    const body = new ReadableStream<Uint8Array>({
      start(controller) {
        for (const piece of pieces) controller.enqueue(encoder.encode(piece));
        controller.close();
      },
    });
    return new Response(body, {
      status: 200,
      headers: { "Content-Type": "text/event-stream" },
    });
  };
  const client = new ClankClient(
    "http://127.0.0.1:7720",
    "t",
    fetcher as typeof fetch,
  );
  const heard = [];
  for await (const event of client.stream(
    "agents/conversation/stream",
    { folder: "C:/work/paper", after: 6 },
    new AbortController().signal,
  )) {
    heard.push(event);
  }
  assert.deepEqual(heard, [
    { name: "connected", id: undefined, data: {} },
    { name: "snapshot", id: 7, data: { session: null } },
    { name: "delta", id: 8, data: { text: "a" } },
  ]);
  assert.equal(
    calls[0],
    "http://127.0.0.1:7720/api/v1/agents/conversation/stream?folder=C%3A%2Fwork%2Fpaper&after=6",
  );
});
