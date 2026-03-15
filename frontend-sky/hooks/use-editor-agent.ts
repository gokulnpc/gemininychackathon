"use client";

import { useCallback, useMemo, useState, type MutableRefObject } from "react";
import type { ProjectJSON } from "@twick/timeline";

import { apiFetch } from "@/lib/api";
import type { AgentMessage, EditProposal, EditorBridgeHandle } from "@/components/editor/types";

interface UseEditorAgentArgs {
  projectId: string;
  agentPanelOpen: boolean;
  isVoiceActiveRef: MutableRefObject<boolean>;
  wsRef: MutableRefObject<WebSocket | null>;
  getCurrentCanonicalProjectJson: () => ProjectJSON | null;
  editorBridgeRef: MutableRefObject<EditorBridgeHandle | null>;
  applyLiveProjectJson: (json: ProjectJSON | null, changes?: Record<string, unknown>) => void;
  focusedAssetRef?: MutableRefObject<{ id: string; category: string } | null>;
  onThumbnailApplied?: (thumbnailUrl: string) => void;
  onProjectRenamed?: (hook: string) => void;
}

const INITIAL_MESSAGES: AgentMessage[] = [
  {
    id: "welcome",
    role: "agent",
    text: "Hi! I'm your AI video editor. Describe what changes you'd like to make, or try a quick action below.",
  },
];

export function useEditorAgent({
  projectId,
  agentPanelOpen,
  isVoiceActiveRef,
  wsRef,
  getCurrentCanonicalProjectJson,
  editorBridgeRef,
  applyLiveProjectJson,
  focusedAssetRef,
  onThumbnailApplied,
  onProjectRenamed,
}: UseEditorAgentArgs) {
  const [agentMessages, setAgentMessages] = useState<AgentMessage[]>(INITIAL_MESSAGES);
  const [agentInput, setAgentInput] = useState("");
  const [agentLoading, setAgentLoading] = useState(false);
  const [undoSnapshot, setUndoSnapshot] = useState<ProjectJSON | null>(null);

  const sendAgentInstruction = useCallback(async (
    instruction: string,
    displayText?: string,
    screenshotCtx?: { image_b64: string; mime_type: string; width: number; height: number }
  ) => {
    if (!instruction.trim() || agentLoading) return;

    const userMsg: AgentMessage = { id: Date.now().toString(), role: "user", text: displayText ?? instruction };
    const thinkingId = `${Date.now()}-t`;
    const thinkingMsg: AgentMessage = {
      id: thinkingId,
      role: "agent",
      text: "",
      isThinking: true,
      actions: [],
      ...(screenshotCtx ? { isInspection: true } : {}),
    };

    setAgentMessages((prev) => [...prev, userMsg, thinkingMsg]);
    setAgentInput("");
    setAgentLoading(true);

    const currentProjectJson = getCurrentCanonicalProjectJson();
    const editorContext = editorBridgeRef.current?.getEditorContext() ?? null;

    try {
      const res = await apiFetch(`/api/v1/projects/${projectId}/edit-agent`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          instruction,
          current_project_json: currentProjectJson,
          editor_context: {
            ...(agentPanelOpen ? { ...editorContext, active_panel: "agent" } : editorContext),
            ...(focusedAssetRef?.current ? {
              focused_asset_id: focusedAssetRef.current.id,
              focused_asset_category: focusedAssetRef.current.category,
            } : {}),
            ...(screenshotCtx ? { screenshot: screenshotCtx } : {}),
          },
          mode: "plan",
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
              if (event.tool) actions.push(event.tool);
            } else if (event.type === "tool_call" && event.tool) {
              actions.push(event.tool);
            } else if (event.type === "tool_event" && event.name) {
              actions.push(event.name);
            } else if (event.type === "script_proposals" && event.proposals) {
              setAgentMessages((prev) =>
                prev.map((message) =>
                  message.id === thinkingId
                    ? { ...message, scriptProposals: event.proposals as import("@/components/editor/types").ScriptProposal[], isThinking: false }
                    : message,
                ),
              );
            } else if (event.type === "creative_block" && event.block) {
              setAgentMessages((prev) =>
                prev.map((message) =>
                  message.id === thinkingId
                    ? { ...message, creativeBlocks: [...(message.creativeBlocks ?? []), event.block as import("@/components/editor/types").CreativeBlock] }
                    : message,
                ),
              );
            } else if (event.type === "thumbnail_option" && event.image_b64) {
              const opt = { index: event.index as number, image_b64: event.image_b64 as string, mime_type: (event.mime_type as string) ?? "image/jpeg" };
              setAgentMessages((prev) =>
                prev.map((message) =>
                  message.id === thinkingId
                    ? { ...message, thumbnailOptions: [...(message.thumbnailOptions ?? []), opt] }
                    : message,
                ),
              );
            } else if (event.type === "thumbnail_applied" && event.thumbnail_url) {
              onThumbnailApplied?.(event.thumbnail_url as string);
            } else if (event.type === "creative_preview_start") {
              setAgentMessages((prev) =>
                prev.map((message) =>
                  message.id === thinkingId
                    ? { ...message, previewOptions: [], previewId: event.preview_id as string }
                    : message,
                ),
              );
            } else if (event.type === "creative_preview_option" && event.image) {
              const opt = {
                option_id: event.option_id as string,
                index: event.index as number,
                title: event.title as string,
                style: event.style as string,
                image: event.image as import("@/components/editor/types").CreativeBlock,
              };
              setAgentMessages((prev) =>
                prev.map((message) =>
                  message.id === thinkingId
                    ? {
                        ...message,
                        previewId: event.preview_id as string,
                        previewOptions: [...(message.previewOptions ?? []), opt],
                      }
                    : message,
                ),
              );
            } else if (event.type === "proposal" && event.proposal) {
              const proposal: EditProposal = { ...event.proposal as EditProposal, state: "pending" };
              agentText = proposal.summary;
              setAgentMessages((prev) =>
                prev.map((message) =>
                  message.id === thinkingId
                    ? { ...message, text: agentText, actions: [...actions], proposal, isThinking: false }
                    : message,
                ),
              );
            } else if (event.type === "project_renamed" && event.hook) {
              onProjectRenamed?.(event.hook as string);
            } else if (event.type === "complete") {
              if (event.message) agentText = event.message as string;
              if (event.project_json) {
                applyLiveProjectJson(event.project_json as ProjectJSON, event.changes as Record<string, unknown> | undefined);
              }
            } else if (event.type === "lyria_generating") {
              agentText = "Generating your AI music...";
              setAgentMessages((prev) =>
                prev.map((m) =>
                  m.id === thinkingId
                    ? { ...m, isLyriaGenerating: true, text: agentText, isThinking: true }
                    : m
                )
              );
            } else if (event.type === "lyria_ready") {
              setAgentMessages((prev) =>
                prev.map((m) =>
                  m.id === thinkingId
                    ? { ...m, isLyriaGenerating: false, lyriaPreviewUrl: event.url as string }
                    : m
                )
              );
            } else if (event.type === "error") {
              agentText = event.message ?? "Something went wrong.";
            }

            setAgentMessages((prev) =>
              prev.map((message) =>
                message.id === thinkingId
                  ? {
                      ...message,
                      text: agentText,
                      actions: [...actions],
                      isThinking: !["proposal", "complete", "error", "agent_text"].includes(event.type as string),
                    }
                  : message,
              ),
            );
          } catch {
            // Skip malformed SSE events.
          }
        }
      }
    } catch (error) {
      setAgentMessages((prev) =>
        prev.map((message) =>
          message.id === thinkingId
            ? {
                ...message,
                text: error instanceof Error ? error.message : "Request failed",
                isThinking: false,
                isError: true,
              }
            : message,
        ),
      );
    } finally {
      setAgentLoading(false);
    }
  }, [
    agentLoading,
    agentPanelOpen,
    applyLiveProjectJson,
    editorBridgeRef,
    getCurrentCanonicalProjectJson,
    projectId,
  ]);

  const confirmProposal = useCallback(async (proposal: EditProposal) => {
    setUndoSnapshot(getCurrentCanonicalProjectJson());

    setAgentMessages((prev) =>
      prev.map((message) =>
        message.proposal?.proposal_id === proposal.proposal_id
          ? { ...message, proposal: { ...message.proposal, state: "confirmed" as const } }
          : message,
      ),
    );

    if (isVoiceActiveRef.current && wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({
        type: "agent_decision",
        decision: "confirm",
        proposal_id: proposal.proposal_id,
        commands: proposal.commands,
      }));
      return;
    }

    setAgentLoading(true);
    const currentProjectJson = getCurrentCanonicalProjectJson();
    const editorContext = editorBridgeRef.current?.getEditorContext() ?? null;
    const applyMsgId = `${proposal.proposal_id}-apply`;

    setAgentMessages((prev) => [
      ...prev,
      { id: applyMsgId, role: "agent", text: "", isThinking: true, actions: [] },
    ]);

    try {
      const res = await apiFetch(`/api/v1/projects/${projectId}/edit-agent`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          instruction: proposal.summary,
          current_project_json: currentProjectJson,
          editor_context: {
            ...(agentPanelOpen ? { ...editorContext, active_panel: "agent" } : editorContext),
            ...(focusedAssetRef?.current ? {
              focused_asset_id: focusedAssetRef.current.id,
              focused_asset_category: focusedAssetRef.current.category,
            } : {}),
          },
          mode: "apply",
          commands: proposal.commands,
        }),
      });

      if (!res.ok || !res.body) throw new Error(`HTTP ${res.status}`);

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let applyBuffer = "";
      let applyText = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        applyBuffer += decoder.decode(value, { stream: true });
        const lines = applyBuffer.split("\n");
        applyBuffer = lines.pop() ?? "";

        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          try {
            const event = JSON.parse(line.slice(6));
            if (event.type === "applied" || event.type === "complete") {
              applyText = event.message ?? "Changes applied.";
              if (event.project_json) {
                applyLiveProjectJson(event.project_json as ProjectJSON, event.changes as Record<string, unknown>);
              }
            } else if (event.type === "error") {
              applyText = event.message ?? "Apply failed.";
              setUndoSnapshot(null);
            }
            setAgentMessages((prev) =>
              prev.map((message) =>
                message.id === applyMsgId
                  ? {
                      ...message,
                      text: applyText,
                      isThinking: event.type !== "applied" && event.type !== "complete" && event.type !== "error",
                      isError: event.type === "error",
                    }
                  : message,
              ),
            );
          } catch {
            // Skip malformed SSE events.
          }
        }
      }
    } catch (error) {
      setAgentMessages((prev) =>
        prev.map((message) =>
          message.id === applyMsgId
            ? {
                ...message,
                isThinking: false,
                isError: true,
                text: error instanceof Error ? error.message : "Apply failed",
              }
            : message,
        ),
      );
      setUndoSnapshot(null);
    } finally {
      setAgentLoading(false);
    }
  }, [
    agentPanelOpen,
    applyLiveProjectJson,
    editorBridgeRef,
    getCurrentCanonicalProjectJson,
    isVoiceActiveRef,
    projectId,
    wsRef,
  ]);

  const rejectProposal = useCallback((proposal: EditProposal) => {
    setAgentMessages((prev) =>
      prev.map((message) =>
        message.proposal?.proposal_id === proposal.proposal_id
          ? { ...message, proposal: { ...message.proposal, state: "rejected" as const } }
          : message,
      ),
    );
    if (isVoiceActiveRef.current && wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({
        type: "agent_decision",
        decision: "reject",
        proposal_id: proposal.proposal_id,
        commands: [],
      }));
    }
  }, [isVoiceActiveRef, wsRef]);

  const revertLastEdit = useCallback(() => {
    if (!undoSnapshot) return;
    applyLiveProjectJson(undoSnapshot);
    setUndoSnapshot(null);
  }, [applyLiveProjectJson, undoSnapshot]);

  return useMemo(() => ({
    agentMessages,
    agentInput,
    agentLoading,
    setAgentMessages,
    setAgentInput,
    sendAgentInstruction,
    confirmProposal,
    rejectProposal,
    revertLastEdit,
    hasUndo: undoSnapshot !== null,
  }), [
    agentInput,
    agentLoading,
    agentMessages,
    confirmProposal,
    rejectProposal,
    revertLastEdit,
    sendAgentInstruction,
    undoSnapshot,
  ]);
}
