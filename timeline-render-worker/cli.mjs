import path from "node:path";
import { promises as fsPromises } from "node:fs";

import { renderTimelineToFile } from "./render-timeline.mjs";

async function main() {
  const [, , inputJsonPath, outputFilePath] = process.argv;

  if (!inputJsonPath || !outputFilePath) {
    console.error("Usage: node cli.mjs <input-json-path> <output-mp4-path>");
    process.exit(1);
  }

  const input = await fsPromises.readFile(path.resolve(inputJsonPath), "utf8");
  const projectJson = JSON.parse(input);
  await renderTimelineToFile(projectJson, path.resolve(outputFilePath));
}

main().catch((error) => {
  console.error(error instanceof Error ? error.stack ?? error.message : String(error));
  process.exit(1);
});
