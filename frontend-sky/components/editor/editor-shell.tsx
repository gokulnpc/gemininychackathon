"use client";

import type { RefObject } from "react";
import { useCallback, useEffect, useId, useMemo } from "react";
import { AgentPanel } from "@/components/editor/agent-panel";
import { EditorLeftRail } from "@/components/editor/editor-left-rail";
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

const clampEnd = (start: number, duration: number, totalDuration: number): number =>
  totalDuration > 0 ? Math.min(start + duration, totalDuration) : start + duration;

const sanitizeName = (name: string): string => {
  const trimmed = name.trim();
  if (!trimmed) return "Untitled";
  return trimmed.replace(/\.[a-z0-9]+$/i, "");
};

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
}: EditorShellProps) {
  const timelineId = useId();
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
    const track = ensureTrack("Media Inserts", TRACK_TYPES.SCENE);
    const start = currentTime;
    const end = clampEnd(start, 4.5, totalDuration);
    const element = new ImageElement(src, SCENE_SIZE)
      .setName(sanitizeName(label))
      .setStart(start)
      .setEnd(end);

    await editor.addElementToTrack(track, element);
  }, [currentTime, editor, ensureTrack, totalDuration]);

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
    <div className="h-full overflow-hidden bg-[#0a0d14]">
      <VideoEditor
        leftPanel={(
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
        )}
        rightPanel={(
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
        )}
        bottomPanel={(
          <div className="h-[340px] min-h-[340px]">
            <TimelineDock key={timelineId} />
          </div>
        )}
        defaultPlayControls={false}
        editorConfig={{
          canvasMode: true,
          videoProps: {
            width: SCENE_SIZE.width,
            height: SCENE_SIZE.height,
            backgroundColor: "#05070c",
          },
          playerProps: {
            maxWidth: 640,
            maxHeight: 920,
          },
          fps: 30,
        }}
      />
    </div>
  );
}
