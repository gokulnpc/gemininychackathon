"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Download, Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";
import { useEditorExport } from "@/hooks/use-editor-export";
import type { ProjectJSON } from "@twick/timeline";
import { useTimelineContext } from "@twick/timeline";
import apiClient from "@/lib/apiClient";
import type { EditorExport } from "@/components/editor/types";

interface ExportButtonProps {
  projectId: string;
  serializeProjectJson?: (projectJson: ProjectJSON) => ProjectJSON;
  initialExport?: EditorExport | null;
}

export function ExportButton({ projectId, serializeProjectJson, initialExport }: ExportButtonProps) {
  const editorExport = useEditorExport(projectId, initialExport);
  const { editor } = useTimelineContext();
  const pendingQueuedSignatureRef = useRef<string | null>(null);
  const previousExportStateRef = useRef(editorExport.state);
  const [currentSignature, setCurrentSignature] = useState<string | null>(null);
  const [lastCompletedSignature, setLastCompletedSignature] = useState<string | null>(null);

  const getCanonicalProjectJson = useCallback(() => {
    const currentJson = editor.getProject();
    return serializeProjectJson ? serializeProjectJson(currentJson) : currentJson;
  }, [editor, serializeProjectJson]);

  useEffect(() => {
    const updateSignature = () => {
      try {
        setCurrentSignature(JSON.stringify(getCanonicalProjectJson()));
      } catch {
        setCurrentSignature(null);
      }
    };

    updateSignature();

    editor.on("element:added", updateSignature);
    editor.on("element:removed", updateSignature);
    editor.on("element:updated", updateSignature);
    editor.on("elements:removed", updateSignature);
    editor.on("track:added", updateSignature);
    editor.on("track:removed", updateSignature);
    editor.on("track:reordered", updateSignature);

    return () => {
      editor.off("element:added", updateSignature);
      editor.off("element:removed", updateSignature);
      editor.off("element:updated", updateSignature);
      editor.off("elements:removed", updateSignature);
      editor.off("track:added", updateSignature);
      editor.off("track:removed", updateSignature);
      editor.off("track:reordered", updateSignature);
    };
  }, [editor, getCanonicalProjectJson]);

  useEffect(() => {
    if (initialExport?.status === "completed" && currentSignature && !lastCompletedSignature) {
      setLastCompletedSignature(currentSignature);
    }
  }, [currentSignature, initialExport?.status, lastCompletedSignature]);

  useEffect(() => {
    const previousState = previousExportStateRef.current;

    if (
      editorExport.state === "completed" &&
      previousState !== "completed" &&
      pendingQueuedSignatureRef.current
    ) {
      setLastCompletedSignature(pendingQueuedSignatureRef.current);
      pendingQueuedSignatureRef.current = null;
    }

    if (editorExport.state === "failed" && previousState !== "failed") {
      pendingQueuedSignatureRef.current = null;
    }

    previousExportStateRef.current = editorExport.state;
  }, [editorExport.state]);

  const isFreshCompletedExport =
    editorExport.state === "completed" &&
    !!editorExport.downloadUrl &&
    !!currentSignature &&
    currentSignature === lastCompletedSignature;

  const handleExport = useCallback(async () => {
    const exportJson = getCanonicalProjectJson();
    const exportSignature = JSON.stringify(exportJson);

    if (
      isFreshCompletedExport
    ) {
      editorExport.download();
      return;
    }
    if (editorExport.isExporting) return;

    try {
      await apiClient.put(`/api/v1/projects/${projectId}/timeline`, exportJson);
      editorExport.replaceState({
        status: "queued",
        current_stage: "Queueing export",
        progress_pct: 0,
        error: null,
      });
      await editorExport.queueExport();
      pendingQueuedSignatureRef.current = exportSignature;
    } catch (err) {
      console.error("[ExportButton] Export failed:", err);
      const message = err instanceof Error ? err.message : "Failed to queue export";
      editorExport.setLocalError(message);
    }
  }, [editorExport, getCanonicalProjectJson, isFreshCompletedExport, projectId]);

  const buttonLabel = editorExport.isExporting
    ? editorExport.currentStage || `${Math.round(editorExport.progress * 100)}%`
    : isFreshCompletedExport
      ? "Download"
      : editorExport.state === "failed"
        ? "Retry Export"
        : "Export";

  return (
    <div className="flex items-center gap-2">
      {editorExport.errorMessage ? (
        <div
          className="hidden max-w-72 truncate rounded-full border border-destructive/30 bg-destructive/10 px-2.5 py-1 text-[11px] text-destructive md:block"
          title={editorExport.errorMessage}
        >
          {editorExport.errorMessage}
        </div>
      ) : null}
      {editorExport.isExporting && (
        <div className="hidden items-center gap-1.5 rounded-full border border-primary/30 bg-primary/10 px-2.5 py-1 text-[11px] md:flex">
          <div className="h-1.5 w-16 overflow-hidden rounded-full bg-muted">
            <div
              className="h-full rounded-full bg-primary transition-all duration-300"
              style={{ width: `${Math.round(editorExport.progress * 100)}%` }}
            />
          </div>
          <span className="text-foreground">
            {Math.round(editorExport.progress * 100)}%
          </span>
        </div>
      )}
      <button
        onClick={handleExport}
        disabled={editorExport.isExporting}
        title={editorExport.errorMessage ?? undefined}
        className={cn(
          "flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm font-medium transition-colors",
          isFreshCompletedExport
            ? "bg-accent text-accent-foreground"
            : editorExport.state === "failed"
              ? "bg-destructive/15 text-destructive"
              : "bg-secondary text-secondary-foreground hover:bg-secondary/80 disabled:opacity-50"
        )}
      >
        {editorExport.isExporting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Download className="h-4 w-4" />}
        {buttonLabel}
      </button>
    </div>
  );
}
