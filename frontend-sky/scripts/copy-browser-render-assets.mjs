import { execFileSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";

const appRoot = process.cwd();
const publicDir = path.join(appRoot, "public");

function copyIfNewer(src, dest) {
  if (!fs.existsSync(src)) return false;
  const destDir = path.dirname(dest);
  if (!fs.existsSync(destDir)) {
    fs.mkdirSync(destDir, { recursive: true });
  }
  if (!fs.existsSync(dest) || fs.statSync(src).mtimeMs > fs.statSync(dest).mtimeMs) {
    fs.copyFileSync(src, dest);
    return true;
  }
  return false;
}

function resolveFfmpegSource() {
  const directCandidates = [
    path.join(appRoot, "node_modules", "@ffmpeg", "core", "dist", "esm"),
    path.join(appRoot, "node_modules", "@ffmpeg", "core", "dist"),
  ];

  for (const candidate of directCandidates) {
    if (
      fs.existsSync(path.join(candidate, "ffmpeg-core.js")) &&
      fs.existsSync(path.join(candidate, "ffmpeg-core.wasm"))
    ) {
      return candidate;
    }
  }

  const pnpmDir = path.join(appRoot, "node_modules", ".pnpm");
  if (!fs.existsSync(pnpmDir)) return null;

  const entries = fs.readdirSync(pnpmDir, { withFileTypes: true });
  for (const entry of entries) {
    if (!entry.isDirectory() || !entry.name.startsWith("@ffmpeg+core@")) continue;
    const candidate = path.join(
      pnpmDir,
      entry.name,
      "node_modules",
      "@ffmpeg",
      "core",
      "dist",
      "esm",
    );
    if (
      fs.existsSync(path.join(candidate, "ffmpeg-core.js")) &&
      fs.existsSync(path.join(candidate, "ffmpeg-core.wasm"))
    ) {
      return candidate;
    }
  }

  return null;
}

execFileSync(process.execPath, ["node_modules/@twick/browser-render/scripts/copy-public-assets.js"], {
  cwd: appRoot,
  stdio: "inherit",
});

const ffmpegSource = resolveFfmpegSource();
if (!ffmpegSource) {
  console.warn("[twick-browser-render] Could not resolve @ffmpeg/core for same-origin export assets.");
  process.exit(0);
}

const copied = [];
if (
  copyIfNewer(
    path.join(ffmpegSource, "ffmpeg-core.js"),
    path.join(publicDir, "ffmpeg", "ffmpeg-core.js"),
  )
) {
  copied.push("ffmpeg-core.js");
}
if (
  copyIfNewer(
    path.join(ffmpegSource, "ffmpeg-core.wasm"),
    path.join(publicDir, "ffmpeg", "ffmpeg-core.wasm"),
  )
) {
  copied.push("ffmpeg-core.wasm");
}

if (copied.length > 0) {
  console.log(`[twick-browser-render] Copied FFmpeg assets to ${publicDir}/ffmpeg: ${copied.join(", ")}`);
}
