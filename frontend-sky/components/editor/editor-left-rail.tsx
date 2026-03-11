"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Captions,
  Clapperboard,
  Film,
  Image as ImageIcon,
  Loader2,
  Music4,
  Play,
  Plus,
  Sparkles,
  Trash2,
  Type,
  Upload,
  Volume2,
  Waves,
  Check,
  Search,
} from "lucide-react";
import apiClient from "@/lib/apiClient";
import type { Asset } from "@/components/editor/types";
import { cn } from "@/lib/utils";
import type { EditorLeftPanelKey, Project } from "@/components/editor/types";
import { useLivePlayerContext } from "@twick/live-player";
import { useTimelineContext, TextElement, TRACK_TYPES } from "@twick/timeline";

type AssetCategory = "image" | "video" | "audio";

// Effect thumbnail public path constants
const crossDissolveImg = "/effects/cross-dissolve.jpg";
const fadeBlackImg = "/effects/fade-black.jpg";
const zoomPushImg = "/effects/zoom-push.jpg";
const slideWipeImg = "/effects/slide-wipe.jpg";
const filmGrainImg = "/effects/film-grain.jpg";
const vignetteImg = "/effects/vignette.jpg";
const slowMotionImg = "/effects/slow-motion.jpg";
const colorGradeImg = "/effects/color-grade.jpg";
const glitchImg = "/effects/glitch.jpg";
const kenBurnsImg = "/effects/ken-burns.jpg";

const PANEL_CONFIG: Array<{
  key: EditorLeftPanelKey;
  label: string;
  icon: typeof ImageIcon;
  description: string;
}> = [
  { key: "media", label: "Image", icon: ImageIcon, description: "Insert uploaded images fast" },
  { key: "video", label: "Video", icon: Film, description: "Insert uploaded videos fast" },
  { key: "audio", label: "Audio", icon: Music4, description: "Preview and swap soundtrack choices" },
  { key: "text", label: "Text", icon: Type, description: "Add hook titles and overlays" },
  { key: "caption", label: "Caption", icon: Captions, description: "Retheme subtitles and captions" },
  { key: "effects", label: "Effects", icon: Sparkles, description: "Apply light directional edits" },
];

const TEXT_PRESETS = [
  { label: "Hook Title", title: "DREAD MORNINGS NO MORE", subtitle: "Centered opener for the first beat" },
  { label: "Lower Third", title: "Your Story Starts Here", subtitle: "Small anchored text card" },
  { label: "Callout", title: "Watch this moment", subtitle: "Short emphasis overlay" },
] as const;

const CAPTION_PRESETS = [
  { label: "Karaoke", prompt: "Change captions to karaoke style" },
  { label: "Elegant", prompt: "Change captions to elegant style" },
  { label: "Clarity", prompt: "Change captions to clarity style" },
  { label: "Bold Stroke", prompt: "Change captions to bold_stroke style" },
] as const;

type AudioTab = "music" | "sfx" | "upload";

const MUSIC_TRACKS = [
  { id: "happy_rhythm", title: "Happy Rhythm", tags: "Upbeat, Energetic", preset: "happy_rhythm" },
  { id: "quiet_before_storm", title: "Quiet Before Storm", tags: "Suspense, Epic", preset: "quiet_before_storm" },
  { id: "peaceful_vibes", title: "Peaceful Vibes", tags: "Romantic, Calm", preset: "peaceful_vibes" },
  { id: "brilliant_symphony", title: "Brilliant Symphony", tags: "Cinematic, Grand", preset: "brilliant_symphony" },
  { id: "breathing_shadows", title: "Breathing Shadows", tags: "Dark, Atmospheric", preset: "breathing_shadows" },
] as const;

type EffectsTab = "animations" | "text-effects" | "frame-effects";

interface AnimationItem {
  id: string;
  name: string;
  label: string;
  description: string;
  image: string;
  defaults: Record<string, unknown>;
  appliesTo: "any" | "text";
}

// Animations from @twick/visualizer — applied via element.animation property
const VISUALIZER_ANIMATIONS: AnimationItem[] = [
  { id: "fade-enter", name: "fade", label: "Fade In", description: "Smooth opacity fade in", image: fadeBlackImg, defaults: { animate: "enter", duration: 2 }, appliesTo: "any" },
  { id: "fade-exit", name: "fade", label: "Fade Out", description: "Smooth opacity fade out", image: fadeBlackImg, defaults: { animate: "exit", duration: 2 }, appliesTo: "any" },
  { id: "fade-both", name: "fade", label: "Fade In/Out", description: "Fade in then out", image: fadeBlackImg, defaults: { animate: "both", duration: 3, interval: 1 }, appliesTo: "any" },
  { id: "blur-enter", name: "blur", label: "Blur In", description: "Blurred to clear transition", image: vignetteImg, defaults: { animate: "enter", duration: 2, intensity: 15 }, appliesTo: "any" },
  { id: "blur-exit", name: "blur", label: "Blur Out", description: "Clear to blurred transition", image: vignetteImg, defaults: { animate: "exit", duration: 1.5, intensity: 25 }, appliesTo: "any" },
  { id: "breathe-in", name: "breathe", label: "Breathe In", description: "Gentle scale-down pulse", image: slowMotionImg, defaults: { mode: "in", duration: 2, intensity: 0.8 }, appliesTo: "any" },
  { id: "breathe-out", name: "breathe", label: "Breathe Out", description: "Gentle scale-up pulse", image: slowMotionImg, defaults: { mode: "out", duration: 1.5, intensity: 0.6 }, appliesTo: "any" },
  { id: "photo-rise-up", name: "photo-rise", label: "Slide Up", description: "Slide in from bottom", image: slideWipeImg, defaults: { direction: "up", duration: 1.5, intensity: 300 }, appliesTo: "any" },
  { id: "photo-rise-left", name: "photo-rise", label: "Slide Left", description: "Slide in from right", image: slideWipeImg, defaults: { direction: "left", duration: 1.5, intensity: 300 }, appliesTo: "any" },
  { id: "photo-zoom-in", name: "photo-zoom", label: "Zoom In", description: "Ken Burns zoom in", image: kenBurnsImg, defaults: { mode: "in", duration: 2, intensity: 1.8 }, appliesTo: "any" },
  { id: "photo-zoom-out", name: "photo-zoom", label: "Zoom Out", description: "Ken Burns zoom out", image: kenBurnsImg, defaults: { mode: "out", duration: 1.5, intensity: 2.0 }, appliesTo: "any" },
  { id: "rise-enter", name: "rise", label: "Rise Enter", description: "Vertical rise with fade", image: zoomPushImg, defaults: { animate: "enter", duration: 1.5 }, appliesTo: "any" },
  { id: "succession-enter", name: "succession", label: "Succession", description: "Scale + fade zoom effect", image: zoomPushImg, defaults: { animate: "enter", duration: 1.5 }, appliesTo: "any" },
];

// Text effects from @twick/visualizer — applied via element.textEffect property
const VISUALIZER_TEXT_EFFECTS: AnimationItem[] = [
  { id: "typewriter", name: "typewriter", label: "Typewriter", description: "Appear one character at a time", image: crossDissolveImg, defaults: { duration: 3, delay: 0 }, appliesTo: "text" },
  { id: "stream-word", name: "stream-word", label: "Stream Words", description: "Appear one word at a time", image: crossDissolveImg, defaults: { duration: 3, delay: 0 }, appliesTo: "text" },
  { id: "elastic", name: "elastic", label: "Elastic Pop", description: "Bounce into view with spring", image: glitchImg, defaults: { duration: 1.5, delay: 0.5 }, appliesTo: "text" },
  { id: "erase", name: "erase", label: "Erase", description: "Disappear letter by letter", image: filmGrainImg, defaults: { duration: 3, delay: 1 }, appliesTo: "text" },
];

// Frame effects from @twick/visualizer — applied via element.frameEffects property
interface FrameEffectItem {
  id: string;
  name: string;
  label: string;
  description: string;
  image: string;
  defaults: Record<string, unknown>;
}

const VISUALIZER_FRAME_EFFECTS: FrameEffectItem[] = [
  { id: "circle-frame", name: "circle", label: "Circle Frame", description: "Circular mask with transition", image: colorGradeImg, defaults: { frameSize: [500, 500], frameShape: "circle", framePosition: { x: 288, y: 512 }, radius: 250, objectFit: "cover", transitionDuration: 1.5 } },
  { id: "rect-frame", name: "rect", label: "Rectangle Frame", description: "Rounded rectangle mask", image: colorGradeImg, defaults: { frameSize: [400, 300], frameShape: "rect", framePosition: { x: 288, y: 512 }, radius: 20, objectFit: "cover" } },
];

const formatSeconds = (seconds: number | null | undefined): string => {
  if (typeof seconds !== "number" || Number.isNaN(seconds)) return "--:--";
  const minutes = Math.floor(seconds / 60);
  const remainingSeconds = Math.floor(seconds % 60);
  return `${minutes.toString().padStart(2, "0")}:${remainingSeconds.toString().padStart(2, "0")}`;
};

const getSelectedItemLabel = (selectedItem: unknown): string => {
  if (!selectedItem || typeof selectedItem !== "object") return "Nothing selected";
  if ("getName" in selectedItem && typeof (selectedItem as Record<string, unknown>).getName === "function") {
    const name = (selectedItem as { getName: () => unknown }).getName();
    if (typeof name === "string" && name.trim()) return name;
  }
  if ("getType" in selectedItem && typeof (selectedItem as Record<string, unknown>).getType === "function") {
    const type = (selectedItem as { getType: () => unknown }).getType();
    if (typeof type === "string" && type.trim()) return type;
  }
  return "Selected item";
};

function CaptionPanel({ agentLoading }: { onQuickAction: (s: string) => void; agentLoading: boolean }) {
  const { editor, present } = useTimelineContext();
  const { currentTime } = useLivePlayerContext();

  // Extract all text/caption elements from timeline tracks
  const captionElements = useMemo(() => {
    const tracks = present?.tracks ?? [];
    const items: {
      trackId: string;
      elementId: string;
      text: string;
      start: number;
      end: number;
      type: string;
    }[] = [];
    for (const track of tracks) {
      for (const el of track.elements ?? []) {
        if (el.type === "text" || el.type === "caption") {
          const props = (el as unknown as { props?: Record<string, unknown> }).props ?? {};
          items.push({
            trackId: track.id,
            elementId: el.id,
            text: (props.text as string) ?? (el as unknown as { t?: string }).t ?? (el as unknown as { name?: string }).name ?? "",
            start: (el as unknown as { s?: number }).s ?? (el as unknown as { start?: number }).start ?? 0,
            end: (el as unknown as { e?: number }).e ?? (el as unknown as { end?: number }).end ?? 0,
            type: el.type,
          });
        }
      }
    }
    return items.sort((a, b) => a.start - b.start);
  }, [present]);

  const formatTime = (s: number) => {
    const m = Math.floor(s / 60);
    const sec = Math.floor(s % 60);
    return `${m}:${sec.toString().padStart(2, "0")}`;
  };

  const handleUpdateText = useCallback(
    (trackId: string, elementId: string, newText: string) => {
      void trackId;
      try {
        editor.updateElements([{ elementId, updates: { props: { text: newText } } }]);
      } catch (err) {
        console.error("[CaptionPanel] Failed to update element:", err);
      }
    },
    [editor]
  );

  const handleRemove = useCallback(
    (elementId: string) => {
      try {
        editor.removeElements([elementId]);
      } catch (err) {
        console.error("[CaptionPanel] Failed to remove element:", err);
      }
    },
    [editor]
  );

  const handleAdd = useCallback(async () => {
    try {
      const playhead = currentTime ?? 0;
      const el = new TextElement("New caption");
      el.setStart(playhead);
      el.setEnd(playhead + 3);
      const track = editor.addTrack("Caption", TRACK_TYPES.ELEMENT);
      await editor.addElementToTrack(track, el);
    } catch (err) {
      console.error("[CaptionPanel] Failed to add caption:", err);
    }
  }, [editor, currentTime]);

  return (
    <div className="space-y-3">
      {captionElements.length === 0 && (
        <p className="py-4 text-center text-xs text-editor-text-muted">No captions on the timeline yet.</p>
      )}

      {captionElements.map((cap) => (
        <div key={cap.elementId} className="space-y-2">
          <input
            type="text"
            value={cap.text}
            onChange={(e) => handleUpdateText(cap.trackId, cap.elementId, e.target.value)}
            placeholder="Caption text..."
            className="w-full rounded-xl border border-editor-border bg-editor-card px-3 py-2.5 text-sm text-foreground placeholder:text-muted-foreground focus:border-primary/50 focus:outline-none focus:ring-1 focus:ring-primary/30"
          />
          <div className="flex items-center justify-between">
            <span className="text-[10px] text-editor-text-dim">
              {formatTime(cap.start)} – {formatTime(cap.end)}
            </span>
            <button
              type="button"
              onClick={() => handleRemove(cap.elementId)}
              className="flex h-8 w-8 items-center justify-center rounded-lg border border-editor-border bg-editor-control text-red-400/70 transition hover:bg-editor-control-hover hover:text-red-400"
              title="Delete"
            >
              <Trash2 className="h-3.5 w-3.5" />
            </button>
          </div>
        </div>
      ))}

      <button
        type="button"
        onClick={() => void handleAdd()}
        disabled={agentLoading}
        className="w-full rounded-xl bg-primary py-2.5 text-sm font-semibold text-primary-foreground shadow-sm transition hover:bg-primary/90 disabled:opacity-40"
      >
        Add
      </button>
    </div>
  );
}

function AudioPanel({
  project,
  onQuickAction,
  agentLoading,
}: {
  project: Project;
  onQuickAction: (s: string) => void;
  agentLoading: boolean;
}) {
  const [audioTab, setAudioTab] = useState<AudioTab>("music");
  const [search, setSearch] = useState("");
  const [playingId, setPlayingId] = useState<string | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);

  const filteredTracks = MUSIC_TRACKS.filter(
    (t) =>
      t.title.toLowerCase().includes(search.toLowerCase()) ||
      t.tags.toLowerCase().includes(search.toLowerCase())
  );

  const audioTabs: { key: AudioTab; label: string; icon: typeof Music4 }[] = [
    { key: "music", label: "My assets", icon: Music4 },
    { key: "sfx", label: "Public", icon: Volume2 },
    { key: "upload", label: "Upload", icon: Upload },
  ];

  const handlePlay = useCallback(
    (trackId: string) => {
      if (playingId === trackId) {
        audioRef.current?.pause();
        audioRef.current = null;
        setPlayingId(null);
        return;
      }
      audioRef.current?.pause();
      audioRef.current = null;
      setPlayingId(trackId);
      // Auto-stop after a brief preview
      setTimeout(() => setPlayingId((cur) => (cur === trackId ? null : cur)), 5000);
    },
    [playingId]
  );

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      audioRef.current?.pause();
    };
  }, []);

  return (
    <div className="space-y-3">
      {/* Tab row */}
      <div className="flex gap-1 rounded-lg border border-editor-border bg-editor-card p-1">
        {audioTabs.map((tab) => {
          const Icon = tab.icon;
          return (
            <button
              key={tab.key}
              type="button"
              onClick={() => setAudioTab(tab.key)}
              className={cn(
                "flex flex-1 items-center justify-center gap-1 rounded-md px-2 py-1 text-[11px] font-medium transition-all",
                audioTab === tab.key
                  ? "bg-primary/18 text-primary shadow-sm"
                  : "bg-editor-control text-muted-foreground hover:bg-editor-control-hover hover:text-foreground"
              )}
            >
              <Icon className="h-3 w-3" />
              {tab.label}
            </button>
          );
        })}
      </div>

      {/* Search */}
      <div className="relative">
        <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-editor-text-dim" />
        <input
          type="text"
          placeholder="Search audio..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="w-full rounded-xl border border-editor-border bg-editor-control py-2.5 pl-9 pr-3 text-sm text-foreground placeholder:text-muted-foreground focus:border-primary/50 focus:outline-none focus:ring-1 focus:ring-primary/30"
        />
      </div>

      {/* Track list */}
      {audioTab === "music" && (
        <div className="space-y-2">
          {filteredTracks.map((track) => {
            const isActive = project.background_music === track.preset;
            const isPlaying = playingId === track.id;
            return (
              <div
                key={track.id}
                className={cn(
                  "flex items-center gap-2 rounded-xl border px-2 py-2 transition",
                  isActive
                    ? "border-primary/50 bg-primary/10 ring-1 ring-primary/20"
                    : "border-editor-border bg-editor-card"
                )}
              >
                {/* Play / Stop button */}
                <button
                  type="button"
                  onClick={() => handlePlay(track.id)}
                  className={cn(
                    "flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border transition",
                    isPlaying
                      ? "border-primary/50 bg-primary text-primary-foreground"
                      : "border-editor-border bg-editor-control text-foreground hover:border-primary/40 hover:bg-editor-control-hover"
                  )}
                  title={isPlaying ? "Stop preview" : "Preview audio"}
                >
                  {isPlaying ? (
                    <div className="h-3 w-3 rounded-sm bg-primary-foreground" />
                  ) : (
                    <Play className="ml-0.5 h-3.5 w-3.5" />
                  )}
                </button>

                {/* Speaker icon */}
                <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border border-editor-border bg-editor-control">
                  <Volume2 className="h-4 w-4 text-editor-text-dim" />
                </div>

                {/* Title */}
                <p className="min-w-0 flex-1 truncate text-sm font-medium text-foreground">{track.title}</p>

                {/* Add to timeline button */}
                <button
                  type="button"
                  onClick={() => onQuickAction(`Change the music to ${track.preset}`)}
                  disabled={agentLoading}
                  className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border border-editor-border bg-editor-control text-foreground transition hover:border-primary/40 hover:bg-editor-control-hover disabled:opacity-40"
                  title="Add to timeline"
                >
                  <Plus className="h-4 w-4" />
                </button>
              </div>
            );
          })}

          {/* Remove music option */}
          <button
            type="button"
            onClick={() => onQuickAction("Remove the background music")}
            disabled={agentLoading}
            className="w-full rounded-xl border border-dashed border-editor-border px-3 py-3 text-center text-xs text-editor-text-muted transition hover:border-muted-foreground/30 hover:text-foreground disabled:opacity-40"
          >
            No music
          </button>

          {filteredTracks.length === 0 && search && (
            <p className="py-4 text-center text-xs text-editor-text-muted">No tracks match &quot;{search}&quot;</p>
          )}
        </div>
      )}

      {audioTab === "sfx" && (
        <div className="rounded-xl border border-dashed border-editor-border bg-editor-card/60 px-3 py-6 text-center text-sm text-editor-text-muted">
          Public audio coming soon
        </div>
      )}

      {audioTab === "upload" && (
        <div className="rounded-xl border border-dashed border-editor-border bg-editor-card/60 px-3 py-6 text-center text-sm text-editor-text-muted">
          Upload custom audio coming soon
        </div>
      )}
    </div>
  );
}

function EffectsPanel({ agentLoading }: { onQuickAction: (s: string) => void; agentLoading: boolean }) {
  const [activeTab, setActiveTab] = useState<EffectsTab>("animations");
  const [appliedEffects, setAppliedEffects] = useState<Set<string>>(new Set());
  const { editor, selectedItem, selectedIds } = useTimelineContext();
  const hasSelection = selectedIds.size > 0;
  const selectedType =
    selectedItem &&
    typeof selectedItem === "object" &&
    "getType" in selectedItem
      ? (selectedItem as { getType?: () => string }).getType?.() ?? ""
      : "";
  const isTextSelected = selectedType === "text" || selectedType === "caption";

  const handleApplyAnimation = useCallback(
    (item: AnimationItem) => {
      if (agentLoading || !hasSelection) return;
      try {
        const ids = Array.from(selectedIds);
        editor.updateElements(
          ids.map((elementId) => ({
            elementId,
            updates: { animation: { name: item.name, ...item.defaults } },
          }))
        );
        setAppliedEffects((prev) => new Set(prev).add(item.id));
      } catch (err) {
        console.error("[EffectsPanel] Failed to apply animation:", err);
      }
    },
    [agentLoading, hasSelection, selectedIds, editor]
  );

  const handleApplyTextEffect = useCallback(
    (item: AnimationItem) => {
      if (agentLoading || !hasSelection) return;
      try {
        const ids = Array.from(selectedIds);
        editor.updateElements(
          ids.map((elementId) => ({
            elementId,
            updates: { textEffect: { name: item.name, ...item.defaults } },
          }))
        );
        setAppliedEffects((prev) => new Set(prev).add(item.id));
      } catch (err) {
        console.error("[EffectsPanel] Failed to apply text effect:", err);
      }
    },
    [agentLoading, hasSelection, selectedIds, editor]
  );

  const handleApplyFrameEffect = useCallback(
    (item: FrameEffectItem) => {
      if (agentLoading || !hasSelection) return;
      try {
        const ids = Array.from(selectedIds);
        const el = selectedItem as { getStart?: () => number; s?: number; getEnd?: () => number; e?: number } | null;
        const s = el?.getStart?.() ?? el?.s ?? 0;
        const e = el?.getEnd?.() ?? el?.e ?? 10;
        editor.updateElements(
          ids.map((elementId) => ({
            elementId,
            updates: { frameEffects: [{ name: item.name, s, e, props: { ...item.defaults } }] },
          }))
        );
        setAppliedEffects((prev) => new Set(prev).add(item.id));
      } catch (err) {
        console.error("[EffectsPanel] Failed to apply frame effect:", err);
      }
    },
    [agentLoading, hasSelection, selectedIds, selectedItem, editor]
  );

  const handleRemoveEffect = useCallback(
    (type: "animation" | "textEffect" | "frameEffects") => {
      if (!hasSelection) return;
      try {
        const ids = Array.from(selectedIds);
        editor.updateElements(ids.map((elementId) => ({ elementId, updates: { [type]: undefined } })));
      } catch (err) {
        console.error("[EffectsPanel] Failed to remove effect:", err);
      }
    },
    [hasSelection, selectedIds, editor]
  );

  const tabs: { key: EffectsTab; label: string }[] = [
    { key: "animations", label: "Animations" },
    { key: "text-effects", label: "Text FX" },
    { key: "frame-effects", label: "Frames" },
  ];

  const renderGrid = (
    items: (AnimationItem | FrameEffectItem)[],
    onClick: (item: AnimationItem | FrameEffectItem) => void,
    disabled: boolean
  ) => (
    <div className="grid grid-cols-2 gap-2">
      {items.map((item) => {
        const isApplied = appliedEffects.has(item.id);
        return (
          <button
            key={item.id}
            type="button"
            onClick={() => onClick(item)}
            disabled={disabled}
            className={cn(
              "group relative overflow-hidden rounded-xl border transition-all disabled:opacity-40",
              isApplied
                ? "border-primary/50 ring-1 ring-primary/30"
                : "border-editor-border hover:border-primary/40 hover:ring-1 hover:ring-primary/20"
            )}
          >
            <div className="relative aspect-[4/3] w-full overflow-hidden">
              <img
                src={item.image}
                alt={item.label}
                className="h-full w-full object-cover transition-transform duration-300 group-hover:scale-110"
                loading="lazy"
              />
              <div className="absolute inset-0 bg-gradient-to-t from-black/90 via-black/20 to-transparent" />
              {isApplied && (
                <div className="absolute right-1.5 top-1.5 flex h-5 w-5 items-center justify-center rounded-full bg-primary shadow-md">
                  <Check className="h-3 w-3 text-primary-foreground" />
                </div>
              )}
            </div>
            <div className="px-2 py-2">
              <p className="text-xs font-semibold text-foreground">{item.label}</p>
              <p className="mt-0.5 text-[10px] leading-tight text-editor-text-muted">{item.description}</p>
            </div>
          </button>
        );
      })}
    </div>
  );

  return (
    <div className="space-y-3">
      {!hasSelection && (
        <div className="rounded-xl border border-dashed border-editor-border bg-editor-card/60 px-3 py-4 text-center text-xs text-editor-text-muted">
          Select an element on the timeline to apply effects
        </div>
      )}

      <div className="flex gap-1 rounded-xl border border-editor-border bg-editor-card p-1">
        {tabs.map((tab) => (
          <button
            key={tab.key}
            type="button"
            onClick={() => setActiveTab(tab.key)}
            className={cn(
              "flex-1 rounded-lg px-3 py-1.5 text-xs font-semibold transition-all",
              activeTab === tab.key
                ? "bg-primary/15 text-editor-accent-glow shadow-sm"
                : "text-muted-foreground hover:text-foreground"
            )}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {activeTab === "animations" && (
        <div className="space-y-2">
          {renderGrid(VISUALIZER_ANIMATIONS, (item) => handleApplyAnimation(item as AnimationItem), agentLoading || !hasSelection)}
          {hasSelection && (
            <button
              type="button"
              onClick={() => handleRemoveEffect("animation")}
              className="w-full rounded-xl border border-dashed border-editor-border px-3 py-2.5 text-center text-xs text-editor-text-muted transition hover:border-red-400/40 hover:text-red-400"
            >
              Remove animation
            </button>
          )}
        </div>
      )}

      {activeTab === "text-effects" && (
        <div className="space-y-2">
          {!isTextSelected && hasSelection && (
            <div className="rounded-xl border border-dashed border-editor-border bg-editor-card/60 px-3 py-3 text-center text-xs text-editor-text-muted">
              Select a text or caption element for text effects
            </div>
          )}
          {renderGrid(
            VISUALIZER_TEXT_EFFECTS,
            (item) => handleApplyTextEffect(item as AnimationItem),
            agentLoading || !hasSelection || !isTextSelected
          )}
          {hasSelection && isTextSelected && (
            <button
              type="button"
              onClick={() => handleRemoveEffect("textEffect")}
              className="w-full rounded-xl border border-dashed border-editor-border px-3 py-2.5 text-center text-xs text-editor-text-muted transition hover:border-red-400/40 hover:text-red-400"
            >
              Remove text effect
            </button>
          )}
        </div>
      )}

      {activeTab === "frame-effects" && (
        <div className="space-y-2">
          {renderGrid(VISUALIZER_FRAME_EFFECTS, handleApplyFrameEffect, agentLoading || !hasSelection)}
          {hasSelection && (
            <button
              type="button"
              onClick={() => handleRemoveEffect("frameEffects")}
              className="w-full rounded-xl border border-dashed border-editor-border px-3 py-2.5 text-center text-xs text-editor-text-muted transition hover:border-red-400/40 hover:text-red-400"
            >
              Remove frame effect
            </button>
          )}
        </div>
      )}
    </div>
  );
}

const PUBLIC_IMAGES = [
  { id: "pub-1", label: "Mountain Lake", url: "https://images.unsplash.com/photo-1506744038136-46273834b3fb?w=576&h=1024&fit=crop" },
  { id: "pub-2", label: "City Skyline", url: "https://images.unsplash.com/photo-1477959858617-67f85cf4f1df?w=576&h=1024&fit=crop" },
  { id: "pub-3", label: "Ocean Waves", url: "https://images.unsplash.com/photo-1507525428034-b723cf961d3e?w=576&h=1024&fit=crop" },
  { id: "pub-4", label: "Forest Path", url: "https://images.unsplash.com/photo-1441974231531-c6227db76b6e?w=576&h=1024&fit=crop" },
  { id: "pub-5", label: "Sunset Clouds", url: "https://images.unsplash.com/photo-1495616811223-4d98c6e9c869?w=576&h=1024&fit=crop" },
  { id: "pub-6", label: "Neon Lights", url: "https://images.unsplash.com/photo-1514525253161-7a46d19cd819?w=576&h=1024&fit=crop" },
  { id: "pub-7", label: "Desert Dunes", url: "https://images.unsplash.com/photo-1509316975850-ff9c5deb0cd9?w=576&h=1024&fit=crop" },
  { id: "pub-8", label: "Abstract Gradient", url: "https://images.unsplash.com/photo-1557682250-33bd709cbe85?w=576&h=1024&fit=crop" },
];

type MediaTab = "my-assets" | "upload" | "public";

function MediaPanel({ onInsertImage }: { onInsertImage: (src: string, label: string) => void | Promise<void> }) {
  const [mediaTab, setMediaTab] = useState<MediaTab>("my-assets");
  const [search, setSearch] = useState("");
  const [assets, setAssets] = useState<Asset[]>([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [urls, setUrls] = useState<Record<string, string>>({});
  const fileInputRef = useRef<HTMLInputElement>(null);

  const fetchAssets = useCallback(async () => {
    try {
      setLoading(true);
      const data = (await apiClient.get("/api/v1/assets", { params: { category: "images" } })).data as
        | Asset[]
        | { assets: Asset[] };
      const list: Asset[] = Array.isArray(data) ? data : (data as { assets: Asset[] }).assets ?? [];
      setAssets(list);
      const urlMap: Record<string, string> = {};
      await Promise.all(
        list.map(async (a) => {
          try {
            const res = (await apiClient.get(`/api/v1/assets/${a.id}/url`, { params: { category: "images" } })).data as {
              url: string;
            };
            urlMap[a.id] = res.url;
          } catch {
            /* skip */
          }
        })
      );
      setUrls(urlMap);
    } catch (err) {
      console.warn("[MediaPanel] Failed to list assets; using empty state.", err);
      setAssets([]);
      setUrls({});
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void fetchAssets();
  }, [fetchAssets]);

  const handleUpload = useCallback(
    async (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0];
      if (!file) return;
      try {
        setUploading(true);
        const formData = new FormData();
        formData.append("file", file);
        await apiClient.post("/api/v1/assets/upload", formData, {
          params: { category: "images" },
          headers: { "Content-Type": "multipart/form-data" },
        });
        await fetchAssets();
        setMediaTab("my-assets");
      } catch (err) {
        console.error("[MediaPanel] Upload failed:", err);
      } finally {
        setUploading(false);
        if (fileInputRef.current) fileInputRef.current.value = "";
      }
    },
    [fetchAssets]
  );

  const handleDelete = useCallback(async (id: string) => {
    try {
      await apiClient.delete(`/api/v1/assets/${id}`, { params: { category: "images" } });
      setAssets((prev) => prev.filter((a) => a.id !== id));
    } catch (err) {
      console.error("[MediaPanel] Delete failed:", err);
    }
  }, []);

  const mediaTabs: { key: MediaTab; label: string; icon: typeof ImageIcon }[] = [
    { key: "my-assets", label: "My Assets", icon: Clapperboard },
    { key: "upload", label: "Upload", icon: Upload },
    { key: "public", label: "Public", icon: ImageIcon },
  ];
  const filteredAssets = assets.filter((asset) => asset.filename.toLowerCase().includes(search.toLowerCase()));

  return (
    <div className="space-y-3">
      {/* Tab row */}
      <div className="flex gap-1 rounded-lg border border-editor-border bg-editor-card p-1">
        {mediaTabs.map((tab) => {
          const Icon = tab.icon;
          return (
            <button
              key={tab.key}
              type="button"
              onClick={() => setMediaTab(tab.key)}
              className={cn(
                "flex flex-1 items-center justify-center gap-1 rounded-md px-2 py-1.5 text-[11px] font-medium transition-all",
                mediaTab === tab.key
                  ? "bg-primary/18 text-primary shadow-sm"
                  : "bg-editor-control text-muted-foreground hover:bg-editor-control-hover hover:text-foreground"
              )}
            >
              <Icon className="h-3 w-3" />
              {tab.label}
            </button>
          );
        })}
      </div>

      {/* My Assets tab */}
      {mediaTab === "my-assets" && (
        <div className="space-y-3">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-editor-text-dim" />
            <input
              type="text"
              placeholder="Search images..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="w-full rounded-xl border border-editor-border bg-editor-control py-2.5 pl-9 pr-3 text-sm text-foreground placeholder:text-muted-foreground focus:border-primary/50 focus:outline-none focus:ring-1 focus:ring-primary/30"
            />
          </div>
          {loading ? (
            <div className="flex items-center justify-center py-8">
              <Loader2 className="h-5 w-5 animate-spin text-editor-text-dim" />
            </div>
          ) : assets.length === 0 ? (
            <div className="rounded-xl border border-dashed border-editor-border bg-editor-card/60 px-3 py-6 text-center">
              <ImageIcon className="mx-auto h-8 w-8 text-muted-foreground/25" />
              <p className="mt-2 text-sm text-editor-text-muted">No assets yet.</p>
              <button
                type="button"
                onClick={() => setMediaTab("upload")}
                className="mt-3 rounded-lg bg-primary px-4 py-1.5 text-xs font-semibold text-primary-foreground transition hover:bg-primary/90"
              >
                Upload your first
              </button>
            </div>
          ) : filteredAssets.length === 0 ? (
            <div className="rounded-xl border border-dashed border-editor-border bg-editor-card/60 px-3 py-6 text-center">
              <ImageIcon className="mx-auto h-8 w-8 text-muted-foreground/25" />
              <p className="mt-2 text-sm text-editor-text-muted">No images match &quot;{search}&quot;.</p>
            </div>
          ) : (
            <div className="grid grid-cols-2 gap-2">
              {filteredAssets.map((asset) => (
                <div
                  key={asset.id}
                  className="group relative overflow-hidden rounded-xl border border-editor-border transition hover:border-primary/40"
                >
                  <div className="block w-full">
                    {urls[asset.id] ? (
                      <img
                        src={urls[asset.id]}
                        alt={asset.filename}
                        className="aspect-video w-full object-cover"
                        loading="lazy"
                      />
                    ) : (
                      <div className="flex aspect-video items-center justify-center bg-editor-card">
                        <ImageIcon className="h-5 w-5 text-editor-text-dim" />
                      </div>
                    )}
                  </div>
                  <button
                    type="button"
                    onClick={() => {
                      const url = urls[asset.id];
                      if (url) void onInsertImage(url, asset.filename);
                    }}
                    className="absolute left-1 top-1 flex h-6 w-6 items-center justify-center rounded-full bg-editor-control text-foreground/80 opacity-0 transition group-hover:opacity-100 hover:bg-editor-control-hover hover:text-foreground"
                    title="Add to timeline"
                  >
                    <Plus className="h-3 w-3" />
                  </button>
                  <button
                    type="button"
                    onClick={() => void handleDelete(asset.id)}
                    className="absolute right-1 top-1 flex h-6 w-6 items-center justify-center rounded-full bg-editor-toolbar/95 text-red-400/70 opacity-0 transition group-hover:opacity-100 hover:text-red-400"
                    title="Delete"
                  >
                    <Trash2 className="h-3 w-3" />
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Upload tab */}
      {mediaTab === "upload" && (
        <div className="space-y-3">
          <div
            onClick={() => !uploading && fileInputRef.current?.click()}
            className={cn(
              "cursor-pointer rounded-xl border-2 border-dashed border-editor-border bg-editor-card/60 px-4 py-10 text-center transition hover:border-primary/40 hover:bg-primary/5",
              uploading && "pointer-events-none opacity-60"
            )}
          >
            {uploading ? (
              <>
                <Loader2 className="mx-auto h-8 w-8 animate-spin text-primary" />
                <p className="mt-3 text-sm font-medium text-foreground">Uploading...</p>
              </>
            ) : (
              <>
                <Upload className="mx-auto h-8 w-8 text-muted-foreground/30" />
                <p className="mt-3 text-sm font-medium text-foreground">Click to upload</p>
                <p className="mt-1 text-xs text-editor-text-muted">Images & videos supported</p>
              </>
            )}
          </div>
          <input ref={fileInputRef} type="file" accept="image/*" className="hidden" onChange={(e) => void handleUpload(e)} />
        </div>
      )}

      {/* Public tab */}
      {mediaTab === "public" && (
        <div className="grid grid-cols-2 gap-2">
          {PUBLIC_IMAGES.map((img) => (
            <div
              key={img.id}
              className="group relative overflow-hidden rounded-xl border border-editor-border transition hover:border-primary/40 hover:ring-1 hover:ring-primary/20"
            >
              <img
                src={img.url}
                alt={img.label}
                className="aspect-video w-full object-cover transition-transform duration-300 group-hover:scale-110"
                loading="lazy"
              />
              <div className="absolute inset-0 bg-gradient-to-t from-black/80 via-transparent to-transparent" />
              <button
                type="button"
                onClick={() => void onInsertImage(img.url, img.label)}
                className="absolute left-1 top-1 flex h-6 w-6 items-center justify-center rounded-full bg-editor-control text-foreground/80 opacity-0 transition group-hover:opacity-100 hover:bg-editor-control-hover hover:text-foreground"
                title="Add to timeline"
              >
                <Plus className="h-3 w-3" />
              </button>
              <p className="absolute bottom-0 w-full truncate px-2 py-1.5 text-[10px] font-medium text-foreground">
                {img.label}
              </p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function VideoPanel({ onInsertImage }: { onInsertImage: (src: string, label: string) => void | Promise<void> }) {
  const [videoTab, setVideoTab] = useState<MediaTab>("my-assets");
  const [search, setSearch] = useState("");
  const [assets, setAssets] = useState<Asset[]>([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [urls, setUrls] = useState<Record<string, string>>({});
  const fileInputRef = useRef<HTMLInputElement>(null);

  const fetchAssets = useCallback(async () => {
    try {
      setLoading(true);
      // Reuse "images" category — backend stores both; filter client-side for video types
      const data = (await apiClient.get("/api/v1/assets", { params: { category: "images" } })).data as
        | Asset[]
        | { assets: Asset[] };
      const all: Asset[] = Array.isArray(data) ? data : (data as { assets: Asset[] }).assets ?? [];
      const videos = all.filter((a) => a.content_type.startsWith("video/"));
      setAssets(videos);
      const urlMap: Record<string, string> = {};
      await Promise.all(
        videos.map(async (a) => {
          try {
            const res = (await apiClient.get(`/api/v1/assets/${a.id}/url`, { params: { category: "images" } })).data as {
              url: string;
            };
            urlMap[a.id] = res.url;
          } catch {
            /* skip */
          }
        })
      );
      setUrls(urlMap);
    } catch (err) {
      console.warn("[VideoPanel] Failed to list assets; using empty state.", err);
      setAssets([]);
      setUrls({});
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void fetchAssets();
  }, [fetchAssets]);

  const handleUpload = useCallback(
    async (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0];
      if (!file) return;
      try {
        setUploading(true);
        const formData = new FormData();
        formData.append("file", file);
        await apiClient.post("/api/v1/assets/upload", formData, {
          params: { category: "images" },
          headers: { "Content-Type": "multipart/form-data" },
        });
        await fetchAssets();
        setVideoTab("my-assets");
      } catch (err) {
        console.error("[VideoPanel] Upload failed:", err);
      } finally {
        setUploading(false);
        if (fileInputRef.current) fileInputRef.current.value = "";
      }
    },
    [fetchAssets]
  );

  const handleDelete = useCallback(async (id: string) => {
    try {
      await apiClient.delete(`/api/v1/assets/${id}`, { params: { category: "images" } });
      setAssets((prev) => prev.filter((a) => a.id !== id));
    } catch (err) {
      console.error("[VideoPanel] Delete failed:", err);
    }
  }, []);

  const videoTabs: { key: MediaTab; label: string; icon: typeof ImageIcon }[] = [
    { key: "my-assets", label: "My Assets", icon: Clapperboard },
    { key: "upload", label: "Upload", icon: Upload },
    { key: "public", label: "Public", icon: Film },
  ];
  const filteredAssets = assets.filter((asset) => asset.filename.toLowerCase().includes(search.toLowerCase()));

  return (
    <div className="space-y-3">
      <div className="flex gap-1 rounded-lg border border-editor-border bg-editor-card p-1">
        {videoTabs.map((tab) => {
          const Icon = tab.icon;
          return (
            <button
              key={tab.key}
              type="button"
              onClick={() => setVideoTab(tab.key)}
              className={cn(
                "flex flex-1 items-center justify-center gap-1 rounded-md px-2 py-1.5 text-[11px] font-medium transition-all",
                videoTab === tab.key
                  ? "bg-primary/18 text-primary shadow-sm"
                  : "bg-editor-control text-muted-foreground hover:bg-editor-control-hover hover:text-foreground"
              )}
            >
              <Icon className="h-3 w-3" />
              {tab.label}
            </button>
          );
        })}
      </div>

      {videoTab === "my-assets" && (
        <div className="space-y-3">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-editor-text-dim" />
            <input
              type="text"
              placeholder="Search videos..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="w-full rounded-xl border border-editor-border bg-editor-control py-2.5 pl-9 pr-3 text-sm text-foreground placeholder:text-muted-foreground focus:border-primary/50 focus:outline-none focus:ring-1 focus:ring-primary/30"
            />
          </div>
          {loading ? (
            <div className="flex items-center justify-center py-8">
              <Loader2 className="h-5 w-5 animate-spin text-editor-text-dim" />
            </div>
          ) : assets.length === 0 ? (
            <div className="rounded-xl border border-dashed border-editor-border bg-editor-card/60 px-3 py-6 text-center">
              <Film className="mx-auto h-8 w-8 text-muted-foreground/25" />
              <p className="mt-2 text-sm text-editor-text-muted">No videos yet.</p>
              <button
                type="button"
                onClick={() => setVideoTab("upload")}
                className="mt-3 rounded-lg bg-primary px-4 py-1.5 text-xs font-semibold text-primary-foreground transition hover:bg-primary/90"
              >
                Upload your first
              </button>
            </div>
          ) : filteredAssets.length === 0 ? (
            <div className="rounded-xl border border-dashed border-editor-border bg-editor-card/60 px-3 py-6 text-center">
              <Film className="mx-auto h-8 w-8 text-muted-foreground/25" />
              <p className="mt-2 text-sm text-editor-text-muted">No videos match &quot;{search}&quot;.</p>
            </div>
          ) : (
            <div className="grid grid-cols-2 gap-2">
              {filteredAssets.map((asset) => (
                <div
                  key={asset.id}
                  className="group relative overflow-hidden rounded-xl border border-editor-border transition hover:border-primary/40"
                >
                  <div className="block w-full">
                    {urls[asset.id] ? (
                      <video
                        src={urls[asset.id]}
                        className="aspect-video w-full object-cover"
                        muted
                        preload="metadata"
                      />
                    ) : (
                      <div className="flex aspect-video items-center justify-center bg-editor-card">
                        <Film className="h-5 w-5 text-editor-text-dim" />
                      </div>
                    )}
                  </div>
                  <button
                    type="button"
                    onClick={() => {
                      const url = urls[asset.id];
                      if (url) void onInsertImage(url, asset.filename);
                    }}
                    className="absolute left-1 top-1 flex h-6 w-6 items-center justify-center rounded-full bg-editor-control text-foreground/80 opacity-0 transition group-hover:opacity-100 hover:bg-editor-control-hover hover:text-foreground"
                    title="Add to timeline"
                  >
                    <Plus className="h-3 w-3" />
                  </button>
                  <button
                    type="button"
                    onClick={() => void handleDelete(asset.id)}
                    className="absolute right-1 top-1 flex h-6 w-6 items-center justify-center rounded-full bg-editor-toolbar/95 text-red-400/70 opacity-0 transition group-hover:opacity-100 hover:text-red-400"
                    title="Delete"
                  >
                    <Trash2 className="h-3 w-3" />
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {videoTab === "upload" && (
        <div className="space-y-3">
          <div
            onClick={() => !uploading && fileInputRef.current?.click()}
            className={cn(
              "cursor-pointer rounded-xl border-2 border-dashed border-editor-border bg-editor-card/60 px-4 py-10 text-center transition hover:border-primary/40 hover:bg-primary/5",
              uploading && "pointer-events-none opacity-60"
            )}
          >
            {uploading ? (
              <>
                <Loader2 className="mx-auto h-8 w-8 animate-spin text-primary" />
                <p className="mt-3 text-sm font-medium text-foreground">Uploading...</p>
              </>
            ) : (
              <>
                <Upload className="mx-auto h-8 w-8 text-muted-foreground/30" />
                <p className="mt-3 text-sm font-medium text-foreground">Click to upload</p>
                <p className="mt-1 text-xs text-editor-text-muted">Video files supported</p>
              </>
            )}
          </div>
          <input ref={fileInputRef} type="file" accept="video/*" className="hidden" onChange={(e) => void handleUpload(e)} />
        </div>
      )}

      {videoTab === "public" && (
        <div className="rounded-xl border border-dashed border-editor-border bg-editor-card/60 px-3 py-6 text-center">
          <Film className="mx-auto h-8 w-8 text-muted-foreground/25" />
          <p className="mt-2 text-sm text-editor-text-muted">Public videos coming soon</p>
        </div>
      )}
    </div>
  );
}

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
            (el) => (el as unknown as { type: string }).type === "text" || (el as unknown as { type: string }).type === "caption"
          ).length,
        0
      ),
    };
  }, [present, project.project_json]);

  const currentSelection = getSelectedItemLabel(selectedItem);

  return (
    <aside className="flex h-full w-[320px] min-w-[320px] max-w-[320px] border-r border-editor-border bg-editor-panel">
      {/* Icon sidebar */}
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

      {/* Panel content */}
      <div className="flex min-w-0 flex-1 flex-col overflow-hidden">
        <div className="shrink-0 border-b border-editor-border px-4 py-3">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-2xl bg-primary/15 text-editor-accent-glow">
              {(() => {
                const ActiveIcon = PANEL_CONFIG.find((p) => p.key === activePanel)?.icon ?? ImageIcon;
                return <ActiveIcon className="h-5 w-5" />;
              })()}
            </div>
            <div className="min-w-0">
              <p className="text-sm font-semibold text-foreground">
                {PANEL_CONFIG.find((p) => p.key === activePanel)?.label}
              </p>
              <p className="text-xs text-editor-text-muted">
                {PANEL_CONFIG.find((p) => p.key === activePanel)?.description}
              </p>
            </div>
          </div>
        </div>

        <div className="editor-scroll min-h-0 flex-1 overflow-y-auto px-4 py-3">
          {activePanel === "media" && <MediaPanel onInsertImage={onInsertImage} />}

          {activePanel === "video" && <VideoPanel onInsertImage={onInsertImage} />}

          {activePanel === "text" && (
            <div className="space-y-4">
              <div className="rounded-2xl border border-editor-border bg-editor-card p-4">
                <p className="text-sm font-semibold text-foreground">Text presets</p>
                <p className="mt-1 text-xs text-editor-text-muted">Insert overlays directly without opening the agent.</p>
                <div className="mt-4 space-y-3">
                  {TEXT_PRESETS.map((preset) => (
                    <button
                      key={preset.label}
                      type="button"
                      onClick={() =>
                        void onInsertText(
                          preset.title,
                          preset.label === "Hook Title"
                            ? "hook"
                            : preset.label === "Lower Third"
                            ? "lower-third"
                            : "callout"
                        )
                      }
                      className="w-full rounded-2xl border border-editor-border bg-editor-card px-4 py-3 text-left transition hover:border-primary/45 hover:bg-primary/10"
                    >
                      <p className="text-sm font-medium text-foreground">{preset.label}</p>
                      <p className="mt-1 text-xs text-muted-foreground">{preset.subtitle}</p>
                      <p className="mt-3 text-[11px] uppercase tracking-[0.18em] text-muted-foreground/30">{preset.title}</p>
                    </button>
                  ))}
                </div>
              </div>
            </div>
          )}

          {activePanel === "caption" && (
            <CaptionPanel onQuickAction={onQuickAction} agentLoading={agentLoading} />
          )}

          {activePanel === "audio" && (
            <AudioPanel project={project} onQuickAction={onQuickAction} agentLoading={agentLoading} />
          )}

          {activePanel === "effects" && (
            <EffectsPanel onQuickAction={onQuickAction} agentLoading={agentLoading} />
          )}
        </div>

        {/* Footer */}
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
