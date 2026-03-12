"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import apiClient from "@/lib/apiClient";
import type { EditorExport } from "@/components/editor/types";

type EditorExportStatus = "idle" | "queued" | "in_progress" | "completed" | "failed";

const DEFAULT_EXPORT_STATE: Required<Pick<EditorExport, "status">> & EditorExport = {
  status: "idle",
  export_id: null,
  current_stage: null,
  progress_pct: null,
  queued_at: null,
  started_at: null,
  completed_at: null,
  download_url: null,
  thumbnail_url: null,
  error: null,
};

function normalizeEditorExport(state?: EditorExport | null): EditorExport & { status: EditorExportStatus } {
  const status = state?.status;
  return {
    ...DEFAULT_EXPORT_STATE,
    ...state,
    status:
      status === "queued" ||
      status === "in_progress" ||
      status === "completed" ||
      status === "failed"
        ? status
        : "idle",
  };
}

export interface UseEditorExportReturn {
  state: EditorExportStatus;
  progress: number;
  currentStage: string | null;
  downloadUrl: string | null;
  errorMessage: string | null;
  isExporting: boolean;
  queueExport: () => Promise<void>;
  download: () => void;
  replaceState: (nextState: EditorExport | null | undefined) => void;
  setLocalError: (message: string | null) => void;
}

export function useEditorExport(projectId: string, initialExport?: EditorExport | null): UseEditorExportReturn {
  const [exportState, setExportState] = useState(() => normalizeEditorExport(initialExport));
  const [localError, setLocalError] = useState<string | null>(null);

  useEffect(() => {
    setExportState(normalizeEditorExport(initialExport));
    setLocalError(null);
  }, [
    initialExport?.completed_at,
    initialExport?.current_stage,
    initialExport?.download_url,
    initialExport?.error,
    initialExport?.export_id,
    initialExport?.progress_pct,
    initialExport?.queued_at,
    initialExport?.started_at,
    initialExport?.status,
    initialExport?.thumbnail_url,
    projectId,
  ]);

  const fetchStatus = useCallback(async () => {
    const response = await apiClient.get(`/api/v1/projects/${projectId}/export-status`);
    const nextState = normalizeEditorExport(response.data as EditorExport);
    setExportState(nextState);
    return nextState;
  }, [projectId]);

  useEffect(() => {
    const shouldPoll = exportState.status === "queued" || exportState.status === "in_progress";
    if (!shouldPoll) {
      return;
    }

    let cancelled = false;

    const pollOnce = async () => {
      try {
        await fetchStatus();
        if (!cancelled) {
          setLocalError(null);
        }
      } catch (error) {
        if (!cancelled) {
          const message = error instanceof Error ? error.message : "Failed to poll export status";
          setLocalError(message);
        }
      }
    };

    void pollOnce();
    const intervalId = window.setInterval(() => {
      void pollOnce();
    }, 2000);

    return () => {
      cancelled = true;
      window.clearInterval(intervalId);
    };
  }, [exportState.status, fetchStatus]);

  const queueExport = useCallback(async () => {
    setLocalError(null);
    try {
      const response = await apiClient.post(`/api/v1/projects/${projectId}/queue-export`);
      const payload = response.data as EditorExport & { export_id: string; status: EditorExportStatus };
      setExportState(normalizeEditorExport({
        current_stage: "Queued for export",
        progress_pct: 0,
        error: null,
        ...payload,
      }));
    } catch (error) {
      const message = error instanceof Error ? error.message : "Failed to queue export";
      setExportState((previousState) =>
        normalizeEditorExport({
          ...previousState,
          status: "failed",
          current_stage: "Export queue failed",
          progress_pct: null,
          error: message,
        })
      );
      throw error;
    }
  }, [projectId]);

  const download = useCallback(() => {
    const downloadUrl = exportState.download_url;
    if (!downloadUrl) {
      setLocalError("Export is not ready to download yet.");
      return;
    }

    if (typeof window !== "undefined") {
      window.open(downloadUrl, "_blank", "noopener,noreferrer");
    }
  }, [exportState.download_url]);

  const replaceState = useCallback((nextState: EditorExport | null | undefined) => {
    setExportState(normalizeEditorExport(nextState));
  }, []);

  const errorMessage = useMemo(() => localError || exportState.error || null, [exportState.error, localError]);

  return {
    state: exportState.status,
    progress: Math.max(0, Math.min(1, (exportState.progress_pct ?? 0) / 100)),
    currentStage: exportState.current_stage ?? null,
    downloadUrl: exportState.download_url ?? null,
    errorMessage,
    isExporting: exportState.status === "queued" || exportState.status === "in_progress",
    queueExport,
    download,
    replaceState,
    setLocalError,
  };
}
