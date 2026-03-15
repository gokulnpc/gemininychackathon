"use client";

import type { RefObject } from "react";
import { useCallback, useRef, useState } from "react";
import {
  Check,
  ChevronUp,
  Loader2,
  Mic,
  MicOff,
  Monitor,
  MonitorOff,
  Pause,
  Pencil,
  Play,
  ScanEye,
  Search,
  Send,
  Sparkles,
  Wand2,
  X,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { apiFetch } from "@/lib/api";
import type {
  AgentMessage,
  CreativeBlock,
  CreativePreviewOption,
  EditProposal,
  ScriptProposal,
  ThumbnailOption,
} from "@/components/editor/types";

interface AssetMeta {
  id: string;
  filename: string;
  content_type: string;
  uploaded_at: string;
  gcs_key: string;
}

interface MentionState {
  visible: boolean;
  query: string;
  atIndex: number;
  assets: AssetMeta[];
}

interface ChipOption {
  label: string;
  instruction: string;
}

const MUSIC_PRESETS = [
  "happy_rhythm",
  "quiet_before_storm",
  "peaceful_vibes",
  "brilliant_symphony",
  "breathing_shadows",
  "lyria",
  "none",
];
const TEXT_POSITIONS = ["top", "middle", "bottom"];

const PUBLIC_IMAGES: ChipOption[] = [
  {
    label: "Mountain Lake",
    instruction:
      "Replace the selected image with Mountain Lake. Use this URL: https://images.unsplash.com/photo-1506744038136-46273834b3fb?w=576&h=1024&fit=crop",
  },
  {
    label: "City Skyline",
    instruction:
      "Replace the selected image with City Skyline. Use this URL: https://images.unsplash.com/photo-1477959858617-67f85cf4f1df?w=576&h=1024&fit=crop",
  },
  {
    label: "Ocean Waves",
    instruction:
      "Replace the selected image with Ocean Waves. Use this URL: https://images.unsplash.com/photo-1507525428034-b723cf961d3e?w=576&h=1024&fit=crop",
  },
  {
    label: "Forest Path",
    instruction:
      "Replace the selected image with Forest Path. Use this URL: https://images.unsplash.com/photo-1441974231531-c6227db76b6e?w=576&h=1024&fit=crop",
  },
  {
    label: "Sunset Clouds",
    instruction:
      "Replace the selected image with Sunset Clouds. Use this URL: https://images.unsplash.com/photo-1495616811223-4d98c6e9c869?w=576&h=1024&fit=crop",
  },
  {
    label: "Neon Lights",
    instruction:
      "Replace the selected image with Neon Lights. Use this URL: https://images.unsplash.com/photo-1514525253161-7a46d19cd819?w=576&h=1024&fit=crop",
  },
  {
    label: "Desert Dunes",
    instruction:
      "Replace the selected image with Desert Dunes. Use this URL: https://images.unsplash.com/photo-1509316975850-ff9c5deb0cd9?w=576&h=1024&fit=crop",
  },
  {
    label: "Abstract Gradient",
    instruction:
      "Replace the selected image with Abstract Gradient. Use this URL: https://images.unsplash.com/photo-1557682250-33bd709cbe85?w=576&h=1024&fit=crop",
  },
];

const LABEL_CHIPS: Record<string, ChipOption[]> = {
  "Change music": MUSIC_PRESETS.map((p) => ({
    label: p === "lyria" ? "lyria (AI ✨)" : p.replace(/_/g, " "),
    instruction:
      p === "lyria" ? "Generate AI music using Lyria for this video" : p,
  })),
  "Swap selected image": PUBLIC_IMAGES,
  "Adjust volume": [
    {
      label: "music louder",
      instruction: "Turn up the background music volume",
    },
    {
      label: "music quieter",
      instruction: "Turn down the background music volume",
    },
    { label: "voice louder", instruction: "Turn up the voiceover volume" },
    { label: "voice quieter", instruction: "Turn down the voiceover volume" },
  ],
};

interface DetectResult {
  options: ChipOption[];
  volumeInput?: boolean;
}

function detectOptionSet(text: string): DetectResult | null {
  if (text.includes("I can:")) return null;
  // Volume disambiguation: "a little" / "a lot" with custom input
  if (
    text.toLowerCase().includes("a little") &&
    text.toLowerCase().includes("a lot")
  )
    return {
      options: [
        { label: "a little", instruction: "a little" },
        { label: "a lot", instruction: "a lot" },
      ],
      volumeInput: true,
    };
  // Detect "Which — background music or voiceover?" disambiguation
  if (
    /background music or voiceover/i.test(text) ||
    /music or voiceover/i.test(text)
  ) {
    return {
      options: [
        { label: "background music", instruction: "background music" },
        { label: "voiceover", instruction: "voiceover" },
      ],
    };
  }
  // Music preset chips
  if (MUSIC_PRESETS.filter((p) => text.includes(p)).length >= 3)
    return {
      options: MUSIC_PRESETS.map((p) => ({
        label: p === "lyria" ? "lyria (AI ✨)" : p.replace(/_/g, " "),
        instruction:
          p === "lyria" ? "Generate AI music using Lyria for this video" : p,
      })),
    };
  // Delete overlay disambiguation: parse quoted overlay names as chips
  if (
    /which should I remove/i.test(text) ||
    /found these text overlays/i.test(text)
  ) {
    const quoted = [...text.matchAll(/'([^']+)'/g)]
      .map((m) => m[1])
      .filter(Boolean);
    const unique = [...new Set(quoted)];
    if (unique.length >= 1) {
      const chips: ChipOption[] = unique.map((label) => ({
        label,
        instruction: `Remove the text overlay that says "${label}"`,
      }));
      chips.push({
        label: "remove all",
        instruction: "Remove all text overlays",
      });
      return { options: chips };
    }
  }
  // Text position chips
  if (TEXT_POSITIONS.filter((p) => text.toLowerCase().includes(p)).length >= 2)
    return {
      options: TEXT_POSITIONS.map((p) => ({ label: p, instruction: p })),
    };
  return null;
}

type AgentMode = "live_edit" | "creative" | "screen_aware";

const MODES = [
  {
    key: "live_edit" as AgentMode,
    label: "Live Edit",
    Icon: Pencil,
    description: "Apply confirmed edits to the timeline",
    placeholder: "Tell Scout what to change...",
    accent: "text-sky-400",
    activeBg: "bg-sky-500/30 text-sky-100 shadow-sm",
  },
  {
    key: "creative" as AgentMode,
    label: "Creative",
    Icon: Wand2,
    description: "Generate visual concepts, images & ideas",
    placeholder: "Describe a creative direction or concept...",
    accent: "text-violet-400",
    activeBg: "bg-violet-500/30 text-violet-100 shadow-sm",
  },
  {
    key: "screen_aware" as AgentMode,
    label: "Screen Aware",
    Icon: ScanEye,
    description: "Analyse the canvas and act on what's visible",
    placeholder: "What do you see? Ask Scout to analyse or fix it...",
    accent: "text-emerald-400",
    activeBg: "bg-emerald-500/30 text-emerald-100 shadow-sm",
  },
] as const;

const MODE_QUICK_ACTIONS: Record<
  AgentMode,
  readonly { label: string; instruction: string }[]
> = {
  live_edit: [
    {
      label: "Change music",
      instruction:
        "Change the background music. Ask which preset: happy_rhythm, quiet_before_storm, peaceful_vibes, brilliant_symphony, breathing_shadows, lyria (AI-generated), none.",
    },
    {
      label: "Swap selected image",
      instruction:
        "Swap the currently selected image with a public stock photo. Do NOT call get_user_assets — the user will @mention their own uploaded assets in the chat if they want to use them. Just ask which stock photo they want from the chips shown, or wait for them to @mention an asset.",
    },
    {
      label: "Adjust volume",
      instruction:
        "Adjust the background music or voiceover volume. Ask me whether to adjust music or voiceover, and whether to make it louder or quieter.",
    },
    {
      label: "Add text overlay",
      instruction:
        "Add a text overlay to the video. First ask me what text to display (a single question only). Only after I provide the text, ask where to place it (top / middle / bottom).",
    },
  ],
  creative: [
    {
      label: "Create from scratch ✦",
      instruction: "I want to create a new video from scratch. Ask me what it's about, then generate a storyboard for me.",
    },
    {
      label: "Creative direction ✦",
      instruction:
        "Generate creative direction for this video — visual concepts, hook ideas, caption themes, and mood suggestions with generated preview images. Use mode=social_content.",
    },
    {
      label: "New thumbnail ✦",
      instruction:
        "Generate 2 new clickbait thumbnail options for this video based on what you see on screen. Use the current screen as reference.",
    },
    {
      label: "Generate image ✦",
      instruction:
        "Generate an AI image for the currently selected scene and replace it. First check what is selected, then generate a fitting image based on the video's theme.",
    },
  ],
  screen_aware: [
    {
      label: "Inspect screen",
      instruction:
        "Analyse my screen carefully. What do you see? Note any visual improvements I could make — text positioning, caption style, contrast, pacing. Maximum 3 sentences.",
    },
    {
      label: "What's wrong?",
      instruction:
        "Look at what's visible on screen and tell me the top 2–3 things I should fix to make this video more engaging.",
    },
    {
      label: "Suggest edits",
      instruction:
        "Based on what you see on screen, suggest the most impactful edit I could make right now and apply it.",
    },
    {
      label: "Fix selected element",
      instruction:
        "Look at the currently selected element on screen. What's wrong with it and how should I improve it? Then apply the fix.",
    },
  ],
};

function renderAgentText(text: string): React.ReactNode {
  const parts = text
    .split("•")
    .map((s) => s.trim())
    .filter(Boolean);
  if (parts.length >= 3) {
    const [intro, ...items] = parts;
    return (
      <>
        {intro && <p className="mb-2 text-sm leading-relaxed">{intro}</p>}
        <ul className="space-y-1">
          {items.map((item, i) => (
            <li
              key={i}
              className="flex items-start gap-1.5 text-sm leading-relaxed"
            >
              <span className="mt-0.5 shrink-0 text-primary">•</span>
              <span>{item}</span>
            </li>
          ))}
        </ul>
      </>
    );
  }
  return <span>{text}</span>;
}

function cleanTextForChips(text: string): string {
  return (
    text
      .replace(/[.?]?\s*Options:[\s\S]*$/i, "")
      .replace(/\s*Which should I remove.*$/i, "")
      .replace(/\s*—\s*say ['"]a little['"].*$/i, "")
      .trim() || text
  );
}

function LyriaAudioPlayer({ src }: { src: string }) {
  const audioRef = useRef<HTMLAudioElement>(null);
  const [playing, setPlaying] = useState(false);
  const [progress, setProgress] = useState(0);
  const [duration, setDuration] = useState(0);

  const toggle = () => {
    const a = audioRef.current;
    if (!a) return;
    if (playing) {
      a.pause();
      setPlaying(false);
    } else {
      void a.play();
      setPlaying(true);
    }
  };

  const seek = (e: React.MouseEvent<HTMLDivElement>) => {
    const a = audioRef.current;
    if (!a || !duration) return;
    const rect = e.currentTarget.getBoundingClientRect();
    const ratio = (e.clientX - rect.left) / rect.width;
    a.currentTime = ratio * duration;
  };

  const fmt = (s: number) =>
    `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, "0")}`;

  return (
    <div className="mt-2 rounded-lg border border-editor-border bg-editor-surface p-2.5">
      <p className="mb-2 text-[10px] font-medium uppercase tracking-widest text-editor-text-dim">
        AI Music Preview
      </p>
      {/* eslint-disable-next-line jsx-a11y/media-has-caption */}
      <audio
        ref={audioRef}
        src={src}
        onTimeUpdate={(e) => setProgress(e.currentTarget.currentTime)}
        onLoadedMetadata={(e) => setDuration(e.currentTarget.duration)}
        onEnded={() => {
          setPlaying(false);
          setProgress(0);
        }}
      />
      <div className="flex items-center gap-2">
        <button
          type="button"
          onClick={toggle}
          className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-primary/20 text-primary-foreground hover:bg-primary/35"
        >
          {playing ? (
            <Pause className="h-3.5 w-3.5" />
          ) : (
            <Play className="h-3.5 w-3.5" />
          )}
        </button>
        <div
          className="h-1.5 flex-1 cursor-pointer rounded-full bg-primary/20"
          onClick={seek}
        >
          <div
            className="h-full rounded-full bg-primary transition-all"
            style={{ width: `${duration ? (progress / duration) * 100 : 0}%` }}
          />
        </div>
        <span className="shrink-0 text-[10px] tabular-nums text-muted-foreground">
          {fmt(progress)} / {fmt(duration)}
        </span>
      </div>
    </div>
  );
}

interface AgentPanelProps {
  agentPanelOpen: boolean;
  agentMessages: AgentMessage[];
  agentInput: string;
  agentLoading: boolean;
  isVoiceActive: boolean;
  agentBottomRef: RefObject<HTMLDivElement | null>;
  setAgentPanelOpen: (open: boolean) => void;
  setAgentInput: (value: string) => void;
  sendAgentInstruction: (instruction: string, displayText?: string) => void;
  startVoiceEdit: () => void | Promise<void>;
  stopVoiceEdit: () => void;
  isScreenShareActive: boolean;
  startScreenShare: () => void | Promise<void>;
  stopScreenShare: () => void;
  inspectScreen?: () => void;
  confirmProposal: (proposal: EditProposal) => void;
  rejectProposal: (proposal: EditProposal) => void;
  revertLastEdit: () => void;
  hasUndo: boolean;
}

export function AgentPanel({
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
  stopVoiceEdit,
  isScreenShareActive,
  startScreenShare,
  stopScreenShare,
  inspectScreen,
  confirmProposal,
  rejectProposal,
  revertLastEdit,
  hasUndo,
}: AgentPanelProps) {
  const [agentMode, setAgentMode] = useState<AgentMode>("live_edit");
  const [showModeMenu, setShowModeMenu] = useState(false);
  const activeMode = MODES.find((m) => m.key === agentMode)!;
  const [mentionState, setMentionState] = useState<MentionState | null>(null);
  const [pendingChipsLabel, setPendingChipsLabel] = useState<string | null>(
    null,
  );
  const [volumeDraft, setVolumeDraft] = useState("");
  const mentionedAssetsRef = useRef<Record<string, AssetMeta>>({});
  const assetCacheRef = useRef<AssetMeta[] | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const fetchMentionAssets = useCallback(async (): Promise<AssetMeta[]> => {
    if (assetCacheRef.current) return assetCacheRef.current;
    try {
      const [imgRes, musicRes] = await Promise.all([
        apiFetch("/api/v1/assets?category=images"),
        apiFetch("/api/v1/assets?category=music"),
      ]);
      const imgs = imgRes.ok
        ? ((await imgRes.json()) as { assets: AssetMeta[] }).assets
        : [];
      const music = musicRes.ok
        ? ((await musicRes.json()) as { assets: AssetMeta[] }).assets
        : [];
      assetCacheRef.current = [...imgs, ...music];
      return assetCacheRef.current;
    } catch {
      return [];
    }
  }, []);

  const handleInputChange = useCallback(
    async (e: React.ChangeEvent<HTMLTextAreaElement>) => {
      const value = e.target.value;
      setAgentInput(value);

      const cursor = e.target.selectionStart ?? value.length;
      const before = value.slice(0, cursor);
      const match = before.match(/@(\w*)$/);

      if (match) {
        const query = match[1].toLowerCase();
        const all = await fetchMentionAssets();
        const filtered = all
          .filter((a) => a.filename.toLowerCase().includes(query))
          .slice(0, 8);
        if (filtered.length > 0) {
          setMentionState({
            visible: true,
            query,
            atIndex: cursor - match[0].length,
            assets: filtered,
          });
        } else {
          setMentionState(null);
        }
      } else {
        setMentionState(null);
      }
    },
    [fetchMentionAssets, setAgentInput],
  );

  const insertMention = useCallback(
    (asset: AssetMeta) => {
      if (!mentionState) return;
      const token = `@${asset.filename}`;
      const before = agentInput.slice(0, mentionState.atIndex);
      const after = agentInput.slice(
        mentionState.atIndex + 1 + mentionState.query.length,
      );
      const newValue = before + token + after;
      setAgentInput(newValue);
      mentionedAssetsRef.current[token] = asset;
      setMentionState(null);
      textareaRef.current?.focus();
    },
    [agentInput, mentionState, setAgentInput],
  );

  const handleSend = useCallback(
    (instruction: string, displayText?: string) => {
      if (!instruction.trim()) return;
      const mentions = Object.values(mentionedAssetsRef.current);
      const enriched =
        mentions.length > 0
          ? `${instruction}\n\n[Mentioned assets: ${mentions.map((a) => `${a.filename} (id:${a.id}, category:${a.content_type.startsWith("image") ? "images" : "music"})`).join(", ")}]`
          : instruction;
      const shown = displayText ?? instruction;
      mentionedAssetsRef.current = {};
      setMentionState(null);
      // Track which quick action fired so we can show context chips after agent responds
      setPendingChipsLabel(
        displayText && LABEL_CHIPS[displayText] ? displayText : null,
      );
      sendAgentInstruction(enriched, shown);
    },
    [sendAgentInstruction],
  );

  if (!agentPanelOpen) return null;

  return (
    <div className="flex h-full w-[340px] flex-col border-l border-editor-border bg-editor-surface">
      <div className="flex items-center justify-between border-b border-editor-border px-4 py-3">
        <div className="flex items-center gap-2">
          <div className="flex h-8 w-8 items-center justify-center rounded-full bg-primary/20">
            <Sparkles className="h-4 w-4 text-primary-foreground" />
          </div>
          <div>
            <p className="text-sm font-semibold text-editor-text">AI Copilot</p>
            <p className="text-[10px] text-editor-text-dim">
              {activeMode.description}
            </p>
          </div>
        </div>
        <button
          type="button"
          onClick={() => setAgentPanelOpen(false)}
          className="text-editor-text-dim transition-colors hover:text-editor-text"
        >
          <X className="h-4 w-4" />
        </button>
      </div>

      <div className="editor-scroll flex-1 space-y-3 overflow-y-auto p-3">
        {agentMessages.map((msg) => (
          <div
            key={msg.id}
            className={cn(
              "flex flex-col gap-1",
              msg.role === "user" ? "items-end" : "items-start",
            )}
          >
            <div
              className={cn(
                "max-w-[90%] rounded-2xl px-3 py-2 text-sm leading-relaxed",
                msg.role === "user"
                  ? "rounded-br-sm bg-primary text-primary-foreground"
                  : msg.isError
                    ? "rounded-bl-sm border border-destructive/20 bg-destructive/20 text-destructive-foreground"
                    : msg.isInspection
                      ? "rounded-bl-sm border border-amber-500/20 bg-amber-500/5 text-foreground/90"
                      : "rounded-bl-sm bg-editor-surface-raised text-foreground/90",
              )}
            >
              {msg.isInspection && !msg.isThinking && (
                <p className="mb-1 text-[10px] font-medium uppercase tracking-widest text-amber-400/70">
                  Screen analysis
                </p>
              )}
              {msg.isThinking && !msg.text ? (
                <div className="flex items-center gap-2 text-muted-foreground">
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  <span>Thinking...</span>
                </div>
              ) : msg.text ? (
                (() => {
                  const isLastAgentMsg =
                    msg.role === "agent" &&
                    msg ===
                      agentMessages.filter((m) => m.role === "agent").at(-1);
                  const hasChips =
                    (isLastAgentMsg &&
                      pendingChipsLabel &&
                      LABEL_CHIPS[pendingChipsLabel]) ||
                    detectOptionSet(msg.text);
                  const displayText = hasChips
                    ? cleanTextForChips(msg.text)
                    : msg.text;
                  return renderAgentText(displayText);
                })()
              ) : (
                <span className="italic text-muted-foreground">
                  Processing...
                </span>
              )}

              {/* Option chips — shown when agent asks user to pick a preset/style/position */}
              {msg.role === "agent" &&
                !msg.isThinking &&
                !msg.proposal &&
                (() => {
                  const isLastAgentMsg =
                    msg ===
                    agentMessages.filter((m) => m.role === "agent").at(-1);
                  const detected: DetectResult | null =
                    (isLastAgentMsg && pendingChipsLabel
                      ? { options: LABEL_CHIPS[pendingChipsLabel] ?? [] }
                      : null) ?? (msg.text ? detectOptionSet(msg.text) : null);
                  const chips = detected?.options ?? null;
                  if (!chips || chips.length === 0) return null;
                  return (
                    <div className="mt-2">
                      <div className="flex flex-wrap gap-1.5">
                        {chips.map((chip) => (
                          <button
                            key={chip.instruction}
                            type="button"
                            onClick={() =>
                              handleSend(chip.instruction, chip.label)
                            }
                            disabled={agentLoading}
                            className="rounded-full border border-primary/30 bg-primary/10 px-2.5 py-1 text-[11px] font-medium text-primary-foreground/80 transition-colors hover:bg-primary/25 disabled:opacity-40"
                          >
                            {chip.label}
                          </button>
                        ))}
                      </div>
                      {detected?.volumeInput && (
                        <div className="mt-1.5 flex items-center gap-1.5">
                          <input
                            type="number"
                            min="0"
                            max="1"
                            step="0.05"
                            placeholder="0.0 – 1.0"
                            value={volumeDraft}
                            onChange={(e) => setVolumeDraft(e.target.value)}
                            onKeyDown={(e) => {
                              if (e.key === "Enter" && volumeDraft) {
                                handleSend(volumeDraft, volumeDraft);
                                setVolumeDraft("");
                              }
                            }}
                            className="w-full rounded-lg border border-editor-border bg-editor-surface px-2 py-1 text-xs text-foreground focus:border-primary/50 focus:outline-none"
                          />
                          <button
                            type="button"
                            onClick={() => {
                              if (volumeDraft) {
                                handleSend(volumeDraft, volumeDraft);
                                setVolumeDraft("");
                              }
                            }}
                            disabled={!volumeDraft || agentLoading}
                            className="shrink-0 rounded-lg bg-primary px-2.5 py-1 text-[11px] font-medium text-primary-foreground disabled:opacity-40"
                          >
                            Set
                          </button>
                        </div>
                      )}
                    </div>
                  );
                })()}

              {msg.lyriaPreviewUrl && (
                <LyriaAudioPlayer src={msg.lyriaPreviewUrl} />
              )}

              {msg.previewOptions && msg.previewOptions.length > 0 && (
                <div className="mt-2">
                  <p className="mb-1.5 text-[10px] font-medium uppercase tracking-widest text-editor-text-dim">
                    {msg.previewOptions.length} style option
                    {msg.previewOptions.length !== 1 ? "s" : ""}
                  </p>
                  <div className="flex flex-col gap-2">
                    {msg.previewOptions.map((opt: CreativePreviewOption) => (
                      <div
                        key={opt.option_id}
                        className="group overflow-hidden rounded-lg border border-editor-border"
                      >
                        <div className="relative">
                          <img
                            src={`data:${opt.image.mime_type ?? "image/png"};base64,${opt.image.content}`}
                            alt={opt.title}
                            className="w-full object-cover"
                          />
                          <div className="absolute inset-0 flex items-end bg-gradient-to-t from-black/60 to-transparent p-2">
                            <span className="text-xs font-semibold text-white">
                              {opt.title}
                            </span>
                          </div>
                        </div>
                        <button
                          type="button"
                          onClick={() =>
                            handleSend(
                              `Use the "${opt.title}" style (option ${opt.index + 1} from the last preview)`,
                            )
                          }
                          className="w-full border-t border-editor-border bg-editor-surface-raised py-1.5 text-xs text-foreground/70 transition-colors hover:bg-editor-surface hover:text-foreground"
                        >
                          Use this style →
                        </button>
                      </div>
                    ))}
                  </div>
                </div>
              )}
              {msg.scriptProposals && msg.scriptProposals.length > 0 && (
                <div className="mt-2 flex flex-col gap-2">
                  <p className="text-[10px] font-medium uppercase tracking-widest text-editor-text-dim">
                    Choose a story direction
                  </p>
                  {msg.scriptProposals.map((p: ScriptProposal, i: number) => (
                    <button
                      key={i}
                      type="button"
                      onClick={() =>
                        handleSend(
                          `Use script option ${i + 1}: "${p.title}". Brief: ${p.hook} ${p.arc}`,
                          p.title,
                        )
                      }
                      className="group flex flex-col gap-1 rounded-xl border border-editor-border bg-editor-surface-raised p-3 text-left transition-colors hover:border-violet-500/50 hover:bg-violet-500/10"
                    >
                      <span className="text-[12px] font-semibold text-foreground">{p.title}</span>
                      <span className="text-[11px] italic text-sky-300">"{p.hook}"</span>
                      <span className="text-[10px] text-editor-text-dim leading-relaxed">{p.arc}</span>
                      <span className="mt-1 text-[10px] font-medium text-violet-400 opacity-0 transition-opacity group-hover:opacity-100">
                        Use this story →
                      </span>
                    </button>
                  ))}
                </div>
              )}
              {msg.creativeBlocks && msg.creativeBlocks.length > 0 && (
                <div className="mt-2 flex flex-col gap-2">
                  {msg.creativeBlocks
                    .filter((b: CreativeBlock) => b.type === "image" || b.type === "panel")
                    .map((block: CreativeBlock, i: number) => (
                      <div
                        key={i}
                        className="overflow-hidden rounded-xl border border-editor-border"
                      >
                        <img
                          src={`data:${block.mime_type ?? "image/jpeg"};base64,${block.content}`}
                          alt={`Panel ${i + 1}`}
                          className="w-full object-cover"
                        />
                        {block.type !== "panel" && (
                          <button
                            type="button"
                            onClick={() =>
                              handleSend(`Apply the style from preview ${i + 1}`)
                            }
                            className="w-full border-t border-editor-border bg-editor-surface-raised py-1.5 text-center text-xs font-medium text-foreground/60 transition-colors hover:bg-editor-surface hover:text-foreground"
                          >
                            Use this style →
                          </button>
                        )}
                      </div>
                    ))}
                </div>
              )}

              {msg.thumbnailOptions && msg.thumbnailOptions.length > 0 && (
                <div className="mt-2 flex flex-col gap-2">
                  <p className="text-[10px] font-medium uppercase tracking-widest text-editor-text-dim">
                    Thumbnail options — pick one to apply
                  </p>
                  <div className="flex flex-col gap-2">
                    {msg.thumbnailOptions.map((opt: ThumbnailOption) => (
                      <div
                        key={opt.index}
                        className="group overflow-hidden rounded-lg border border-editor-border"
                      >
                        <img
                          src={`data:${opt.mime_type};base64,${opt.image_b64}`}
                          alt={`Thumbnail option ${opt.index + 1}`}
                          className="w-full object-cover"
                        />
                        <button
                          type="button"
                          onClick={() =>
                            handleSend(
                              `Apply thumbnail option ${opt.index + 1}`,
                              `Apply thumbnail ${opt.index + 1}`,
                            )
                          }
                          disabled={agentLoading}
                          className="w-full border-t border-editor-border bg-editor-surface-raised py-1.5 text-xs font-medium text-foreground/70 transition-colors hover:bg-primary/10 hover:text-primary disabled:opacity-40"
                        >
                          Use option {opt.index + 1} as thumbnail →
                        </button>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
            {msg.actions && msg.actions.length > 0 && !msg.proposal && (
              <div className="flex max-w-[90%] flex-wrap gap-1">
                {msg.actions.map((action, index) => (
                  <span
                    key={`${msg.id}-${index}`}
                    className="rounded-full border border-primary/30 bg-primary/15 px-2 py-0.5 text-[10px] font-mono text-editor-accent-glow"
                  >
                    {action}
                  </span>
                ))}
              </div>
            )}
            {msg.proposal && (
              <div
                className={cn(
                  "mt-1 w-[90%] rounded-xl border p-3",
                  msg.proposal.state === "pending"
                    ? "border-primary/30 bg-editor-surface-raised"
                    : msg.proposal.state === "confirmed"
                      ? "border-emerald-500/30 bg-emerald-500/10"
                      : "border-editor-border bg-editor-surface opacity-60",
                )}
              >
                {msg.proposal.state === "pending" && (
                  <>
                    <p className="mb-2 text-[11px] font-medium uppercase tracking-[0.15em] text-editor-text-dim">
                      {msg.proposal.commands.length} suggested change
                      {msg.proposal.commands.length !== 1 ? "s" : ""}
                    </p>
                    <ul className="mb-3 space-y-1">
                      {msg.proposal.commands.map((cmd, i) => (
                        <li
                          key={i}
                          className="text-xs font-mono text-foreground/70"
                        >
                          {cmd.kind.replace(/_/g, " ")}
                          {Object.keys(cmd.args).length > 0 && (
                            <span className="ml-1 text-editor-text-dim">
                              (
                              {Object.values(cmd.args)
                                .filter(Boolean)
                                .join(", ")}
                              )
                            </span>
                          )}
                        </li>
                      ))}
                    </ul>
                    <div className="flex gap-2">
                      <button
                        type="button"
                        onClick={() => confirmProposal(msg.proposal!)}
                        disabled={agentLoading}
                        className="flex-1 rounded-lg bg-primary py-1.5 text-xs font-semibold text-primary-foreground disabled:opacity-40"
                      >
                        Apply
                      </button>
                      <button
                        type="button"
                        onClick={() => rejectProposal(msg.proposal!)}
                        disabled={agentLoading}
                        className="flex-1 rounded-lg border border-editor-border py-1.5 text-xs text-foreground/70 hover:border-primary/30"
                      >
                        Discard
                      </button>
                    </div>
                  </>
                )}
                {msg.proposal.state === "confirmed" && (
                  <p className="text-xs font-medium text-emerald-300">
                    Applied
                  </p>
                )}
                {msg.proposal.state === "rejected" && (
                  <p className="text-xs italic text-editor-text-dim">
                    Discarded
                  </p>
                )}
              </div>
            )}
          </div>
        ))}
        <div ref={agentBottomRef} />
      </div>

      <div className="grid grid-cols-2 gap-1.5 border-t border-editor-border px-3 py-2">
        {MODE_QUICK_ACTIONS[agentMode].map(({ label, instruction }) => (
          <button
            key={label}
            type="button"
            onClick={() => handleSend(instruction, label)}
            disabled={agentLoading}
            className="rounded-lg border border-editor-border bg-editor-surface-raised px-2 py-1.5 text-xs text-foreground/70 transition-colors hover:border-primary/45 hover:bg-editor-surface hover:text-foreground disabled:cursor-not-allowed disabled:opacity-40"
          >
            {label}
          </button>
        ))}
      </div>

      {hasUndo && (
        <div className="border-t border-editor-border px-3 py-2">
          <button
            type="button"
            onClick={revertLastEdit}
            className="w-full rounded-lg border border-amber-500/30 bg-amber-500/10 py-1.5 text-xs font-medium text-amber-200 hover:bg-amber-500/20"
          >
            Undo last edit
          </button>
        </div>
      )}

      <div className="border-t border-editor-border p-3">
        <div className="relative rounded-xl border border-editor-border bg-editor-surface-raised px-3 py-2 transition-colors focus-within:border-primary/55">
          {/* @mention dropdown */}
          {mentionState?.visible && mentionState.assets.length > 0 && (
            <div className="absolute bottom-full left-0 right-0 mb-1 overflow-hidden rounded-xl border border-editor-border bg-editor-surface shadow-lg z-50">
              <p className="border-b border-editor-border px-3 py-1.5 text-[10px] font-medium uppercase tracking-widest text-editor-text-dim">
                Your assets
              </p>
              <div className="flex max-h-48 flex-col overflow-y-auto">
                {mentionState.assets.map((asset) => (
                  <button
                    key={asset.id}
                    type="button"
                    onMouseDown={(e) => {
                      e.preventDefault();
                      insertMention(asset);
                    }}
                    className="flex items-center gap-2 px-3 py-2 text-left text-xs text-foreground/80 hover:bg-editor-surface-raised"
                  >
                    <span className="truncate">{asset.filename}</span>
                    <span className="ml-auto shrink-0 text-[9px] text-editor-text-dim">
                      {asset.content_type.startsWith("image") ? "img" : "music"}
                    </span>
                  </button>
                ))}
              </div>
            </div>
          )}

          <textarea
            ref={textareaRef}
            value={agentInput}
            onChange={(e) => {
              void handleInputChange(e);
            }}
            onKeyDown={(event) => {
              if (event.key === "Escape") {
                setMentionState(null);
                return;
              }
              if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault();
                handleSend(agentInput);
              }
            }}
            placeholder={`${activeMode.placeholder} (type @ to tag an asset)`}
            rows={2}
            className="w-full resize-none bg-transparent text-sm leading-relaxed text-foreground placeholder-muted-foreground focus:outline-none"
          />
          <div className="mt-2 flex items-center justify-between">
            <div className="relative">
              <button
                type="button"
                onClick={() => setShowModeMenu((v) => !v)}
                className="flex items-center gap-1 rounded-md px-1.5 py-0.5 text-[11px] text-editor-text-dim transition-colors hover:bg-muted hover:text-foreground"
              >
                <activeMode.Icon className="h-3 w-3" />
                {activeMode.label}
                <ChevronUp className="h-2.5 w-2.5" />
              </button>

              {showModeMenu && (
                <>
                  <div
                    className="fixed inset-0 z-40"
                    onClick={() => setShowModeMenu(false)}
                  />
                  <div className="absolute bottom-full left-0 z-50 mb-1.5 w-52 overflow-hidden rounded-xl border border-editor-border bg-editor-surface shadow-xl">
                    {MODES.map((mode) => {
                      const Icon = mode.Icon;
                      const isActive = agentMode === mode.key;
                      return (
                        <button
                          key={mode.key}
                          type="button"
                          onClick={() => {
                            setAgentMode(mode.key);
                            setShowModeMenu(false);
                          }}
                          className={cn(
                            "flex w-full items-center gap-2.5 px-3 py-2.5 text-left transition-colors hover:bg-editor-surface-raised",
                            isActive ? "text-foreground" : "text-foreground/60",
                          )}
                        >
                          <div className="flex h-4 w-4 shrink-0 items-center justify-center">
                            {isActive ? (
                              <Check className="h-3.5 w-3.5" />
                            ) : (
                              <Icon className="h-3.5 w-3.5" />
                            )}
                          </div>
                          <div>
                            <p className="text-[12px] font-medium leading-tight">
                              {mode.label}
                            </p>
                            <p className="text-[10px] text-editor-text-dim">
                              {mode.description}
                            </p>
                          </div>
                        </button>
                      );
                    })}
                  </div>
                </>
              )}
            </div>
            <div className="flex items-center gap-1.5">
              <button
                type="button"
                onClick={() => {
                  if (isVoiceActive) stopVoiceEdit();
                  else void startVoiceEdit();
                }}
                className={cn(
                  "rounded-lg p-1.5 transition-colors",
                  isVoiceActive
                    ? "animate-pulse bg-destructive/20 text-destructive"
                    : "text-editor-text-dim hover:bg-muted hover:text-foreground",
                )}
              >
                {isVoiceActive ? (
                  <MicOff className="h-4 w-4" />
                ) : (
                  <Mic className="h-4 w-4" />
                )}
              </button>
              <button
                type="button"
                disabled={!isVoiceActive}
                onClick={() => {
                  if (isScreenShareActive) stopScreenShare();
                  else void startScreenShare();
                }}
                title={
                  !isVoiceActive
                    ? "Start voice edit to enable screen sharing"
                    : isScreenShareActive
                      ? "Stop screen sharing"
                      : "Share screen with agent"
                }
                className={cn(
                  "relative rounded-lg p-1.5 transition-colors disabled:cursor-not-allowed disabled:opacity-30",
                  isScreenShareActive
                    ? "bg-blue-500/20 text-blue-400"
                    : "text-editor-text-dim hover:bg-muted hover:text-foreground",
                )}
              >
                {isScreenShareActive ? (
                  <MonitorOff className="h-4 w-4" />
                ) : (
                  <Monitor className="h-4 w-4" />
                )}
                {isScreenShareActive && (
                  <span className="absolute right-0.5 top-0.5 h-1.5 w-1.5 animate-pulse rounded-full bg-blue-400" />
                )}
              </button>

              <button
                type="button"
                onClick={() => handleSend(agentInput)}
                disabled={!agentInput.trim() || agentLoading}
                className="rounded-lg bg-primary p-1.5 text-primary-foreground transition-colors hover:bg-primary/80 disabled:cursor-not-allowed disabled:opacity-40"
              >
                {agentLoading ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Send className="h-4 w-4" />
                )}
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
