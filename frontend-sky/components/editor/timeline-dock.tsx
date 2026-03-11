"use client";

import { useCallback, useState } from "react";
import { PLAYER_STATE, PlayerControls, TimelineManager, usePlayerControl, useTimelineControl } from "@twick/studio";
import { useTimelineContext } from "@twick/timeline";
import { useLivePlayerContext } from "@twick/live-player";

const formatSeconds = (seconds: number | null | undefined): string => {
  if (typeof seconds !== "number" || Number.isNaN(seconds)) return "--:--";
  const minutes = Math.floor(seconds / 60);
  const remainingSeconds = Math.floor(seconds % 60);
  return `${minutes.toString().padStart(2, "0")}:${remainingSeconds.toString().padStart(2, "0")}`;
};

const isTimelineElement = (selectedItem: unknown): boolean => {
  if (!selectedItem || typeof selectedItem !== "object") return false;
  return "getStartTime" in selectedItem && typeof selectedItem.getStartTime === "function";
};

export function TimelineDock() {
  const {
    selectedItem,
    selectedIds,
    totalDuration,
    canUndo,
    canRedo,
    followPlayheadEnabled,
    setFollowPlayheadEnabled,
  } = useTimelineContext();
  const livePlayer = useLivePlayerContext() as {
    currentTime?: number;
    playerState?: keyof typeof PLAYER_STATE;
    setCurrentTime?: (time: number) => void;
  } | null;
  const { togglePlayback } = usePlayerControl();
  const { deleteItem, splitElement, handleUndo, handleRedo } = useTimelineControl();
  const [trackZoom, setTrackZoom] = useState(1.15);

  const onDelete = useCallback(() => {
    deleteItem(selectedItem ?? undefined);
  }, [deleteItem, selectedItem]);

  const onSplit = useCallback(() => {
    if (!isTimelineElement(selectedItem)) return;
    splitElement(selectedItem as never, livePlayer?.currentTime ?? 0);
  }, [livePlayer?.currentTime, selectedItem, splitElement]);

  const seekTo = useCallback((time: number) => {
    livePlayer?.setCurrentTime?.(time);
  }, [livePlayer]);

  return (
    <div className="flex shrink-0 flex-col border-t border-editor-border bg-editor-panel" style={{ height: "300px" }}>
      {/* Timeline header */}
      <div className="shrink-0 border-b border-editor-border bg-editor-card px-4 py-1.5">
        <p className="text-sm font-semibold text-editor-text">Timeline</p>
        <p className="text-xs text-editor-text-muted">
          {selectedIds.size > 0 ? `${selectedIds.size} selected` : "No selection"} · duration {formatSeconds(totalDuration)}
        </p>
      </div>

      {/* Control bar */}
      <div className="shrink-0 border-b border-editor-border bg-editor-card-strong px-3 py-1">
        <PlayerControls
          selectedItem={selectedItem}
          selectedIds={selectedIds}
          currentTime={livePlayer?.currentTime ?? 0}
          duration={totalDuration}
          canUndo={canUndo}
          canRedo={canRedo}
          playerState={(livePlayer?.playerState ?? "PAUSED") as keyof typeof PLAYER_STATE}
          togglePlayback={togglePlayback}
          onUndo={handleUndo}
          onRedo={handleRedo}
          onDelete={onDelete}
          onSplit={isTimelineElement(selectedItem) ? (() => onSplit()) : undefined}
          zoomLevel={trackZoom}
          setZoomLevel={setTrackZoom}
          onSeek={seekTo}
          followPlayheadEnabled={followPlayheadEnabled}
          onFollowPlayheadToggle={() => setFollowPlayheadEnabled(!followPlayheadEnabled)}
          fps={30}
        />
      </div>

      {/* Track editor */}
      <div className="min-h-0 flex-1 overflow-y-auto bg-editor-surface">
        <TimelineManager trackZoom={trackZoom} />
      </div>
    </div>
  );
}
