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
  Loader2,
  Save,
} from "lucide-react";
import { cn } from "@/lib/utils";
import apiClient from "@/lib/apiClient";
import { apiFetch } from "@/lib/api";
import { auth } from "@/lib/firebase";
import type { ProjectJSON } from "@twick/timeline";
import "@twick/studio/dist/studio.css";
import { TimelineProvider, INITIAL_TIMELINE_DATA, useTimelineContext } from "@twick/timeline";
import { LivePlayerProvider, PLAYER_STATE, useLivePlayerContext } from "@twick/live-player";
import dynamic from "next/dynamic";
import type { AgentMessage, Project } from "@/components/editor/types";

const EditorShell = dynamic(
  () => import("@/components/editor/editor-shell").then((m) => ({ default: m.EditorShell })),
  { ssr: false },
);

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

type TimelineTrackJson = NonNullable<ProjectJSON["tracks"]>[number];
type TimelineElementJson = TimelineTrackJson["elements"][number];

interface MediaTransformRecord {
  canonicalSrc: string;
  editorSrc: string;
  canonicalElementObjectFit: string | null;
  canonicalPropsObjectFit: string | null;
  editorElementObjectFit: string | null;
  editorPropsObjectFit: string | null;
  canonicalFrame: TimelineElementJson["frame"] | null;
  editorFrame: TimelineElementJson["frame"] | null;
}

interface SkippedEditorElement {
  element: TimelineElementJson;
  index: number;
}

interface PlaybackWarning {
  elementId: string;
  trackId: string;
  type: string;
  src: string | null;
  editorSrc: string | null;
  reason: string;
}

interface MediaSourceReference {
  elementId: string;
  trackId: string;
  type: string;
  canonicalSrc: string;
}

interface EditorProjectSession {
  editorProjectJson: ProjectJSON;
  canonicalMediaByElementId: Record<string, MediaTransformRecord>;
  skippedElementsByTrackId: Record<string, SkippedEditorElement[]>;
  playbackWarnings: PlaybackWarning[];
  mediaIndexByEditorSrc: Record<string, MediaSourceReference[]>;
}

const ABSOLUTE_SRC_PATTERN = /^(?:[a-z]+:)?\/\//i;
const DATA_OR_BLOB_SRC_PATTERN = /^(?:data:|blob:)/i;
const GS_MEDIA_SRC_PATTERN = /^gs:\/\/([^/]+)\/(.+)$/i;
const REFRESH_STALL_TIMEOUT_MS = 8000;
const EDITOR_SCENE_IMAGE_FRAME_SCALE = 0.9;

const isAbsoluteMediaSrc = (src: string): boolean =>
  ABSOLUTE_SRC_PATTERN.test(src) || DATA_OR_BLOB_SRC_PATTERN.test(src);

const cloneTimelineElement = (element: TimelineElementJson): TimelineElementJson => {
  const frame = element.frame
    ? {
        ...element.frame,
        size: Array.isArray(element.frame.size) ? [...element.frame.size] : element.frame.size,
      }
    : element.frame;

  return {
    ...element,
    props: typeof element.props === "object" && element.props ? { ...element.props } : element.props,
    frame,
    frameEffects: Array.isArray(element.frameEffects) ? [...element.frameEffects] : element.frameEffects,
  };
};

const cloneTimelineTrack = (track: TimelineTrackJson): TimelineTrackJson => ({
  ...track,
  props: typeof track.props === "object" && track.props ? { ...track.props } : track.props,
  elements: (track.elements ?? []).map((element) => cloneTimelineElement(element)),
});

const resolveGsMediaSrc = (src: string): string | null => {
  const match = src.match(GS_MEDIA_SRC_PATTERN);
  if (!match) {
    return null;
  }

  return `https://storage.googleapis.com/${match[1]}/${match[2]}`;
};

const normalizeEditorMediaSrc = (src: string): { editorSrc: string | null; reason?: string } => {
  if (!src) {
    return { editorSrc: null, reason: "Missing media source." };
  }

  if (DATA_OR_BLOB_SRC_PATTERN.test(src) || ABSOLUTE_SRC_PATTERN.test(src)) {
    return { editorSrc: src };
  }

  if (src.startsWith("gs://")) {
    const resolvedSrc = resolveGsMediaSrc(src);
    return resolvedSrc
      ? { editorSrc: resolvedSrc }
      : { editorSrc: null, reason: "Unsupported gs:// media source." };
  }

  if (src.startsWith("/assets/") || src.startsWith("/outputs/")) {
    return { editorSrc: `${API}${src}` };
  }

  if (src.startsWith("/")) {
    if (typeof window === "undefined") {
      return { editorSrc: src };
    }

    return { editorSrc: `${window.location.origin}${src}` };
  }

  return { editorSrc: null, reason: "Unsupported media source for browser playback." };
};

const isSceneImageElement = (element: TimelineElementJson): boolean => {
  if (element.type !== "image") {
    return false;
  }

  const props = typeof element.props === "object" && element.props ? element.props : null;
  return typeof props?.sceneId === "number" || typeof props?.sceneId === "string";
};

const isCanvasSizedSceneFrame = (frame: TimelineElementJson["frame"] | null | undefined): boolean => {
  if (!frame || !Array.isArray(frame.size) || frame.size.length < 2) {
    return false;
  }

  const [width, height] = frame.size;
  return Math.abs(width - 576) <= 1 && Math.abs(height - 1024) <= 1 && Math.abs(frame.x ?? 0) <= 1 && Math.abs(frame.y ?? 0) <= 1;
};

const buildEditorSceneImageFrame = (frame: TimelineElementJson["frame"] | null | undefined): TimelineElementJson["frame"] | null => {
  if (!frame || !Array.isArray(frame.size) || frame.size.length < 2) {
    return null;
  }

  const [width, height] = frame.size;
  return {
    ...frame,
    size: [
      Math.round(width * EDITOR_SCENE_IMAGE_FRAME_SCALE),
      Math.round(height * EDITOR_SCENE_IMAGE_FRAME_SCALE),
    ],
    x: frame.x ?? 0,
    y: frame.y ?? 0,
  };
};

const buildEditorProjectSession = (json: ProjectJSON | null): EditorProjectSession | null => {
  if (!json) {
    return null;
  }

  const canonicalMediaByElementId: Record<string, MediaTransformRecord> = {};
  const skippedElementsByTrackId: Record<string, SkippedEditorElement[]> = {};
  const playbackWarnings: PlaybackWarning[] = [];
  const mediaIndexByEditorSrc: Record<string, MediaSourceReference[]> = {};

  const editorTracks = (json.tracks ?? []).map((track) => {
    const editorTrack = cloneTimelineTrack(track);
    const nextElements: TimelineElementJson[] = [];

    for (const [index, rawElement] of (editorTrack.elements ?? []).entries()) {
      const element = cloneTimelineElement(rawElement);
      const props = typeof element.props === "object" && element.props ? { ...element.props } : {};
      const src = typeof props.src === "string" ? props.src : null;
      const shouldForceContain = isSceneImageElement(element);
      const shouldInsetFrame = shouldForceContain && isCanvasSizedSceneFrame(element.frame);
      const canonicalElementObjectFit = typeof element.objectFit === "string" ? element.objectFit : null;
      const canonicalPropsObjectFit = typeof props.objectFit === "string" ? props.objectFit : null;
      const canonicalFrame = element.frame ? cloneTimelineElement(element).frame ?? null : null;
      const editorFrame = shouldInsetFrame ? buildEditorSceneImageFrame(element.frame) : canonicalFrame;

      if (src) {
        const { editorSrc, reason } = normalizeEditorMediaSrc(src);
        if (!editorSrc) {
          playbackWarnings.push({
            elementId: element.id,
            trackId: track.id,
            type: element.type,
            src,
            editorSrc: null,
            reason: reason ?? "Media source could not be normalized for browser playback.",
          });
          skippedElementsByTrackId[track.id] = [
            ...(skippedElementsByTrackId[track.id] ?? []),
            { element: cloneTimelineElement(rawElement), index },
          ];
          continue;
        }

        props.src = editorSrc;
        canonicalMediaByElementId[element.id] = {
          canonicalSrc: src,
          editorSrc,
          canonicalElementObjectFit,
          canonicalPropsObjectFit,
          editorElementObjectFit: shouldForceContain ? "contain" : canonicalElementObjectFit,
          editorPropsObjectFit: shouldForceContain ? "contain" : canonicalPropsObjectFit,
          canonicalFrame,
          editorFrame,
        };
        mediaIndexByEditorSrc[editorSrc] = [
          ...(mediaIndexByEditorSrc[editorSrc] ?? []),
          {
            elementId: element.id,
            trackId: track.id,
            type: element.type,
            canonicalSrc: src,
          },
        ];
      }

      if (shouldForceContain) {
        element.objectFit = "contain";
        props.objectFit = "contain";
      }

      if (editorFrame) {
        element.frame = {
          ...editorFrame,
          size: Array.isArray(editorFrame.size) ? [...editorFrame.size] : editorFrame.size,
        };
      }

      element.props = props;
      nextElements.push(element);
    }

    editorTrack.elements = nextElements;
    return editorTrack;
  });

  return {
    editorProjectJson: {
      ...json,
      tracks: editorTracks,
    },
    canonicalMediaByElementId,
    skippedElementsByTrackId,
    playbackWarnings,
    mediaIndexByEditorSrc,
  };
};

const restoreCanonicalElement = (
  element: TimelineElementJson,
  transformRecord: MediaTransformRecord | undefined,
): TimelineElementJson => {
  if (!transformRecord) {
    return cloneTimelineElement(element);
  }

  const restored = cloneTimelineElement(element);
  const props = typeof restored.props === "object" && restored.props ? { ...restored.props } : {};

  if (typeof props.src === "string" && props.src === transformRecord.editorSrc) {
    props.src = transformRecord.canonicalSrc;
  }

  if (transformRecord.editorElementObjectFit && restored.objectFit === transformRecord.editorElementObjectFit) {
    if (transformRecord.canonicalElementObjectFit) {
      restored.objectFit = transformRecord.canonicalElementObjectFit;
    } else {
      delete restored.objectFit;
    }
  }

  if (transformRecord.editorPropsObjectFit && props.objectFit === transformRecord.editorPropsObjectFit) {
    if (transformRecord.canonicalPropsObjectFit) {
      props.objectFit = transformRecord.canonicalPropsObjectFit;
    } else {
      delete props.objectFit;
    }
  }

  if (transformRecord.editorFrame && restored.frame) {
    const restoredSize = Array.isArray(restored.frame.size) ? restored.frame.size : [];
    const editorSize = Array.isArray(transformRecord.editorFrame.size) ? transformRecord.editorFrame.size : [];
    const frameMatchesEditor =
      restoredSize.length >= 2 &&
      editorSize.length >= 2 &&
      Math.abs(restoredSize[0] - editorSize[0]) <= 1 &&
      Math.abs(restoredSize[1] - editorSize[1]) <= 1 &&
      Math.abs((restored.frame.x ?? 0) - (transformRecord.editorFrame.x ?? 0)) <= 1 &&
      Math.abs((restored.frame.y ?? 0) - (transformRecord.editorFrame.y ?? 0)) <= 1;

    if (frameMatchesEditor) {
      restored.frame = transformRecord.canonicalFrame
        ? {
            ...transformRecord.canonicalFrame,
            size: Array.isArray(transformRecord.canonicalFrame.size)
              ? [...transformRecord.canonicalFrame.size]
              : transformRecord.canonicalFrame.size,
          }
        : null;
    }
  }

  restored.props = props;
  return restored;
};

const serializeProjectJsonForPersistence = (
  editorProjectJson: ProjectJSON | null,
  session: EditorProjectSession | null,
): ProjectJSON | null => {
  if (!editorProjectJson) {
    return null;
  }

  const canonicalMediaByElementId = session?.canonicalMediaByElementId ?? {};
  const skippedElementsByTrackId = session?.skippedElementsByTrackId ?? {};

  return {
    ...editorProjectJson,
    tracks: (editorProjectJson.tracks ?? []).map((track) => {
      const restoredElements = (track.elements ?? []).map((element) =>
        restoreCanonicalElement(element, canonicalMediaByElementId[element.id])
      );
      const mergedElements = [...restoredElements];

      for (const skipped of (skippedElementsByTrackId[track.id] ?? []).sort((left, right) => left.index - right.index)) {
        mergedElements.splice(
          Math.min(skipped.index, mergedElements.length),
          0,
          cloneTimelineElement(skipped.element),
        );
      }

      return {
        ...track,
        elements: mergedElements,
      };
    }),
  };
};

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

function PlaybackDebugBridge() {
  const { timelineAction } = useTimelineContext();
  const livePlayer = useLivePlayerContext() as {
    playerState?: keyof typeof PLAYER_STATE | string;
    currentTime?: number;
  } | null;
  const refreshTimeoutRef = useRef<number | null>(null);

  useEffect(() => {
    const nextPlayerState = livePlayer?.playerState ?? "unknown";
    if (nextPlayerState === PLAYER_STATE.REFRESH) {
      console.info("[EditorPlayback] player entered REFRESH", {
        currentTime: livePlayer?.currentTime ?? 0,
      });
      if (refreshTimeoutRef.current) {
        clearTimeout(refreshTimeoutRef.current);
      }
      refreshTimeoutRef.current = window.setTimeout(() => {
        console.warn("[EditorPlayback] player refresh is stalled", {
          currentTime: livePlayer?.currentTime ?? 0,
          timeoutMs: REFRESH_STALL_TIMEOUT_MS,
        });
      }, REFRESH_STALL_TIMEOUT_MS);
      return;
    }

    if (refreshTimeoutRef.current) {
      clearTimeout(refreshTimeoutRef.current);
      refreshTimeoutRef.current = null;
    }
  }, [livePlayer?.currentTime, livePlayer?.playerState]);

  useEffect(() => {
    if (timelineAction?.type === "updatePlayerData") {
      console.info("[EditorPlayback] timeline requested player refresh");
    }
    if (timelineAction?.type === "onPlayerUpdated") {
      console.info("[EditorPlayback] player reported ON_PLAYER_UPDATED");
    }
  }, [timelineAction]);

  useEffect(() => {
    return () => {
      if (refreshTimeoutRef.current) {
        clearTimeout(refreshTimeoutRef.current);
      }
    };
  }, []);

  return null;
}

// ─── Editor Page ──────────────────────────────────────────────────────────────

export default function EditorPage() {
  const params = useParams();
  const projectId = params.id as string;
  const router = useRouter();

  // Project data
  const [project, setProject] = useState<Project | null>(null);
  const [editorProjectJson, setEditorProjectJson] = useState<ProjectJSON | null>(null);
  const [playbackWarnings, setPlaybackWarnings] = useState<PlaybackWarning[]>([]);
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
  const editorRootRef = useRef<HTMLDivElement>(null);
  const editorSessionRef = useRef<EditorProjectSession | null>(null);

  const applyEditorSession = useCallback((json: ProjectJSON | null, label: string): ProjectJSON | null => {
    const session = buildEditorProjectSession(json);
    editorSessionRef.current = session;
    setEditorProjectJson(session?.editorProjectJson ?? null);
    setPlaybackWarnings(session?.playbackWarnings ?? []);
    console.info(`[EditorPlayback] media session (${label})`, {
      projectId,
      count: Object.keys(session?.mediaIndexByEditorSrc ?? {}).length,
      sources: Object.entries(session?.mediaIndexByEditorSrc ?? {}).map(([editorSrc, refs]) => ({
        editorSrc,
        elements: refs,
      })),
      warnings: session?.playbackWarnings ?? [],
    });
    return session?.editorProjectJson ?? null;
  }, [projectId]);

  const serializeProjectJson = useCallback((json: ProjectJSON | null): ProjectJSON | null => {
    return serializeProjectJsonForPersistence(json, editorSessionRef.current);
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
    const canonical = serializeProjectJson(json);
    if (!canonical) return;
    applyEditorSession(canonical, "editor_mutation");
    setProject((prev) => prev ? { ...prev, project_json: canonical } : prev);
    saveTimelineDebounced(canonical);
  }, [applyEditorSession, saveTimelineDebounced, serializeProjectJson]);

  const applyLiveProjectJson = useCallback((json: ProjectJSON | null, changes?: Record<string, unknown>) => {
    if (!json) return;
    const editorJson = applyEditorSession(json, "live_update");
    editorBridgeRef.current?.loadProject(editorJson ?? INITIAL_TIMELINE_DATA);
    saveTimelineDebounced(json);
    setProject((prev) => prev ? ({
      ...prev,
      ...(changes?.caption_style ? { caption_style: String(changes.caption_style) } : {}),
      ...(changes?.background_music ? { background_music: String(changes.background_music) } : {}),
      project_json: json,
    }) : prev);
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      const editorContext = editorBridgeRef.current?.getEditorContext() ?? null;
      wsRef.current.send(JSON.stringify({
        type: "editor_state",
        project_json: json,
        editor_context: agentPanelOpen
          ? { ...editorContext, active_panel: "agent" }
          : editorContext,
      }));
    }
  }, [agentPanelOpen, applyEditorSession, saveTimelineDebounced]);

  // Load project
  const fetchProject = useCallback(async () => {
    try {
      const res = await apiClient.get(`/api/v1/projects/${projectId}`);
      const data = res.data as Project;
      const canonicalProjectJson = (data.project_json as ProjectJSON | null) ?? null;
      applyEditorSession(canonicalProjectJson, "initial_load");
      setProject({
        ...data,
        project_json: canonicalProjectJson,
      });
      setLoadError(null);
    } catch (e) {
      setLoadError(e instanceof Error ? e.message : "Failed to load project");
    }
  }, [applyEditorSession, projectId]);

  useEffect(() => { fetchProject(); }, [fetchProject]);

  // Scroll agent to bottom
  useEffect(() => {
    agentBottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [agentMessages]);

  useEffect(() => {
    const root = editorRootRef.current;
    if (!root) return;

    const logMediaEvent = (event: Event) => {
      const target = event.target;
      if (!(target instanceof HTMLMediaElement || target instanceof HTMLImageElement)) {
        return;
      }

      const src = target instanceof HTMLMediaElement
        ? target.currentSrc || target.src
        : target.currentSrc || target.src;
      const linkedElements = src
        ? (editorSessionRef.current?.mediaIndexByEditorSrc[src] ?? [])
        : [];

      console.warn(`[EditorPlayback] media ${event.type}`, {
        src,
        linkedElements,
        ...(target instanceof HTMLMediaElement
          ? {
              readyState: target.readyState,
              networkState: target.networkState,
              error: target.error?.message ?? target.error?.code ?? null,
            }
          : {}),
      });

      if (event.type === "error" && linkedElements.length > 0) {
        setPlaybackWarnings((previousWarnings) => {
          const nextWarnings = [...previousWarnings];
          for (const elementRef of linkedElements) {
            const alreadyTracked = nextWarnings.some((warning) =>
              warning.elementId === elementRef.elementId && warning.reason === "Browser reported a media load error."
            );
            if (!alreadyTracked) {
              nextWarnings.push({
                elementId: elementRef.elementId,
                trackId: elementRef.trackId,
                type: elementRef.type,
                src: elementRef.canonicalSrc,
                editorSrc: src,
                reason: "Browser reported a media load error.",
              });
            }
          }
          return nextWarnings;
        });
      }
    };

    root.addEventListener("error", logMediaEvent, true);
    root.addEventListener("stalled", logMediaEvent, true);
    root.addEventListener("waiting", logMediaEvent, true);

    return () => {
      root.removeEventListener("error", logMediaEvent, true);
      root.removeEventListener("stalled", logMediaEvent, true);
      root.removeEventListener("waiting", logMediaEvent, true);
    };
  }, []);

  const getCurrentCanonicalProjectJson = useCallback(() => {
    return serializeProjectJson(editorBridgeRef.current?.getProject() ?? null);
  }, [serializeProjectJson]);

  const exportPortalRef = useRef<HTMLDivElement>(null);

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
    const currentProjectJson = getCurrentCanonicalProjectJson();
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
        const currentProjectJson = getCurrentCanonicalProjectJson();
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
      const currentProjectJson = getCurrentCanonicalProjectJson();
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
  }, [agentPanelOpen, getCurrentCanonicalProjectJson, isVoiceActive]);

  // ─── Helpers ─────────────────────────────────────────────────────────────────

  const timelineData = editorProjectJson ?? INITIAL_TIMELINE_DATA;

  // ─── Error state ─────────────────────────────────────────────────────────────

  if (loadError) {
    return (
      <div className="flex h-screen items-center justify-center bg-editor-toolbar text-editor-text-muted">
        <div className="text-center">
          <AlertCircle className="w-12 h-12 mx-auto mb-4 text-red-400/60" />
          <p className="text-lg mb-2">{loadError}</p>
          <button
            onClick={() => router.push(`/projects/${projectId}`)}
            className="text-sm text-primary hover:underline"
          >
            ← Back to project
          </button>
        </div>
      </div>
    );
  }

  // ─── Render ───────────────────────────────────────────────────────────────────

  return (
    <div ref={editorRootRef} className="editor-theme flex h-screen min-h-0 flex-col overflow-hidden bg-editor-bg text-foreground">

      {/* ── Toolbar ────────────────────────────────────────────────────────── */}
      <div className="flex items-center justify-between px-4 h-12 bg-editor-toolbar border-b border-editor-border shrink-0 z-10">
        {/* Left */}
        <div className="flex items-center gap-3">
          <button
            onClick={() => router.push(`/projects/${projectId}`)}
            className="flex items-center gap-1.5 text-muted-foreground hover:text-foreground transition-colors text-sm"
          >
            <ArrowLeft className="w-4 h-4" /> Back
          </button>
        </div>

        {/* Center — project title */}
        <div className="flex items-center gap-3">
          <div className="w-2 h-2 rounded-full bg-editor-accent" />
          <span className="text-sm text-editor-text-muted truncate max-w-xs">
            {project?.hook ?? "Loading..."}
          </span>
          {playbackWarnings.length > 0 && (
            <div
              title={playbackWarnings.map((warning) => `${warning.elementId}: ${warning.reason}`).join("\n")}
              className="hidden items-center gap-1.5 rounded-full border border-amber-500/25 bg-amber-500/10 px-2.5 py-1 text-[11px] text-amber-100 md:flex"
            >
              <AlertCircle className="h-3 w-3" />
              {playbackWarnings.length} playback issue{playbackWarnings.length === 1 ? "" : "s"}
            </div>
          )}
            <div className={cn(
            "hidden items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] md:flex",
            saveState === "error"
              ? "border-destructive/20 bg-destructive/10 text-destructive"
              : saveState === "saving"
                ? "border-editor-border bg-editor-control text-muted-foreground"
                : "border-primary/30 bg-primary/10 text-foreground"
          )}>
            {saveState === "saving" ? <Loader2 className="h-3 w-3 animate-spin" /> : <Save className="h-3 w-3" />}
            {saveStateLabel}
          </div>
        </div>

        {/* Right */}
        <div className="flex items-center gap-2">
          {/* Export button is portalled here from EditorShell (inside provider tree) */}
          <div ref={exportPortalRef} />

          {/* Agent toggle */}
          <button
            onClick={() => setAgentPanelOpen((v) => !v)}
            className={cn(
              "flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium transition-colors",
              agentPanelOpen
                ? "bg-primary text-primary-foreground"
                : "bg-secondary text-secondary-foreground hover:bg-editor-control-hover"
            )}
          >
            <Bot className="w-4 h-4" />
            Agent
          </button>
        </div>
      </div>

      {/* ── Main area ──────────────────────────────────────────────────────── */}
      <div className="flex min-h-0 flex-1 overflow-hidden">

        {/* ── Custom Twick Shell ───────────────────────────────────────────── */}
        <div className="min-h-0 flex-1 overflow-hidden">
          {project ? (
            <LivePlayerProvider>
              <TimelineProvider
                initialData={timelineData}
                contextId={projectId}
              >
                <AgentBridge ref={editorBridgeRef} />
                <PlaybackDebugBridge />
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
                  serializeProjectJson={(json) => serializeProjectJson(json) ?? json}
                  exportPortalRef={exportPortalRef}
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
