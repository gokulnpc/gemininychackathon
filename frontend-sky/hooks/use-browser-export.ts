"use client";

import { useCallback } from "react";
import { useBrowserRenderer } from "@twick/browser-render";
import type { ProjectJSON } from "@twick/timeline";

const SCENE_SIZE = { width: 576, height: 1024 } as const;

export interface UseBrowserExportReturn {
  startExport: (projectJson: ProjectJSON, filename?: string) => Promise<void>;
  progress: number;
  isExporting: boolean;
  videoBlob: Blob | null;
  state: "idle" | "exporting" | "done" | "error";
  errorMessage: string | null;
}

export function useBrowserExport(): UseBrowserExportReturn {
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

  const startExport = useCallback(
    async (projectJson: ProjectJSON, filename = "twick-export.mp4") => {
      if (isRendering) return;
      try {
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
      }
    },
    [isRendering, render, download],
  );

  return {
    startExport,
    progress,
    isExporting: isRendering,
    videoBlob,
    state: isRendering ? "exporting" : error ? "error" : videoBlob ? "done" : "idle",
    errorMessage: error ? String(error) : null,
  };
}
