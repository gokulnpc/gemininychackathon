"use client";

import type { ProjectJSON } from "@twick/timeline";

import type {
  EditorProjectSession,
  MediaTransformRecord,
  PlaybackWarning,
  TimelineElementJson,
  TimelineTrackJson,
} from "@/components/editor/types";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const ABSOLUTE_SRC_PATTERN = /^(?:[a-z]+:)?\/\//i;
const DATA_OR_BLOB_SRC_PATTERN = /^(?:data:|blob:)/i;
const GS_MEDIA_SRC_PATTERN = /^gs:\/\/([^/]+)\/(.+)$/i;

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

export const buildEditorProjectSession = (json: ProjectJSON | null): EditorProjectSession | null => {
  if (!json) {
    return null;
  }

  const canonicalMediaByElementId: Record<string, MediaTransformRecord> = {};
  const skippedElementsByTrackId: EditorProjectSession["skippedElementsByTrackId"] = {};
  const playbackWarnings: PlaybackWarning[] = [];
  const mediaIndexByEditorSrc: EditorProjectSession["mediaIndexByEditorSrc"] = {};

  const editorTracks = (json.tracks ?? []).map((track) => {
    const editorTrack = cloneTimelineTrack(track);
    const nextElements: TimelineElementJson[] = [];

    for (const [index, rawElement] of (editorTrack.elements ?? []).entries()) {
      const element = cloneTimelineElement(rawElement);
      const props = typeof element.props === "object" && element.props ? { ...element.props } : {};
      const src = typeof props.src === "string" ? props.src : null;
      const shouldForceContain = isSceneImageElement(element);
      const canonicalElementObjectFit = typeof element.objectFit === "string" ? element.objectFit : null;
      const canonicalPropsObjectFit = typeof props.objectFit === "string" ? props.objectFit : null;

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

  restored.props = props;
  return restored;
};

export const serializeProjectJsonForPersistence = (
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
        restoreCanonicalElement(element, canonicalMediaByElementId[element.id]),
      );
      const mergedElements = [...restoredElements];

      for (const skipped of (skippedElementsByTrackId[track.id] ?? []).sort((left, right) => left.index - right.index)) {
        mergedElements.splice(Math.min(skipped.index, mergedElements.length), 0, cloneTimelineElement(skipped.element));
      }

      return {
        ...track,
        elements: mergedElements,
      };
    }),
  };
};
