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
const packageRootCache = new Map();

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

function resolvePackageRoot(packageName) {
  const cachedRoot = packageRootCache.get(packageName);
  if (cachedRoot) {
    return cachedRoot;
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

function loadRenderer() {
  return workerRequire("@twick/renderer");
}

function getVisualizerProjectFile() {
  const projectFilePath = resolvePackageFile("@twick/visualizer", "dist/project.js");
  return path.relative(REPO_ROOT, projectFilePath);
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
        viteConfig: withTwickAliases(),
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
