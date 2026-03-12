"use client";

import { useCallback, useMemo } from "react";
import { Trash2 } from "lucide-react";
import { useLivePlayerContext } from "@twick/live-player";
import { TextElement, TRACK_TYPES, useTimelineContext } from "@twick/timeline";

interface CaptionPanelProps {
  agentLoading: boolean;
}

export function CaptionPanel({ agentLoading }: CaptionPanelProps) {
  const { editor, present } = useTimelineContext();
  const { currentTime } = useLivePlayerContext();

  const captionElements = useMemo(() => {
    const tracks = present?.tracks ?? [];
    const items: {
      trackId: string;
      elementId: string;
      text: string;
      start: number;
      end: number;
      type: string;
    }[] = [];

    for (const track of tracks) {
      for (const el of track.elements ?? []) {
        if (el.type === "text" || el.type === "caption") {
          const props = (el as unknown as { props?: Record<string, unknown> }).props ?? {};
          items.push({
            trackId: track.id,
            elementId: el.id,
            text: (props.text as string) ?? (el as unknown as { t?: string }).t ?? (el as unknown as { name?: string }).name ?? "",
            start: (el as unknown as { s?: number }).s ?? (el as unknown as { start?: number }).start ?? 0,
            end: (el as unknown as { e?: number }).e ?? (el as unknown as { end?: number }).end ?? 0,
            type: el.type,
          });
        }
      }
    }

    return items.sort((a, b) => a.start - b.start);
  }, [present]);

  const formatTime = (seconds: number) => {
    const minutes = Math.floor(seconds / 60);
    const remainingSeconds = Math.floor(seconds % 60);
    return `${minutes}:${remainingSeconds.toString().padStart(2, "0")}`;
  };

  const handleUpdateText = useCallback(
    (trackId: string, elementId: string, newText: string) => {
      void trackId;
      try {
        editor.updateElements([{ elementId, updates: { props: { text: newText } } }]);
      } catch (error) {
        console.error("[CaptionPanel] Failed to update element:", error);
      }
    },
    [editor]
  );

  const handleRemove = useCallback(
    (elementId: string) => {
      try {
        editor.removeElements([elementId]);
      } catch (error) {
        console.error("[CaptionPanel] Failed to remove element:", error);
      }
    },
    [editor]
  );

  const handleAdd = useCallback(async () => {
    try {
      const playhead = currentTime ?? 0;
      const element = new TextElement("New caption");
      element.setStart(playhead);
      element.setEnd(playhead + 3);
      const track = editor.addTrack("Caption", TRACK_TYPES.ELEMENT);
      await editor.addElementToTrack(track, element);
    } catch (error) {
      console.error("[CaptionPanel] Failed to add caption:", error);
    }
  }, [currentTime, editor]);

  return (
    <div className="space-y-3">
      {captionElements.length === 0 && (
        <p className="py-4 text-center text-xs text-editor-text-muted">No captions on the timeline yet.</p>
      )}

      {captionElements.map((caption) => (
        <div key={caption.elementId} className="space-y-2">
          <input
            type="text"
            value={caption.text}
            onChange={(event) => handleUpdateText(caption.trackId, caption.elementId, event.target.value)}
            placeholder="Caption text..."
            className="w-full rounded-xl border border-editor-border bg-editor-card px-3 py-2.5 text-sm text-foreground placeholder:text-muted-foreground focus:border-primary/50 focus:outline-none focus:ring-1 focus:ring-primary/30"
          />
          <div className="flex items-center justify-between">
            <span className="text-[10px] text-editor-text-dim">
              {formatTime(caption.start)} - {formatTime(caption.end)}
            </span>
            <button
              type="button"
              onClick={() => handleRemove(caption.elementId)}
              className="flex h-8 w-8 items-center justify-center rounded-lg border border-editor-border bg-editor-control text-red-400/70 transition hover:bg-editor-control-hover hover:text-red-400"
              title="Delete"
            >
              <Trash2 className="h-3.5 w-3.5" />
            </button>
          </div>
        </div>
      ))}

      <button
        type="button"
        onClick={() => void handleAdd()}
        disabled={agentLoading}
        className="w-full rounded-xl bg-primary py-2.5 text-sm font-semibold text-primary-foreground shadow-sm transition hover:bg-primary/90 disabled:opacity-40"
      >
        Add
      </button>
    </div>
  );
}
