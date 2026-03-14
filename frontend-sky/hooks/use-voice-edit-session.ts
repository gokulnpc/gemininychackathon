"use client";

import { useCallback, useEffect, useRef, useState, type MutableRefObject } from "react";
import type { ProjectJSON } from "@twick/timeline";

import { auth } from "@/lib/firebase";
import type { AgentMessage, CreativeBlock, EditProposal, EditorBridgeHandle } from "@/components/editor/types";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const WS_API = API.replace(/^http/, "ws");

const VAD_RMS_THRESHOLD = 0.015;
const SPEECH_START_CHUNKS = 2;
const SPEECH_END_CHUNKS = 6;
const PREROLL_CHUNKS = 3;
const BASE64_CHUNK_SIZE = 0x8000;
const MAX_BATCHED_AUDIO_BYTES = 64 * 1024;
const READY_TIMEOUT_MS = 10000;

type VoiceTurnState = "connecting" | "idle" | "user_speaking" | "waiting_for_agent" | "agent_speaking" | "interrupted" | "recovering";
type VoiceSessionTransport = "vertex" | "gemini_api";

interface BufferedPcmChunk {
  buffer: ArrayBuffer;
  rms: number;
}

interface TurnMessageIds {
  userId: string;
  agentId: string;
}

interface UseVoiceEditSessionArgs {
  projectId: string;
  agentPanelOpen: boolean;
  isVoiceActiveRef: MutableRefObject<boolean>;
  wsRef: MutableRefObject<WebSocket | null>;
  getCurrentCanonicalProjectJson: () => ProjectJSON | null;
  editorBridgeRef: MutableRefObject<EditorBridgeHandle | null>;
  applyLiveProjectJson: (json: ProjectJSON | null, changes?: Record<string, unknown>) => void;
  setAgentMessages: React.Dispatch<React.SetStateAction<AgentMessage[]>>;
  focusedAssetRef?: MutableRefObject<{ id: string; category: string } | null>;
  onThumbnailApplied?: (thumbnailUrl: string) => void;
}

function pcmBufferToBase64(buffer: ArrayBuffer): string {
  const bytes = new Uint8Array(buffer);
  let binary = "";

  for (let index = 0; index < bytes.length; index += BASE64_CHUNK_SIZE) {
    binary += String.fromCharCode(...bytes.subarray(index, index + BASE64_CHUNK_SIZE));
  }

  return btoa(binary);
}

function computeChunkRms(samples: Int16Array): number {
  if (samples.length === 0) return 0;

  let sumSquares = 0;
  for (let index = 0; index < samples.length; index += 1) {
    const normalized = samples[index] / 32768;
    sumSquares += normalized * normalized;
  }

  return Math.sqrt(sumSquares / samples.length);
}

export function useVoiceEditSession({
  projectId,
  agentPanelOpen,
  isVoiceActiveRef,
  wsRef,
  getCurrentCanonicalProjectJson,
  editorBridgeRef,
  applyLiveProjectJson,
  setAgentMessages,
  focusedAssetRef,
  onThumbnailApplied,
}: UseVoiceEditSessionArgs) {
  const [isVoiceActive, setIsVoiceActive] = useState(false);
  const [voiceTurnState, setVoiceTurnStateState] = useState<VoiceTurnState>("idle");
  const [currentTurnId, setCurrentTurnId] = useState<string | null>(null);
  const [isScreenShareActive, setIsScreenShareActive] = useState(false);

  const captureAudioCtxRef = useRef<AudioContext | null>(null);
  const playbackAudioCtxRef = useRef<AudioContext | null>(null);
  const playbackNodeRef = useRef<AudioWorkletNode | null>(null);
  const mediaStreamRef = useRef<MediaStream | null>(null);
  const recorderNodeRef = useRef<AudioWorkletNode | null>(null);
  const screenStreamRef = useRef<MediaStream | null>(null);
  const screenVideoRef = useRef<HTMLVideoElement | null>(null);
  const screenCanvasRef = useRef<HTMLCanvasElement | null>(null);
  const screenFrameIntervalRef = useRef<number | null>(null);

  const turnCounterRef = useRef(0);
  const currentTurnIdRef = useRef<string | null>(null);
  const currentUserMessageIdRef = useRef<string | null>(null);
  const currentAgentMessageIdRef = useRef<string | null>(null);
  const turnMessageIdsRef = useRef<Record<string, TurnMessageIds>>({});
  const voiceTurnStateRef = useRef<VoiceTurnState>("idle");
  const speechActiveRef = useRef(false);
  const speechChunkRunRef = useRef(0);
  const silenceChunkRunRef = useRef(0);
  const forwardedChunkCountRef = useRef(0);
  const preSpeechChunksRef = useRef<BufferedPcmChunk[]>([]);
  const utteranceChunksRef = useRef<BufferedPcmChunk[]>([]);
  const sessionReadyRef = useRef(false);
  const sessionFailedRef = useRef(false);
  const sessionTransportRef = useRef<VoiceSessionTransport | null>(null);
  const readyTimeoutRef = useRef<number | null>(null);
  const closingSessionRef = useRef(false);

  const setVoiceTurnState = useCallback((nextState: VoiceTurnState) => {
    voiceTurnStateRef.current = nextState;
    setVoiceTurnStateState(nextState);
  }, []);

  const resetVadState = useCallback(() => {
    speechActiveRef.current = false;
    speechChunkRunRef.current = 0;
    silenceChunkRunRef.current = 0;
    forwardedChunkCountRef.current = 0;
    preSpeechChunksRef.current = [];
    utteranceChunksRef.current = [];
  }, []);

  const clearReadyTimeout = useCallback(() => {
    if (readyTimeoutRef.current !== null) {
      window.clearTimeout(readyTimeoutRef.current);
      readyTimeoutRef.current = null;
    }
  }, []);

  const patchMessage = useCallback((messageId: string | null, updater: (message: AgentMessage) => AgentMessage) => {
    if (!messageId) return;

    setAgentMessages((previous) => {
      let found = false;
      const nextMessages = previous.map((message) => {
        if (message.id !== messageId) return message;
        found = true;
        return updater(message);
      });
      return found ? nextMessages : previous;
    });
  }, [setAgentMessages]);

  const clearActiveTurnRefs = useCallback(() => {
    currentTurnIdRef.current = null;
    currentUserMessageIdRef.current = null;
    currentAgentMessageIdRef.current = null;
    setCurrentTurnId(null);
  }, []);

  const setActiveTurnRefs = useCallback((turnId: string) => {
    const existing = turnMessageIdsRef.current[turnId];
    if (!existing) return;

    currentTurnIdRef.current = turnId;
    currentUserMessageIdRef.current = existing.userId;
    currentAgentMessageIdRef.current = existing.agentId;
    setCurrentTurnId(turnId);
  }, []);

  const finishAgentMessage = useCallback((turnId?: string | null, fallbackText?: string) => {
    const targetTurnId = turnId ?? currentTurnIdRef.current;
    const agentMessageId = targetTurnId ? turnMessageIdsRef.current[targetTurnId]?.agentId : currentAgentMessageIdRef.current;

    patchMessage(agentMessageId ?? null, (message) => ({
      ...message,
      isThinking: false,
      ...(fallbackText && !message.text ? { text: fallbackText } : {}),
    }));
  }, [patchMessage]);

  const appendAgentMessage = useCallback((message: AgentMessage) => {
    setAgentMessages((previous) => [...previous, message]);
  }, [setAgentMessages]);

  const createTurnMessages = useCallback((turnId: string) => {
    if (turnMessageIdsRef.current[turnId]) {
      return turnMessageIdsRef.current[turnId];
    }

    const ids = {
      userId: `${turnId}-user`,
      agentId: `${turnId}-agent`,
    };
    turnMessageIdsRef.current[turnId] = ids;

    setAgentMessages((previous) => ([
      ...previous,
      { id: ids.userId, role: "user", text: "Listening..." },
      { id: ids.agentId, role: "agent", text: "", isThinking: true, actions: [] },
    ]));

    return ids;
  }, [setAgentMessages]);

  const beginLocalTurn = useCallback((turnId: string) => {
    if (voiceTurnStateRef.current !== "idle") {
      finishAgentMessage(currentTurnIdRef.current);
    }

    createTurnMessages(turnId);
    setActiveTurnRefs(turnId);
  }, [createTurnMessages, finishAgentMessage, setActiveTurnRefs]);

  const ensureTurn = useCallback((turnId?: string | null, activate = true) => {
    const normalizedTurnId = turnId ?? currentTurnIdRef.current ?? `voice-turn-${Date.now()}-${++turnCounterRef.current}`;
    createTurnMessages(normalizedTurnId);

    if (activate || currentTurnIdRef.current === normalizedTurnId || currentTurnIdRef.current === null) {
      setActiveTurnRefs(normalizedTurnId);
    }

    return normalizedTurnId;
  }, [createTurnMessages, setActiveTurnRefs]);

  const appendAgentAction = useCallback((action: string, turnId?: string | null) => {
    const normalizedTurnId = ensureTurn(turnId, !turnId || currentTurnIdRef.current === turnId);
    patchMessage(turnMessageIdsRef.current[normalizedTurnId]?.agentId ?? null, (message) => ({
      ...message,
      actions: [...(message.actions ?? []), action],
    }));
  }, [ensureTurn, patchMessage]);

  const updateUserTranscript = useCallback((text: string, turnId?: string | null) => {
    const normalizedTurnId = ensureTurn(turnId, !turnId || currentTurnIdRef.current === turnId);
    patchMessage(turnMessageIdsRef.current[normalizedTurnId]?.userId ?? null, (message) => ({
      ...message,
      text: text || message.text,
    }));
  }, [ensureTurn, patchMessage]);

  const updateAgentTranscript = useCallback((text: string, turnId?: string | null) => {
    const shouldActivate = !turnId || currentTurnIdRef.current === null || currentTurnIdRef.current === turnId;
    const normalizedTurnId = ensureTurn(turnId, shouldActivate);
    if (shouldActivate) {
      setVoiceTurnState("agent_speaking");
    }
    patchMessage(turnMessageIdsRef.current[normalizedTurnId]?.agentId ?? null, (message) => ({
      ...message,
      text: text || message.text,
      isThinking: false,
    }));
  }, [ensureTurn, patchMessage, setVoiceTurnState]);

  const initPlaybackContext = useCallback(async () => {
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
  }, []);

  const queuePcmAudio = useCallback((buffer: ArrayBuffer) => {
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

    for (let index = 0; index < outputLength; index += 1) {
      const sourceIndex = index / ratio;
      const leftIndex = Math.floor(sourceIndex);
      const rightIndex = Math.min(leftIndex + 1, input.length - 1);
      const mix = sourceIndex - leftIndex;
      const left = input[leftIndex] / 32768;
      const right = input[rightIndex] / 32768;
      output[index] = left + (right - left) * mix;
    }

    node.port.postMessage({ type: "push", samples: output }, [output.buffer]);
  }, []);

  const sendBatchedAudio = useCallback((socket: WebSocket, turnId: string, chunks: BufferedPcmChunk[]) => {
    if (socket.readyState !== WebSocket.OPEN || chunks.length === 0) return;

    let currentBatch: Uint8Array[] = [];
    let currentBatchBytes = 0;

    const flushBatch = () => {
      if (currentBatch.length === 0) return;

      const merged = new Uint8Array(currentBatchBytes);
      let offset = 0;
      for (const bytes of currentBatch) {
        merged.set(bytes, offset);
        offset += bytes.byteLength;
      }

      socket.send(JSON.stringify({
        type: "audio",
        data: pcmBufferToBase64(merged.buffer),
        turn_id: turnId,
      }));

      currentBatch = [];
      currentBatchBytes = 0;
    };

    for (const chunk of chunks) {
      const bytes = new Uint8Array(chunk.buffer);
      if (currentBatchBytes + bytes.byteLength > MAX_BATCHED_AUDIO_BYTES && currentBatch.length > 0) {
        flushBatch();
      }

      currentBatch.push(bytes);
      currentBatchBytes += bytes.byteLength;
    }

    flushBatch();
  }, []);

  const sendEditorState = useCallback((socket: WebSocket) => {
    if (socket.readyState !== WebSocket.OPEN) return;

    const currentProjectJson = getCurrentCanonicalProjectJson();
    const editorContext = editorBridgeRef.current?.getEditorContext() ?? null;
    socket.send(JSON.stringify({
      type: "editor_state",
      project_json: currentProjectJson,
      editor_context: {
        ...(agentPanelOpen ? { ...editorContext, active_panel: "agent" } : editorContext),
        ...(focusedAssetRef?.current ? {
          focused_asset_id: focusedAssetRef.current.id,
          focused_asset_category: focusedAssetRef.current.category,
        } : {}),
      },
    }));
  }, [agentPanelOpen, editorBridgeRef, focusedAssetRef, getCurrentCanonicalProjectJson]);

  const initializeCapturePipeline = useCallback(async (socket: WebSocket, stream: MediaStream) => {
    await initPlaybackContext();

    const captureCtx = new AudioContext({ sampleRate: 16000 });
    captureAudioCtxRef.current = captureCtx;

    await captureCtx.audioWorklet.addModule("/audio/audio-recording-worklet.js");
    const recorderNode = new AudioWorkletNode(captureCtx, "recording-processor");
    recorderNodeRef.current = recorderNode;

    recorderNode.port.onmessage = (event: MessageEvent) => {
      if (event.data.event !== "chunk" || socket.readyState !== WebSocket.OPEN || !sessionReadyRef.current || sessionFailedRef.current) {
        return;
      }

      const int16Buffer = event.data.data.int16arrayBuffer as ArrayBuffer;
      const samples = new Int16Array(int16Buffer);
      if (samples.length === 0) return;

      const rms = computeChunkRms(samples);
      const chunk = { buffer: int16Buffer.slice(0), rms };
      const isSpeechLike = rms >= VAD_RMS_THRESHOLD;
      const isGeminiApiTransport = sessionTransportRef.current === "gemini_api";

      if (!speechActiveRef.current) {
        if (voiceTurnStateRef.current !== "idle") {
          preSpeechChunksRef.current = [];
          utteranceChunksRef.current = [];
          speechChunkRunRef.current = 0;
          silenceChunkRunRef.current = 0;
          return;
        }

        preSpeechChunksRef.current.push(chunk);
        if (preSpeechChunksRef.current.length > PREROLL_CHUNKS) {
          preSpeechChunksRef.current.shift();
        }

        speechChunkRunRef.current = isSpeechLike ? speechChunkRunRef.current + 1 : 0;
        if (speechChunkRunRef.current < SPEECH_START_CHUNKS) {
          return;
        }

        const turnId = `voice-turn-${Date.now()}-${++turnCounterRef.current}`;
        beginLocalTurn(turnId);
        setVoiceTurnState("user_speaking");
        speechActiveRef.current = true;
        silenceChunkRunRef.current = 0;
        forwardedChunkCountRef.current = preSpeechChunksRef.current.length;

        const preSpeechChunks = [...preSpeechChunksRef.current];
        preSpeechChunksRef.current = [];
        utteranceChunksRef.current = preSpeechChunks;

        if (!isGeminiApiTransport) {
          console.debug("[voice-edit] activity_start", {
            turnId,
            preRoll: preSpeechChunks.length,
            rms,
            transport: sessionTransportRef.current,
          });
          socket.send(JSON.stringify({ type: "activity_start", turn_id: turnId }));
          sendBatchedAudio(socket, turnId, preSpeechChunks);
        }
        return;
      }

      const turnId = currentTurnIdRef.current ?? ensureTurn();
      forwardedChunkCountRef.current += 1;

      if (isGeminiApiTransport) {
        utteranceChunksRef.current.push(chunk);
      } else {
        sendBatchedAudio(socket, turnId, [chunk]);
      }

      if (isSpeechLike) {
        silenceChunkRunRef.current = 0;
      } else {
        silenceChunkRunRef.current += 1;
      }

      if (silenceChunkRunRef.current >= SPEECH_END_CHUNKS) {
        console.debug("[voice-edit] activity_end", {
          turnId,
          chunks: forwardedChunkCountRef.current,
          rms,
          transport: sessionTransportRef.current,
        });
        if (isGeminiApiTransport) {
          socket.send(JSON.stringify({ type: "activity_start", turn_id: turnId }));
          sendBatchedAudio(socket, turnId, utteranceChunksRef.current);
        }
        socket.send(JSON.stringify({ type: "activity_end", turn_id: turnId }));
        speechActiveRef.current = false;
        speechChunkRunRef.current = 0;
        silenceChunkRunRef.current = 0;
        forwardedChunkCountRef.current = 0;
        preSpeechChunksRef.current = [];
        utteranceChunksRef.current = [];
        setVoiceTurnState("waiting_for_agent");
      }
    };

    captureCtx.createMediaStreamSource(stream).connect(recorderNode);
    sendEditorState(socket);
  }, [
    beginLocalTurn,
    ensureTurn,
    initPlaybackContext,
    sendBatchedAudio,
    sendEditorState,
    setVoiceTurnState,
  ]);

  const cleanupVoiceSession = useCallback((closeSocket: boolean) => {
    clearReadyTimeout();

    if (closeSocket && wsRef.current) {
      closingSessionRef.current = true;
      if (wsRef.current.readyState === WebSocket.OPEN) {
        wsRef.current.send(JSON.stringify({ type: "done" }));
      }
      if (wsRef.current.readyState === WebSocket.OPEN || wsRef.current.readyState === WebSocket.CONNECTING) {
        wsRef.current.close();
      }
    }

    wsRef.current = null;
    recorderNodeRef.current?.disconnect();
    recorderNodeRef.current = null;
    captureAudioCtxRef.current?.close().catch(() => {});
    captureAudioCtxRef.current = null;
    playbackNodeRef.current?.port.postMessage({ type: "clear" });
    playbackNodeRef.current?.disconnect();
    playbackNodeRef.current = null;
    playbackAudioCtxRef.current?.close().catch(() => {});
    playbackAudioCtxRef.current = null;
    mediaStreamRef.current?.getTracks().forEach((track) => track.stop());
    mediaStreamRef.current = null;
    // Clean up screen share
    if (screenFrameIntervalRef.current !== null) {
      window.clearInterval(screenFrameIntervalRef.current);
      screenFrameIntervalRef.current = null;
    }
    screenStreamRef.current?.getTracks().forEach((track) => track.stop());
    screenStreamRef.current = null;
    screenVideoRef.current = null;
    screenCanvasRef.current = null;
    setIsScreenShareActive(false);
    resetVadState();
    finishAgentMessage();
    clearActiveTurnRefs();
    turnMessageIdsRef.current = {};
    sessionReadyRef.current = false;
    sessionTransportRef.current = null;
    setVoiceTurnState("idle");
    setIsVoiceActive(false);
    isVoiceActiveRef.current = false;
  }, [clearActiveTurnRefs, clearReadyTimeout, finishAgentMessage, isVoiceActiveRef, resetVadState, setVoiceTurnState, wsRef]);

  const stopVoiceEdit = useCallback(() => {
    cleanupVoiceSession(true);
  }, [cleanupVoiceSession]);

  const stopScreenShare = useCallback(() => {
    const ws = wsRef.current;
    if (screenFrameIntervalRef.current !== null) {
      window.clearInterval(screenFrameIntervalRef.current);
      screenFrameIntervalRef.current = null;
    }
    screenStreamRef.current?.getTracks().forEach((track) => track.stop());
    screenStreamRef.current = null;
    screenVideoRef.current = null;
    screenCanvasRef.current = null;
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: "screen_share_end" }));
    }
    setIsScreenShareActive(false);
  }, [wsRef]);

  const inspectScreen = useCallback(() => {
    const ws = wsRef.current;
    if (!ws || ws.readyState !== WebSocket.OPEN || !isScreenShareActive) return;
    ws.send(JSON.stringify({ type: "inspect_screen" }));
  }, [wsRef, isScreenShareActive]);

  const startScreenShare = useCallback(async () => {
    const ws = wsRef.current;
    if (!ws || ws.readyState !== WebSocket.OPEN || !sessionReadyRef.current) return;

    try {
      const stream = await navigator.mediaDevices.getDisplayMedia({ video: true });
      screenStreamRef.current = stream;

      const video = document.createElement("video");
      video.srcObject = stream;
      video.muted = true;
      await video.play();
      screenVideoRef.current = video;

      const canvas = document.createElement("canvas");
      screenCanvasRef.current = canvas;

      ws.send(JSON.stringify({ type: "screen_share_start" }));
      setIsScreenShareActive(true);

      screenFrameIntervalRef.current = window.setInterval(() => {
        const currentWs = wsRef.current;
        const currentVideo = screenVideoRef.current;
        const currentCanvas = screenCanvasRef.current;
        if (
          !currentWs ||
          currentWs.readyState !== WebSocket.OPEN ||
          !currentVideo ||
          !currentCanvas ||
          currentVideo.videoWidth === 0
        ) return;

        currentCanvas.width = currentVideo.videoWidth;
        currentCanvas.height = currentVideo.videoHeight;
        const ctx = currentCanvas.getContext("2d");
        if (!ctx) return;
        ctx.drawImage(currentVideo, 0, 0);
        const dataUrl = currentCanvas.toDataURL("image/jpeg", 0.8);
        const base64 = dataUrl.split(",")[1];
        if (base64) {
          currentWs.send(JSON.stringify({ type: "screen_frame", data: base64 }));
        }
      }, 1000); // 1 FPS — Gemini Live maximum

      // Handle user stopping via browser UI (clicking the stop button in browser chrome)
      stream.getVideoTracks()[0]?.addEventListener("ended", () => {
        stopScreenShare();
      });
    } catch {
      // Permission denied or screen share cancelled — no-op
    }
  }, [wsRef, stopScreenShare]);

  const startVoiceEdit = useCallback(async () => {
    if (isVoiceActiveRef.current) {
      stopVoiceEdit();
      return;
    }

    try {
      resetVadState();
      clearActiveTurnRefs();
      turnMessageIdsRef.current = {};
      sessionReadyRef.current = false;
      sessionFailedRef.current = false;
      setVoiceTurnState("connecting");

      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          channelCount: 1,
          sampleRate: 16000,
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        },
      });
      mediaStreamRef.current = stream;

      const token = await auth.currentUser?.getIdToken();
      const ws = new WebSocket(`${WS_API}/api/v1/projects/${projectId}/edit-voice${token ? `?token=${token}` : ""}`);
      wsRef.current = ws;

      setAgentMessages((previous) => [
        ...previous,
        { id: Date.now().toString(), role: "user", text: "🎤 Voice edit started..." },
      ]);
      setIsVoiceActive(true);
      isVoiceActiveRef.current = true;

      ws.onopen = () => {
        clearReadyTimeout();
        readyTimeoutRef.current = window.setTimeout(() => {
          if (sessionReadyRef.current || sessionFailedRef.current) return;
          sessionFailedRef.current = true;
          appendAgentMessage({
            id: `${Date.now()}-voice-timeout`,
            role: "agent",
            text: "Voice edit failed to start. The live session did not become ready in time.",
            isError: true,
          });
          cleanupVoiceSession(true);
        }, READY_TIMEOUT_MS);
      };

      ws.onmessage = (messageEvent) => {
        if (typeof messageEvent.data !== "string") return;

        let data: Record<string, unknown>;
        try {
          data = JSON.parse(messageEvent.data) as Record<string, unknown>;
        } catch {
          return;
        }

        const turnId = typeof data.turn_id === "string" ? data.turn_id : null;

        if (data.type === "ready") {
          if (sessionReadyRef.current) return;
          sessionReadyRef.current = true;
          sessionTransportRef.current = data.transport === "vertex" || data.transport === "gemini_api"
            ? data.transport
            : "gemini_api";
          clearReadyTimeout();
          setVoiceTurnState("idle");
          void initializeCapturePipeline(ws, stream).catch(() => {
            sessionFailedRef.current = true;
            appendAgentMessage({
              id: `${Date.now()}-voice-init-error`,
              role: "agent",
              text: "Voice edit failed while starting the microphone pipeline.",
              isError: true,
            });
            cleanupVoiceSession(true);
          });
          return;
        }

        if (data.type === "audio") {
          try {
            const bytes = Uint8Array.from(atob(String(data.data ?? "")), (char) => char.charCodeAt(0));
            if (bytes.length > 0) {
              setVoiceTurnState("agent_speaking");
              queuePcmAudio(bytes.buffer);
            }
          } catch {
            // Ignore malformed audio frames.
          }
          return;
        }

        if (data.type === "agent_transcript") {
          updateAgentTranscript(String(data.text ?? ""), turnId);
        } else if (data.type === "user_transcript") {
          updateUserTranscript(String(data.text ?? ""), turnId);
        } else if (data.type === "generation_complete") {
          appendAgentAction("generation_complete", turnId);
          finishAgentMessage(turnId);
        } else if (data.type === "script_proposals" && data.proposals) {
          const resolvedTurnId = ensureTurn(turnId, !turnId || currentTurnIdRef.current === turnId);
          patchMessage(turnMessageIdsRef.current[resolvedTurnId]?.agentId ?? null, (message) => ({
            ...message,
            scriptProposals: data.proposals as import("@/components/editor/types").ScriptProposal[],
            isThinking: false,
          }));
        } else if (data.type === "creative_block" && data.block) {
          const resolvedTurnId = ensureTurn(turnId, !turnId || currentTurnIdRef.current === turnId);
          patchMessage(turnMessageIdsRef.current[resolvedTurnId]?.agentId ?? null, (message) => ({
            ...message,
            creativeBlocks: [...(message.creativeBlocks ?? []), data.block as CreativeBlock],
            actions: [...(message.actions ?? []), "generate_style_preview"],
            isThinking: false,
          }));
        } else if (data.type === "thumbnail_option" && data.image_b64) {
          const resolvedTurnId = ensureTurn(turnId, !turnId || currentTurnIdRef.current === turnId);
          patchMessage(turnMessageIdsRef.current[resolvedTurnId]?.agentId ?? null, (message) => ({
            ...message,
            thumbnailOptions: [
              ...(message.thumbnailOptions ?? []),
              { index: data.index as number, image_b64: data.image_b64 as string, mime_type: (data.mime_type as string) ?? "image/jpeg" },
            ],
            isThinking: false,
          }));
        } else if (data.type === "thumbnail_applied" && data.thumbnail_url) {
          onThumbnailApplied?.(data.thumbnail_url as string);
        } else if (data.type === "creative_preview_start") {
          const resolvedTurnId = ensureTurn(turnId, !turnId || currentTurnIdRef.current === turnId);
          patchMessage(turnMessageIdsRef.current[resolvedTurnId]?.agentId ?? null, (message) => ({
            ...message,
            previewOptions: [],
            previewId: data.preview_id as string,
            isThinking: false,
          }));
        } else if (data.type === "creative_preview_option" && data.image) {
          const resolvedTurnId = ensureTurn(turnId, !turnId || currentTurnIdRef.current === turnId);
          const option = {
            option_id: data.option_id as string,
            index: data.index as number,
            title: data.title as string,
            style: data.style as string,
            image: data.image as import("@/components/editor/types").CreativeBlock,
          };
          patchMessage(turnMessageIdsRef.current[resolvedTurnId]?.agentId ?? null, (message) => ({
            ...message,
            previewId: data.preview_id as string,
            previewOptions: [...(message.previewOptions ?? []), option],
            isThinking: false,
          }));
        } else if (data.type === "tool_event" || data.type === "tool_call") {
          appendAgentAction(String(data.name ?? data.tool ?? data.type), turnId);
        } else if (data.type === "proposal" && data.proposal) {
          const resolvedTurnId = ensureTurn(turnId, !turnId || currentTurnIdRef.current === turnId);
          const proposal: EditProposal = { ...(data.proposal as EditProposal), state: "pending" };
          patchMessage(turnMessageIdsRef.current[resolvedTurnId]?.agentId ?? null, (message) => ({
            ...message,
            text: proposal.summary,
            proposal,
            isThinking: false,
          }));
        } else if (data.type === "applied" || data.type === "complete") {
          const resolvedTurnId = ensureTurn(turnId, !turnId || currentTurnIdRef.current === turnId);
          patchMessage(turnMessageIdsRef.current[resolvedTurnId]?.agentId ?? null, (message) => ({
            ...message,
            isThinking: false,
            text: data.message as string ?? message.text ?? "Live edits applied.",
          }));
          if (data.project_json) {
            applyLiveProjectJson(data.project_json as ProjectJSON, data.changes as Record<string, unknown> | undefined);
          }
        } else if (data.type === "interrupted") {
          console.debug("[voice-edit] interrupted", { turnId });
          playbackNodeRef.current?.port.postMessage({ type: "clear" });
          finishAgentMessage(turnId);
          if (!turnId || currentTurnIdRef.current === turnId) {
            setVoiceTurnState("interrupted");
          }
        } else if (data.type === "session_recovering") {
          console.debug("[voice-edit] session_recovering", { turnId });
          playbackNodeRef.current?.port.postMessage({ type: "clear" });
          finishAgentMessage(turnId, "Voice session stalled. Reconnecting...");
          setVoiceTurnState("recovering");
        } else if (data.type === "session_restarted") {
          console.debug("[voice-edit] session_restarted", { transport: data.transport });
          sessionTransportRef.current = data.transport === "vertex" || data.transport === "gemini_api"
            ? data.transport
            : sessionTransportRef.current;
          resetVadState();
          clearActiveTurnRefs();
          appendAgentMessage({
            id: `${Date.now()}-voice-restarted`,
            role: "agent",
            text: "Voice session restarted. Repeat your last request.",
          });
          setVoiceTurnState("idle");
        } else if (data.type === "turn_complete") {
          console.debug("[voice-edit] turn_complete", { turnId });
          finishAgentMessage(turnId);
          if (!turnId || currentTurnIdRef.current === turnId) {
            setVoiceTurnState("idle");
            clearActiveTurnRefs();
          }
        } else if (data.type === "screen_analysis_started") {
          const msgId = `${Date.now()}-screen-analysis`;
          appendAgentMessage({
            id: msgId,
            role: "agent",
            text: "",
            isThinking: true,
            isInspection: true,
          });
          currentAgentMessageIdRef.current = msgId;
          setVoiceTurnState("agent_speaking");
        } else if (data.type === "error") {
          sessionFailedRef.current = true;
          clearReadyTimeout();
          const errorMessage = String(data.message ?? "Voice edit error");

          if (currentAgentMessageIdRef.current) {
            patchMessage(currentAgentMessageIdRef.current, (message) => ({
              ...message,
              isThinking: false,
              isError: true,
              text: errorMessage,
            }));
          } else {
            appendAgentMessage({
              id: `${Date.now()}-voice-error`,
              role: "agent",
              text: errorMessage,
              isError: true,
            });
          }

          cleanupVoiceSession(true);
        }
      };

      ws.onclose = () => {
        const wasClosingLocally = closingSessionRef.current;
        const closedBeforeReady = !wasClosingLocally && !sessionReadyRef.current && !sessionFailedRef.current;
        clearReadyTimeout();
        if (closedBeforeReady) {
          appendAgentMessage({
            id: `${Date.now()}-voice-closed`,
            role: "agent",
            text: "Voice edit ended before the live session became ready.",
            isError: true,
          });
        }
        closingSessionRef.current = false;
        cleanupVoiceSession(false);
      };
    } catch {
      cleanupVoiceSession(false);
      setAgentMessages((previous) => [
        ...previous,
        { id: Date.now().toString(), role: "agent", text: "Microphone access denied.", isError: true },
      ]);
    }
  }, [
    agentPanelOpen,
    applyLiveProjectJson,
    onThumbnailApplied,
    beginLocalTurn,
    cleanupVoiceSession,
    clearActiveTurnRefs,
    clearReadyTimeout,
    editorBridgeRef,
    ensureTurn,
    focusedAssetRef,
    getCurrentCanonicalProjectJson,
    initializeCapturePipeline,
    isVoiceActiveRef,
    patchMessage,
    projectId,
    queuePcmAudio,
    resetVadState,
    setAgentMessages,
    setVoiceTurnState,
    stopVoiceEdit,
    updateAgentTranscript,
    updateUserTranscript,
    appendAgentAction,
    appendAgentMessage,
    finishAgentMessage,
    wsRef,
  ]);

  useEffect(() => {
    return () => {
      stopVoiceEdit();
    };
  }, [stopVoiceEdit]);

  useEffect(() => {
    if (!isVoiceActive) return undefined;

    const intervalId = window.setInterval(() => {
      if (wsRef.current?.readyState !== WebSocket.OPEN || !sessionReadyRef.current) return;
      sendEditorState(wsRef.current);
    }, 1000);

    return () => window.clearInterval(intervalId);
  }, [isVoiceActive, sendEditorState, wsRef]);

  return {
    isVoiceActive,
    startVoiceEdit,
    stopVoiceEdit,
    currentTurnId,
    voiceTurnState,
    isScreenShareActive,
    startScreenShare,
    stopScreenShare,
    inspectScreen,
  };
}
