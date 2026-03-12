import http from "node:http";
import os from "node:os";
import path from "node:path";
import { promises as fsPromises } from "node:fs";

import { renderTimelineToFile } from "./render-timeline.mjs";

const PORT = Number(process.env.PORT || 4001);

function sendJson(response, statusCode, payload) {
  response.writeHead(statusCode, { "Content-Type": "application/json" });
  response.end(JSON.stringify(payload));
}

const server = http.createServer(async (request, response) => {
  if (!request.url) {
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
      await renderTimelineToFile(projectJson, tempOutputPath);
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
});

server.listen(PORT, () => {
  console.log(`timeline-render-worker listening on port ${PORT}`);
});
