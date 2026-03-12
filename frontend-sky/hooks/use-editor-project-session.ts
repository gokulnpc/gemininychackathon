"use client";

import { useCallback, useEffect, useMemo, useRef, useState, type RefObject } from "react";
import type { ProjectJSON } from "@twick/timeline";

import apiClient from "@/lib/apiClient";
import type { EditorProjectSession, PlaybackWarning } from "@/components/editor/types";
import { buildEditorProjectSession, serializeProjectJsonForPersistence } from "@/components/editor/project-session";

export function useEditorProjectSession(
  projectId: string,
  editorRootRef: RefObject<HTMLDivElement | null>,
  onCanonicalProjectChange?: (projectJson: ProjectJSON) => void,
) {
  const [editorProjectJson, setEditorProjectJson] = useState<ProjectJSON | null>(null);
  const [playbackWarnings, setPlaybackWarnings] = useState<PlaybackWarning[]>([]);
  const [saveState, setSaveState] = useState<"saved" | "saving" | "error">("saved");
  const [lastSavedAt, setLastSavedAt] = useState<Date | null>(null);
  const editorSessionRef = useRef<EditorProjectSession | null>(null);
  const persistTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

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
    onCanonicalProjectChange?.(canonical);
    saveTimelineDebounced(canonical);
  }, [applyEditorSession, onCanonicalProjectChange, saveTimelineDebounced, serializeProjectJson]);

  useEffect(() => {
    const root = editorRootRef.current;
    if (!root) return;

    const logMediaEvent = (event: Event) => {
      const target = event.target;
      if (!(target instanceof HTMLMediaElement || target instanceof HTMLImageElement)) {
        return;
      }

      const src = target.currentSrc || target.src;
      const linkedElements = src ? (editorSessionRef.current?.mediaIndexByEditorSrc[src] ?? []) : [];

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
              warning.elementId === elementRef.elementId && warning.reason === "Browser reported a media load error.",
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
  }, [editorRootRef]);

  useEffect(() => {
    return () => {
      if (persistTimeoutRef.current) {
        clearTimeout(persistTimeoutRef.current);
      }
    };
  }, []);

  const saveStateLabel = useMemo(() => (
    saveState === "saving"
      ? "Saving..."
      : saveState === "error"
        ? "Save failed"
        : lastSavedAt
          ? `Saved ${lastSavedAt.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}`
          : "Saved"
  ), [lastSavedAt, saveState]);

  return {
    editorProjectJson,
    playbackWarnings,
    saveState,
    saveStateLabel,
    applyEditorSession,
    serializeProjectJson,
    syncProjectJson,
    saveTimelineDebounced,
  };
}
