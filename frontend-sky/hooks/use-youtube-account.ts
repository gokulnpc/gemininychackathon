"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import apiClient from "@/lib/apiClient";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const YOUTUBE_CALLBACK_URL = `${API_BASE}/api/v1/auth/youtube/callback`;

export type SocialAuthStatus = {
  youtube: boolean;
  instagram: boolean;
  tiktok: boolean;
};

const DEFAULT_STATUS: SocialAuthStatus = {
  youtube: false,
  instagram: false,
  tiktok: false,
};

export function useYoutubeAccount() {
  const [authStatus, setAuthStatus] = useState<SocialAuthStatus>(DEFAULT_STATUS);
  const [youtubeConnecting, setYoutubeConnecting] = useState(false);
  const [youtubeDisconnecting, setYoutubeDisconnecting] = useState(false);
  const popupRef = useRef<Window | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const clearPendingPopup = useCallback(() => {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
    if (popupRef.current && !popupRef.current.closed) {
      popupRef.current.close();
    }
    popupRef.current = null;
  }, []);

  useEffect(() => {
    return () => {
      clearPendingPopup();
    };
  }, [clearPendingPopup]);

  const refreshStatus = useCallback(async () => {
    const status = await apiClient
      .get<SocialAuthStatus>("/api/v1/auth/status")
      .then((response) => response.data);
    setAuthStatus(status);
    return status;
  }, []);

  useEffect(() => {
    refreshStatus().catch(() => {
      // Non-fatal: the page can still render while auth status is unavailable.
    });
  }, [refreshStatus]);

  const connectYouTube = useCallback(async () => {
    setYoutubeConnecting(true);

    try {
      const { auth_url } = await apiClient
        .get<{ auth_url: string }>("/api/v1/auth/youtube", {
          params: { redirect_uri: YOUTUBE_CALLBACK_URL },
        })
        .then((response) => response.data);

      const popup = window.open(
        auth_url,
        "youtube-auth",
        "width=520,height=640,left=200,top=100",
      );
      if (!popup) {
        throw new Error("Popup blocked");
      }

      popupRef.current = popup;

      return await new Promise<boolean>((resolve) => {
        pollRef.current = setInterval(async () => {
          if (popup.closed) {
            clearPendingPopup();
            setYoutubeConnecting(false);
            resolve(false);
            return;
          }

          try {
            const nextStatus = await refreshStatus();
            if (nextStatus.youtube) {
              clearPendingPopup();
              setYoutubeConnecting(false);
              resolve(true);
            }
          } catch {
            // Ignore transient polling failures while the popup flow is in progress.
          }
        }, 2000);
      });
    } catch (error) {
      clearPendingPopup();
      setYoutubeConnecting(false);
      throw error;
    }
  }, [clearPendingPopup, refreshStatus]);

  const disconnectYouTube = useCallback(async () => {
    setYoutubeDisconnecting(true);
    try {
      await apiClient.delete("/api/v1/auth/youtube");
      const nextStatus = await refreshStatus();
      return nextStatus;
    } finally {
      setYoutubeDisconnecting(false);
    }
  }, [refreshStatus]);

  return {
    authStatus,
    refreshStatus,
    youtubeConnected: authStatus.youtube,
    youtubeConnecting,
    youtubeDisconnecting,
    connectYouTube,
    disconnectYouTube,
  };
}
