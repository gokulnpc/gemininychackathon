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
    <div className="flex h-full min-h-[320px] flex-col border-t border-white/10 bg-[#0b0e14]">
      <div className="flex items-center justify-between border-b border-white/10 px-4 py-3">
        <div>
          <p className="text-sm font-semibold text-white">Timeline Dock</p>
          <p className="text-xs text-white/45">
            {selectedIds.size > 0 ? `${selectedIds.size} selected` : "No selection"} · duration {formatSeconds(totalDuration)}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => setTrackZoom((value) => Math.max(0.5, Number((value - 0.1).toFixed(2))))}
            className="rounded-lg border border-white/10 bg-white/5 px-2 py-1 text-xs text-white/75 transition hover:bg-white/10"
          >
            Zoom -
          </button>
          <button
            type="button"
            onClick={() => setTrackZoom((value) => Math.min(3, Number((value + 0.1).toFixed(2))))}
            className="rounded-lg border border-white/10 bg-white/5 px-2 py-1 text-xs text-white/75 transition hover:bg-white/10"
          >
            Zoom +
          </button>
        </div>
      </div>

      <div className="border-b border-white/10 bg-white/[0.02] px-3 py-2">
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

      <div className="min-h-0 flex-1 overflow-hidden">
        <TimelineManager trackZoom={trackZoom} />
      </div>
    </div>
  );
}
