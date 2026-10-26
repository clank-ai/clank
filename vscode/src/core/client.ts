// The extension's client of the Clank API (design 0002 §2.7, §2.14). Every call carries the local token and names the
// client `vscode`, so what it does is recorded as you (vscode); a request that starts an operation may carry a request
// key, so a click sent twice starts one. The API's one error shape becomes a `ClankError` with the service's own
// words, and a service that does not answer a `NotRunning`. `events` follows the event stream after a given event.

import { EventReader, type ServerEvent } from "./events";

/** The service does not answer. */
export class NotRunning extends Error {}

/** The service refused a request; the message is its own. */
export class ClankError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly code: string,
  ) {
    super(message);
  }
}

type Parameters = Record<string, string | number | boolean | undefined>;

/** A connection to the Clank API. */
export class ClankClient {
  constructor(
    readonly url: string,
    private readonly token: string,
    private readonly fetcher: typeof fetch = fetch,
  ) {}

  /** GET a route under /api/v1/. */
  get<T>(path: string, parameters: Parameters = {}): Promise<T> {
    return this.call<T>("GET", path + query(parameters));
  }

  /** DELETE a route under /api/v1/. */
  delete<T>(path: string): Promise<T> {
    return this.call<T>("DELETE", path);
  }

  /** POST to a route under /api/v1/, with a request key when it starts an operation. */
  post<T>(path: string, body?: unknown, requestKey?: string): Promise<T> {
    const headers: Record<string, string> = {
      "Content-Type": "application/json",
    };
    if (requestKey) {
      headers["X-Clank-Request-Key"] = requestKey;
    }
    return this.call<T>("POST", path, JSON.stringify(body ?? {}), headers);
  }

  /** The event stream's messages after the event `after` (or only new ones), until `signal` aborts it. */
  async *events(
    after: number | undefined,
    signal: AbortSignal,
  ): AsyncGenerator<ServerEvent> {
    yield* this.stream("events", { after }, signal);
  }

  /** A stream route's messages (the event stream, a conversation's stream: design 0023 §3), until `signal` aborts
   * it. */
  async *stream(
    path: string,
    parameters: Parameters,
    signal: AbortSignal,
  ): AsyncGenerator<ServerEvent> {
    let answer: Response;
    try {
      answer = await this.fetcher(
        `${this.url}/api/v1/${path}${query(parameters)}`,
        {
          headers: this.headers(),
          signal,
        },
      );
    } catch {
      if (signal.aborted) {
        return;
      }
      throw new NotRunning(`the Clank service at ${this.url} does not answer`);
    }
    if (!answer.ok || answer.body === null) {
      throw await refusal(answer);
    }
    const reader = new EventReader();
    const decoder = new TextDecoder();
    const pieces = answer.body.getReader();
    try {
      for (;;) {
        const { done, value } = await pieces.read();
        if (done) {
          return;
        }
        yield* reader.push(decoder.decode(value, { stream: true }));
      }
    } catch {
      if (!signal.aborted) {
        throw new NotRunning(
          `the Clank service at ${this.url} stopped answering`,
        );
      }
    } finally {
      pieces.releaseLock();
    }
  }

  private headers(extra: Record<string, string> = {}): Record<string, string> {
    return {
      Authorization: `Bearer ${this.token}`,
      "X-Clank-Client": "vscode",
      ...extra,
    };
  }

  private async call<T>(
    method: string,
    path: string,
    body?: string,
    headers: Record<string, string> = {},
  ): Promise<T> {
    let answer: Response;
    try {
      answer = await this.fetcher(`${this.url}/api/v1/${path}`, {
        method,
        headers: this.headers(headers),
        ...(body === undefined ? {} : { body }),
      });
    } catch {
      throw new NotRunning(`the Clank service at ${this.url} does not answer`);
    }
    if (!answer.ok) {
      throw await refusal(answer);
    }
    return (await answer.json()) as T;
  }
}

function query(parameters: Parameters): string {
  const pairs = Object.entries(parameters).filter(
    (pair): pair is [string, string | number | boolean] =>
      pair[1] !== undefined,
  );
  const written = pairs.map(([name, value]): [string, string] => [
    name,
    String(value),
  ]);
  return written.length ? `?${new URLSearchParams(written).toString()}` : "";
}

async function refusal(answer: Response): Promise<ClankError> {
  try {
    const shape = (await answer.json()) as {
      error?: { message?: string; code?: string };
    };
    if (shape.error?.message) {
      return new ClankError(
        shape.error.message,
        answer.status,
        shape.error.code ?? "http_error",
      );
    }
  } catch {
    // not the API's error shape: say what status it was
  }
  return new ClankError(
    `the service answered ${answer.status}`,
    answer.status,
    "http_error",
  );
}
