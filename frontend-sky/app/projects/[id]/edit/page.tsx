"use client";

import {
  useCallback,
  useEffect,
  useRef,
  useState,
} from "react";
import { useParams, useRouter } from "next/navigation";
import {
  AlertCircle,
  ArrowLeft,
  Bot,
  ChevronDown,
  Download,
  Film,
  Image,
  Loader2,
  Mic,
  MicOff,
  Music,
  Pause,
  Play,
  Plus,
  Redo2,
  Smile,
  Sparkles,
  Square,
  Undo2,
  Upload,
  Video,
  Volume2,
  VolumeX,
  Wand2,
  ZoomIn,
  ZoomOut,
} from "lucide-react";
import { cn } from "@/lib/utils";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const WS_API = API.replace(/^http/, "ws");

// ─── Types ──────────────────────────────────────────────────────────────────

interface Project {
  project_id: string;
  status: string;
  hook?: string;
  scenes_count?: number;
  video_duration?: number;
  platforms?: string[];
  video_urls?: Record<string, string>;
  thumbnail_url?: string;
  caption_style?: string;
  background_music?: string;
  voiceover_full_script?: string;
  voiceover_duration?: number;
  error?: string;
}

interface AgentMessage {
  id: string;
  role: "user" | "agent";
  text: string;
  actions?: string[];
  isThinking?: boolean;
  isError?: boolean;
}

// ─── Constants ───────────────────────────────────────────────────────────────

const CAPTION_STYLES = [
  { value: "bold_stroke",   label: "Bold Stroke",   desc: "ALL CAPS, white + black outline" },
  { value: "red_highlight", label: "Red Highlight",  desc: "White on red background" },
  { value: "sleek",         label: "Sleek",          desc: "Thin outline, bottom" },
  { value: "karaoke",       label: "Karaoke",        desc: "Word-by-word gold highlight" },
  { value: "majestic",      label: "Majestic",       desc: "Large centered, gold shadow" },
  { value: "beast",         label: "Beast",          desc: "1 word, maximum impact" },
  { value: "elegant",       label: "Elegant",        desc: "Italic, thin outline" },
  { value: "clarity",       label: "Clarity",        desc: "Lowercase, soft gray, minimal" },
];

const MUSIC_PRESETS = [
  { value: "none",                label: "None",                genres: "" },
  { value: "happy_rhythm",        label: "Happy Rhythm",        genres: "Upbeat, Pop" },
  { value: "quiet_before_storm",  label: "Quiet Before Storm",  genres: "Suspense, Epic" },
  { value: "peaceful_vibes",      label: "Peaceful Vibes",      genres: "Calm, Ambient" },
  { value: "brilliant_symphony",  label: "Brilliant Symphony",  genres: "Orchestral, Epic" },
  { value: "breathing_shadows",   label: "Breathing Shadows",   genres: "Dark, Cinematic" },
  { value: "lyria",               label: "Lyria (AI)",          genres: "AI Generated" },
];

const EFFECTS = [
  { value: "cash",      label: "Cash",      category: "visual" },
  { value: "burn",      label: "Burn",      category: "visual" },
  { value: "comic",     label: "Comic",     category: "cinematic" },
  { value: "paint_in",  label: "Paint In",  category: "cinematic" },
  { value: "paint_out", label: "Paint Out", category: "cinematic" },
  { value: "smoke",     label: "Smoke",     category: "visual" },
  { value: "glitch",    label: "Glitch",    category: "motion" },
  { value: "zoom_in",   label: "Zoom In",   category: "motion" },
  { value: "zoom_out",  label: "Zoom Out",  category: "motion" },
];

const EMOJIS = ["🔥", "💀", "🎭", "🌙", "⚡", "💥", "🎯", "🚀", "💫", "🎬", "🎵", "😱",
                "👑", "💎", "🌊", "🎪", "🦋", "🌟", "💣", "🎸", "🤯", "✨", "🖤", "🫀"];

const PLATFORMS = ["instagram_reels", "tiktok", "youtube_shorts", "master"];

function formatTime(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  const cs = Math.floor((seconds % 1) * 100);
  return `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}.${String(cs).padStart(2, "0")}`;
}

// ─── Editor Page ─────────────────────────────────────────────────────────────

export default function EditorPage() {
  const params = useParams();
  const projectId = params.id as string;
  const router = useRouter();

  // Project data
  const [project, setProject] = useState<Project | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  // Video state
  const videoRef = useRef<HTMLVideoElement>(null);
  const [currentPlatform, setCurrentPlatform] = useState("instagram_reels");
  const [isPlaying, setIsPlaying] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const [volume, setVolume] = useState(1);
  const [isMuted, setIsMuted] = useState(false);
  const [timelineZoom, setTimelineZoom] = useState(1);

  // Editor state
  const [leftTab, setLeftTab] = useState<"audio" | "broll" | "effects" | "emojis" | "ai">("audio");
  const [effectCategory, setEffectCategory] = useState<"all" | "visual" | "cinematic" | "motion">("all");
  const [musicSearch, setMusicSearch] = useState("");
  const [brollSubTab, setBrollSubTab] = useState<"images" | "upload" | "ai">("images");
  const [captionStyle, setCaptionStyle] = useState(project?.caption_style ?? "bold_stroke");
  const [backgroundMusic, setBackgroundMusic] = useState(project?.background_music ?? "none");
  const [musicVolume, setMusicVolume] = useState(0.15);
  const [recomposing, setRecomposing] = useState(false);
  const [recomposeMsg, setRecomposeMsg] = useState("");
  const [brollPct, setBrollPct] = useState(50);
  const [emojiPct, setEmojiPct] = useState(50);

  // Agent panel
  const [agentPanelOpen, setAgentPanelOpen] = useState(true);
  const [agentMessages, setAgentMessages] = useState<AgentMessage[]>([
    {
      id: "welcome",
      role: "agent",
      text: "Hi! I'm your AI video editor. Describe what changes you'd like to make, or try a quick action below.",
    },
  ]);
  const [agentInput, setAgentInput] = useState("");
  const [agentLoading, setAgentLoading] = useState(false);
  const [isVoiceActive, setIsVoiceActive] = useState(false);
  const agentBottomRef = useRef<HTMLDivElement>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const audioCtxRef = useRef<AudioContext | null>(null);
  const mediaStreamRef = useRef<MediaStream | null>(null);
  const processorRef = useRef<ScriptProcessorNode | null>(null);

  // Timeline drag
  const timelineRef = useRef<HTMLDivElement>(null);
  const [isDraggingPlayhead, setIsDraggingPlayhead] = useState(false);

  // Load project
  const fetchProject = useCallback(async () => {
    try {
      const res = await fetch(`${API}/api/v1/projects/${projectId}`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      setProject(data);
      setCaptionStyle(data.caption_style ?? "bold_stroke");
      setBackgroundMusic(data.background_music ?? "none");
      setLoadError(null);
    } catch (e) {
      setLoadError(e instanceof Error ? e.message : "Failed to load project");
    }
  }, [projectId]);

  useEffect(() => { fetchProject(); }, [fetchProject]);

  // Video event handlers
  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;
    const onPlay = () => setIsPlaying(true);
    const onPause = () => setIsPlaying(false);
    const onTimeUpdate = () => setCurrentTime(video.currentTime);
    const onLoadedMetadata = () => setDuration(video.duration);
    video.addEventListener("play", onPlay);
    video.addEventListener("pause", onPause);
    video.addEventListener("timeupdate", onTimeUpdate);
    video.addEventListener("loadedmetadata", onLoadedMetadata);
    return () => {
      video.removeEventListener("play", onPlay);
      video.removeEventListener("pause", onPause);
      video.removeEventListener("timeupdate", onTimeUpdate);
      video.removeEventListener("loadedmetadata", onLoadedMetadata);
    };
  }, []);

  // Scroll agent to bottom
  useEffect(() => {
    agentBottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [agentMessages]);

  // ─── Recompose ─────────────────────────────────────────────────────────────

  async function triggerRecompose(style: string, music: string, vol: number = musicVolume) {
    if (!project) return;
    setRecomposing(true);
    setRecomposeMsg("Applying changes...");
    try {
      const res = await fetch(`${API}/api/v1/projects/${projectId}/recompose`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          caption_style: style,
          background_music: music,
          music_volume: vol,
          target_platforms: project.platforms ?? ["instagram_reels"],
        }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: "Recompose failed" }));
        throw new Error(err.detail ?? "Recompose failed");
      }
      const data = await res.json();
      setProject((prev) => prev ? { ...prev, video_urls: data.video_urls, caption_style: style, background_music: music } : prev);
      setRecomposeMsg("Done!");
      setTimeout(() => setRecomposeMsg(""), 2000);
      // Reload video
      const video = videoRef.current;
      if (video) {
        const prevTime = video.currentTime;
        video.load();
        video.currentTime = prevTime;
      }
    } catch (e) {
      setRecomposeMsg(e instanceof Error ? e.message : "Recompose failed");
      setTimeout(() => setRecomposeMsg(""), 3000);
    } finally {
      setRecomposing(false);
    }
  }

  // ─── Agent (SSE text) ──────────────────────────────────────────────────────

  async function sendAgentInstruction(instruction: string) {
    if (!instruction.trim() || agentLoading) return;

    const userMsg: AgentMessage = { id: Date.now().toString(), role: "user", text: instruction };
    const thinkingId = Date.now().toString() + "-t";
    const thinkingMsg: AgentMessage = { id: thinkingId, role: "agent", text: "", isThinking: true, actions: [] };

    setAgentMessages((prev) => [...prev, userMsg, thinkingMsg]);
    setAgentInput("");
    setAgentLoading(true);

    try {
      const res = await fetch(`${API}/api/v1/projects/${projectId}/edit-agent`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ instruction }),
      });

      if (!res.ok || !res.body) {
        throw new Error(`HTTP ${res.status}`);
      }

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      let agentText = "";
      const actions: string[] = [];

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() ?? "";

        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          try {
            const event = JSON.parse(line.slice(6));
            if (event.type === "progress" && event.message) {
              agentText = event.message;
            } else if (event.type === "tool_call" && event.tool) {
              actions.push(event.tool);
            } else if (event.type === "complete") {
              agentText = event.message ?? "Done! Your video has been updated.";
              if (event.video_urls) {
                setProject((prev) => prev ? { ...prev, video_urls: event.video_urls } : prev);
                videoRef.current?.load();
              } else {
                fetchProject();
              }
            } else if (event.type === "error") {
              agentText = event.message ?? "Something went wrong.";
            }
            // Update the thinking message live
            setAgentMessages((prev) =>
              prev.map((m) =>
                m.id === thinkingId
                  ? { ...m, text: agentText, actions: [...actions], isThinking: event.type !== "complete" && event.type !== "error" }
                  : m
              )
            );
          } catch { /* skip malformed */ }
        }
      }
    } catch (e) {
      setAgentMessages((prev) =>
        prev.map((m) =>
          m.id === thinkingId
            ? { ...m, text: e instanceof Error ? e.message : "Request failed", isThinking: false, isError: true }
            : m
        )
      );
    } finally {
      setAgentLoading(false);
    }
  }

  // ─── Voice edit (WebSocket) ────────────────────────────────────────────────

  async function startVoiceEdit() {
    if (isVoiceActive) {
      stopVoiceEdit();
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      mediaStreamRef.current = stream;
      const ws = new WebSocket(`${WS_API}/api/v1/projects/${projectId}/edit-voice`);
      wsRef.current = ws;

      const voiceMsgId = Date.now().toString() + "-v";
      setAgentMessages((prev) => [
        ...prev,
        { id: Date.now().toString(), role: "user", text: "🎤 Voice edit started..." },
        { id: voiceMsgId, role: "agent", text: "", isThinking: true, actions: [] },
      ]);
      setIsVoiceActive(true);

      ws.onopen = () => {
        // Set up audio processing
        const audioCtx = new AudioContext({ sampleRate: 16000 });
        audioCtxRef.current = audioCtx;
        const source = audioCtx.createMediaStreamSource(stream);
        const processor = audioCtx.createScriptProcessor(4096, 1, 1);
        processorRef.current = processor;

        processor.onaudioprocess = (e) => {
          if (ws.readyState !== WebSocket.OPEN) return;
          const float32 = e.inputBuffer.getChannelData(0);
          const int16 = new Int16Array(float32.length);
          for (let i = 0; i < float32.length; i++) {
            int16[i] = Math.max(-32768, Math.min(32767, float32[i] * 32768));
          }
          ws.send(int16.buffer);
        };

        source.connect(processor);
        processor.connect(audioCtx.destination);
      };

      ws.onmessage = (event) => {
        if (event.data instanceof Blob) {
          // Agent voice audio — play it back
          event.data.arrayBuffer().then((buf) => {
            audioCtxRef.current?.decodeAudioData(buf).then((decoded) => {
              const src = audioCtxRef.current!.createBufferSource();
              src.buffer = decoded;
              src.connect(audioCtxRef.current!.destination);
              src.start();
            }).catch(() => {});
          });
          return;
        }
        try {
          const data = JSON.parse(event.data);
          if (data.type === "transcript_chunk") {
            setAgentMessages((prev) =>
              prev.map((m) =>
                m.id === voiceMsgId
                  ? { ...m, text: (m.text || "") + data.text }
                  : m
              )
            );
          } else if (data.type === "creative_block" || data.type === "tool_call") {
            const tool = data.block ?? data.tool ?? "";
            setAgentMessages((prev) =>
              prev.map((m) =>
                m.id === voiceMsgId
                  ? { ...m, actions: [...(m.actions ?? []), tool] }
                  : m
              )
            );
          } else if (data.type === "edit_complete") {
            setAgentMessages((prev) =>
              prev.map((m) =>
                m.id === voiceMsgId
                  ? { ...m, isThinking: false, text: m.text || "Edit complete! Video updated." }
                  : m
              )
            );
            fetchProject();
            stopVoiceEdit();
          } else if (data.type === "error") {
            setAgentMessages((prev) =>
              prev.map((m) =>
                m.id === voiceMsgId
                  ? { ...m, isThinking: false, isError: true, text: data.message ?? "Voice edit error" }
                  : m
              )
            );
            stopVoiceEdit();
          }
        } catch { /* binary handled above */ }
      };

      ws.onclose = () => {
        stopVoiceEdit();
      };

    } catch (e) {
      setAgentMessages((prev) => [
        ...prev,
        { id: Date.now().toString(), role: "agent", text: "Microphone access denied.", isError: true },
      ]);
    }
  }

  function stopVoiceEdit() {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: "done" }));
      wsRef.current.close();
    }
    wsRef.current = null;
    processorRef.current?.disconnect();
    processorRef.current = null;
    audioCtxRef.current?.close().catch(() => {});
    audioCtxRef.current = null;
    mediaStreamRef.current?.getTracks().forEach((t) => t.stop());
    mediaStreamRef.current = null;
    setIsVoiceActive(false);
  }

  useEffect(() => () => stopVoiceEdit(), []);

  // ─── Timeline drag ─────────────────────────────────────────────────────────

  function handleTimelineMouseDown(e: React.MouseEvent) {
    setIsDraggingPlayhead(true);
    seekFromMouseEvent(e);
  }

  function handleTimelineMouseMove(e: React.MouseEvent) {
    if (!isDraggingPlayhead) return;
    seekFromMouseEvent(e);
  }

  function seekFromMouseEvent(e: React.MouseEvent) {
    const rect = timelineRef.current?.getBoundingClientRect();
    if (!rect || !duration) return;
    const ratio = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
    const newTime = ratio * duration;
    if (videoRef.current) videoRef.current.currentTime = newTime;
    setCurrentTime(newTime);
  }

  const streamUrl = (platform: string) =>
    `${API}/api/v1/projects/${projectId}/stream/${platform}`;

  const availablePlatforms = project?.platforms?.length
    ? project.platforms
    : PLATFORMS.filter((p) => project?.video_urls?.[p]);

  // ─── Render ───────────────────────────────────────────────────────────────

  if (loadError) {
    return (
      <div className="flex h-screen items-center justify-center bg-[#1a1a1a] text-white/50">
        <div className="text-center">
          <AlertCircle className="w-12 h-12 mx-auto mb-4 text-red-400/60" />
          <p className="text-lg mb-2">{loadError}</p>
          <button onClick={() => router.push(`/projects/${projectId}`)} className="text-sm text-[#7c3aed] hover:underline">
            ← Back to project
          </button>
        </div>
      </div>
    );
  }

  return (
    <div
      className="flex flex-col h-screen bg-[#1a1a1a] text-white overflow-hidden"
      onMouseMove={(e) => handleTimelineMouseMove(e)}
      onMouseUp={() => setIsDraggingPlayhead(false)}
    >
      {/* ── Toolbar ──────────────────────────────────────────────────────── */}
      <div className="flex items-center justify-between px-4 h-12 bg-[#111111] border-b border-white/10 shrink-0 z-10">
        {/* Left */}
        <div className="flex items-center gap-3">
          <button
            onClick={() => router.push(`/projects/${projectId}`)}
            className="flex items-center gap-1.5 text-white/50 hover:text-white transition-colors text-sm"
          >
            <ArrowLeft className="w-4 h-4" /> Back
          </button>
          <div className="w-px h-5 bg-white/10" />
          <button className="p-1.5 text-white/40 hover:text-white transition-colors rounded">
            <Undo2 className="w-4 h-4" />
          </button>
          <button className="p-1.5 text-white/40 hover:text-white transition-colors rounded">
            <Redo2 className="w-4 h-4" />
          </button>
          <button className="p-1.5 text-white/40 hover:text-white transition-colors rounded">
            <Square className="w-3.5 h-3.5" />
          </button>
        </div>

        {/* Center — project title */}
        <div className="flex items-center gap-2">
          {recomposing ? (
            <div className="flex items-center gap-2 text-sm text-[#7c3aed]">
              <Loader2 className="w-4 h-4 animate-spin" />
              <span>{recomposeMsg || "Processing..."}</span>
            </div>
          ) : recomposeMsg ? (
            <span className="text-sm text-green-400">{recomposeMsg}</span>
          ) : (
            <>
              <div className="w-2 h-2 rounded-full bg-green-400" />
              <span className="text-sm text-white/70 truncate max-w-xs">
                {project?.hook ?? "Loading..."}
              </span>
            </>
          )}
        </div>

        {/* Right */}
        <div className="flex items-center gap-2">
          {/* Export dropdown */}
          <div className="relative group">
            <button className="flex items-center gap-1.5 px-3 py-1.5 bg-white/10 hover:bg-white/15 rounded-lg text-sm font-medium transition-colors">
              <Download className="w-4 h-4" />
              Export
              <ChevronDown className="w-3 h-3" />
            </button>
            <div className="absolute right-0 top-full mt-1 w-48 bg-[#2a2a2a] border border-white/10 rounded-xl overflow-hidden opacity-0 group-hover:opacity-100 transition-opacity z-50 shadow-xl">
              {availablePlatforms.map((p) => (
                <a
                  key={p}
                  href={streamUrl(p)}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex items-center gap-2 px-4 py-2.5 hover:bg-white/10 text-sm text-white/80 hover:text-white transition-colors capitalize"
                >
                  <Download className="w-3.5 h-3.5" />
                  {p.replace(/_/g, " ")}
                </a>
              ))}
            </div>
          </div>

          {/* Agent toggle */}
          <button
            onClick={() => setAgentPanelOpen((v) => !v)}
            className={cn(
              "flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium transition-colors",
              agentPanelOpen
                ? "bg-[#7c3aed] text-white"
                : "bg-white/10 hover:bg-white/15 text-white"
            )}
          >
            <Bot className="w-4 h-4" />
            Agent
          </button>
        </div>
      </div>

      {/* ── Main area ────────────────────────────────────────────────────── */}
      <div className="flex flex-1 overflow-hidden">

        {/* ── Left Panel ─────────────────────────────────────────────────── */}
        <div className="flex shrink-0 bg-[#1e1e1e] border-r border-white/10">
          {/* Icon strip */}
          <div className="flex flex-col items-center gap-1 py-3 px-1.5 border-r border-white/10 w-12">
            {([
              { key: "audio",   icon: <Music className="w-5 h-5" />,    label: "Audio" },
              { key: "broll",   icon: <Film className="w-5 h-5" />,     label: "B-Roll" },
              { key: "effects", icon: <Wand2 className="w-5 h-5" />,    label: "Effects" },
              { key: "emojis",  icon: <Smile className="w-5 h-5" />,    label: "Emojis" },
              { key: "ai",      icon: <Sparkles className="w-5 h-5" />, label: "AI" },
            ] as { key: "audio"|"broll"|"effects"|"emojis"|"ai"; icon: React.ReactNode; label: string }[]).map(({ key, icon, label }) => (
              <button
                key={key}
                onClick={() => setLeftTab(key)}
                title={label}
                className={cn(
                  "w-9 h-9 flex items-center justify-center rounded-lg transition-colors",
                  leftTab === key
                    ? "bg-[#7c3aed] text-white"
                    : "text-white/40 hover:text-white hover:bg-white/10"
                )}
              >
                {icon}
              </button>
            ))}
          </div>

          {/* Panel content */}
          <div className="w-52 flex flex-col overflow-hidden">
            {/* Audio */}
            {leftTab === "audio" && (
              <div className="flex flex-col h-full">
                <div className="px-3 py-2 border-b border-white/10">
                  <p className="text-xs font-semibold text-white/60 uppercase tracking-wider mb-2">Audio</p>
                  <div className="flex gap-1 mb-2">
                    {["Music", "Upload"].map((t) => (
                      <button key={t} className="px-2.5 py-1 rounded-full bg-[#7c3aed] text-white text-xs font-medium first:block [&:not(:first-child)]:bg-white/10 [&:not(:first-child)]:text-white/60">{t}</button>
                    ))}
                  </div>
                  <div className="relative">
                    <input
                      type="text"
                      placeholder="Search music..."
                      value={musicSearch}
                      onChange={(e) => setMusicSearch(e.target.value)}
                      className="w-full bg-white/5 border border-white/10 rounded-lg pl-3 pr-3 py-1.5 text-xs text-white placeholder-white/30 focus:outline-none"
                    />
                  </div>
                </div>
                <div className="flex-1 overflow-y-auto py-1">
                  {MUSIC_PRESETS.filter((m) =>
                    !musicSearch || m.label.toLowerCase().includes(musicSearch.toLowerCase())
                  ).map((track) => (
                    <button
                      key={track.value}
                      onClick={() => {
                        setBackgroundMusic(track.value);
                        triggerRecompose(captionStyle, track.value);
                      }}
                      className={cn(
                        "w-full flex items-center gap-2 px-3 py-2.5 hover:bg-white/5 transition-colors text-left",
                        backgroundMusic === track.value && "bg-[#7c3aed]/10"
                      )}
                    >
                      <div className={cn(
                        "w-8 h-8 rounded-full flex items-center justify-center shrink-0",
                        backgroundMusic === track.value ? "bg-[#7c3aed]" : "bg-white/10"
                      )}>
                        <Play className="w-3 h-3 text-white ml-0.5" />
                      </div>
                      <div className="flex-1 min-w-0">
                        <p className="text-xs font-medium text-white truncate">{track.label}</p>
                        {track.genres && <p className="text-xs text-white/40 truncate">{track.genres}</p>}
                      </div>
                      {backgroundMusic === track.value && (
                        <div className="w-1.5 h-1.5 rounded-full bg-[#7c3aed] shrink-0" />
                      )}
                    </button>
                  ))}
                </div>
                {/* Music volume */}
                <div className="px-3 py-2 border-t border-white/10">
                  <p className="text-xs text-white/50 mb-1">Volume: {Math.round(musicVolume * 100)}%</p>
                  <input
                    type="range"
                    min={0} max={1} step={0.05}
                    value={musicVolume}
                    onChange={(e) => setMusicVolume(parseFloat(e.target.value))}
                    onMouseUp={() => triggerRecompose(captionStyle, backgroundMusic, musicVolume)}
                    className="w-full accent-[#7c3aed]"
                  />
                </div>
              </div>
            )}

            {/* B-Roll */}
            {leftTab === "broll" && (
              <div className="flex flex-col h-full">
                <div className="px-3 py-2 border-b border-white/10">
                  <p className="text-xs font-semibold text-white/60 uppercase tracking-wider mb-2">B-Roll</p>
                  <div className="flex gap-1">
                    {(["images", "upload", "ai"] as const).map((t) => (
                      <button
                        key={t}
                        onClick={() => setBrollSubTab(t)}
                        className={cn(
                          "px-2 py-1 rounded-full text-xs font-medium capitalize transition-colors",
                          brollSubTab === t ? "bg-[#7c3aed] text-white" : "bg-white/10 text-white/60 hover:text-white"
                        )}
                      >
                        {t === "ai" ? "AI Image" : t}
                      </button>
                    ))}
                  </div>
                </div>
                <div className="flex-1 flex flex-col items-center justify-center gap-3 text-white/30 px-3">
                  {brollSubTab === "upload" ? (
                    <>
                      <Upload className="w-8 h-8" />
                      <p className="text-xs text-center">Upload images or videos from your device</p>
                      <button className="px-3 py-1.5 bg-[#7c3aed] rounded-lg text-white text-xs font-medium">
                        Upload File
                      </button>
                    </>
                  ) : brollSubTab === "ai" ? (
                    <>
                      <Sparkles className="w-8 h-8" />
                      <p className="text-xs text-center">Generate AI images with a prompt</p>
                      <textarea
                        placeholder="A dark forest at midnight..."
                        className="w-full bg-white/5 border border-white/10 rounded-lg px-2 py-1.5 text-xs text-white resize-none focus:outline-none"
                        rows={3}
                      />
                      <button className="px-3 py-1.5 bg-[#7c3aed] rounded-lg text-white text-xs font-medium w-full">
                        Generate
                      </button>
                    </>
                  ) : (
                    <>
                      <Image className="w-8 h-8" />
                      <p className="text-xs text-center">Your uploaded images appear here</p>
                    </>
                  )}
                </div>
              </div>
            )}

            {/* Effects */}
            {leftTab === "effects" && (
              <div className="flex flex-col h-full">
                <div className="px-3 py-2 border-b border-white/10">
                  <p className="text-xs font-semibold text-white/60 uppercase tracking-wider mb-2">Effects</p>
                  <div className="flex gap-1 flex-wrap">
                    {(["all", "visual", "cinematic", "motion"] as const).map((cat) => (
                      <button
                        key={cat}
                        onClick={() => setEffectCategory(cat)}
                        className={cn(
                          "px-2 py-0.5 rounded-full text-xs font-medium capitalize transition-colors",
                          effectCategory === cat ? "bg-[#7c3aed] text-white" : "bg-white/10 text-white/60 hover:text-white"
                        )}
                      >
                        {cat === "all" ? "All" : `${cat} (${EFFECTS.filter(e => e.category === cat).length})`}
                      </button>
                    ))}
                  </div>
                </div>
                <div className="flex-1 overflow-y-auto p-2 grid grid-cols-2 gap-2 content-start">
                  {EFFECTS.filter((e) => effectCategory === "all" || e.category === effectCategory).map((effect) => (
                    <button
                      key={effect.value}
                      onClick={() => sendAgentInstruction(`Apply ${effect.label} effect to the video`)}
                      className="aspect-square rounded-xl bg-[#2a2a2a] border border-white/10 hover:border-[#7c3aed]/50 flex flex-col items-center justify-center gap-1 transition-colors group"
                    >
                      <Wand2 className="w-5 h-5 text-white/30 group-hover:text-[#7c3aed] transition-colors" />
                      <span className="text-xs text-white/60 group-hover:text-white transition-colors">{effect.label}</span>
                    </button>
                  ))}
                </div>
              </div>
            )}

            {/* Emojis */}
            {leftTab === "emojis" && (
              <div className="flex flex-col h-full">
                <div className="px-3 py-2 border-b border-white/10">
                  <p className="text-xs font-semibold text-white/60 uppercase tracking-wider">Emojis</p>
                </div>
                <div className="flex-1 overflow-y-auto p-2 grid grid-cols-5 gap-1.5 content-start">
                  {EMOJIS.map((emoji) => (
                    <button
                      key={emoji}
                      onClick={() => sendAgentInstruction(`Add ${emoji} emoji at a relevant moment in the video`)}
                      className="aspect-square flex items-center justify-center text-xl hover:bg-white/10 rounded-lg transition-colors"
                    >
                      {emoji}
                    </button>
                  ))}
                </div>
              </div>
            )}

            {/* AI Features */}
            {leftTab === "ai" && (
              <div className="flex flex-col h-full overflow-y-auto">
                <div className="px-3 py-2 border-b border-white/10">
                  <p className="text-xs font-semibold text-white/60 uppercase tracking-wider">AI Features</p>
                </div>
                <div className="p-3 flex flex-col gap-4">
                  {/* Auto B-roll */}
                  <div className="bg-[#2a2a2a] rounded-xl p-3 border border-white/10">
                    <div className="flex items-center justify-between mb-1">
                      <div className="flex items-center gap-2">
                        <Film className="w-4 h-4 text-[#7c3aed]" />
                        <span className="text-xs font-medium text-white">Auto AI B-roll</span>
                      </div>
                      <button
                        onClick={() => sendAgentInstruction(`Add AI B-roll footage at ${brollPct}% of key moments`)}
                        className="px-2 py-1 bg-[#7c3aed] rounded-lg text-white text-xs font-medium"
                      >
                        Generate
                      </button>
                    </div>
                    <p className="text-xs text-white/40 mb-2">Auto-generate B-roll at key moments</p>
                    <p className="text-xs text-white/50">Percentage: {brollPct}%</p>
                    <input
                      type="range" min={10} max={100} step={10}
                      value={brollPct}
                      onChange={(e) => setBrollPct(parseInt(e.target.value))}
                      className="w-full accent-[#7c3aed] mt-1"
                    />
                  </div>

                  {/* Add Emojis */}
                  <div className="bg-[#2a2a2a] rounded-xl p-3 border border-white/10">
                    <div className="flex items-center justify-between mb-1">
                      <div className="flex items-center gap-2">
                        <Smile className="w-4 h-4 text-[#7c3aed]" />
                        <span className="text-xs font-medium text-white">Add Emojis</span>
                      </div>
                      <button
                        onClick={() => sendAgentInstruction(`Add relevant emojis at ${emojiPct}% of key moments`)}
                        className="px-2 py-1 bg-[#7c3aed] rounded-lg text-white text-xs font-medium"
                      >
                        Generate
                      </button>
                    </div>
                    <p className="text-xs text-white/40 mb-2">AI places emojis at the right moments</p>
                    <p className="text-xs text-white/50">Percentage: {emojiPct}%</p>
                    <input
                      type="range" min={10} max={100} step={10}
                      value={emojiPct}
                      onChange={(e) => setEmojiPct(parseInt(e.target.value))}
                      className="w-full accent-[#7c3aed] mt-1"
                    />
                  </div>

                  {/* Magic Zooms */}
                  <div className="bg-[#2a2a2a] rounded-xl p-3 border border-white/10">
                    <div className="flex items-center justify-between mb-1">
                      <div className="flex items-center gap-2">
                        <ZoomIn className="w-4 h-4 text-[#7c3aed]" />
                        <span className="text-xs font-medium text-white">Magic Zooms</span>
                      </div>
                      <button
                        onClick={() => sendAgentInstruction("Add dynamic zoom in and zoom out effects at key moments")}
                        className="px-2 py-1 bg-[#7c3aed] rounded-lg text-white text-xs font-medium"
                      >
                        Apply
                      </button>
                    </div>
                    <p className="text-xs text-white/40">Sprinkle zoom effects at the right moments</p>
                  </div>

                  {/* Caption Style */}
                  <div className="bg-[#2a2a2a] rounded-xl p-3 border border-white/10">
                    <div className="flex items-center gap-2 mb-2">
                      <Wand2 className="w-4 h-4 text-[#7c3aed]" />
                      <span className="text-xs font-medium text-white">Caption Style</span>
                    </div>
                    <div className="flex flex-col gap-1">
                      {CAPTION_STYLES.map((style) => (
                        <button
                          key={style.value}
                          onClick={() => {
                            setCaptionStyle(style.value);
                            triggerRecompose(style.value, backgroundMusic);
                          }}
                          className={cn(
                            "flex items-center gap-2 px-2 py-1.5 rounded-lg text-left transition-colors text-xs",
                            captionStyle === style.value
                              ? "bg-[#7c3aed]/20 border border-[#7c3aed]/40 text-white"
                              : "hover:bg-white/5 text-white/60 hover:text-white border border-transparent"
                          )}
                        >
                          <span className="font-medium">{style.label}</span>
                        </button>
                      ))}
                    </div>
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>

        {/* ── Center: Video Preview ─────────────────────────────────────── */}
        <div className="flex-1 flex flex-col items-center justify-center bg-[#0d0d0d] relative overflow-hidden">
          {/* Platform selector */}
          {availablePlatforms.length > 1 && (
            <div className="absolute top-3 left-1/2 -translate-x-1/2 flex items-center gap-1 z-10">
              {availablePlatforms.map((p) => (
                <button
                  key={p}
                  onClick={() => setCurrentPlatform(p)}
                  className={cn(
                    "px-3 py-1 rounded-full text-xs font-medium transition-colors capitalize",
                    currentPlatform === p
                      ? "bg-[#7c3aed] text-white"
                      : "bg-white/10 text-white/50 hover:text-white"
                  )}
                >
                  {p.replace(/_/g, " ")}
                </button>
              ))}
            </div>
          )}

          {/* Video */}
          <div className="relative max-h-[calc(100vh-220px)] aspect-[9/16]">
            {recomposing && (
              <div className="absolute inset-0 bg-black/70 flex flex-col items-center justify-center z-20 rounded-2xl">
                <Loader2 className="w-10 h-10 text-[#7c3aed] animate-spin mb-3" />
                <p className="text-sm text-white">{recomposeMsg || "Applying changes..."}</p>
              </div>
            )}
            {project ? (
              <video
                ref={videoRef}
                src={streamUrl(currentPlatform)}
                className="h-full w-full object-contain rounded-2xl"
                poster={`${API}/api/v1/projects/${projectId}/thumbnail`}
                onPlay={() => setIsPlaying(true)}
                onPause={() => setIsPlaying(false)}
                onTimeUpdate={() => setCurrentTime(videoRef.current?.currentTime ?? 0)}
                onLoadedMetadata={() => setDuration(videoRef.current?.duration ?? 0)}
                playsInline
              />
            ) : (
              <div className="h-full w-full rounded-2xl bg-[#1a1a1a] flex items-center justify-center">
                <Loader2 className="w-8 h-8 text-white/20 animate-spin" />
              </div>
            )}
          </div>

          {/* Playback controls */}
          <div className="absolute bottom-4 left-1/2 -translate-x-1/2 flex items-center gap-3 bg-[#111111]/90 backdrop-blur-sm rounded-full px-5 py-2 border border-white/10">
            <button
              onClick={() => { if (videoRef.current) videoRef.current.currentTime = 0; }}
              className="text-white/50 hover:text-white transition-colors"
            >
              <svg className="w-4 h-4" viewBox="0 0 24 24" fill="currentColor"><path d="M6 6h2v12H6zm3.5 6 8.5 6V6z"/></svg>
            </button>
            <button
              onClick={() => isPlaying ? videoRef.current?.pause() : videoRef.current?.play()}
              className="w-9 h-9 rounded-full bg-white flex items-center justify-center text-black hover:bg-white/90 transition-colors"
            >
              {isPlaying
                ? <Pause className="w-4 h-4" />
                : <Play className="w-4 h-4 ml-0.5" />
              }
            </button>
            <button
              onClick={() => { if (videoRef.current) videoRef.current.currentTime = duration; }}
              className="text-white/50 hover:text-white transition-colors"
            >
              <svg className="w-4 h-4" viewBox="0 0 24 24" fill="currentColor"><path d="M6 18l8.5-6L6 6v12zm2.5-6 5.5 4V8z M16 6h2v12h-2z"/></svg>
            </button>
            <span className="text-xs text-white/60 font-mono min-w-[90px] text-center">
              {formatTime(currentTime)} / {formatTime(duration)}
            </span>
            <button
              onClick={() => {
                if (videoRef.current) {
                  videoRef.current.muted = !isMuted;
                  setIsMuted(!isMuted);
                }
              }}
              className="text-white/50 hover:text-white transition-colors"
            >
              {isMuted ? <VolumeX className="w-4 h-4" /> : <Volume2 className="w-4 h-4" />}
            </button>
          </div>
        </div>

        {/* ── Right: Agent Panel ────────────────────────────────────────── */}
        {agentPanelOpen && (
          <div className="w-80 shrink-0 flex flex-col bg-[#1e1e1e] border-l border-white/10">
            {/* Header */}
            <div className="flex items-center justify-between px-4 py-3 border-b border-white/10">
              <div className="flex items-center gap-2">
                <Bot className="w-4 h-4 text-[#7c3aed]" />
                <span className="text-sm font-medium text-white">Agent</span>
              </div>
              <div className="flex items-center gap-1">
                <button className="p-1 text-white/30 hover:text-white transition-colors text-xs">
                  <Plus className="w-3.5 h-3.5" />
                </button>
              </div>
            </div>

            {/* Project name chip */}
            {project?.hook && (
              <div className="px-3 py-2 border-b border-white/10">
                <span className="text-xs bg-white/10 rounded-full px-2.5 py-1 text-white/60 truncate block">
                  {project.hook.slice(0, 40)}{project.hook.length > 40 ? "..." : ""}
                </span>
              </div>
            )}

            {/* Messages */}
            <div className="flex-1 overflow-y-auto px-3 py-3 flex flex-col gap-3">
              {agentMessages.map((msg) => (
                <div
                  key={msg.id}
                  className={cn("flex", msg.role === "user" ? "justify-end" : "justify-start")}
                >
                  {msg.role === "user" ? (
                    <div className="max-w-[85%] bg-[#7c3aed]/20 border border-[#7c3aed]/30 rounded-2xl rounded-tr-sm px-3 py-2">
                      <p className="text-sm text-white">{msg.text}</p>
                    </div>
                  ) : (
                    <div className="max-w-[95%] flex flex-col gap-1.5">
                      {(msg.text || msg.isThinking) && (
                        <div className="bg-[#2a2a2a] border border-white/10 rounded-2xl rounded-tl-sm px-3 py-2">
                          {msg.isThinking && !msg.text && (
                            <div className="flex items-center gap-1.5 text-white/40">
                              <Loader2 className="w-3 h-3 animate-spin" />
                              <span className="text-xs">Thinking...</span>
                            </div>
                          )}
                          {msg.text && (
                            <p className={cn("text-sm", msg.isError ? "text-red-400" : "text-white/80")}>
                              {msg.text}
                            </p>
                          )}
                        </div>
                      )}
                      {msg.actions && msg.actions.length > 0 && (
                        <div className="flex flex-wrap gap-1">
                          {msg.actions.map((action, i) => (
                            <span
                              key={i}
                              className="text-xs bg-[#7c3aed]/10 border border-[#7c3aed]/20 text-[#a78bfa] rounded-full px-2 py-0.5"
                            >
                              ✓ {action}
                            </span>
                          ))}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              ))}
              <div ref={agentBottomRef} />
            </div>

            {/* Quick actions */}
            <div className="px-3 py-2 border-t border-white/10">
              <p className="text-xs text-white/40 mb-2 uppercase tracking-wider">Quick Actions</p>
              <div className="grid grid-cols-2 gap-1.5">
                {[
                  { label: "Add B-rolls",  icon: <Film className="w-3 h-3" />,    prompt: "Add relevant B-roll footage at key moments" },
                  { label: "Add Zooms",    icon: <ZoomIn className="w-3 h-3" />,   prompt: "Add dynamic zoom effects at key moments" },
                  { label: "Change Theme", icon: <Wand2 className="w-3 h-3" />,    prompt: "Change the caption theme to be more engaging and vibrant" },
                  { label: "Add Music",    icon: <Music className="w-3 h-3" />,     action: () => setLeftTab("audio") },
                ].map((qa) => (
                  <button
                    key={qa.label}
                    onClick={() => qa.action ? qa.action() : sendAgentInstruction(qa.prompt!)}
                    disabled={agentLoading}
                    className="flex items-center gap-1.5 px-2.5 py-2 bg-white/5 hover:bg-white/10 border border-white/10 rounded-xl text-xs text-white/70 hover:text-white transition-colors disabled:opacity-50"
                  >
                    {qa.icon}
                    {qa.label}
                  </button>
                ))}
              </div>
            </div>

            {/* Text input */}
            <div className="px-3 py-3 border-t border-white/10">
              <div className="flex items-end gap-2 bg-[#2a2a2a] border border-white/10 rounded-2xl px-3 py-2 focus-within:border-[#7c3aed]/50 transition-colors">
                <textarea
                  value={agentInput}
                  onChange={(e) => setAgentInput(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && !e.shiftKey) {
                      e.preventDefault();
                      sendAgentInstruction(agentInput);
                    }
                  }}
                  placeholder="Describe changes to your video..."
                  className="flex-1 bg-transparent text-sm text-white placeholder-white/30 resize-none focus:outline-none max-h-24 min-h-[20px]"
                  rows={1}
                  disabled={agentLoading || isVoiceActive}
                />
                <div className="flex items-center gap-1.5 shrink-0">
                  {/* Voice button */}
                  <button
                    onClick={startVoiceEdit}
                    className={cn(
                      "p-1.5 rounded-lg transition-colors",
                      isVoiceActive
                        ? "bg-red-500 text-white animate-pulse"
                        : "text-white/40 hover:text-white hover:bg-white/10"
                    )}
                  >
                    {isVoiceActive ? <MicOff className="w-4 h-4" /> : <Mic className="w-4 h-4" />}
                  </button>
                  {/* Send button */}
                  <button
                    onClick={() => sendAgentInstruction(agentInput)}
                    disabled={!agentInput.trim() || agentLoading}
                    className="p-1.5 rounded-lg bg-[#7c3aed] text-white hover:bg-[#6d28d9] transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
                  >
                    {agentLoading
                      ? <Loader2 className="w-4 h-4 animate-spin" />
                      : <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}><path d="m22 2-7 20-4-9-9-4 20-7z"/></svg>
                    }
                  </button>
                </div>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* ── Timeline ─────────────────────────────────────────────────────── */}
      <div className="h-44 bg-[#111111] border-t border-white/10 shrink-0 flex flex-col">
        {/* Timeline toolbar */}
        <div className="flex items-center justify-between px-4 h-8 border-b border-white/10">
          <div className="flex items-center gap-2">
            <button className="p-1 text-white/40 hover:text-white transition-colors">
              <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}><path d="M12 5v14M5 12h14"/></svg>
            </button>
            <button className="p-1 text-white/40 hover:text-white transition-colors">
              <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}><path d="M5 12h14"/></svg>
            </button>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-xs text-white/40 font-mono">{formatTime(currentTime)}</span>
            <span className="text-xs text-white/40">/</span>
            <span className="text-xs text-white/40 font-mono">{formatTime(duration)}</span>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={() => setTimelineZoom((z) => Math.max(0.5, z - 0.25))}
              className="p-1 text-white/40 hover:text-white transition-colors"
            >
              <ZoomOut className="w-3.5 h-3.5" />
            </button>
            <span className="text-xs text-white/30 w-8 text-center">{Math.round(timelineZoom * 100)}%</span>
            <button
              onClick={() => setTimelineZoom((z) => Math.min(4, z + 0.25))}
              className="p-1 text-white/40 hover:text-white transition-colors"
            >
              <ZoomIn className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>

        {/* Track area */}
        <div className="flex flex-1 overflow-hidden">
          {/* Track labels */}
          <div className="w-20 shrink-0 border-r border-white/10 flex flex-col">
            {["", "Video", "Audio", "Captions", "Emojis", "Effects"].map((label, i) => (
              <div
                key={i}
                className={cn(
                  "flex items-center justify-end pr-2 text-xs text-white/30",
                  i === 0 ? "h-6 border-b border-white/10" : "flex-1 border-b border-white/5 last:border-0"
                )}
              >
                {label}
              </div>
            ))}
          </div>

          {/* Scrollable track content + ruler */}
          <div className="flex-1 overflow-x-auto overflow-y-hidden relative">
            <div style={{ width: `${Math.max(100, timelineZoom * 100)}%`, minWidth: "100%", height: "100%" }}>
              {/* Time ruler */}
              <div
                ref={timelineRef}
                className="h-6 border-b border-white/10 relative cursor-pointer select-none"
                onMouseDown={handleTimelineMouseDown}
              >
                {/* Tick marks */}
                {Array.from({ length: Math.ceil(duration) + 1 }).map((_, i) => (
                  <div
                    key={i}
                    className="absolute top-0 flex flex-col items-center"
                    style={{ left: `${duration ? (i / duration) * 100 : 0}%` }}
                  >
                    <div className="w-px h-2.5 bg-white/20" />
                    <span className="text-[10px] text-white/30 mt-0.5">{i}s</span>
                  </div>
                ))}
                {/* Playhead */}
                {duration > 0 && (
                  <div
                    className="absolute top-0 bottom-0 flex flex-col items-center pointer-events-none"
                    style={{ left: `${(currentTime / duration) * 100}%` }}
                  >
                    <div className="w-3 h-3 bg-[#7c3aed] rotate-45 -mt-1.5 rounded-sm" />
                    <div className="w-0.5 flex-1 bg-[#7c3aed]" />
                  </div>
                )}
              </div>

              {/* Tracks */}
              <div className="flex flex-col" style={{ height: "calc(100% - 24px)" }}>
                {/* Video track */}
                <div className="flex-1 border-b border-white/5 relative px-1 py-1">
                  {project && duration > 0 && (
                    <div
                      className="h-full rounded bg-[#374151] border border-[#4b5563] flex items-center px-2 overflow-hidden"
                      style={{ width: "100%" }}
                    >
                      <Video className="w-3 h-3 text-white/40 mr-1.5 shrink-0" />
                      <span className="text-xs text-white/50 truncate">{project.hook ?? "Video"}</span>
                    </div>
                  )}
                  {/* Playhead line */}
                  {duration > 0 && (
                    <div
                      className="absolute top-0 bottom-0 w-0.5 bg-[#7c3aed] pointer-events-none"
                      style={{ left: `${(currentTime / duration) * 100}%` }}
                    />
                  )}
                </div>

                {/* Audio track */}
                <div className="flex-1 border-b border-white/5 relative px-1 py-1">
                  {backgroundMusic !== "none" && duration > 0 && (
                    <div
                      className="h-full rounded bg-[#1e3a5f] border border-[#2563eb]/40 flex items-center px-2"
                      style={{ width: "100%" }}
                    >
                      <Music className="w-3 h-3 text-blue-400/60 mr-1.5 shrink-0" />
                      <span className="text-xs text-white/50 truncate capitalize">
                        {backgroundMusic.replace(/_/g, " ")}
                      </span>
                    </div>
                  )}
                  {duration > 0 && (
                    <div
                      className="absolute top-0 bottom-0 w-0.5 bg-[#7c3aed] pointer-events-none"
                      style={{ left: `${(currentTime / duration) * 100}%` }}
                    />
                  )}
                </div>

                {/* Captions track */}
                <div className="flex-1 border-b border-white/5 relative px-1 py-1">
                  {captionStyle && duration > 0 && (
                    <div
                      className="h-full rounded bg-[#3b1f5e] border border-[#7c3aed]/40 flex items-center px-2"
                      style={{ width: "80%" }}
                    >
                      <span className="text-xs text-white/50 truncate capitalize">
                        {captionStyle.replace(/_/g, " ")}
                      </span>
                    </div>
                  )}
                  {duration > 0 && (
                    <div
                      className="absolute top-0 bottom-0 w-0.5 bg-[#7c3aed] pointer-events-none"
                      style={{ left: `${(currentTime / duration) * 100}%` }}
                    />
                  )}
                </div>

                {/* Emojis / Effects tracks */}
                {["Emojis", "Effects"].map((label) => (
                  <div key={label} className="flex-1 border-b border-white/5 last:border-0 relative">
                    {duration > 0 && (
                      <div
                        className="absolute top-0 bottom-0 w-0.5 bg-[#7c3aed] pointer-events-none"
                        style={{ left: `${(currentTime / duration) * 100}%` }}
                      />
                    )}
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
