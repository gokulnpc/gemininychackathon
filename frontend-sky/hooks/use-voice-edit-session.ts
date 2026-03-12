"use client";

import { useCallback, useEffect, useRef, useState, type MutableRefObject } from "react";
import type { ProjectJSON } from "@twick/timeline";

import { auth } from "@/lib/firebase";
import type { AgentMessage, EditProposal, EditorBridgeHandle } from "@/components/editor/types";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const WS_API = API.replace(/^http/, "ws");

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
}: UseVoiceEditSessionArgs) {
  const [isVoiceActive, setIsVoiceActive] = useState(false);
  const captureAudioCtxRef = useRef<AudioContext | null>(null);
  const playbackAudioCtxRef = useRef<AudioContext | null>(null);
  const playbackNodeRef = useRef<AudioWorkletNode | null>(null);
  const mediaStreamRef = useRef<MediaStream | null>(null);
  const processorRef = useRef<ScriptProcessorNode | null>(null);
  const mediaSourceRef = useRef<MediaStreamAudioSourceNode | null>(null);

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

    for (let i = 0; i < outputLength; i += 1) {
      const sourceIndex = i / ratio;
      const leftIndex = Math.floor(sourceIndex);
      const rightIndex = Math.min(leftIndex + 1, input.length - 1);
      const mix = sourceIndex - leftIndex;
      const left = input[leftIndex] / 32768;
      const right = input[rightIndex] / 32768;
      output[i] = left + (right - left) * mix;
    }

    node.port.postMessage({ type: "push", samples: output }, [output.buffer]);
  }, []);

  const stopVoiceEdit = useCallback(() => {
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
    mediaStreamRef.current?.getTracks().forEach((track) => track.stop());
    mediaStreamRef.current = null;
    setIsVoiceActive(false);
    isVoiceActiveRef.current = false;
  }, [isVoiceActiveRef]);

  const startVoiceEdit = useCallback(async () => {
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

      const voiceMsgId = `${Date.now()}-v`;
      setAgentMessages((prev) => [
        ...prev,
        { id: Date.now().toString(), role: "user", text: "🎤 Voice edit started..." },
        { id: voiceMsgId, role: "agent", text: "", isThinking: true, actions: [] },
      ]);
      setIsVoiceActive(true);
      isVoiceActiveRef.current = true;

      ws.onopen = () => {
        void initPlaybackContext();
        const audioCtx = new AudioContext({ sampleRate: 16000 });
        captureAudioCtxRef.current = audioCtx;
        const source = audioCtx.createMediaStreamSource(stream);
        mediaSourceRef.current = source;
        const processor = audioCtx.createScriptProcessor(4096, 1, 1);
        processorRef.current = processor;

        processor.onaudioprocess = (event) => {
          if (ws.readyState !== WebSocket.OPEN) return;
          const float32 = event.inputBuffer.getChannelData(0);
          const int16 = new Int16Array(float32.length);
          for (let i = 0; i < float32.length; i += 1) {
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
          editor_context: {
            ...(agentPanelOpen ? { ...editorContext, active_panel: "agent" } : editorContext),
            ...(focusedAssetRef?.current ? {
              focused_asset_id: focusedAssetRef.current.id,
              focused_asset_category: focusedAssetRef.current.category,
            } : {}),
          },
        }));
      };

      ws.onmessage = (messageEvent) => {
        if (messageEvent.data instanceof Blob) {
          messageEvent.data.arrayBuffer().then((buffer) => {
            queuePcmAudio(buffer);
          });
          return;
        }

        try {
          const data = JSON.parse(messageEvent.data);
          if (data.type === "agent_transcript") {
            setAgentMessages((prev) =>
              prev.map((message) =>
                message.id === voiceMsgId ? { ...message, text: data.text ?? message.text } : message,
              ),
            );
          } else if (data.type === "user_transcript") {
            setAgentMessages((prev) => {
              const userMessageId = `${voiceMsgId}-user`;
              const existing = prev.find((message) => message.id === userMessageId);
              if (existing) {
                return prev.map((message) =>
                  message.id === userMessageId ? { ...message, text: data.text ?? message.text } : message,
                );
              }
              return [...prev, { id: userMessageId, role: "user", text: data.text ?? "" }];
            });
          } else if (data.type === "creative_block" && data.block) {
            setAgentMessages((prev) =>
              prev.map((message) =>
                message.id === voiceMsgId
                  ? {
                      ...message,
                      creativeBlocks: [...(message.creativeBlocks ?? []), data.block as import("@/components/editor/types").CreativeBlock],
                      actions: [...(message.actions ?? []), "generate_style_preview"],
                    }
                  : message,
              ),
            );
          } else if (data.type === "creative_preview_start") {
            setAgentMessages((prev) =>
              prev.map((message) =>
                message.id === voiceMsgId
                  ? { ...message, previewOptions: [], previewId: data.preview_id as string }
                  : message,
              ),
            );
          } else if (data.type === "creative_preview_option" && data.image) {
            const opt = {
              option_id: data.option_id as string,
              index: data.index as number,
              title: data.title as string,
              style: data.style as string,
              image: data.image as import("@/components/editor/types").CreativeBlock,
            };
            setAgentMessages((prev) =>
              prev.map((message) =>
                message.id === voiceMsgId
                  ? {
                      ...message,
                      previewId: data.preview_id as string,
                      previewOptions: [...(message.previewOptions ?? []), opt],
                    }
                  : message,
              ),
            );
          } else if (data.type === "tool_event" || data.type === "tool_call") {
            const tool = (data.name ?? data.tool ?? data.type) as string;
            setAgentMessages((prev) =>
              prev.map((message) =>
                message.id === voiceMsgId
                  ? { ...message, actions: [...(message.actions ?? []), tool] }
                  : message,
              ),
            );
          } else if (data.type === "proposal" && data.proposal) {
            const proposal: EditProposal = { ...(data.proposal as EditProposal), state: "pending" };
            setAgentMessages((prev) =>
              prev.map((message) =>
                message.id === voiceMsgId
                  ? { ...message, text: proposal.summary, proposal, isThinking: false }
                  : message,
              ),
            );
          } else if (data.type === "applied" || data.type === "complete") {
            setAgentMessages((prev) =>
              prev.map((message) =>
                message.id === voiceMsgId
                  ? { ...message, isThinking: false, text: data.message ?? "Live edits applied." }
                  : message,
              ),
            );
            if (data.project_json) {
              applyLiveProjectJson(data.project_json as ProjectJSON, data.changes as Record<string, unknown> | undefined);
            }
          } else if (data.type === "interrupted") {
            playbackNodeRef.current?.port.postMessage({ type: "clear" });
          } else if (data.type === "error") {
            setAgentMessages((prev) =>
              prev.map((message) =>
                message.id === voiceMsgId
                  ? { ...message, isThinking: false, isError: true, text: data.message ?? "Voice edit error" }
                  : message,
              ),
            );
            stopVoiceEdit();
          }
        } catch {
          // Binary payloads handled above.
        }
      };

      ws.onclose = () => {
        stopVoiceEdit();
      };
    } catch {
      setAgentMessages((prev) => [
        ...prev,
        { id: Date.now().toString(), role: "agent", text: "Microphone access denied.", isError: true },
      ]);
    }
  }, [
    agentPanelOpen,
    applyLiveProjectJson,
    editorBridgeRef,
    getCurrentCanonicalProjectJson,
    initPlaybackContext,
    isVoiceActive,
    isVoiceActiveRef,
    projectId,
    queuePcmAudio,
    setAgentMessages,
    stopVoiceEdit,
  ]);

  useEffect(() => {
    return () => {
      stopVoiceEdit();
    };
  }, [stopVoiceEdit]);

  useEffect(() => {
    if (!isVoiceActive) return undefined;

    const intervalId = window.setInterval(() => {
      if (wsRef.current?.readyState !== WebSocket.OPEN) return;
      const currentProjectJson = getCurrentCanonicalProjectJson();
      const editorContext = editorBridgeRef.current?.getEditorContext() ?? null;
      wsRef.current.send(JSON.stringify({
        type: "editor_state",
        project_json: currentProjectJson,
        editor_context: agentPanelOpen ? { ...editorContext, active_panel: "agent" } : editorContext,
      }));
    }, 1000);

    return () => window.clearInterval(intervalId);
  }, [agentPanelOpen, editorBridgeRef, getCurrentCanonicalProjectJson, isVoiceActive]);

  return {
    isVoiceActive,
    startVoiceEdit,
    stopVoiceEdit,
  };
}
