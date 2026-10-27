// Design 0002 §2.7 and §2.14: the extension's client sends the local token and names itself `vscode` on every call,
// a request that starts an operation carries its request key, the API's error shape becomes a `ClankError` with the
// service's own words, and a service that does not answer is `NotRunning`. Design 0004 §5 (revised 2026-10-26): every
// call has a time limit, a slow answer ending as `TimedOut` in words that say which.

import assert from "node:assert/strict";
import { test } from "node:test";

import { ClankClient, ClankError, inTime, NotRunning, TimedOut } from "../src/core/client";

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

test("a call the service does not answer in time ends, saying which and after how long", async () => {
  const signals: Array<AbortSignal | null | undefined> = [];
  const waiting: typeof fetch = async (_url: string | URL | Request, init?: RequestInit) =>
    new Promise<Response>((_resolve, reject) => {
      signals.push(init?.signal);
      init?.signal?.addEventListener("abort", () => reject(init.signal?.reason));
    });
  const client = new ClankClient("http://127.0.0.1:7720", "t", waiting);
  const quick = client.within(30);
  assert.equal(quick.url, client.url);
  // AbortSignal.timeout's timer does not keep Node's event loop alive, and nothing else here does: without this the
  // test runner sees the loop end while the call still waits, and cancels the file's remaining tests.
  const alive = setInterval(() => undefined, 1_000);
  try {
    await assert.rejects(quick.post("agents/prepare", { workspace: "paper" }), (error: unknown) => {
      assert.ok(error instanceof TimedOut, "not NotRunning: the service runs, it is slow");
      assert.equal(error.message, "the Clank service did not answer agents/prepare within 0.03 s");
      return true;
    });
  } finally {
    clearInterval(alive);
  }
  assert.ok(signals[0] instanceof AbortSignal);
  void client.get("service").catch(() => undefined);
  assert.ok(signals[1] instanceof AbortSignal, "every call has a limit, the client's own unless one is asked");
});

test("inTime ends a wait that takes too long, and passes on what comes in time", async () => {
  assert.equal(await inTime(Promise.resolve(7), 50, "the folder's workspace"), 7);
  await assert.rejects(inTime(new Promise<never>(() => undefined), 20, "the folder's workspace"), (error: unknown) => {
    assert.ok(error instanceof TimedOut);
    assert.equal(error.message, "the Clank service did not answer the folder's workspace within 0.02 s");
    return true;
  });
  await assert.rejects(inTime(Promise.reject(new NotRunning("down")), 50, "x"), NotRunning);
});
