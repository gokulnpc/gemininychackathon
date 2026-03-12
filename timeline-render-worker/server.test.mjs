import test from "node:test";
import assert from "node:assert/strict";
import { Readable, Writable } from "node:stream";
import { promises as fsPromises } from "node:fs";

import { createRequestHandler } from "./server.mjs";

class MockResponse extends Writable {
  constructor() {
    super();
    this.statusCode = 200;
    this.headers = {};
    this.bodyChunks = [];
  }

  writeHead(statusCode, headers = {}) {
    this.statusCode = statusCode;
    this.headers = {
      ...this.headers,
      ...headers,
    };
    return this;
  }

  _write(chunk, _encoding, callback) {
    this.bodyChunks.push(Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk));
    callback();
  }

  bodyAsBuffer() {
    return Buffer.concat(this.bodyChunks);
  }

  bodyAsJson() {
    return JSON.parse(this.bodyAsBuffer().toString("utf8"));
  }
}

async function invoke(handler, {
  method = "GET",
  url = "/",
  headers = { host: "localhost" },
  body,
} = {}) {
  const request = Readable.from(body ? [body] : []);
  request.method = method;
  request.url = url;
  request.headers = headers;

  const response = new MockResponse();
  const finished = new Promise((resolve, reject) => {
    response.on("finish", resolve);
    response.on("error", reject);
  });

  await handler(request, response);
  await finished;
  return response;
}

test("GET /health returns ok", async () => {
  const handler = createRequestHandler({ renderTimeline: async () => {} });
  const response = await invoke(handler, { url: "/health" });
  assert.equal(response.statusCode, 200);
  assert.deepEqual(response.bodyAsJson(), { status: "ok" });
});

test("POST /render rejects invalid json", async () => {
  const handler = createRequestHandler({ renderTimeline: async () => {} });
  const response = await invoke(handler, {
    method: "POST",
    url: "/render",
    headers: { host: "localhost", "content-type": "application/json" },
    body: "{invalid",
  });

  assert.equal(response.statusCode, 400);
  assert.deepEqual(response.bodyAsJson(), { error: "Invalid JSON payload" });
});

test("POST /render rejects missing projectJson", async () => {
  const handler = createRequestHandler({ renderTimeline: async () => {} });
  const response = await invoke(handler, {
    method: "POST",
    url: "/render",
    headers: { host: "localhost", "content-type": "application/json" },
    body: JSON.stringify({}),
  });

  assert.equal(response.statusCode, 400);
  assert.deepEqual(response.bodyAsJson(), { error: "Missing projectJson" });
});

test("POST /render returns mp4 payload from renderer", async () => {
  const calls = [];
  const videoPayload = Buffer.from("fake-mp4");

  const handler = createRequestHandler({
    renderTimeline: async (projectJson, outputPath) => {
      calls.push({ projectJson, outputPath });
      await fsPromises.writeFile(outputPath, videoPayload);
    },
  });

  const input = { properties: { width: 576, height: 1024 } };
  const response = await invoke(handler, {
    method: "POST",
    url: "/render",
    headers: { host: "localhost", "content-type": "application/json" },
    body: JSON.stringify({ projectJson: input }),
  });

  assert.equal(response.statusCode, 200);
  assert.equal(response.headers["Content-Type"], "video/mp4");
  assert.deepEqual(response.bodyAsBuffer(), videoPayload);
  assert.equal(calls.length, 1);
  assert.deepEqual(calls[0].projectJson, input);
  assert.match(calls[0].outputPath, /timeline-render-.*\.mp4$/);
});

test("POST /render surfaces renderer failures", async () => {
  const handler = createRequestHandler({
    renderTimeline: async () => {
      throw new Error("boom");
    },
  });

  const response = await invoke(handler, {
    method: "POST",
    url: "/render",
    headers: { host: "localhost", "content-type": "application/json" },
    body: JSON.stringify({ projectJson: { ok: true } }),
  });

  assert.equal(response.statusCode, 500);
  assert.deepEqual(response.bodyAsJson(), { error: "boom" });
});

test("unknown route returns not found", async () => {
  const handler = createRequestHandler({ renderTimeline: async () => {} });
  const response = await invoke(handler, { url: "/unknown" });
  assert.equal(response.statusCode, 404);
  assert.deepEqual(response.bodyAsJson(), { error: "Not found" });
});
