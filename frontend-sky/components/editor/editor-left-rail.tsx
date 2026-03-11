"use client";

import { useEffect, useMemo, useState } from "react";
import {
  Captions,
  Clapperboard,
  Image as ImageIcon,
  Loader2,
  Music4,
  Plus,
  Sparkles,
  Type,
  Waves,
} from "lucide-react";
import apiClient from "@/lib/apiClient";
import { cn } from "@/lib/utils";
import type { Asset, EditorLeftPanelKey, Project } from "@/components/editor/types";
import { useLivePlayerContext } from "@twick/live-player";
import { useTimelineContext } from "@twick/timeline";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

const PANEL_CONFIG: Array<{
  key: EditorLeftPanelKey;
  label: string;
  icon: typeof ImageIcon;
  description: string;
}> = [
  { key: "media", label: "Media", icon: ImageIcon, description: "Insert uploaded visuals fast" },
  { key: "text", label: "Text", icon: Type, description: "Add hook titles and overlays" },
  { key: "caption", label: "Caption", icon: Captions, description: "Retheme subtitles and captions" },
  { key: "audio", label: "Audio", icon: Music4, description: "Preview and swap soundtrack choices" },
  { key: "effects", label: "Effects", icon: Sparkles, description: "Apply light directional edits" },
];

const TEXT_PRESETS = [
  {
    label: "Hook Title",
    title: "DREAD MORNINGS NO MORE",
    subtitle: "Centered opener for the first beat",
  },
  {
    label: "Lower Third",
    title: "Your Story Starts Here",
    subtitle: "Small anchored text card",
  },
  {
    label: "Callout",
    title: "Watch this moment",
    subtitle: "Short emphasis overlay",
  },
] as const;

const CAPTION_PRESETS = [
  { label: "Karaoke", prompt: "Change captions to karaoke style" },
  { label: "Elegant", prompt: "Change captions to elegant style" },
  { label: "Clarity", prompt: "Change captions to clarity style" },
  { label: "Bold Stroke", prompt: "Change captions to bold_stroke style" },
] as const;

const MUSIC_PRESETS = [
  "happy_rhythm",
  "quiet_before_storm",
  "peaceful_vibes",
  "brilliant_symphony",
  "breathing_shadows",
  "none",
] as const;

const EFFECT_QUICK_ACTIONS = [
  "Add subtle zooms to the main shots",
  "Make the first three seconds punchier",
  "Add a darker cinematic feel to this cut",
  "Add a hook title at the beginning",
] as const;

const formatSeconds = (seconds: number | null | undefined): string => {
  if (typeof seconds !== "number" || Number.isNaN(seconds)) return "--:--";
  const minutes = Math.floor(seconds / 60);
  const remainingSeconds = Math.floor(seconds % 60);
  return `${minutes.toString().padStart(2, "0")}:${remainingSeconds.toString().padStart(2, "0")}`;
};

const formatSize = (bytes: number): string => {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
};

const getSelectedItemLabel = (selectedItem: unknown): string => {
  if (!selectedItem || typeof selectedItem !== "object") return "Nothing selected";
  if ("getName" in selectedItem && typeof selectedItem.getName === "function") {
    const name = selectedItem.getName();
    if (typeof name === "string" && name.trim()) return name;
  }
  if ("getType" in selectedItem && typeof selectedItem.getType === "function") {
    const type = selectedItem.getType();
    if (typeof type === "string" && type.trim()) return type;
  }
  return "Selected item";
};

const getAssetUrl = (assetId: string, category: "images" | "music" | "voice_memos"): string =>
  `${API}/api/v1/assets/${assetId}/url?category=${category}`;

interface EditorLeftRailProps {
  project: Project;
  activePanel: EditorLeftPanelKey;
  setActivePanel: (panel: EditorLeftPanelKey) => void;
  agentLoading: boolean;
  isVoiceActive: boolean;
  onQuickAction: (instruction: string) => void;
  onInsertText: (text: string, variant: "hook" | "lower-third" | "callout") => void | Promise<void>;
  onInsertImage: (src: string, label: string) => void | Promise<void>;
  onInsertAudio: (src: string, label: string) => void | Promise<void>;
}

export function EditorLeftRail({
  project,
  activePanel,
  setActivePanel,
  agentLoading,
  isVoiceActive,
  onQuickAction,
  onInsertText,
  onInsertImage,
  onInsertAudio,
}: EditorLeftRailProps) {
  const [imageAssets, setImageAssets] = useState<Asset[]>([]);
  const [musicAssets, setMusicAssets] = useState<Asset[]>([]);
  const [voiceMemoAssets, setVoiceMemoAssets] = useState<Asset[]>([]);
  const [assetLoading, setAssetLoading] = useState(true);
  const [assetError, setAssetError] = useState<string | null>(null);
  const { present, selectedItem, selectedIds, totalDuration } = useTimelineContext();
  const livePlayer = useLivePlayerContext() as { currentTime?: number } | null;

  useEffect(() => {
    let cancelled = false;

    async function loadAssets() {
      setAssetLoading(true);
      setAssetError(null);
      try {
        const [imagesRes, musicRes, voiceRes] = await Promise.all([
          apiClient.get("/api/v1/assets?category=images"),
          apiClient.get("/api/v1/assets?category=music"),
          apiClient.get("/api/v1/assets?category=voice_memos"),
        ]);
        if (cancelled) return;
        setImageAssets(imagesRes.data.assets ?? []);
        setMusicAssets(musicRes.data.assets ?? []);
        setVoiceMemoAssets(voiceRes.data.assets ?? []);
      } catch (error) {
        if (cancelled) return;
        setAssetError(error instanceof Error ? error.message : "Failed to load assets");
      } finally {
        if (!cancelled) setAssetLoading(false);
      }
    }

    void loadAssets();

    return () => {
      cancelled = true;
    };
  }, []);

  const timelineStats = useMemo(() => {
    const projectJson = present ?? project.project_json ?? null;
    const tracks = projectJson?.tracks ?? [];
    const audioTrackCount = tracks.filter((track) => track.type === "audio").length;
    const textElementCount = tracks.reduce((count, track) => (
      count + (track.elements ?? []).filter((element) => element.type === "text" || element.type === "caption").length
    ), 0);

    return {
      tracks: tracks.length,
      audioTrackCount,
      textElementCount,
    };
  }, [present, project.project_json]);

  const currentSelection = getSelectedItemLabel(selectedItem);

  return (
    <aside className="flex h-full min-w-0 border-r border-white/10 bg-[#0c0f16]">
      <div className="flex w-[76px] shrink-0 flex-col items-center gap-2 border-r border-white/10 bg-[#090b11] px-3 py-4">
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
                  ? "border-[#7c3aed]/50 bg-[#7c3aed]/18 text-white"
                  : "border-white/8 bg-white/[0.03] text-white/50 hover:border-white/15 hover:bg-white/[0.05] hover:text-white/85"
              )}
              title={panel.label}
            >
              <Icon className="h-4 w-4" />
              <span className="text-[10px] font-medium leading-tight">{panel.label}</span>
            </button>
          );
        })}
      </div>

      <div className="flex min-w-0 flex-1 flex-col">
        <div className="border-b border-white/10 px-5 py-4">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-2xl bg-[#7c3aed]/15 text-[#c4b5fd]">
              {(() => {
                const ActiveIcon = PANEL_CONFIG.find((panel) => panel.key === activePanel)?.icon ?? ImageIcon;
                return <ActiveIcon className="h-5 w-5" />;
              })()}
            </div>
            <div className="min-w-0">
              <p className="text-sm font-semibold text-white">
                {PANEL_CONFIG.find((panel) => panel.key === activePanel)?.label}
              </p>
              <p className="text-xs text-white/45">
                {PANEL_CONFIG.find((panel) => panel.key === activePanel)?.description}
              </p>
            </div>
          </div>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4">
          {activePanel === "media" && (
            <div className="space-y-4">
              <div className="rounded-2xl border border-white/10 bg-white/[0.03] p-4">
                <div className="mb-3 flex items-center justify-between">
                  <div>
                    <p className="text-sm font-semibold text-white">Uploaded Visuals</p>
                    <p className="text-xs text-white/45">Click to place at the current playhead.</p>
                  </div>
                  <span className="rounded-full border border-white/10 bg-white/5 px-2 py-1 text-[11px] text-white/50">
                    {imageAssets.length} items
                  </span>
                </div>
                {assetLoading ? (
                  <div className="flex items-center gap-2 rounded-xl border border-white/10 bg-white/[0.02] px-3 py-4 text-sm text-white/45">
                    <Loader2 className="h-4 w-4 animate-spin" /> Loading image library...
                  </div>
                ) : assetError ? (
                  <div className="rounded-xl border border-red-500/20 bg-red-500/10 px-3 py-3 text-sm text-red-200">
                    {assetError}
                  </div>
                ) : imageAssets.length === 0 ? (
                  <div className="rounded-xl border border-dashed border-white/10 bg-white/[0.02] px-3 py-4 text-sm text-white/45">
                    No uploaded images yet. Use the Files menu or asset library to add some first.
                  </div>
                ) : (
                  <div className="grid grid-cols-2 gap-3">
                    {imageAssets.slice(0, 8).map((asset) => (
                      <button
                        key={asset.id}
                        type="button"
                        onClick={() => void onInsertImage(getAssetUrl(asset.id, "images"), asset.filename)}
                        className="group overflow-hidden rounded-2xl border border-white/10 bg-white/[0.03] text-left transition hover:border-[#7c3aed]/40 hover:bg-white/[0.06]"
                      >
                        <div
                          className="h-32 w-full bg-cover bg-center"
                          style={{ backgroundImage: `url(${getAssetUrl(asset.id, "images")})` }}
                        />
                        <div className="space-y-1 px-3 py-3">
                          <p className="truncate text-xs font-medium text-white/90">{asset.filename}</p>
                          <p className="text-[11px] text-white/40">{formatSize(asset.size_bytes)}</p>
                        </div>
                      </button>
                    ))}
                  </div>
                )}
              </div>

              <div className="rounded-2xl border border-white/10 bg-white/[0.03] p-4">
                <div className="mb-2 flex items-center gap-2">
                  <Clapperboard className="h-4 w-4 text-[#60a5fa]" />
                  <p className="text-sm font-semibold text-white">Scene notes</p>
                </div>
                <p className="text-xs leading-relaxed text-white/55">
                  Full video-scene replacement stays in the Files/AI path for now. This panel handles fast insertions
                  and overlays inside the live editor.
                </p>
              </div>
            </div>
          )}

          {activePanel === "text" && (
            <div className="space-y-4">
              <div className="rounded-2xl border border-white/10 bg-white/[0.03] p-4">
                <p className="text-sm font-semibold text-white">Text presets</p>
                <p className="mt-1 text-xs text-white/45">Insert overlays directly without opening the agent.</p>
                <div className="mt-4 space-y-3">
                  {TEXT_PRESETS.map((preset) => (
                    <button
                      key={preset.label}
                      type="button"
                      onClick={() => void onInsertText(
                        preset.title,
                        preset.label === "Hook Title" ? "hook" : preset.label === "Lower Third" ? "lower-third" : "callout"
                      )}
                      className="w-full rounded-2xl border border-white/10 bg-white/[0.03] px-4 py-3 text-left transition hover:border-[#7c3aed]/40 hover:bg-[#7c3aed]/10"
                    >
                      <p className="text-sm font-medium text-white">{preset.label}</p>
                      <p className="mt-1 text-xs text-white/50">{preset.subtitle}</p>
                      <p className="mt-3 text-[11px] uppercase tracking-[0.18em] text-white/30">{preset.title}</p>
                    </button>
                  ))}
                </div>
              </div>

              <div className="rounded-2xl border border-white/10 bg-white/[0.03] p-4">
                <p className="text-sm font-semibold text-white">AI-assisted text actions</p>
                <div className="mt-3 grid grid-cols-1 gap-2">
                  {[
                    "Add a hook title at the beginning",
                    "Move the selected text up by 80 pixels",
                    "Change the selected title to a darker tone",
                  ].map((prompt) => (
                    <button
                      key={prompt}
                      type="button"
                      onClick={() => onQuickAction(prompt)}
                      disabled={agentLoading}
                      className="rounded-xl border border-white/10 bg-white/[0.03] px-3 py-2 text-left text-xs text-white/70 transition hover:border-[#7c3aed]/40 hover:bg-[#7c3aed]/10 hover:text-white disabled:opacity-40"
                    >
                      {prompt}
                    </button>
                  ))}
                </div>
              </div>
            </div>
          )}

          {activePanel === "caption" && (
            <div className="space-y-4">
              <div className="rounded-2xl border border-white/10 bg-white/[0.03] p-4">
                <p className="text-sm font-semibold text-white">Caption styles</p>
                <p className="mt-1 text-xs text-white/45">These reuse the existing live edit path and update instantly.</p>
                <div className="mt-4 grid grid-cols-2 gap-2">
                  {CAPTION_PRESETS.map((preset) => (
                    <button
                      key={preset.label}
                      type="button"
                      onClick={() => onQuickAction(preset.prompt)}
                      disabled={agentLoading}
                      className="rounded-xl border border-white/10 bg-white/[0.03] px-3 py-3 text-left transition hover:border-[#7c3aed]/40 hover:bg-[#7c3aed]/10 disabled:opacity-40"
                    >
                      <p className="text-sm font-medium text-white">{preset.label}</p>
                      <p className="mt-1 text-[11px] text-white/40">Live timeline update</p>
                    </button>
                  ))}
                </div>
              </div>
            </div>
          )}

          {activePanel === "audio" && (
            <div className="space-y-4">
              <div className="rounded-2xl border border-white/10 bg-white/[0.03] p-4">
                <p className="text-sm font-semibold text-white">Background music</p>
                <p className="mt-1 text-xs text-white/45">Pick a soundtrack preset and preview it in the timeline.</p>
                <div className="mt-4 grid grid-cols-2 gap-2">
                  {MUSIC_PRESETS.map((preset) => (
                    <button
                      key={preset}
                      type="button"
                      onClick={() => onQuickAction(
                        preset === "none"
                          ? "Remove the background music"
                          : `Change the music to ${preset}`
                      )}
                      disabled={agentLoading}
                      className={cn(
                        "rounded-xl border px-3 py-3 text-left transition disabled:opacity-40",
                        project.background_music === preset
                          ? "border-cyan-400/30 bg-cyan-400/12 text-cyan-100"
                          : "border-white/10 bg-white/[0.03] text-white/80 hover:border-[#7c3aed]/40 hover:bg-[#7c3aed]/10"
                      )}
                    >
                      <p className="text-sm font-medium">{preset}</p>
                      <p className="mt-1 text-[11px] text-white/40">Preview lane + export aware</p>
                    </button>
                  ))}
                </div>
              </div>

              <div className="rounded-2xl border border-white/10 bg-white/[0.03] p-4">
                <p className="text-sm font-semibold text-white">Uploaded audio</p>
                <p className="mt-1 text-xs text-white/45">Drop supporting audio or voice memo clips onto the timeline.</p>
                <div className="mt-4 space-y-2">
                  {[...musicAssets.slice(0, 3).map((asset) => ({ asset, category: "music" as const })), ...voiceMemoAssets.slice(0, 3).map((asset) => ({ asset, category: "voice_memos" as const }))].map(({ asset, category }) => (
                    <button
                      key={`${category}-${asset.id}`}
                      type="button"
                      onClick={() => void onInsertAudio(getAssetUrl(asset.id, category), asset.filename)}
                      className="flex w-full items-center justify-between rounded-xl border border-white/10 bg-white/[0.03] px-3 py-2 text-left transition hover:border-[#7c3aed]/40 hover:bg-white/[0.06]"
                    >
                      <div className="min-w-0">
                        <p className="truncate text-sm text-white">{asset.filename}</p>
                        <p className="text-[11px] text-white/40">{category === "music" ? "Music asset" : "Voice memo"}</p>
                      </div>
                      <Plus className="h-4 w-4 shrink-0 text-white/35" />
                    </button>
                  ))}
                  {!assetLoading && musicAssets.length === 0 && voiceMemoAssets.length === 0 && (
                    <div className="rounded-xl border border-dashed border-white/10 bg-white/[0.02] px-3 py-4 text-sm text-white/45">
                      No uploaded audio assets yet.
                    </div>
                  )}
                </div>
              </div>
            </div>
          )}

          {activePanel === "effects" && (
            <div className="space-y-4">
              <div className="rounded-2xl border border-white/10 bg-white/[0.03] p-4">
                <p className="text-sm font-semibold text-white">Quick enhancement passes</p>
                <p className="mt-1 text-xs text-white/45">These use the copilot for fast, timeline-aware polish.</p>
                <div className="mt-4 space-y-2">
                  {EFFECT_QUICK_ACTIONS.map((action) => (
                    <button
                      key={action}
                      type="button"
                      onClick={() => onQuickAction(action)}
                      disabled={agentLoading}
                      className="w-full rounded-xl border border-white/10 bg-white/[0.03] px-3 py-3 text-left text-sm text-white/80 transition hover:border-[#7c3aed]/40 hover:bg-[#7c3aed]/10 disabled:opacity-40"
                    >
                      {action}
                    </button>
                  ))}
                </div>
              </div>
            </div>
          )}
        </div>

        <div className="space-y-3 border-t border-white/10 px-5 py-4">
          <div className="grid grid-cols-2 gap-2 text-xs">
            <div className="rounded-2xl border border-white/10 bg-white/[0.03] px-3 py-3">
              <p className="text-white/40">Tracks</p>
              <p className="mt-1 text-lg font-semibold text-white">{timelineStats.tracks}</p>
            </div>
            <div className="rounded-2xl border border-white/10 bg-white/[0.03] px-3 py-3">
              <p className="text-white/40">Audio lanes</p>
              <p className="mt-1 text-lg font-semibold text-white">{timelineStats.audioTrackCount}</p>
            </div>
            <div className="rounded-2xl border border-white/10 bg-white/[0.03] px-3 py-3">
              <p className="text-white/40">Playhead</p>
              <p className="mt-1 text-lg font-semibold text-white">{formatSeconds(livePlayer?.currentTime ?? 0)}</p>
            </div>
            <div className="rounded-2xl border border-white/10 bg-white/[0.03] px-3 py-3">
              <p className="text-white/40">Text</p>
              <p className="mt-1 text-lg font-semibold text-white">{timelineStats.textElementCount}</p>
            </div>
          </div>

          <div className="rounded-2xl border border-white/10 bg-white/[0.03] px-3 py-3">
            <div className="flex items-center justify-between gap-3">
              <div>
                <p className="text-sm font-semibold text-white">Selection</p>
                <p className="mt-1 text-xs text-white/45">{currentSelection}</p>
              </div>
              <div className="rounded-full border border-white/10 bg-white/5 px-2 py-1 text-[11px] text-white/55">
                {selectedIds.size > 0 ? `${selectedIds.size} active` : "Idle"}
              </div>
            </div>
            <div className="mt-3 flex items-center gap-2 text-[11px] text-white/40">
              <Waves className="h-3.5 w-3.5" />
              Voice copilot is {isVoiceActive ? "listening" : "idle"} · duration {formatSeconds(totalDuration)}
            </div>
          </div>
        </div>
      </div>
    </aside>
  );
}
