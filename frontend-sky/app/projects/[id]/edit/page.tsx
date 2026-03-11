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
  Save,
} from "lucide-react";
import { cn } from "@/lib/utils";
import apiClient from "@/lib/apiClient";
import { apiFetch } from "@/lib/api";
import { auth } from "@/lib/firebase";
import { useAuth } from "@/context/AuthContext";
import type { Result } from "@twick/studio";
import type { ProjectJSON } from "@twick/timeline";
import "@twick/studio/dist/studio.css";
import { TimelineProvider, INITIAL_TIMELINE_DATA, useTimelineContext } from "@twick/timeline";
import { LivePlayerProvider, useLivePlayerContext } from "@twick/live-player";
import { EditorShell } from "@/components/editor/editor-shell";
import type { AgentMessage, Project } from "@/components/editor/types";

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
  const [exportLoading, setExportLoading] = useState(false);
  const [exportMessage, setExportMessage] = useState<string | null>(null);
  const [saveState, setSaveState] = useState<"saved" | "saving" | "error">("saved");
  const [lastSavedAt, setLastSavedAt] = useState<Date | null>(null);
  const agentBottomRef = useRef<HTMLDivElement>(null);
  const editorBridgeRef = useRef<EditorBridgeHandle | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const captureAudioCtxRef = useRef<AudioContext | null>(null);
  const playbackAudioCtxRef = useRef<AudioContext | null>(null);
  const playbackNodeRef = useRef<AudioWorkletNode | null>(null);
  const mediaStreamRef = useRef<MediaStream | null>(null);
  const processorRef = useRef<ScriptProcessorNode | null>(null);
  const mediaSourceRef = useRef<MediaStreamAudioSourceNode | null>(null);
  const persistTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const normalizeProjectJson = useCallback((json: ProjectJSON | null): ProjectJSON | null => {
    if (!json) return null;
    return {
      ...json,
      tracks: (json.tracks ?? []).map((track) => ({
        ...track,
        elements: (track.elements ?? []).map((element) => {
          const props = typeof element.props === "object" && element.props ? { ...element.props } : element.props;
          const src = typeof props?.src === "string" ? props.src : null;
          if (src && src.startsWith("/assets/")) {
            props.src = `${API}${src}`;
          }
          return props ? { ...element, props } : element;
        }),
      })),
    };
  }, []);

  const saveTimelineDebounced = useCallback((json: ProjectJSON | null) => {
    if (!json) return;
    setSaveState("saving");
    if (persistTimeoutRef.current) {
      clearTimeout(persistTimeoutRef.current);
    }
    persistTimeoutRef.current = setTimeout(() => {
      apiClient.put(`/api/v1/projects/${projectId}/timeline`, json)
        .then(() => {
          setSaveState("saved");
          setLastSavedAt(new Date());
        })
        .catch((error) => {
          console.error("Failed to persist live timeline:", error);
          setSaveState("error");
        });
    }, 600);
  }, [projectId]);

  const syncProjectJson = useCallback((json: ProjectJSON | null) => {
    const normalized = normalizeProjectJson(json);
    if (!normalized) return;
    setProject((prev) => prev ? { ...prev, project_json: normalized } : prev);
    saveTimelineDebounced(normalized);
  }, [normalizeProjectJson, saveTimelineDebounced]);

  const applyLiveProjectJson = useCallback((json: ProjectJSON | null, changes?: Record<string, unknown>) => {
    const normalized = normalizeProjectJson(json);
    if (!normalized) return;
    editorBridgeRef.current?.loadProject(normalized);
    saveTimelineDebounced(normalized);
    setProject((prev) => prev ? ({
      ...prev,
      ...(changes?.caption_style ? { caption_style: String(changes.caption_style) } : {}),
      ...(changes?.background_music ? { background_music: String(changes.background_music) } : {}),
      project_json: normalized,
    }) : prev);
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      const editorContext = editorBridgeRef.current?.getEditorContext() ?? null;
      wsRef.current.send(JSON.stringify({
        type: "editor_state",
        project_json: normalized,
        editor_context: agentPanelOpen
          ? { ...editorContext, active_panel: "agent" }
          : editorContext,
      }));
    }
  }, [agentPanelOpen, normalizeProjectJson, saveTimelineDebounced]);

  // Load project
  const fetchProject = useCallback(async () => {
    try {
      const res = await apiClient.get(`/api/v1/projects/${projectId}`);
      const data = res.data as Project;
      setProject({
        ...data,
        project_json: normalizeProjectJson((data.project_json as ProjectJSON | null) ?? null),
      });
      setLoadError(null);
    } catch (e) {
      setLoadError(e instanceof Error ? e.message : "Failed to load project");
    }
  }, [normalizeProjectJson, projectId]);

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

  const exportCurrentTimeline = useCallback(async () => {
    const currentProject = editorBridgeRef.current?.getProject() ?? project?.project_json ?? null;
    if (!currentProject || exportLoading) return;
    setExportLoading(true);
    setSaveState("saving");
    setExportMessage(null);
    const result = await handleExportVideo(currentProject);
    setExportMessage(result.message);
    setExportLoading(false);
    setSaveState(result.status ? "saved" : "error");
    if (result.status) {
      setLastSavedAt(new Date());
    }
  }, [exportLoading, handleExportVideo, project?.project_json]);

  const saveStateLabel = saveState === "saving"
    ? "Saving..."
    : saveState === "error"
      ? "Save failed"
      : lastSavedAt
        ? `Saved ${lastSavedAt.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}`
        : "Saved";

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
            if ((event.type === "progress" || event.type === "agent_step") && event.message) {
              agentText = event.message;
              if (event.tool) {
                actions.push(event.tool);
              }
            } else if (event.type === "tool_call" && event.tool) {
              actions.push(event.tool);
            } else if (event.type === "tool_event" && event.name) {
              actions.push(event.name);
            } else if (event.type === "complete") {
              agentText = event.message ?? "Done! Changes applied.";
              if (event.project_json) {
                applyLiveProjectJson(
                  event.project_json as ProjectJSON,
                  event.changes as Record<string, unknown> | undefined,
                );
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

  async function initPlaybackContext() {
    if (playbackAudioCtxRef.current && playbackNodeRef.current) {
      if (playbackAudioCtxRef.current.state === "suspended") {
        await playbackAudioCtxRef.current.resume();
      }
      return;
    }

    const audioCtx = new AudioContext();
    await audioCtx.audioWorklet.addModule("/audio/pcm-player.worklet.js");
    const node = new AudioWorkletNode(audioCtx, "pcm-player-processor");
    node.connect(audioCtx.destination);

    playbackAudioCtxRef.current = audioCtx;
    playbackNodeRef.current = node;

    if (audioCtx.state === "suspended") {
      await audioCtx.resume();
    }
  }

  function queuePcmAudio(buffer: ArrayBuffer) {
    const audioCtx = playbackAudioCtxRef.current;
    const node = playbackNodeRef.current;
    if (!audioCtx || !node) return;

    const input = new Int16Array(buffer);
    if (input.length === 0) return;

    const inputRate = 24000;
    const outputRate = audioCtx.sampleRate;
    const ratio = outputRate / inputRate;
    const outputLength = Math.max(1, Math.round(input.length * ratio));
    const output = new Float32Array(outputLength);

    for (let i = 0; i < outputLength; i++) {
      const sourceIndex = i / ratio;
      const leftIndex = Math.floor(sourceIndex);
      const rightIndex = Math.min(leftIndex + 1, input.length - 1);
      const mix = sourceIndex - leftIndex;
      const left = input[leftIndex] / 32768;
      const right = input[rightIndex] / 32768;
      output[i] = left + (right - left) * mix;
    }

    node.port.postMessage({ type: "push", samples: output }, [output.buffer]);
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
        void initPlaybackContext();
        const audioCtx = new AudioContext({ sampleRate: 16000 });
        captureAudioCtxRef.current = audioCtx;
        const source = audioCtx.createMediaStreamSource(stream);
        mediaSourceRef.current = source;
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
        const currentProjectJson = editorBridgeRef.current?.getProject() ?? null;
        const editorContext = editorBridgeRef.current?.getEditorContext() ?? null;
        ws.send(JSON.stringify({
          type: "editor_state",
          project_json: currentProjectJson,
          editor_context: agentPanelOpen
            ? { ...editorContext, active_panel: "agent" }
            : editorContext,
        }));
      };

      ws.onmessage = (event) => {
        if (event.data instanceof Blob) {
          event.data.arrayBuffer().then((buf) => {
            queuePcmAudio(buf);
          });
          return;
        }
        try {
          const data = JSON.parse(event.data);
          if (data.type === "agent_transcript") {
            setAgentMessages((prev) =>
              prev.map((m) =>
                m.id === voiceMsgId ? { ...m, text: data.text ?? m.text } : m
              )
            );
          } else if (data.type === "user_transcript") {
            setAgentMessages((prev) => {
              const userMessageId = `${voiceMsgId}-user`;
              const existing = prev.find((m) => m.id === userMessageId);
              if (existing) {
                return prev.map((m) =>
                  m.id === userMessageId ? { ...m, text: data.text ?? m.text } : m
                );
              }
              return [...prev, { id: userMessageId, role: "user", text: data.text ?? "" }];
            });
          } else if (data.type === "creative_block" || data.type === "tool_event") {
            const tool = data.name ?? data.block?.type ?? "creative_block";
            setAgentMessages((prev) =>
              prev.map((m) =>
                m.id === voiceMsgId ? { ...m, actions: [...(m.actions ?? []), tool] } : m
              )
            );
          } else if (data.type === "complete") {
            setAgentMessages((prev) =>
              prev.map((m) =>
                m.id === voiceMsgId
                  ? { ...m, isThinking: false, text: data.message ?? (m.text || "Live edits applied.") }
                  : m
              )
            );
            if (data.project_json) {
              applyLiveProjectJson(
                data.project_json as ProjectJSON,
                data.changes as Record<string, unknown> | undefined,
              );
            }
          } else if (data.type === "interrupted") {
            playbackNodeRef.current?.port.postMessage({ type: "clear" });
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
    mediaSourceRef.current?.disconnect();
    mediaSourceRef.current = null;
    processorRef.current?.disconnect();
    processorRef.current = null;
    captureAudioCtxRef.current?.close().catch(() => {});
    captureAudioCtxRef.current = null;
    playbackNodeRef.current?.port.postMessage({ type: "clear" });
    playbackNodeRef.current?.disconnect();
    playbackNodeRef.current = null;
    playbackAudioCtxRef.current?.close().catch(() => {});
    playbackAudioCtxRef.current = null;
    mediaStreamRef.current?.getTracks().forEach((t) => t.stop());
    mediaStreamRef.current = null;
    setIsVoiceActive(false);
  }

  useEffect(() => () => {
    if (persistTimeoutRef.current) {
      clearTimeout(persistTimeoutRef.current);
    }
    stopVoiceEdit();
  }, []);

  useEffect(() => {
    if (!isVoiceActive) return;

    const intervalId = window.setInterval(() => {
      if (wsRef.current?.readyState !== WebSocket.OPEN) return;
      const currentProjectJson = editorBridgeRef.current?.getProject() ?? null;
      const editorContext = editorBridgeRef.current?.getEditorContext() ?? null;
      wsRef.current.send(JSON.stringify({
        type: "editor_state",
        project_json: currentProjectJson,
        editor_context: agentPanelOpen
          ? { ...editorContext, active_panel: "agent" }
          : editorContext,
      }));
    }, 1000);

    return () => window.clearInterval(intervalId);
  }, [agentPanelOpen, isVoiceActive]);

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
        <div className="flex items-center gap-3">
          <div className="w-2 h-2 rounded-full bg-green-400" />
          <span className="text-sm text-white/70 truncate max-w-xs">
            {project?.hook ?? "Loading..."}
          </span>
          <div className={cn(
            "hidden items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] md:flex",
            saveState === "error"
              ? "border-red-500/20 bg-red-500/10 text-red-200"
              : saveState === "saving"
                ? "border-amber-400/20 bg-amber-400/10 text-amber-100"
                : "border-emerald-400/20 bg-emerald-400/10 text-emerald-100"
          )}>
            {saveState === "saving" ? <Loader2 className="h-3 w-3 animate-spin" /> : <Save className="h-3 w-3" />}
            {saveStateLabel}
          </div>
        </div>

        {/* Right */}
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => {
              void exportCurrentTimeline();
            }}
            disabled={exportLoading || !project}
            className="flex items-center gap-1.5 rounded-lg bg-white/10 px-3 py-1.5 text-sm font-medium transition-colors hover:bg-white/15 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {exportLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Download className="h-4 w-4" />}
            {exportLoading ? "Exporting..." : "Export"}
          </button>

          <div className="relative group">
            <button className="flex items-center gap-1.5 rounded-lg bg-white/10 px-3 py-1.5 text-sm font-medium transition-colors hover:bg-white/15">
              <Download className="w-4 h-4" />
              Files
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

      {exportMessage && (
        <div className="border-b border-white/10 bg-[#151823] px-4 py-2 text-xs text-white/65">
          {exportMessage}
        </div>
      )}

      {/* ── Main area ──────────────────────────────────────────────────────── */}
      <div className="flex flex-1 overflow-hidden">

        {/* ── Custom Twick Shell ───────────────────────────────────────────── */}
        <div className="flex-1 overflow-hidden">
          {project ? (
            <LivePlayerProvider>
              <TimelineProvider
                initialData={timelineData}
                contextId={projectId}
              >
                <AgentBridge ref={editorBridgeRef} />
                <EditorShell
                  project={project}
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
                  onProjectJsonChange={syncProjectJson}
                />
              </TimelineProvider>
            </LivePlayerProvider>
          ) : (
            <div className="flex h-full items-center justify-center">
              <Loader2 className="w-8 h-8 animate-spin text-white/30" />
            </div>
          )}
        </div>

      </div>
    </div>
  );
}
