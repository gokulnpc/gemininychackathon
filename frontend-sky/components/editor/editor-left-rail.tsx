"use client";

import { useMemo } from "react";
import { Image as ImageIcon, Waves } from "lucide-react";
import { TextElement, useTimelineContext } from "@twick/timeline";

import type { EditorLeftPanelKey, Project, TextInsertConfig } from "@/components/editor/types";
import { cn } from "@/lib/utils";

import { AudioPanel } from "./left-rail/audio-panel";
import { CaptionPanel } from "./left-rail/caption-panel";
import { EffectsPanel } from "./left-rail/effects-panel";
import { MediaPanel } from "./left-rail/media-panel";
import { PANEL_CONFIG } from "./left-rail/panel-config";
import { TextPanel } from "./left-rail/text-panel";
import { formatSeconds, getSelectedItemLabel } from "./left-rail/utils";
import { VideoPanel } from "./left-rail/video-panel";

interface EditorLeftRailProps {
  project: Project;
  activePanel: EditorLeftPanelKey;
  setActivePanel: (panel: EditorLeftPanelKey) => void;
  agentLoading: boolean;
  isVoiceActive: boolean;
  onInsertText: (config: TextInsertConfig) => void | Promise<TextElement | null> | TextElement | null;
  onInsertImage: (src: string, label: string) => void | Promise<void>;
  onInsertAudio: (src: string, label: string) => void | Promise<void>;
}

export function EditorLeftRail({
  project,
  activePanel,
  setActivePanel,
  agentLoading,
  isVoiceActive,
  onInsertText,
  onInsertImage,
  onInsertAudio,
}: EditorLeftRailProps) {
  const { present, selectedItem, selectedIds, totalDuration } = useTimelineContext();

  const timelineStats = useMemo(() => {
    const projectJson = present ?? project.project_json ?? null;
    const tracks = projectJson?.tracks ?? [];
    return {
      tracks: tracks.length,
      audioTrackCount: tracks.filter((track) => (track as unknown as { type: string }).type === "audio").length,
      textElementCount: tracks.reduce(
        (count, track) =>
          count +
          (track.elements ?? []).filter(
            (element) =>
              (element as unknown as { type: string }).type === "text" ||
              (element as unknown as { type: string }).type === "caption"
          ).length,
        0
      ),
    };
  }, [present, project.project_json]);

  const activePanelConfig = PANEL_CONFIG.find((panel) => panel.key === activePanel);
  const currentSelection = getSelectedItemLabel(selectedItem);

  return (
    <aside className="flex h-full w-[320px] min-w-[320px] max-w-[320px] border-r border-editor-border bg-editor-panel">
      <div className="flex w-[68px] shrink-0 flex-col items-center gap-2 border-r border-editor-border bg-editor-sidebar px-2 py-4">
        {PANEL_CONFIG.map((panel) => {
          const Icon = panel.icon;
          const isActive = activePanel === panel.key;
          return (
            <button
              key={panel.key}
              type="button"
              onClick={() => setActivePanel(panel.key)}
              className={cn(
                "group flex w-full flex-col items-center gap-2 rounded-2xl border px-2 py-3 text-center transition-colors",
                isActive
                  ? "border-primary/55 bg-primary/18 text-foreground"
                  : "border-editor-border bg-editor-control text-muted-foreground hover:border-primary/25 hover:bg-editor-control-hover hover:text-foreground/85"
              )}
              title={panel.label}
            >
              <Icon className="h-4 w-4" />
              <span className="text-[10px] font-medium leading-tight">{panel.label}</span>
            </button>
          );
        })}
      </div>

      <div className="flex min-w-0 flex-1 flex-col overflow-hidden">
        <div className="shrink-0 border-b border-editor-border px-4 py-3">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-2xl bg-primary/15 text-editor-accent-glow">
              {(() => {
                const ActiveIcon = activePanelConfig?.icon ?? ImageIcon;
                return <ActiveIcon className="h-5 w-5" />;
              })()}
            </div>
            <div className="min-w-0">
              <p className="text-sm font-semibold text-foreground">{activePanelConfig?.label}</p>
              <p className="text-xs text-editor-text-muted">{activePanelConfig?.description}</p>
            </div>
          </div>
        </div>

        <div className="editor-scroll min-h-0 flex-1 overflow-y-auto px-4 py-3">
          {activePanel === "media" ? <MediaPanel onInsertImage={onInsertImage} /> : null}
          {activePanel === "video" ? <VideoPanel onInsertImage={onInsertImage} /> : null}
          {activePanel === "text" ? <TextPanel onInsertText={onInsertText} /> : null}
          {activePanel === "caption" ? <CaptionPanel agentLoading={agentLoading} /> : null}
          {activePanel === "audio" ? <AudioPanel onInsertAudio={onInsertAudio} /> : null}
          {activePanel === "effects" ? <EffectsPanel agentLoading={agentLoading} /> : null}
        </div>

        <div className="shrink-0 border-t border-editor-border bg-editor-panel px-4 py-3">
          <div className="rounded-2xl border border-editor-border bg-editor-card px-3 py-3 shadow-[0_-1px_0_rgba(255,255,255,0.03)]">
            <div className="flex items-center justify-between gap-3">
              <div>
                <p className="text-sm font-semibold text-foreground">Selection</p>
                <p className="mt-1 text-xs text-editor-text-muted">{currentSelection}</p>
              </div>
              <div className="rounded-full border border-editor-border bg-editor-control px-2 py-1 text-[11px] text-muted-foreground">
                {selectedIds.size > 0 ? `${selectedIds.size} active` : "Idle"}
              </div>
            </div>
            <div className="mt-3 flex items-center gap-2 text-[11px] text-editor-text-dim">
              <Waves className="h-3.5 w-3.5" />
              Voice copilot is {isVoiceActive ? "listening" : "idle"} · {timelineStats.tracks} tracks ·{" "}
              {formatSeconds(totalDuration)}
            </div>
          </div>
        </div>
      </div>
    </aside>
  );
}
