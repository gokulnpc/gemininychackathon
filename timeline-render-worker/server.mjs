import http from "node:http";
import os from "node:os";
import path from "node:path";
import { promises as fsPromises } from "node:fs";
import { fileURLToPath } from "node:url";

const PORT = Number(process.env.PORT || 4001);
const __filename = fileURLToPath(import.meta.url);
const STARTUP_CONTEXT = {
  pid: process.pid,
  nodeEnv: process.env.NODE_ENV ?? "unset",
  port: PORT,
  revision: process.env.K_REVISION ?? "local",
  service: process.env.K_SERVICE ?? "local",
};
let defaultRenderTimelinePromise;
let processHandlersInstalled = false;

function logInfo(message, payload = {}) {
  console.info(`[RenderWorkerServer] ${message}`, { ...STARTUP_CONTEXT, ...payload });
}

function logError(message, payload = {}) {
  console.error(`[RenderWorkerServer] ${message}`, { ...STARTUP_CONTEXT, ...payload });
}

function installProcessHandlers() {
  if (processHandlersInstalled) {
    return;
  }
  processHandlersInstalled = true;

  process.on("uncaughtException", (error) => {
    logError("uncaughtException", {
      error: error instanceof Error ? error.stack ?? error.message : String(error),
    });
  });

  process.on("unhandledRejection", (reason) => {
    logError("unhandledRejection", {
      error: reason instanceof Error ? reason.stack ?? reason.message : String(reason),
    });
  });
}

async function loadDefaultRenderTimeline() {
  if (!defaultRenderTimelinePromise) {
    logInfo("lazy-loading render timeline module");
    defaultRenderTimelinePromise = import("./render-timeline.mjs")
      .then((module) => {
        if (typeof module.renderTimelineToFile !== "function") {
          throw new Error("render-timeline.mjs missing renderTimelineToFile export");
        }
        return module.renderTimelineToFile;
      })
      .catch((error) => {
        defaultRenderTimelinePromise = undefined;
        throw error;
      });
  }

  return defaultRenderTimelinePromise;
}

function sendJson(response, statusCode, payload) {
  response.writeHead(statusCode, { "Content-Type": "application/json" });
  response.end(JSON.stringify(payload));
}

export function createRequestHandler({ renderTimeline } = {}) {
  return async (request, response) => {
    if (!request.url || !request.headers.host) {
      sendJson(response, 400, { error: "Missing URL" });
      return;
    }

    const url = new URL(request.url, `http://${request.headers.host ?? "localhost"}`);

    if (request.method === "GET" && url.pathname === "/health") {
      sendJson(response, 200, { status: "ok" });
      return;
    }

    if (request.method === "POST" && url.pathname === "/render") {
      const chunks = [];
      for await (const chunk of request) {
        chunks.push(Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk));
      }

      let body;
      try {
        body = JSON.parse(Buffer.concat(chunks).toString("utf8"));
      } catch {
        sendJson(response, 400, { error: "Invalid JSON payload" });
        return;
      }

      const projectJson = body?.projectJson;
      if (!projectJson || typeof projectJson !== "object") {
        sendJson(response, 400, { error: "Missing projectJson" });
        return;
      }

      const tempOutputPath = path.join(
        os.tmpdir(),
        `timeline-render-${Date.now()}-${Math.random().toString(36).slice(2)}.mp4`,
      );

      try {
        const renderFn = renderTimeline ?? await loadDefaultRenderTimeline();
        await renderFn(projectJson, tempOutputPath);
        const videoBuffer = await fsPromises.readFile(tempOutputPath);
        response.writeHead(200, { "Content-Type": "video/mp4" });
        response.end(videoBuffer);
      } catch (error) {
        const message = error instanceof Error ? error.message : String(error);
        sendJson(response, 500, { error: message });
      } finally {
        await fsPromises.unlink(tempOutputPath).catch(() => {});
      }
      return;
    }

    sendJson(response, 404, { error: "Not found" });
  };
}

export function createServer({ renderTimeline } = {}) {
  return http.createServer(createRequestHandler({ renderTimeline }));
}

export function startServer({
  port = PORT,
  renderTimeline,
} = {}) {
  installProcessHandlers();
  logInfo("process-start");
  const server = createServer({ renderTimeline });
  server.on("error", (error) => {
    logError("server-error", {
      error: error instanceof Error ? error.stack ?? error.message : String(error),
    });
  });
  logInfo("before-listen", { listenPort: port });
  server.listen(port, () => {
    logInfo("listening", { listenPort: port });
  });
  return server;
}

if (process.argv[1] && path.resolve(process.argv[1]) === __filename) {
  startServer();
}
