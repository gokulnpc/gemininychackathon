"use client";

import { useCallback, useMemo, useState } from "react";
import { useBrowserRenderer } from "@twick/browser-render";
import type { ProjectJSON } from "@twick/timeline";

const SCENE_SIZE = { width: 576, height: 1024 } as const;
const WASM_ASSET_PATH = "/mp4-wasm.wasm";
const WASM_MISSING_ERROR =
  "Export assets are missing. Ensure mp4-wasm.wasm is copied to the app public directory.";

export interface UseBrowserExportReturn {
  startExport: (projectJson: ProjectJSON, filename?: string) => Promise<void>;
  progress: number;
  isExporting: boolean;
  videoBlob: Blob | null;
  state: "idle" | "exporting" | "done" | "error";
  errorMessage: string | null;
}

export function useBrowserExport(): UseBrowserExportReturn {
  const [preflightError, setPreflightError] = useState<string | null>(null);
  const {
    render,
    progress,
    isRendering,
    videoBlob,
    download,
    error,
  } = useBrowserRenderer({
    width: SCENE_SIZE.width,
    height: SCENE_SIZE.height,
    fps: 30,
    quality: "high" as never,
    autoDownload: false,
  });

  const ensureExportAssets = useCallback(async () => {
    let response: Response;
    try {
      response = await fetch(WASM_ASSET_PATH, {
        cache: "no-store",
        credentials: "same-origin",
      });
    } catch {
      throw new Error(WASM_MISSING_ERROR);
    }

    if (!response.ok) {
      throw new Error(WASM_MISSING_ERROR);
    }

    const contentType = response.headers.get("content-type")?.toLowerCase() ?? "";
    if (contentType.includes("text/html")) {
      throw new Error(WASM_MISSING_ERROR);
    }
  }, []);

  const startExport = useCallback(
    async (projectJson: ProjectJSON, filename = "twick-export.mp4") => {
      if (isRendering) return;
      setPreflightError(null);
      try {
        await ensureExportAssets();
        await render({
          input: {
            properties: {
              width: SCENE_SIZE.width,
              height: SCENE_SIZE.height,
              fps: 30,
            },
            tracks: projectJson.tracks as never,
          },
        });
        download(filename);
      } catch (err) {
        console.error("[useBrowserExport] Render failed:", err);
        const message = err instanceof Error ? err.message : String(err);
        setPreflightError(message || WASM_MISSING_ERROR);
      }
    },
    [download, ensureExportAssets, isRendering, render],
  );

  const errorMessage = useMemo(() => {
    if (preflightError) return preflightError;
    return error ? String(error) : null;
  }, [error, preflightError]);

  return {
    startExport,
    progress,
    isExporting: isRendering,
    videoBlob,
    state: isRendering ? "exporting" : errorMessage ? "error" : videoBlob ? "done" : "idle",
    errorMessage,
  };
}
