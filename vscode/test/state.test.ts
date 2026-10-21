// Design 0002 §1 and §2.3: what the extension shows is read from the API and kept current by events: a question's
// events change the questions, Docker's change Docker, the service's change the service, a slot's change the slots,
// and a preset's settings change the presets.

import assert from "node:assert/strict";
import { test } from "node:test";

import { touched } from "../src/core/state";

test("each event names the topics it changes", () => {
  assert.deepEqual(touched("question.answered"), ["questions"]);
  assert.deepEqual(touched("docker.changed"), ["docker"]);
  assert.deepEqual(touched("service.started"), ["service"]);
  assert.deepEqual(touched("operation.step"), []);
  assert.deepEqual(touched("runtime.slot"), ["slots"]);
  assert.deepEqual(touched("settings.changed", "preset"), ["presets"]);
  assert.deepEqual(touched("settings.changed", "host"), []);
});
