const assert = require("node:assert/strict");
const { EventEmitter } = require("node:events");
const test = require("node:test");
const { captureMiddleware, redact } = require("../dist");

test("redacts common secrets and bounds serialized content", () => {
  const result = redact({
    authorization: "Bearer top-secret",
    nested: { apiKey: "abc123", description: "🙂".repeat(1000) },
  }, 512);
  assert.equal(result.authorization, "[REDACTED]");
  assert.equal(result.nested.apiKey, "[REDACTED]");
  assert.ok(Buffer.byteLength(JSON.stringify(result)) < 600);
});

test("capture is asynchronous, body-off by default, and reports API failure", async () => {
  const originalFetch = global.fetch;
  let payload;
  let reported;
  global.fetch = async (_url, options) => {
    payload = JSON.parse(options.body);
    return { ok: false, status: 503 };
  };
  try {
    const response = new EventEmitter();
    response.setHeader = () => {};
    response.statusCode = 500;
    const request = {
      method: "GET",
      path: "/ping",
      body: { password: "must-not-be-captured" },
      get: (name) => name === "X-Request-ID" ? "request-123" : "",
    };
    const middleware = captureMiddleware({
      apiUrl: "https://capture.example.test",
      apiKey: "test-key",
      scenarioForRequest: () => "dependency",
      onCaptureError: (error) => { reported = error; },
    });
    middleware(request, response, () => {});
    response.emit("finish");
    await new Promise((resolve) => setImmediate(resolve));
    assert.equal(payload.path, "/ping");
    assert.equal(payload.request_id, "request-123");
    assert.equal(payload.body, undefined);
    assert.ok(reported instanceof Error);
  } finally {
    global.fetch = originalFetch;
  }
});

test("capture-service outage is reported without interrupting the application response", async () => {
  const originalFetch = global.fetch;
  let reported;
  let continued = false;
  global.fetch = async () => {
    throw new TypeError("Failed to fetch");
  };
  try {
    const response = new EventEmitter();
    response.setHeader = () => {};
    response.statusCode = 200;
    const request = {
      method: "GET",
      path: "/ping",
      get: () => "",
    };
    const middleware = captureMiddleware({
      apiUrl: "https://capture.example.test",
      apiKey: "test-key",
      scenarioForRequest: () => "latency",
      onCaptureError: (error) => { reported = error; },
    });

    middleware(request, response, () => { continued = true; });
    assert.equal(continued, true);
    response.emit("finish");
    await new Promise((resolve) => setImmediate(resolve));

    assert.ok(reported instanceof TypeError);
    assert.equal(response.statusCode, 200);
  } finally {
    global.fetch = originalFetch;
  }
});
