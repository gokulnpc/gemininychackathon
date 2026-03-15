"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { AlertCircle, ArrowLeft, Bot, Loader2, Save } from "lucide-react";
import dynamic from "next/dynamic";
import type { ProjectJSON } from "@twick/timeline";
import { INITIAL_TIMELINE_DATA, TimelineProvider } from "@twick/timeline";
import { LivePlayerProvider } from "@twick/live-player";
import "@twick/studio/dist/studio.css";

import { EditorBridge } from "@/components/editor/editor-bridge";
import { PlaybackDebugBridge } from "@/components/editor/playback-debug-bridge";
import type { EditorBridgeHandle, Project } from "@/components/editor/types";
import { cn } from "@/lib/utils";
import apiClient from "@/lib/apiClient";
import { useAuth } from "@/context/AuthContext";
import { useEditorAgent } from "@/hooks/use-editor-agent";
import { useEditorProjectSession } from "@/hooks/use-editor-project-session";
import { useVoiceEditSession } from "@/hooks/use-voice-edit-session";

const EditorShell = dynamic(
  () => import("@/components/editor/editor-shell").then((module) => ({ default: module.EditorShell })),
  { ssr: false },
);

export default function EditorPage() {
  const params = useParams();
  const projectId = params.id as string;
  const router = useRouter();

  const [project, setProject] = useState<Project | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [agentPanelOpen, setAgentPanelOpen] = useState(true);
  const { user, loading: authLoading } = useAuth();

  const agentBottomRef = useRef<HTMLDivElement>(null);
  const editorBridgeRef = useRef<EditorBridgeHandle | null>(null);
  const undoStackRef = useRef<ProjectJSON[]>([]);
  const [hasAgentUndo, setHasAgentUndo] = useState(false);
  const editorRootRef = useRef<HTMLDivElement>(null);
  const exportPortalRef = useRef<HTMLDivElement>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const isVoiceActiveRef = useRef(false);
  const focusedAssetRef = useRef<{ id: string; category: string } | null>(null);

  const captureEditorScreenshot = useCallback((): { image_b64: string; mime_type: string; width: number; height: number } | null => {
    const root = editorRootRef.current;
    if (!root) return null;
    const canvas = root.querySelector("canvas") as HTMLCanvasElement | null;
    if (!canvas) return null;
    try {
      const dataUrl = canvas.toDataURL("image/png");
      const b64 = dataUrl.split(",")[1];
      if (!b64) return null;
      return { image_b64: b64, mime_type: "image/png", width: canvas.width, height: canvas.height };
    } catch {
      return null;
    }
  }, []);

  const handleCanonicalProjectChange = useCallback((canonical: ProjectJSON) => {
    setProject((previous) => (previous ? { ...previous, project_json: canonical } : previous));
  }, []);

  const {
    editorProjectJson,
    playbackWarnings,
    saveState,
    saveStateLabel,
    applyEditorSession,
    serializeProjectJson,
    syncProjectJson,
    saveTimelineDebounced,
  } = useEditorProjectSession(projectId, editorRootRef, handleCanonicalProjectChange);

  const getCurrentCanonicalProjectJson = useCallback(() => {
    return serializeProjectJson(editorBridgeRef.current?.getProject() ?? null);
  }, [serializeProjectJson]);

  const applyLiveProjectJson = useCallback((json: ProjectJSON | null, changes?: Record<string, unknown>) => {
    if (!json) return;

    // Capture snapshot before applying for undo
    const currentSnapshot = editorBridgeRef.current?.getProject();
    if (currentSnapshot) {
      undoStackRef.current = [...undoStackRef.current.slice(-4), currentSnapshot];
      setHasAgentUndo(true);
    }

    const editorJson = applyEditorSession(json, "live_update");
    editorBridgeRef.current?.loadProject(editorJson ?? INITIAL_TIMELINE_DATA);
    saveTimelineDebounced(json);
    setProject((previous) => (previous ? {
      ...previous,
      ...(changes?.caption_style ? { caption_style: String(changes.caption_style) } : {}),
      ...(changes?.background_music ? { background_music: String(changes.background_music) } : {}),
      project_json: json,
    } : previous));

    if (wsRef.current?.readyState === WebSocket.OPEN) {
      const editorContext = editorBridgeRef.current?.getEditorContext() ?? null;
      const focusedAsset = focusedAssetRef.current;
      wsRef.current.send(JSON.stringify({
        type: "editor_state",
        project_json: json,
        editor_context: {
          ...editorContext,
          ...(agentPanelOpen ? { active_panel: "agent" } : {}),
          ...(focusedAsset ? { focused_asset_id: focusedAsset.id, focused_asset_category: focusedAsset.category } : {})
        },
      }));
    }
  }, [agentPanelOpen, applyEditorSession, saveTimelineDebounced]);

  const undoAgentEdit = useCallback(() => {
    const stack = undoStackRef.current;
    if (stack.length === 0) return;
    const previous = stack[stack.length - 1];
    undoStackRef.current = stack.slice(0, -1);
    setHasAgentUndo(undoStackRef.current.length > 0);
    editorBridgeRef.current?.loadProject(previous);
    saveTimelineDebounced(previous);
    setProject((prev) => prev ? { ...prev, project_json: previous } : prev);
  }, [saveTimelineDebounced]);

  const {
    agentMessages,
    agentInput,
    agentLoading,
    setAgentMessages,
    setAgentInput,
    sendAgentInstruction,
    confirmProposal,
    rejectProposal,
    revertLastEdit,
    hasUndo,
  } = useEditorAgent({
    projectId,
    agentPanelOpen,
    isVoiceActiveRef,
    wsRef,
    getCurrentCanonicalProjectJson,
    editorBridgeRef,
    applyLiveProjectJson,
    focusedAssetRef,
    onThumbnailApplied: (url) => setProject((prev) => prev ? { ...prev, thumbnail_url: url } : prev),
  });

  const voiceSession = useVoiceEditSession({
    projectId,
    agentPanelOpen,
    isVoiceActiveRef,
    wsRef,
    getCurrentCanonicalProjectJson,
    editorBridgeRef,
    applyLiveProjectJson,
    setAgentMessages,
    focusedAssetRef,
    onThumbnailApplied: (url) => setProject((prev) => prev ? { ...prev, thumbnail_url: url } : prev),
  });

  const INSPECT_KEYWORDS = /\b(what('s| is) wrong|look at|analyze|inspect|critique|feedback on|what do you (see|think)|how does this (look|feel)|what's weak|what is weak)\b/i;

  const sendAgentInstructionWithScreenshot = useCallback((instruction: string, displayText?: string) => {
    let screenshotCtx: { image_b64: string; mime_type: string; width: number; height: number } | undefined;
    if (INSPECT_KEYWORDS.test(instruction)) {
      screenshotCtx = captureEditorScreenshot() ?? undefined;
    }
    void sendAgentInstruction(instruction, displayText, screenshotCtx);
  }, [captureEditorScreenshot, sendAgentInstruction]);

  useEffect(() => {
    agentBottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [agentMessages]);

  const fetchProject = useCallback(async () => {
    if (authLoading) return;
    if (!user) {
      setLoadError("Not logged in");
      return;
    }
    try {
      const response = await apiClient.get(`/api/v1/projects/${projectId}`);
      const data = response.data as Project;
      const canonicalProjectJson = (data.project_json as ProjectJSON | null) ?? null;
      applyEditorSession(canonicalProjectJson, "initial_load");
      setProject({
        ...data,
        project_json: canonicalProjectJson,
      });
      setLoadError(null);
    } catch (error) {
      setLoadError(error instanceof Error ? error.message : "Failed to load project");
    }
  }, [applyEditorSession, projectId, authLoading, user]);

  useEffect(() => {
    void fetchProject();
  }, [fetchProject]);

  const timelineData = editorProjectJson ?? INITIAL_TIMELINE_DATA;

  if (loadError) {
    return (
      <div className="flex h-screen items-center justify-center bg-editor-toolbar text-editor-text-muted">
        <div className="text-center">
          <AlertCircle className="mx-auto mb-4 h-12 w-12 text-red-400/60" />
          <p className="mb-2 text-lg">{loadError}</p>
          <button
            onClick={() => router.push(`/projects/${projectId}`)}
            className="text-sm text-primary hover:underline"
          >
            ← Back to project
          </button>
        </div>
      </div>
    );
  }

  return (
    <div ref={editorRootRef} className="editor-theme flex h-screen min-h-0 flex-col overflow-hidden bg-editor-bg text-foreground">
      <div className="z-10 flex h-12 shrink-0 items-center justify-between border-b border-editor-border bg-editor-toolbar px-4">
        <div className="flex items-center gap-3">
          <button
            onClick={() => router.push(`/projects/${projectId}`)}
            className="flex items-center gap-1.5 text-sm text-muted-foreground transition-colors hover:text-foreground"
          >
            <ArrowLeft className="h-4 w-4" /> Back
          </button>
        </div>

        <div className="flex items-center gap-3">
          <div className="h-2 w-2 rounded-full bg-editor-accent" />
          <span className="max-w-xs truncate text-sm text-editor-text-muted">
            {project?.hook ?? "Untitled Project"}
          </span>
          {playbackWarnings.length > 0 && (
            <div
              title={playbackWarnings.map((warning) => `${warning.elementId}: ${warning.reason}`).join("\n")}
              className="hidden items-center gap-1.5 rounded-full border border-amber-500/25 bg-amber-500/10 px-2.5 py-1 text-[11px] text-amber-100 md:flex"
            >
              <AlertCircle className="h-3 w-3" />
              {playbackWarnings.length} playback issue{playbackWarnings.length === 1 ? "" : "s"}
            </div>
          )}
          <div
            className={cn(
              "hidden items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] md:flex",
              saveState === "error"
                ? "border-destructive/20 bg-destructive/10 text-destructive"
                : saveState === "saving"
                  ? "border-editor-border bg-editor-control text-muted-foreground"
                  : "border-primary/30 bg-primary/10 text-foreground",
            )}
          >
            {saveState === "saving" ? <Loader2 className="h-3 w-3 animate-spin" /> : <Save className="h-3 w-3" />}
            {saveStateLabel}
          </div>
        </div>

        <div className="flex items-center gap-2">
          <div ref={exportPortalRef} />
          <button
            onClick={() => setAgentPanelOpen((open) => !open)}
            className={cn(
              "flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm font-medium transition-colors",
              agentPanelOpen
                ? "bg-primary text-primary-foreground"
                : "bg-secondary text-secondary-foreground hover:bg-editor-control-hover",
            )}
          >
            <Bot className="h-4 w-4" />
            Agent
          </button>
        </div>
      </div>

      <div className="flex min-h-0 flex-1 overflow-hidden">
        <div className="min-h-0 flex-1 overflow-hidden">
          {project ? (
            <LivePlayerProvider>
              <TimelineProvider initialData={timelineData} contextId={projectId}>
                <EditorBridge ref={editorBridgeRef} />
                <PlaybackDebugBridge />
                <EditorShell
                  project={project}
                  agentPanelOpen={agentPanelOpen}
                  agentMessages={agentMessages}
                  agentInput={agentInput}
                  agentLoading={agentLoading}
                  isVoiceActive={voiceSession.isVoiceActive}
                  isScreenShareActive={voiceSession.isScreenShareActive}
                  agentBottomRef={agentBottomRef}
                  setAgentPanelOpen={setAgentPanelOpen}
                  setAgentInput={setAgentInput}
                  sendAgentInstruction={sendAgentInstructionWithScreenshot}
                  startVoiceEdit={voiceSession.startVoiceEdit}
                  stopVoiceEdit={voiceSession.stopVoiceEdit}
                  startScreenShare={voiceSession.startScreenShare}
                  stopScreenShare={voiceSession.stopScreenShare}
                  inspectScreen={voiceSession.inspectScreen}
                  onProjectJsonChange={syncProjectJson}
                  serializeProjectJson={(json) => serializeProjectJson(json) ?? json}
                  exportPortalRef={exportPortalRef}
                  confirmProposal={confirmProposal}
                  rejectProposal={rejectProposal}
                  revertLastEdit={undoAgentEdit}
                  hasUndo={hasAgentUndo}
                />
              </TimelineProvider>
            </LivePlayerProvider>
          ) : (
            <div className="flex h-full items-center justify-center">
              <Loader2 className="h-8 w-8 animate-spin text-white/30" />
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
