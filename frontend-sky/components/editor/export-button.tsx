"use client";

import { useCallback } from "react";
import { Download, Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";
import { useBrowserExport } from "@/hooks/use-browser-export";
import type { ProjectJSON } from "@twick/timeline";
import { useTimelineContext } from "@twick/timeline";
import apiClient from "@/lib/apiClient";

interface ExportButtonProps {
  projectId: string;
  projectHook?: string;
  serializeProjectJson?: (projectJson: ProjectJSON) => ProjectJSON;
}

export function ExportButton({ projectId, projectHook, serializeProjectJson }: ExportButtonProps) {
  const browserExport = useBrowserExport();
  const { editor } = useTimelineContext();

  const handleExport = useCallback(async () => {
    if (browserExport.isExporting) return;
    try {
      const currentJson = editor.getProject();
      const exportJson = serializeProjectJson ? serializeProjectJson(currentJson) : currentJson;
      await apiClient.put(`/api/v1/projects/${projectId}/timeline`, exportJson);
      await browserExport.startExport(exportJson, `${projectHook ?? "video"}-export.mp4`);
    } catch (err) {
      console.error("[ExportButton] Export failed:", err);
    }
  }, [browserExport, editor, projectId, projectHook, serializeProjectJson]);

  return (
    <div className="flex items-center gap-2">
      {browserExport.isExporting && (
        <div className="hidden items-center gap-1.5 rounded-full border border-primary/30 bg-primary/10 px-2.5 py-1 text-[11px] md:flex">
          <div className="h-1.5 w-16 overflow-hidden rounded-full bg-muted">
            <div
              className="h-full rounded-full bg-primary transition-all duration-300"
              style={{ width: `${Math.round(browserExport.progress * 100)}%` }}
            />
          </div>
          <span className="text-foreground">{Math.round(browserExport.progress * 100)}%</span>
        </div>
      )}
      <button
        onClick={handleExport}
        disabled={browserExport.isExporting}
        className={cn(
          "flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm font-medium transition-colors",
          browserExport.state === "done"
            ? "bg-accent text-accent-foreground"
            : browserExport.state === "error"
              ? "bg-destructive/15 text-destructive"
              : "bg-secondary text-secondary-foreground hover:bg-secondary/80 disabled:opacity-50"
        )}
      >
        {browserExport.isExporting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Download className="h-4 w-4" />}
        {browserExport.isExporting
          ? `${Math.round(browserExport.progress * 100)}%`
          : browserExport.state === "done"
            ? "Exported!"
            : browserExport.state === "error"
              ? "Failed"
              : "Export"}
      </button>
    </div>
  );
}
