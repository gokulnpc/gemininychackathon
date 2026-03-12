import { promises as fsPromises } from "node:fs";
import fs from "node:fs";
import path from "node:path";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const REPO_ROOT = path.resolve(__dirname, "..");
const FRONTEND_ROOT = path.join(REPO_ROOT, "frontend-sky");
const FRONTEND_PNPM_ROOT = path.join(FRONTEND_ROOT, "node_modules", ".pnpm");
const DEFAULT_RENDER_SIZE = { width: 576, height: 1024 };

const workerRequire = createRequire(import.meta.url);

function pathExists(targetPath) {
  try {
    fs.accessSync(targetPath);
    return true;
  } catch {
    return false;
  }
}

function resolvePackageFile(packageName, filePath = "") {
  try {
    const resolvedBase = path.dirname(workerRequire.resolve(`${packageName}/package.json`));
    return filePath ? path.join(resolvedBase, filePath) : resolvedBase;
  } catch (error) {
    const prefix = `${packageName.replace("/", "+")}@`;
    if (!pathExists(FRONTEND_PNPM_ROOT)) {
      const message = error instanceof Error ? error.message : String(error);
      throw new Error(`Cannot resolve ${packageName} from timeline-render-worker dependencies: ${message}`);
    }

    const candidates = fs
      .readdirSync(FRONTEND_PNPM_ROOT)
      .filter((entry) => entry.startsWith(prefix))
      .sort()
      .reverse();

    for (const entry of candidates) {
      const packageBase = path.join(FRONTEND_PNPM_ROOT, entry, "node_modules", ...packageName.split("/"));
      const resolved = filePath ? path.join(packageBase, filePath) : packageBase;
      if (pathExists(resolved)) {
        return resolved;
      }
    }

    const message = error instanceof Error ? error.message : String(error);
    throw new Error(`Cannot resolve ${packageName} from timeline-render-worker or frontend package stores: ${message}`);
  }
}

function loadRenderer() {
  return workerRequire("@twick/renderer");
}

function getVisualizerProjectFile() {
  const projectFilePath = resolvePackageFile("@twick/visualizer", "dist/project.js");
  return path.relative(REPO_ROOT, projectFilePath);
}

function getRendererClientRenderFile() {
  return resolvePackageFile("@twick/renderer", "lib/client/render.js");
}

function withRendererClientAlias(viteConfig = {}) {
  const rendererClientRenderFile = getRendererClientRenderFile();
  const existingResolve = viteConfig.resolve ?? {};
  const existingAlias = existingResolve.alias;

  let alias;
  if (Array.isArray(existingAlias)) {
    alias = [
      { find: "@twick/renderer/lib/client/render", replacement: rendererClientRenderFile },
      ...existingAlias,
    ];
  } else {
    alias = {
      ...(existingAlias ?? {}),
      "@twick/renderer/lib/client/render": rendererClientRenderFile,
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
  const { renderVideo } = loadRenderer();
  const projectFile = getVisualizerProjectFile();
  const outputDirectory = path.dirname(outputPath);
  const outputFileName = path.basename(outputPath);
  const renderSize = readRenderSize(projectJson);

  await fsPromises.mkdir(outputDirectory, { recursive: true });

  const previousCwd = process.cwd();
  process.chdir(REPO_ROOT);

  try {
    const executablePath = process.env.PUPPETEER_EXECUTABLE_PATH || undefined;
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
        puppeteer: {
          headless: true,
          ...(executablePath ? { executablePath } : {}),
          args: ["--no-sandbox", "--disable-setuid-sandbox", "--single-process"],
        },
        projectSettings: {
          size: {
            x: renderSize.width,
            y: renderSize.height,
          },
          exporter: {
            name: "@twick/core/wasm",
          },
        },
        viteConfig: withRendererClientAlias(),
      },
    });

    const resolvedRenderedPath = path.resolve(REPO_ROOT, renderedPath);
    const resolvedOutputPath = path.resolve(outputPath);
    if (resolvedRenderedPath !== resolvedOutputPath) {
      await fsPromises.copyFile(resolvedRenderedPath, resolvedOutputPath);
    }

    return resolvedOutputPath;
  } finally {
    process.chdir(previousCwd);
  }
}
