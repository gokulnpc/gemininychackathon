"use client";

import {
  forwardRef,
  useCallback,
  useEffect,
  useImperativeHandle,
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
  Loader2,
  Mic,
  MicOff,
  Send,
  Sparkles,
  X,
} from "lucide-react";
import { cn } from "@/lib/utils";
import apiClient from "@/lib/apiClient";
import { apiFetch } from "@/lib/api";
import { auth } from "@/lib/firebase";
import { useAuth } from "@/context/AuthContext";
import TwickStudio from "@twick/studio";
import type { Result } from "@twick/studio";
import type { ProjectJSON } from "@twick/timeline";
import "@twick/studio/dist/studio.css";
import { TimelineProvider, INITIAL_TIMELINE_DATA, useTimelineContext } from "@twick/timeline";
import { LivePlayerProvider, useLivePlayerContext } from "@twick/live-player";

// ─── AgentBridge ───────────────────────────────────────────────────────────────
// Zero-render child inside TimelineProvider — exposes editor API to parent via ref.

interface EditorBridgeHandle {
  getProject: () => ProjectJSON;
  loadProject: (json: ProjectJSON) => void;
  getEditorContext: () => {
    mode: string | null;
    active_panel: string | null;
    playhead_seconds: number | null;
    viewport_scale: number | null;
    selected_element_ids: string[];
    selected_track_ids: string[];
    selected_element_types: string[];
  };
}

const AgentBridge = forwardRef<EditorBridgeHandle>((_, ref) => {
  const { editor, selectedItem, selectedIds, timelineAction } = useTimelineContext();
  const livePlayer = useLivePlayerContext();
  useImperativeHandle(ref, () => ({
    getProject: () => editor.getProject(),
    loadProject: (json) => editor.loadProject(json),
    getEditorContext: () => {
      const selectionIds = Array.from(selectedIds ?? []);
      const selectedItemId =
        selectedItem && typeof (selectedItem as { getId?: () => string }).getId === "function"
          ? (selectedItem as { getId: () => string }).getId()
          : null;
      const selectedItemType =
        selectedItem && typeof (selectedItem as { getType?: () => string }).getType === "function"
          ? (selectedItem as { getType: () => string }).getType()
          : null;

      const elementIds = selectionIds.filter((id) => id.startsWith("e-"));
      const trackIds = selectionIds.filter((id) => id.startsWith("t-"));

      if (selectedItemId?.startsWith("e-") && !elementIds.includes(selectedItemId)) {
        elementIds.push(selectedItemId);
      }
      if (selectedItemId?.startsWith("t-") && !trackIds.includes(selectedItemId)) {
        trackIds.push(selectedItemId);
      }

      return {
        mode: typeof timelineAction?.type === "string" && timelineAction.type ? timelineAction.type : null,
        active_panel: "timeline",
        playhead_seconds: typeof livePlayer?.currentTime === "number" ? livePlayer.currentTime : null,
        viewport_scale: null,
        selected_element_ids: elementIds,
        selected_track_ids: trackIds,
        selected_element_types: selectedItemType ? [selectedItemType] : [],
      };
    },
  }), [editor, livePlayer, selectedIds, selectedItem, timelineAction]);
  return null;
});

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const WS_API = API.replace(/^http/, "ws");

// ─── Types ────────────────────────────────────────────────────────────────────

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
  project_json?: ProjectJSON | null;
}

interface AgentMessage {
  id: string;
  role: "user" | "agent";
  text: string;
  actions?: string[];
  isThinking?: boolean;
  isError?: boolean;
}

const PLATFORMS = ["instagram_reels", "tiktok", "youtube_shorts", "master"];

// ─── Editor Page ──────────────────────────────────────────────────────────────

export default function EditorPage() {
  const params = useParams();
  const projectId = params.id as string;
  const router = useRouter();
  const { idToken } = useAuth();

  // Project data
  const [project, setProject] = useState<Project | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

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
  const editorBridgeRef = useRef<EditorBridgeHandle | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const audioCtxRef = useRef<AudioContext | null>(null);
  const mediaStreamRef = useRef<MediaStream | null>(null);
  const processorRef = useRef<ScriptProcessorNode | null>(null);

  // Load project
  const fetchProject = useCallback(async () => {
    try {
      const res = await apiClient.get(`/api/v1/projects/${projectId}`);
      setProject(res.data);
      setLoadError(null);
    } catch (e) {
      setLoadError(e instanceof Error ? e.message : "Failed to load project");
    }
  }, [projectId]);

  useEffect(() => { fetchProject(); }, [fetchProject]);

  // Scroll agent to bottom
  useEffect(() => {
    agentBottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [agentMessages]);

  // ─── Twick exportVideo callback ─────────────────────────────────────────────

  const handleExportVideo = useCallback(async (projectData: ProjectJSON): Promise<Result> => {
    try {
      // 1. Persist timeline edits
      await apiClient.put(`/api/v1/projects/${projectId}/timeline`, projectData);

      // 2. Trigger full video recompose with current settings
      const latest = await apiClient.get(`/api/v1/projects/${projectId}`).then((r) => r.data).catch(() => null);
      await apiClient.post(`/api/v1/projects/${projectId}/recompose`, {
        caption_style: latest?.caption_style ?? "bold_stroke",
        background_music: latest?.background_music ?? "none",
        music_volume: 0.15,
        target_platforms: latest?.platforms ?? ["instagram_reels"],
      });

      return { status: true, message: "Video exported! Recompose started." };
    } catch (e) {
      const message = e instanceof Error ? e.message : "Export failed";
      console.error("Export failed:", e);
      return { status: false, message };
    }
  }, [projectId]);

  // ─── Agent (SSE text) ────────────────────────────────────────────────────────

  async function sendAgentInstruction(instruction: string) {
    if (!instruction.trim() || agentLoading) return;

    const userMsg: AgentMessage = { id: Date.now().toString(), role: "user", text: instruction };
    const thinkingId = Date.now().toString() + "-t";
    const thinkingMsg: AgentMessage = { id: thinkingId, role: "agent", text: "", isThinking: true, actions: [] };

    setAgentMessages((prev) => [...prev, userMsg, thinkingMsg]);
    setAgentInput("");
    setAgentLoading(true);

    // Snapshot current Twick timeline state so the agent has full context
    const currentProjectJson = editorBridgeRef.current?.getProject() ?? null;
    const editorContext = editorBridgeRef.current?.getEditorContext() ?? null;

    try {
      const res = await apiFetch(`/api/v1/projects/${projectId}/edit-agent`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          instruction,
          current_project_json: currentProjectJson,
          editor_context: agentPanelOpen
            ? { ...editorContext, active_panel: "agent" }
            : editorContext,
        }),
      });

      if (!res.ok || !res.body) throw new Error(`HTTP ${res.status}`);

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
              agentText = event.message ?? "Done! Changes applied.";
              if (event.project_json) {
                // Load patched timeline into Twick editor — instant, no video recompose
                editorBridgeRef.current?.loadProject(event.project_json as ProjectJSON);
              }
            } else if (event.type === "error") {
              agentText = event.message ?? "Something went wrong.";
            }
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

  // ─── Voice edit (WebSocket) ──────────────────────────────────────────────────

  async function startVoiceEdit() {
    if (isVoiceActive) {
      stopVoiceEdit();
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      mediaStreamRef.current = stream;
      const token = await auth.currentUser?.getIdToken();
      const ws = new WebSocket(`${WS_API}/api/v1/projects/${projectId}/edit-voice${token ? `?token=${token}` : ""}`);
      wsRef.current = ws;

      const voiceMsgId = Date.now().toString() + "-v";
      setAgentMessages((prev) => [
        ...prev,
        { id: Date.now().toString(), role: "user", text: "🎤 Voice edit started..." },
        { id: voiceMsgId, role: "agent", text: "", isThinking: true, actions: [] },
      ]);
      setIsVoiceActive(true);

      ws.onopen = () => {
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
                m.id === voiceMsgId ? { ...m, text: (m.text || "") + data.text } : m
              )
            );
          } else if (data.type === "creative_block" || data.type === "tool_call") {
            const tool = data.block ?? data.tool ?? "";
            setAgentMessages((prev) =>
              prev.map((m) =>
                m.id === voiceMsgId ? { ...m, actions: [...(m.actions ?? []), tool] } : m
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

      ws.onclose = () => { stopVoiceEdit(); };

    } catch {
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

  // ─── Helpers ─────────────────────────────────────────────────────────────────

  const streamUrl = (platform: string) =>
    `${API}/api/v1/projects/${projectId}/stream/${platform}${idToken ? `?token=${idToken}` : ''}`;

  const availablePlatforms = project?.platforms?.length
    ? project.platforms
    : PLATFORMS.filter((p) => project?.video_urls?.[p]);

  const timelineData = project?.project_json ?? INITIAL_TIMELINE_DATA;

  // ─── Error state ─────────────────────────────────────────────────────────────

  if (loadError) {
    return (
      <div className="flex h-screen items-center justify-center bg-[#1a1a1a] text-white/50">
        <div className="text-center">
          <AlertCircle className="w-12 h-12 mx-auto mb-4 text-red-400/60" />
          <p className="text-lg mb-2">{loadError}</p>
          <button
            onClick={() => router.push(`/projects/${projectId}`)}
            className="text-sm text-[#7c3aed] hover:underline"
          >
            ← Back to project
          </button>
        </div>
      </div>
    );
  }

  // ─── Render ───────────────────────────────────────────────────────────────────

  return (
    <div className="flex flex-col h-screen bg-[#1a1a1a] text-white overflow-hidden">

      {/* ── Toolbar ────────────────────────────────────────────────────────── */}
      <div className="flex items-center justify-between px-4 h-12 bg-[#111111] border-b border-white/10 shrink-0 z-10">
        {/* Left */}
        <div className="flex items-center gap-3">
          <button
            onClick={() => router.push(`/projects/${projectId}`)}
            className="flex items-center gap-1.5 text-white/50 hover:text-white transition-colors text-sm"
          >
            <ArrowLeft className="w-4 h-4" /> Back
          </button>
        </div>

        {/* Center — project title */}
        <div className="flex items-center gap-2">
          <div className="w-2 h-2 rounded-full bg-green-400" />
          <span className="text-sm text-white/70 truncate max-w-xs">
            {project?.hook ?? "Loading..."}
          </span>
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

      {/* ── Main area ──────────────────────────────────────────────────────── */}
      <div className="flex flex-1 overflow-hidden">

        {/* ── Twick Studio ──────────────────────────────────────────────────── */}
        <div className="flex-1 overflow-hidden">
          {project ? (
            <LivePlayerProvider>
              <TimelineProvider
                initialData={timelineData}
                contextId={projectId}
              >
                <AgentBridge ref={editorBridgeRef} />
                <TwickStudio
                  studioConfig={{
                    videoProps: { width: 576, height: 1024 },
                    exportVideo: handleExportVideo,
                  }}
                />
              </TimelineProvider>
            </LivePlayerProvider>
          ) : (
            <div className="flex h-full items-center justify-center">
              <Loader2 className="w-8 h-8 animate-spin text-white/30" />
            </div>
          )}
        </div>

        {/* ── AI Agent Panel ────────────────────────────────────────────────── */}
        {agentPanelOpen && (
          <div className="w-80 flex flex-col bg-[#1e1e1e] border-l border-white/10 shrink-0">
            {/* Header */}
            <div className="flex items-center justify-between px-4 py-3 border-b border-white/10">
              <div className="flex items-center gap-2">
                <div className="w-6 h-6 rounded-full bg-[#7c3aed] flex items-center justify-center">
                  <Sparkles className="w-3.5 h-3.5 text-white" />
                </div>
                <span className="text-sm font-semibold">AI Editor</span>
              </div>
              <button
                onClick={() => setAgentPanelOpen(false)}
                className="text-white/40 hover:text-white transition-colors"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            {/* Messages */}
            <div className="flex-1 overflow-y-auto p-3 space-y-3">
              {agentMessages.map((msg) => (
                <div
                  key={msg.id}
                  className={cn(
                    "flex flex-col gap-1",
                    msg.role === "user" ? "items-end" : "items-start"
                  )}
                >
                  <div
                    className={cn(
                      "max-w-[90%] rounded-2xl px-3 py-2 text-sm leading-relaxed",
                      msg.role === "user"
                        ? "bg-[#7c3aed] text-white rounded-br-sm"
                        : msg.isError
                          ? "bg-red-900/30 text-red-300 border border-red-500/20 rounded-bl-sm"
                          : "bg-white/8 text-white/90 rounded-bl-sm"
                    )}
                  >
                    {msg.isThinking && !msg.text ? (
                      <div className="flex items-center gap-2 text-white/50">
                        <Loader2 className="w-3.5 h-3.5 animate-spin" />
                        <span>Thinking...</span>
                      </div>
                    ) : (
                      msg.text || <span className="text-white/30 italic">Processing...</span>
                    )}
                  </div>
                  {/* Tool call badges */}
                  {msg.actions && msg.actions.length > 0 && (
                    <div className="flex flex-wrap gap-1 max-w-[90%]">
                      {msg.actions.map((action, i) => (
                        <span
                          key={i}
                          className="px-2 py-0.5 bg-[#7c3aed]/20 text-[#a78bfa] border border-[#7c3aed]/30 rounded-full text-[10px] font-mono"
                        >
                          {action}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              ))}
              <div ref={agentBottomRef} />
            </div>

            {/* Quick actions */}
            <div className="px-3 py-2 border-t border-white/10 grid grid-cols-2 gap-1.5">
              {[
                "Add B-rolls",
                "Add Zooms",
                "Change Theme",
                "Add Music",
              ].map((action) => (
                <button
                  key={action}
                  onClick={() => sendAgentInstruction(action)}
                  disabled={agentLoading}
                  className="px-2 py-1.5 bg-white/5 hover:bg-white/10 border border-white/10 rounded-lg text-xs text-white/70 hover:text-white transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
                >
                  {action}
                </button>
              ))}
            </div>

            {/* Input */}
            <div className="p-3 border-t border-white/10">
              <div className="flex items-end gap-2 bg-white/5 border border-white/10 rounded-xl px-3 py-2 focus-within:border-[#7c3aed]/50 transition-colors">
                <textarea
                  value={agentInput}
                  onChange={(e) => setAgentInput(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && !e.shiftKey) {
                      e.preventDefault();
                      sendAgentInstruction(agentInput);
                    }
                  }}
                  placeholder="Describe your edit..."
                  rows={2}
                  className="flex-1 bg-transparent text-sm text-white placeholder-white/30 resize-none focus:outline-none leading-relaxed"
                />
                <div className="flex items-center gap-1.5 pb-0.5">
                  <button
                    onClick={startVoiceEdit}
                    className={cn(
                      "p-1.5 rounded-lg transition-colors",
                      isVoiceActive
                        ? "bg-red-500/20 text-red-400 animate-pulse"
                        : "text-white/40 hover:text-white hover:bg-white/10"
                    )}
                  >
                    {isVoiceActive ? <MicOff className="w-4 h-4" /> : <Mic className="w-4 h-4" />}
                  </button>
                  <button
                    onClick={() => sendAgentInstruction(agentInput)}
                    disabled={!agentInput.trim() || agentLoading}
                    className="p-1.5 bg-[#7c3aed] hover:bg-[#6d28d9] text-white rounded-lg transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
                  >
                    {agentLoading ? (
                      <Loader2 className="w-4 h-4 animate-spin" />
                    ) : (
                      <Send className="w-4 h-4" />
                    )}
                  </button>
                </div>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
