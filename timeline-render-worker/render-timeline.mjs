import { promises as fsPromises } from "node:fs";
import fs from "node:fs";
import path from "node:path";
import { execSync } from "node:child_process";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const REPO_ROOT = path.resolve(__dirname, "..");
const FRONTEND_ROOT = path.join(REPO_ROOT, "frontend-sky");
const FRONTEND_PNPM_ROOT = path.join(FRONTEND_ROOT, "node_modules", ".pnpm");
const DEFAULT_RENDER_SIZE = { width: 576, height: 1024 };
const NAVIGATION_TIMEOUT_MS = 180_000;
const DEFAULT_FFMPEG_PATH = process.env.FFMPEG_PATH || "/usr/bin/ffmpeg";
const DEFAULT_FFPROBE_PATH = process.env.FFPROBE_PATH || "/usr/bin/ffprobe";
const DEFAULT_VITE_BASE_PORT = 9100;
const DEFAULT_CHROMIUM_ARGS = [
  "--no-sandbox",
  "--disable-setuid-sandbox",
  "--disable-dev-shm-usage",
];

process.env.FFMPEG_PATH = DEFAULT_FFMPEG_PATH;
process.env.FFPROBE_PATH = DEFAULT_FFPROBE_PATH;

const workerRequire = createRequire(import.meta.url);
const packageRootCache = new Map();
let hasConfiguredPuppeteerRuntime = false;
let hasConfiguredMediaTooling = false;

function pathExists(targetPath) {
  try {
    fs.accessSync(targetPath);
    return true;
  } catch {
    return false;
  }
}

function findPackageRoot(startPath, packageName) {
  let currentPath = path.dirname(startPath);

  while (currentPath !== path.dirname(currentPath)) {
    const packageJsonPath = path.join(currentPath, "package.json");
    if (pathExists(packageJsonPath)) {
      try {
        const packageJson = JSON.parse(fs.readFileSync(packageJsonPath, "utf8"));
        if (packageJson?.name === packageName) {
          return currentPath;
        }
      } catch {
        // Ignore malformed package.json while walking upward.
      }
    }
    currentPath = path.dirname(currentPath);
  }

  return null;
}

function getPackagePathParts(packageName) {
  return packageName.startsWith("@") ? packageName.split("/") : [packageName];
}

function findInstalledPackageRoot(packageName) {
  const searchPaths = workerRequire.resolve.paths(packageName) ?? [];
  const packagePathParts = getPackagePathParts(packageName);

  for (const searchPath of searchPaths) {
    const packageRoot = path.join(searchPath, ...packagePathParts);
    const packageJsonPath = path.join(packageRoot, "package.json");
    if (pathExists(packageJsonPath)) {
      return packageRoot;
    }
  }

  return null;
}

function resolvePackageRoot(packageName) {
  const cachedRoot = packageRootCache.get(packageName);
  if (cachedRoot) {
    return cachedRoot;
  }

  const installedPackageRoot = findInstalledPackageRoot(packageName);
  if (installedPackageRoot) {
    packageRootCache.set(packageName, installedPackageRoot);
    return installedPackageRoot;
  }

  try {
    const resolvedEntry = workerRequire.resolve(packageName);
    const packageRoot = findPackageRoot(resolvedEntry, packageName);
    if (packageRoot) {
      packageRootCache.set(packageName, packageRoot);
      return packageRoot;
    }
  } catch (error) {
    if (!pathExists(FRONTEND_PNPM_ROOT)) {
      const message = error instanceof Error ? error.message : String(error);
      throw new Error(`Cannot resolve ${packageName} from timeline-render-worker dependencies: ${message}`);
    }
  }

  const prefix = `${packageName.replace("/", "+")}@`;
  if (!pathExists(FRONTEND_PNPM_ROOT)) {
    throw new Error(`Cannot resolve ${packageName}: pnpm fallback store not found at ${FRONTEND_PNPM_ROOT}`);
  }

  const candidates = fs
    .readdirSync(FRONTEND_PNPM_ROOT)
    .filter((entry) => entry.startsWith(prefix))
    .sort()
    .reverse();

  for (const entry of candidates) {
    const packageBase = path.join(FRONTEND_PNPM_ROOT, entry, "node_modules", ...packageName.split("/"));
    const packageJsonPath = path.join(packageBase, "package.json");
    if (pathExists(packageJsonPath)) {
      packageRootCache.set(packageName, packageBase);
      return packageBase;
    }
  }

  throw new Error(`Cannot resolve ${packageName} from timeline-render-worker or frontend package stores`);
}

function resolvePackageFile(packageName, filePath = "") {
  const packageRoot = resolvePackageRoot(packageName);
  const resolved = filePath ? path.join(packageRoot, filePath) : packageRoot;

  if (!pathExists(resolved)) {
    throw new Error(`Resolved ${packageName} but missing expected file ${resolved}`);
  }

  return resolved;
}

function ensureMediaToolingConfigured() {
  if (hasConfiguredMediaTooling) {
    return;
  }

  const { ffmpegSettings } = workerRequire("@twick/ffmpeg");
  const fluentFfmpegModule = workerRequire("fluent-ffmpeg");
  const fluentFfmpeg = fluentFfmpegModule?.default ?? fluentFfmpegModule;

  ffmpegSettings.setFfmpegPath(DEFAULT_FFMPEG_PATH);
  ffmpegSettings.setFfprobePath(DEFAULT_FFPROBE_PATH);
  if (typeof fluentFfmpeg?.setFfmpegPath === "function") {
    fluentFfmpeg.setFfmpegPath(DEFAULT_FFMPEG_PATH);
  }
  if (typeof fluentFfmpeg?.setFfprobePath === "function") {
    fluentFfmpeg.setFfprobePath(DEFAULT_FFPROBE_PATH);
  }

  const configuredFfmpegPath = ffmpegSettings.getFfmpegPath();
  const configuredFfprobePath = ffmpegSettings.getFfprobePath();
  console.log("[RenderWorker] Configured media tooling", {
    ffmpegPath: configuredFfmpegPath,
    ffprobePath: configuredFfprobePath,
  });

  if (process.env.K_SERVICE && configuredFfprobePath !== DEFAULT_FFPROBE_PATH) {
    throw new Error(
      `Render worker must use system ffprobe at ${DEFAULT_FFPROBE_PATH}, got ${configuredFfprobePath}`,
    );
  }

  hasConfiguredMediaTooling = true;
}

export function applyPuppeteerPatches(puppeteerModule) {
  const puppeteer = puppeteerModule?.default ?? puppeteerModule;
  const { Browser, BrowserContext, Page } = puppeteerModule;

  // Log the detected export shape for Cloud Run diagnostics
  const hasLaunch = typeof puppeteer?.launch === "function";
  const hasBrowserClass = typeof Browser === "function";
  const hasBrowserPrototypeNewPage = typeof Browser?.prototype?.newPage === "function";
  const hasBrowserContext = typeof BrowserContext === "function";
  const hasPagePrototypeGoto = typeof Page?.prototype?.goto === "function";
  console.log("[RenderWorker] Puppeteer export shape", {
    hasLaunch,
    hasBrowserClass,
    hasBrowserPrototypeNewPage,
    hasBrowserContext,
    hasPagePrototypeGoto,
  });

  // launch is required — without it Twick cannot open Chromium at all
  const originalLaunch = puppeteer?.launch;
  if (typeof originalLaunch !== "function") {
    throw new Error("Could not patch Puppeteer launch: puppeteer.launch is unavailable");
  }

  puppeteer.launch = async function patchedLaunch(options = {}) {
    const incomingArgs = Array.isArray(options.args) ? options.args : [];
    const dedupedArgs = [...new Set([...DEFAULT_CHROMIUM_ARGS, ...incomingArgs])].filter(
      (arg) => arg !== "--single-process",
    );
    return originalLaunch.call(this, {
      ...options,
      protocolTimeout: NAVIGATION_TIMEOUT_MS,
      executablePath: options.executablePath ?? process.env.PUPPETEER_EXECUTABLE_PATH ?? undefined,
      args: dedupedArgs,
    });
  };
  console.log("[RenderWorker] Puppeteer launch patch applied");

  // newPage patch is best-effort — enhances page timeouts when available
  const originalNewPage = Browser?.prototype?.newPage;
  if (typeof originalNewPage === "function") {
    Browser.prototype.newPage = async function patchedNewPage(...args) {
      const page = await originalNewPage.apply(this, args);
      await page.setDefaultNavigationTimeout(NAVIGATION_TIMEOUT_MS);
      await page.setDefaultTimeout(NAVIGATION_TIMEOUT_MS);
      return page;
    };
    console.log("[RenderWorker] Puppeteer newPage patch applied");
  } else {
    console.warn(
      "[RenderWorker] Puppeteer newPage patch skipped: Browser.prototype.newPage unavailable",
    );
  }

  // BrowserContext.prototype.newPage patch — sets navigation timeout on every created page
  const originalBcNewPage = BrowserContext?.prototype?.newPage;
  if (typeof originalBcNewPage === "function") {
    BrowserContext.prototype.newPage = async function patchedBcNewPage(...args) {
      const page = await originalBcNewPage.apply(this, args);
      page.setDefaultNavigationTimeout(NAVIGATION_TIMEOUT_MS);
      page.setDefaultTimeout(NAVIGATION_TIMEOUT_MS);
      return page;
    };
    console.log("[RenderWorker] Puppeteer BrowserContext.newPage patch applied");
  } else {
    console.warn("[RenderWorker] Puppeteer BrowserContext.newPage patch skipped");
  }

  // Page.prototype.goto patch — injects timeout option directly at the call site.
  // Frame.goto extracts options.timeout; this ensures it always gets NAVIGATION_TIMEOUT_MS
  // unless the caller provides an explicit override.
  const originalGoto = Page?.prototype?.goto;
  if (typeof originalGoto === "function") {
    Page.prototype.goto = async function patchedGoto(url, options = {}) {
      return originalGoto.call(this, url, { timeout: NAVIGATION_TIMEOUT_MS, ...options });
    };
    console.log("[RenderWorker] Puppeteer Page.goto patch applied");
  } else {
    console.warn("[RenderWorker] Puppeteer Page.goto patch skipped");
  }
}

function ensurePuppeteerRuntimeConfigured() {
  if (hasConfiguredPuppeteerRuntime) {
    return;
  }

  const puppeteerModule = workerRequire("puppeteer");
  applyPuppeteerPatches(puppeteerModule);
  hasConfiguredPuppeteerRuntime = true;
}

function loadRenderer() {
  ensureMediaToolingConfigured();
  ensurePuppeteerRuntimeConfigured();
  return workerRequire("@twick/renderer");
}

function getVisualizerProjectFile() {
  const absoluteProjectFile = resolvePackageFile("@twick/visualizer", "dist/project.js");
  const relativeProjectFile = path.relative(REPO_ROOT, absoluteProjectFile);
  const posixRelativeProjectFile = relativeProjectFile.split(path.sep).join(path.posix.sep);

  if (!posixRelativeProjectFile || posixRelativeProjectFile.startsWith("..")) {
    throw new Error(`Visualizer project file must resolve inside repo root: ${absoluteProjectFile}`);
  }

  return posixRelativeProjectFile.startsWith(".")
    ? posixRelativeProjectFile
    : `./${posixRelativeProjectFile}`;
}

function readPackageJson(packageName) {
  const packageJsonPath = resolvePackageFile(packageName, "package.json");
  return JSON.parse(fs.readFileSync(packageJsonPath, "utf8"));
}

function resolvePackageEntryFile(packageName) {
  const packageJson = readPackageJson(packageName);
  const packageEntry =
    packageJson.module
    ?? packageJson.exports?.["."]?.import
    ?? packageJson.main;

  if (typeof packageEntry !== "string" || !packageEntry) {
    throw new Error(`Cannot determine entry file for ${packageName}`);
  }

  return resolvePackageFile(packageName, packageEntry);
}

function buildTwickViteAliases() {
  return {
    "@twick/renderer/lib/client/render": resolvePackageFile("@twick/renderer", "lib/client/render.js"),
    "@twick/core": resolvePackageEntryFile("@twick/core"),
    "@twick/2d": resolvePackageEntryFile("@twick/2d"),
  };
}

function withTwickAliases(viteConfig = {}) {
  const twickAliases = buildTwickViteAliases();
  const existingResolve = viteConfig.resolve ?? {};
  const existingAlias = existingResolve.alias;

  let alias;
  if (Array.isArray(existingAlias)) {
    alias = [
      ...Object.entries(twickAliases).map(([find, replacement]) => ({ find, replacement })),
      ...existingAlias,
    ];
  } else {
    alias = {
      ...(existingAlias ?? {}),
      ...twickAliases,
    };
  }

  return {
    ...viteConfig,
    resolve: {
      ...existingResolve,
      alias,
    },
  };
}

function readRenderSize(projectJson) {
  const width = Number(projectJson?.properties?.width);
  const height = Number(projectJson?.properties?.height);

  return {
    width: Number.isFinite(width) && width > 0 ? width : DEFAULT_RENDER_SIZE.width,
    height: Number.isFinite(height) && height > 0 ? height : DEFAULT_RENDER_SIZE.height,
  };
}

export async function renderTimelineToFile(projectJson, outputPath) {
  const renderContext = {
    exportId: projectJson?.editor_export?.export_id ?? projectJson?.exportId ?? null,
    outputPath,
  };
  console.log("[RenderWorker] Preparing render worker", renderContext);
  const { renderVideo } = loadRenderer();
  // Bare module specifier — rendererPlugin injects this verbatim as the import path in its
  // virtual module. Vite resolves "@twick/visualizer/dist/project.js" from /app/node_modules/
  // (because process.chdir(__dirname) sets Vite root to /app).
  const projectFile = "@twick/visualizer/dist/project.js";
  const outputDirectory = path.dirname(outputPath);
  const outputFileName = path.basename(outputPath);
  const renderSize = readRenderSize(projectJson);
  const executablePath = process.env.PUPPETEER_EXECUTABLE_PATH || undefined;
  const ffmpegPath = DEFAULT_FFMPEG_PATH;
  const ffprobePath = DEFAULT_FFPROBE_PATH;
  let renderStage = "initializing";

  await fsPromises.mkdir(outputDirectory, { recursive: true });

  const absoluteProjectFile = workerRequire.resolve(projectFile);
  if (!pathExists(absoluteProjectFile)) {
    throw new Error(`Visualizer project file not found: ${absoluteProjectFile}`);
  }

  console.log("[RenderWorker] Resolved render inputs", {
    ...renderContext,
    projectFile,
    absoluteProjectFile,
    outputPath,
    ffmpegPath,
    ffprobePath,
    executablePath,
    navigationTimeoutMs: NAVIGATION_TIMEOUT_MS,
    viteBasePort: DEFAULT_VITE_BASE_PORT,
    renderSize,
  });

  const previousCwd = process.cwd();
  process.chdir(__dirname);

  try {
    renderStage = "renderVideo";
    console.log("[RenderWorker] Starting renderVideo", {
      ...renderContext,
      outputDirectory,
      outputFileName,
      renderSize,
      viteBasePort: DEFAULT_VITE_BASE_PORT,
    });

    const renderedPath = await renderVideo({
      projectFile,
      variables: {
        input: projectJson,
        playerId: "server-export",
      },
      settings: {
        outDir: outputDirectory,
        outFile: outputFileName,
        workers: 1,
        logProgress: false,
        viteBasePort: DEFAULT_VITE_BASE_PORT,
        ffmpeg: {
          ffmpegPath,
          ffprobePath,
        },
        puppeteer: {
          headless: true,
          protocolTimeout: NAVIGATION_TIMEOUT_MS,
          ...(executablePath ? { executablePath } : {}),
          args: DEFAULT_CHROMIUM_ARGS,
        },
        projectSettings: {
          size: {
            x: renderSize.width,
            y: renderSize.height,
          },
          exporter: {
            name: "@twick/core/wasm-effects",
          },
        },
      },
    });

    console.log("[RenderWorker] renderVideo completed", {
      ...renderContext,
      renderedPath,
    });

    const resolvedRenderedPath = path.resolve(__dirname, renderedPath);
    const resolvedOutputPath = path.resolve(outputPath);
    if (resolvedRenderedPath !== resolvedOutputPath) {
      await fsPromises.copyFile(resolvedRenderedPath, resolvedOutputPath);
    }

    return resolvedOutputPath;
  } catch (error) {
    // Kill any Chromium processes left by this failed render.
    // containerConcurrency=1 guarantees only our own chrome is running.
    try {
      execSync("pkill -f chromium", { stdio: "ignore", timeout: 3000 });
    } catch (_) {}
    console.error("[RenderWorker] renderVideo failed", {
      ...renderContext,
      renderStage,
      projectFile,
      absoluteProjectFile,
      ffmpegPath,
      ffprobePath,
      executablePath,
      navigationTimeoutMs: NAVIGATION_TIMEOUT_MS,
      error: error instanceof Error ? error.stack ?? error.message : String(error),
    });
    throw error;
  } finally {
    process.chdir(previousCwd);
  }
}
