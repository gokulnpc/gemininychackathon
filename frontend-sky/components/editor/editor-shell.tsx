"use client";

import type { RefObject } from "react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { AgentPanel } from "@/components/editor/agent-panel";
import { EditorLeftRail } from "@/components/editor/editor-left-rail";
import { ExportButton } from "@/components/editor/export-button";
import { TimelineDock } from "@/components/editor/timeline-dock";
import type { AgentMessage, Project, TextInsertConfig, TextInsertVariant } from "@/components/editor/types";
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
const IMPORTED_AUDIO_TRACK_PREFIX = "Imported Audio";
const DEFAULT_TEXT_FONT = "Poppins";

const TEXT_INSERT_PRESETS: Record<
  TextInsertVariant,
  {
    duration: number;
    fontFamily: string;
    fontSize: number;
    fontWeight: number;
    name: string;
    position: { x: number; y: number };
    fill: string;
    textAlign: "center";
  }
> = {
  freeform: {
    duration: 4,
    fontFamily: DEFAULT_TEXT_FONT,
    fontSize: 48,
    fontWeight: 700,
    name: "Text Overlay",
    position: { x: 96, y: 452 },
    fill: "#ffffff",
    textAlign: "center",
  },
  hook: {
    duration: 3.2,
    fontFamily: "Impact",
    fontSize: 56,
    fontWeight: 800,
    name: "Hook Title",
    position: { x: 84, y: 136 },
    fill: "#f8fafc",
    textAlign: "center",
  },
  "lower-third": {
    duration: 4.5,
    fontFamily: DEFAULT_TEXT_FONT,
    fontSize: 36,
    fontWeight: 700,
    name: "Lower Third",
    position: { x: 112, y: 860 },
    fill: "#ffffff",
    textAlign: "center",
  },
  callout: {
    duration: 3.6,
    fontFamily: "Rubik",
    fontSize: 42,
    fontWeight: 700,
    name: "Callout",
    position: { x: 120, y: 180 },
    fill: "#ffffff",
    textAlign: "center",
  },
};

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
  const previewHostRef = useRef<HTMLDivElement | null>(null);
  const [previewHostSize, setPreviewHostSize] = useState({ width: 0, height: 0 });

  const measurePreviewHost = useCallback((host: HTMLDivElement) => {
    const styles = window.getComputedStyle(host);
    const paddingX = parseFloat(styles.paddingLeft) + parseFloat(styles.paddingRight);
    const paddingY = parseFloat(styles.paddingTop) + parseFloat(styles.paddingBottom);
    return {
      width: Math.max(0, host.clientWidth - paddingX),
      height: Math.max(0, host.clientHeight - paddingY),
    };
  }, []);

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

  useEffect(() => {
    const host = previewHostRef.current;
    if (!host) return;

    const updateHostSize = (width: number, height: number) => {
      const nextWidth = Math.max(0, Math.floor(width));
      const nextHeight = Math.max(0, Math.floor(height));
      setPreviewHostSize((current) =>
        current.width === nextWidth && current.height === nextHeight
          ? current
          : { width: nextWidth, height: nextHeight }
      );
    };

    const initialSize = measurePreviewHost(host);
    updateHostSize(initialSize.width, initialSize.height);

    const resizeObserver = new ResizeObserver((entries) => {
      const nextEntry = entries[0];
      if (!nextEntry) return;
      updateHostSize(nextEntry.contentRect.width, nextEntry.contentRect.height);
    });

    resizeObserver.observe(host);
    return () => resizeObserver.disconnect();
  }, [measurePreviewHost]);

  const currentTime = useMemo(() => livePlayer?.currentTime ?? 0, [livePlayer?.currentTime]);
  const previewSize = useMemo(() => {
    if (previewHostSize.width <= 0 || previewHostSize.height <= 0) {
      return null;
    }

    const scale = Math.min(
      previewHostSize.width / SCENE_SIZE.width,
      previewHostSize.height / SCENE_SIZE.height,
    );

    return {
      width: Math.max(1, Math.floor(SCENE_SIZE.width * scale)),
      height: Math.max(1, Math.floor(SCENE_SIZE.height * scale)),
    };
  }, [previewHostSize.height, previewHostSize.width]);

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

  const getAvailableAudioTrack = useCallback((start: number, end: number) => {
    const tracks = editor.getTimelineData()?.tracks ?? [];
    const audioTracks = tracks
      .filter((track) => track.getType() === TRACK_TYPES.AUDIO)
      .filter((track) => {
        const name = track.getName();
        return new RegExp(`^${IMPORTED_AUDIO_TRACK_PREFIX}(?: \\d+)?$`).test(name);
      })
      .sort((a, b) => {
        const aMatch = a.getName().match(/(\d+)$/);
        const bMatch = b.getName().match(/(\d+)$/);
        const aIndex = aMatch ? Number(aMatch[1]) : 1;
        const bIndex = bMatch ? Number(bMatch[1]) : 1;
        return aIndex - bIndex;
      });

    const freeTrack = audioTracks.find((track) =>
      !track
        .getElements()
        .some((element) => rangesOverlap(start, end, element.getStart(), element.getEnd()))
    );

    if (freeTrack) {
      return freeTrack;
    }

    const nextIndex = audioTracks.reduce((max, track) => {
      const match = track.getName().match(/(\d+)$/);
      const index = match ? Number(match[1]) : 1;
      return Math.max(max, index);
    }, 0);

    return editor.addTrack(
      nextIndex === 0 ? IMPORTED_AUDIO_TRACK_PREFIX : `${IMPORTED_AUDIO_TRACK_PREFIX} ${nextIndex + 1}`,
      TRACK_TYPES.AUDIO,
    );
  }, [editor]);

  const insertText = useCallback(async (config: TextInsertConfig) => {
    const variant = config.variant ?? "freeform";
    const preset = TEXT_INSERT_PRESETS[variant];
    const track = ensureTrack("Text Overlays", TRACK_TYPES.ELEMENT);
    const start = currentTime;
    const resolvedText = config.text.trim() || (variant === "freeform" ? "Sample text" : preset.name);
    const end = clampEnd(start, preset.duration, totalDuration);

    const element = new TextElement(resolvedText, {
      fill: preset.fill,
      fontSize: preset.fontSize,
      fontWeight: preset.fontWeight,
      textAlign: preset.textAlign,
      fontFamily: preset.fontFamily,
    });

    element
      .setName(variant === "freeform" ? sanitizeName(resolvedText) : preset.name)
      .setStart(start)
      .setEnd(end)
      .setPosition(preset.position);

    try {
      const added = await editor.addElementToTrack(track, element);
      return added ? element : null;
    } catch (error) {
      console.warn("[EditorShell] Failed to insert text element:", error);
      return null;
    }
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
    const start = 0;
    const end = totalDuration > 0 ? totalDuration : 4;
    const track = getAvailableAudioTrack(start, end);
    const element = new AudioElement(src)
      .setName(sanitizeName(label))
      .setStart(start)
      .setEnd(end)
      .setVolume(0.4);

    await editor.addElementToTrack(track, element);
  }, [editor, getAvailableAudioTrack, totalDuration]);

  return (
    <div className="flex h-full min-h-0 overflow-hidden">
      {/* Portal the ExportButton into the toolbar (outside provider tree) */}
      {exportPortalRef?.current &&
        createPortal(
          <ExportButton
            projectId={project.project_id}
            initialExport={project.editor_export}
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
        onInsertText={insertText}
        onInsertImage={insertImage}
        onInsertAudio={insertAudio}
      />

      {/* Center column: canvas + timeline */}
      <div className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden">
        {/* Canvas area */}
        <div className="editor-canvas-wrapper flex min-h-0 flex-1 items-center justify-center overflow-hidden bg-editor-bg">
          <div ref={previewHostRef} className="editor-preview-host">
            {previewSize ? (
              <div
                className="editor-preview-shell"
                style={{ width: `${previewSize.width}px`, height: `${previewSize.height}px` }}
              >
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
            ) : null}
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
