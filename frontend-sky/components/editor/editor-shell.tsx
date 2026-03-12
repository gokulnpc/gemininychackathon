"use client";

import type { RefObject } from "react";
import { useCallback, useEffect, useMemo } from "react";
import { createPortal } from "react-dom";
import { AgentPanel } from "@/components/editor/agent-panel";
import { EditorLeftRail } from "@/components/editor/editor-left-rail";
import { ExportButton } from "@/components/editor/export-button";
import { TimelineDock } from "@/components/editor/timeline-dock";
import type { AgentMessage, Project } from "@/components/editor/types";
import { useEditorShellState } from "@/components/editor/use-editor-shell-state";
import { VideoEditor } from "@twick/studio";
import {
  AudioElement,
  ImageElement,
  ProjectJSON,
  TextElement,
  TRACK_TYPES,
  useTimelineContext,
} from "@twick/timeline";
import { useLivePlayerContext } from "@twick/live-player";

const SCENE_SIZE = { width: 576, height: 1024 } as const;
const MEDIA_TRACK_PREFIX = "Media Inserts";

const clampEnd = (start: number, duration: number, totalDuration: number): number =>
  totalDuration > 0 ? Math.min(start + duration, totalDuration) : start + duration;

const sanitizeName = (name: string): string => {
  const trimmed = name.trim();
  if (!trimmed) return "Untitled";
  return trimmed.replace(/\.[a-z0-9]+$/i, "");
};

const rangesOverlap = (start: number, end: number, otherStart: number, otherEnd: number): boolean =>
  otherStart < end && otherEnd > start;

interface EditorShellProps {
  project: Project;
  agentPanelOpen: boolean;
  agentMessages: AgentMessage[];
  agentInput: string;
  agentLoading: boolean;
  isVoiceActive: boolean;
  agentBottomRef: RefObject<HTMLDivElement | null>;
  setAgentPanelOpen: (open: boolean) => void;
  setAgentInput: (value: string) => void;
  sendAgentInstruction: (instruction: string) => void;
  startVoiceEdit: () => void | Promise<void>;
  onProjectJsonChange: (projectJson: ProjectJSON) => void;
  serializeProjectJson: (projectJson: ProjectJSON) => ProjectJSON;
  exportPortalRef?: RefObject<HTMLDivElement | null>;
}

export function EditorShell({
  project,
  agentPanelOpen,
  agentMessages,
  agentInput,
  agentLoading,
  isVoiceActive,
  agentBottomRef,
  setAgentPanelOpen,
  setAgentInput,
  sendAgentInstruction,
  startVoiceEdit,
  onProjectJsonChange,
  serializeProjectJson,
  exportPortalRef,
}: EditorShellProps) {
  const { activeLeftPanel, setActiveLeftPanel } = useEditorShellState("media");
  const { editor, totalDuration } = useTimelineContext();
  const livePlayer = useLivePlayerContext() as { currentTime?: number } | null;

  const commitEditorProject = useCallback(() => {
    onProjectJsonChange(editor.getProject());
  }, [editor, onProjectJsonChange]);

  useEffect(() => {
    const handleMutation = () => {
      commitEditorProject();
    };

    editor.on("element:added", handleMutation);
    editor.on("element:removed", handleMutation);
    editor.on("element:updated", handleMutation);
    editor.on("elements:removed", handleMutation);
    editor.on("track:added", handleMutation);
    editor.on("track:removed", handleMutation);
    editor.on("track:reordered", handleMutation);

    return () => {
      editor.off("element:added", handleMutation);
      editor.off("element:removed", handleMutation);
      editor.off("element:updated", handleMutation);
      editor.off("elements:removed", handleMutation);
      editor.off("track:added", handleMutation);
      editor.off("track:removed", handleMutation);
      editor.off("track:reordered", handleMutation);
    };
  }, [commitEditorProject, editor]);

  const currentTime = useMemo(() => livePlayer?.currentTime ?? 0, [livePlayer?.currentTime]);

  const ensureTrack = useCallback((name: string, type: string) => {
    return editor.getTrackByName(name) ?? editor.addTrack(name, type);
  }, [editor]);

  const getAvailableMediaTrack = useCallback((start: number, end: number) => {
    const tracks = editor.getTimelineData()?.tracks ?? [];
    const mediaTracks = tracks
      .filter((track) => track.getType() === TRACK_TYPES.SCENE)
      .filter((track) => {
        const name = track.getName();
        return new RegExp(`^${MEDIA_TRACK_PREFIX}(?: \\d+)?$`).test(name);
      })
      .sort((a, b) => {
        const aMatch = a.getName().match(/(\d+)$/);
        const bMatch = b.getName().match(/(\d+)$/);
        const aIndex = aMatch ? Number(aMatch[1]) : 1;
        const bIndex = bMatch ? Number(bMatch[1]) : 1;
        return aIndex - bIndex;
      });

    const freeTrack = mediaTracks.find((track) =>
      !track
        .getElements()
        .some((element) => rangesOverlap(start, end, element.getStart(), element.getEnd()))
    );

    if (freeTrack) {
      return freeTrack;
    }

    const nextIndex = mediaTracks.reduce((max, track) => {
      const match = track.getName().match(/(\d+)$/);
      const index = match ? Number(match[1]) : 1;
      return Math.max(max, index);
    }, 0) + 1;

    return editor.addTrack(`${MEDIA_TRACK_PREFIX} ${nextIndex}`, TRACK_TYPES.SCENE);
  }, [editor]);

  const insertText = useCallback(async (text: string, variant: "hook" | "lower-third" | "callout") => {
    const track = ensureTrack("Text Overlays", TRACK_TYPES.ELEMENT);
    const start = currentTime;
    const duration = variant === "hook" ? 3.2 : variant === "lower-third" ? 4.5 : 3.6;
    const end = clampEnd(start, duration, totalDuration);

    const element = new TextElement(text, {
      fill: variant === "hook" ? "#f8fafc" : "#ffffff",
      fontSize: variant === "hook" ? 56 : variant === "lower-third" ? 36 : 42,
      fontWeight: variant === "hook" ? 800 : 700,
      textAlign: "center",
      fontFamily: "Geist",
    });

    element
      .setName(variant === "hook" ? "Hook Title" : variant === "lower-third" ? "Lower Third" : "Callout")
      .setStart(start)
      .setEnd(end)
      .setPosition(
        variant === "lower-third"
          ? { x: 112, y: 860 }
          : variant === "callout"
            ? { x: 120, y: 180 }
            : { x: 84, y: 136 }
      );

    await editor.addElementToTrack(track, element);
  }, [currentTime, editor, ensureTrack, totalDuration]);

  const insertImage = useCallback(async (src: string, label: string) => {
    const start = currentTime;
    const end = clampEnd(start, 4.5, totalDuration);
    const track = getAvailableMediaTrack(start, end);
    const element = new ImageElement(src, SCENE_SIZE)
      .setName(sanitizeName(label))
      .setStart(start)
      .setEnd(end)
      .setObjectFit("contain");

    try {
      await editor.addElementToTrack(track, element);
    } catch (error) {
      console.warn("[EditorShell] Failed to insert media element:", error);
    }
  }, [currentTime, editor, getAvailableMediaTrack, totalDuration]);

  const insertAudio = useCallback(async (src: string, label: string) => {
    const track = ensureTrack("Imported Audio", TRACK_TYPES.AUDIO);
    const start = currentTime;
    const end = clampEnd(start, Math.max(totalDuration - start, 4), totalDuration);
    const element = new AudioElement(src)
      .setName(sanitizeName(label))
      .setStart(start)
      .setEnd(end)
      .setVolume(0.4);

    await editor.addElementToTrack(track, element);
  }, [currentTime, editor, ensureTrack, totalDuration]);

  return (
    <div className="flex h-full min-h-0 overflow-hidden">
      {/* Portal the ExportButton into the toolbar (outside provider tree) */}
      {exportPortalRef?.current &&
        createPortal(
          <ExportButton
            projectId={project.project_id}
            projectHook={project.hook}
            serializeProjectJson={serializeProjectJson}
          />,
          exportPortalRef.current,
        )}

      {/* Left rail */}
      <EditorLeftRail
        project={project}
        activePanel={activeLeftPanel}
        setActivePanel={setActiveLeftPanel}
        agentLoading={agentLoading}
        isVoiceActive={isVoiceActive}
        onQuickAction={sendAgentInstruction}
        onInsertText={insertText}
        onInsertImage={insertImage}
        onInsertAudio={insertAudio}
      />

      {/* Center column: canvas + timeline */}
      <div className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden">
        {/* Canvas area */}
        <div className="editor-canvas-wrapper flex min-h-0 flex-1 items-center justify-center overflow-hidden bg-editor-bg">
          <div className="editor-preview-shell">
            <VideoEditor
              defaultPlayControls={false}
              editorConfig={{
                canvasMode: true,
                videoProps: {
                  width: SCENE_SIZE.width,
                  height: SCENE_SIZE.height,
                  backgroundColor: "var(--editor-bg)",
                },
                fps: 30,
              }}
            />
          </div>
        </div>

        {/* Timeline */}
        <TimelineDock />
      </div>

      {/* Agent panel */}
      <AgentPanel
        agentPanelOpen={agentPanelOpen}
        agentMessages={agentMessages}
        agentInput={agentInput}
        agentLoading={agentLoading}
        isVoiceActive={isVoiceActive}
        agentBottomRef={agentBottomRef}
        setAgentPanelOpen={setAgentPanelOpen}
        setAgentInput={setAgentInput}
        sendAgentInstruction={sendAgentInstruction}
        startVoiceEdit={startVoiceEdit}
      />
    </div>
  );
}
