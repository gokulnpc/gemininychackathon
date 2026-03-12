"use client";

import { useEffect, useRef } from "react";
import { useTimelineContext } from "@twick/timeline";
import { PLAYER_STATE, useLivePlayerContext } from "@twick/live-player";

const REFRESH_STALL_TIMEOUT_MS = 8000;

export function PlaybackDebugBridge() {
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

  useEffect(() => () => {
    if (refreshTimeoutRef.current) {
      clearTimeout(refreshTimeoutRef.current);
    }
  }, []);

  return null;
}
