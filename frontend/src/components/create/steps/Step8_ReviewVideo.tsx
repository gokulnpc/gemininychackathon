"use client";

import {
  Download,
  ArrowRight,
  Sparkles,
  Pause,
  Play,
  Plus,
  X,
  CheckCircle2,
  Loader2,
  ExternalLink,
  AlertCircle,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { motion, AnimatePresence } from "framer-motion";
import { cn } from "@/lib/utils";
import { useRef, useState, useEffect, useCallback } from "react";
import { useWizard } from "@/context/WizardContext";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

function streamUrl(projectId: string, platform: string) {
  return `${API}/api/v1/projects/${projectId}/stream/${platform}`;
}

const PLATFORMS = [
  {
    id: "tiktok",
    name: "TikTok",
    icon: (
      <svg viewBox="0 0 24 24" className="w-7 h-7" fill="currentColor">
        <path d="M19.59 6.69a4.83 4.83 0 0 1-3.77-4.25V2h-3.45v13.67a2.89 2.89 0 0 1-2.88 2.5 2.89 2.89 0 0 1-2.89-2.89 2.89 2.89 0 0 1 2.89-2.89c.28 0 .54.04.79.1V9.01a6.33 6.33 0 0 0-.79-.05 6.34 6.34 0 0 0-6.34 6.34 6.34 6.34 0 0 0 6.34 6.34 6.34 6.34 0 0 0 6.33-6.34V8.69a8.18 8.18 0 0 0 4.78 1.52V6.76a4.85 4.85 0 0 1-1.01-.07z" />
      </svg>
    ),
    enabled: false,
    note: "Coming soon",
  },
  {
    id: "instagram",
    name: "Instagram",
    icon: (
      <svg
        viewBox="0 0 24 24"
        className="w-7 h-7"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.5"
      >
        <rect x="2" y="2" width="20" height="20" rx="5" ry="5" />
        <circle cx="12" cy="12" r="4" />
        <circle cx="17.5" cy="6.5" r="1" fill="currentColor" stroke="none" />
      </svg>
    ),
    enabled: false,
    note: "Coming soon",
  },
  {
    id: "youtube",
    name: "YouTube",
    icon: (
      <svg viewBox="0 0 24 24" className="w-7 h-7" fill="currentColor">
        <path d="M23.5 6.19a3.02 3.02 0 0 0-2.12-2.14C19.54 3.5 12 3.5 12 3.5s-7.54 0-9.38.55A3.02 3.02 0 0 0 .5 6.19 31.6 31.6 0 0 0 0 12a31.6 31.6 0 0 0 .5 5.81 3.02 3.02 0 0 0 2.12 2.14C4.46 20.5 12 20.5 12 20.5s7.54 0 9.38-.55a3.02 3.02 0 0 0 2.12-2.14A31.6 31.6 0 0 0 24 12a31.6 31.6 0 0 0-.5-5.81zM9.75 15.02V8.98L15.5 12l-5.75 3.02z" />
      </svg>
    ),
    enabled: true,
    note: "Connect your YouTube channel",
  },
];

function ConnectAccountModal({
  onClose,
  onConnected,
}: {
  onClose: () => void;
  onConnected: (platformId: string) => void;
}) {
  const [selected, setSelected] = useState<string>("youtube");
  const [connecting, setConnecting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const popupRef = useRef<Window | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const selectedPlatform = PLATFORMS.find((p) => p.id === selected);

  // Clean up poll + popup on unmount
  useEffect(() => {
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
      if (popupRef.current && !popupRef.current.closed)
        popupRef.current.close();
    };
  }, []);

  const handleConnect = async () => {
    if (selected !== "youtube") return;
    setConnecting(true);
    setError(null);

    try {
      // 1. Get the Google OAuth URL from the backend
      const res = await fetch(`${API}/api/v1/auth/youtube`);
      if (!res.ok) throw new Error("Failed to start YouTube auth");
      const { auth_url } = await res.json();

      // 2. Open the Google consent screen in a popup window
      const popup = window.open(
        auth_url,
        "youtube-auth",
        "width=520,height=640,left=200,top=100",
      );
      popupRef.current = popup;

      // 3. Poll /auth/status every 2s until youtube = true or popup closed
      pollRef.current = setInterval(async () => {
        if (popup?.closed) {
          clearInterval(pollRef.current!);
          setConnecting(false);
          return;
        }
        try {
          const statusRes = await fetch(`${API}/api/v1/auth/status`);
          const status = await statusRes.json();
          if (status.youtube) {
            clearInterval(pollRef.current!);
            popup?.close();
            setConnecting(false);
            onConnected("youtube");
          }
        } catch {
          // ignore transient errors while polling
        }
      }, 2000);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Connection failed");
      setConnecting(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4">
      <motion.div
        initial={{ opacity: 0, scale: 0.95, y: 10 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.95, y: 10 }}
        transition={{ duration: 0.2 }}
        className="bg-white rounded-2xl shadow-xl w-full max-w-sm p-6"
      >
        <div className="flex items-start justify-between mb-1">
          <div>
            <h2 className="text-base font-semibold text-[#1A1A1A]">
              Connect social media account
            </h2>
            <p className="text-sm text-[#6B6B6B] mt-0.5">
              Choose one of the supported platforms.
            </p>
          </div>
          <button
            onClick={onClose}
            disabled={connecting}
            className="w-7 h-7 rounded-full hover:bg-gray-100 flex items-center justify-center transition-colors"
          >
            <X className="w-4 h-4 text-[#6B6B6B]" />
          </button>
        </div>

        <div className="grid grid-cols-3 gap-3 my-5">
          {PLATFORMS.map((platform) => (
            <button
              key={platform.id}
              onClick={() =>
                platform.enabled && !connecting && setSelected(platform.id)
              }
              disabled={!platform.enabled || connecting}
              className={cn(
                "flex flex-col items-center gap-2 p-4 rounded-xl border-2 transition-all duration-200",
                platform.enabled
                  ? selected === platform.id
                    ? "border-[#B08D9F] bg-[#B08D9F]/5"
                    : "border-[#E8E0DC] hover:border-[#B08D9F]/40"
                  : "border-[#E8E0DC] opacity-40 cursor-not-allowed",
              )}
            >
              <span
                className={cn(
                  selected === platform.id && platform.enabled
                    ? "text-[#B08D9F]"
                    : "text-[#6B6B6B]",
                )}
              >
                {platform.icon}
              </span>
              <span className="text-xs font-medium text-[#1A1A1A]">
                {platform.name}
              </span>
            </button>
          ))}
        </div>

        {error && <p className="text-xs text-red-500 mb-3">{error}</p>}

        <p className="text-xs text-[#9B9B9B] mb-4">
          {connecting
            ? "A Google sign-in window has opened. Complete authorization there…"
            : selectedPlatform?.note}
        </p>

        <Button
          onClick={handleConnect}
          disabled={!selectedPlatform?.enabled || connecting}
          className="w-full rounded-xl bg-[#B08D9F] hover:bg-[#C9A9B8] text-white h-11"
        >
          {connecting ? (
            <span className="flex items-center gap-2">
              <svg
                className="w-4 h-4 animate-spin"
                fill="none"
                viewBox="0 0 24 24"
              >
                <circle
                  className="opacity-25"
                  cx="12"
                  cy="12"
                  r="10"
                  stroke="currentColor"
                  strokeWidth="4"
                />
                <path
                  className="opacity-75"
                  fill="currentColor"
                  d="M4 12a8 8 0 018-8v4l3-3-3-3V0a12 12 0 100 24v-4l-3 3 3 3v4A12 12 0 014 12z"
                />
              </svg>
              Waiting for authorization…
            </span>
          ) : (
            `Connect ${selectedPlatform?.name}`
          )}
        </Button>
      </motion.div>
    </div>
  );
}

export function Step8_ReviewVideo() {
  const { state } = useWizard();
  const videoRef = useRef<HTMLVideoElement>(null);
  const [isPlaying, setIsPlaying] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const [showModal, setShowModal] = useState(false);
  const [connectedAccounts, setConnectedAccounts] = useState<string[]>([]);
  const [publishing, setPublishing] = useState(false);
  const [publishResults, setPublishResults] = useState<
    | { platform: string; status: string; post_url?: string; error?: string }[]
    | null
  >(null);

  // Check which platforms are already authorized on mount
  const refreshAuthStatus = useCallback(async () => {
    try {
      const res = await fetch(`${API}/api/v1/auth/status`);
      const status: Record<string, boolean> = await res.json();
      const connected = Object.entries(status)
        .filter(([, ok]) => ok)
        .map(([id]) => id);
      setConnectedAccounts(connected);
    } catch {
      // backend may not be available yet — ignore
    }
  }, []);

  useEffect(() => {
    refreshAuthStatus();
  }, [refreshAuthStatus]);

  const projectId = state.pipelineProjectId;
  const videoUrls = state.pipelineVideoUrls;
  const firstPlatform = Object.keys(videoUrls)[0] ?? "instagram_reels";
  const videoSrc = projectId ? streamUrl(projectId, firstPlatform) : null;
  const downloadHref = videoSrc ?? undefined;

  const togglePlay = () => {
    const v = videoRef.current;
    if (!v) return;
    if (v.paused) {
      v.play();
      setIsPlaying(true);
    } else {
      v.pause();
      setIsPlaying(false);
    }
  };

  const handlePublish = async () => {
    if (!projectId || connectedAccounts.length === 0) return;
    setPublishing(true);
    setPublishResults(null);
    try {
      const res = await fetch(`${API}/api/v1/projects/${projectId}/publish`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          platforms: connectedAccounts,
          social_copy: state.generatedScript?.social_copy ?? {},
        }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err?.detail ?? "Publish request failed");
      }
      const data = await res.json();
      setPublishResults(data.posts ?? []);
    } catch (e) {
      setPublishResults([
        {
          platform: "error",
          status: "failed",
          error: e instanceof Error ? e.message : "Publish failed",
        },
      ]);
    } finally {
      setPublishing(false);
    }
  };

  const handleConnected = (platformId: string) => {
    if (!connectedAccounts.includes(platformId)) {
      setConnectedAccounts((prev) => [...prev, platformId]);
    }
    setShowModal(false);
  };

  const progressPercent = duration > 0 ? (currentTime / duration) * 100 : 0;

  const formatTime = (s: number) => {
    const m = Math.floor(s / 60);
    const sec = Math.floor(s % 60);
    return `${m}:${String(sec).padStart(2, "0")}`;
  };

  const aiSuggestions = [
    "Make the hook more energetic",
    "Add more emotion to the narration",
    "Shorten to 30 seconds",
    "Change to a professional tone",
  ];

  return (
    <>
      <AnimatePresence>
        {showModal && (
          <ConnectAccountModal
            onClose={() => setShowModal(false)}
            onConnected={handleConnected}
          />
        )}
      </AnimatePresence>

      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0, y: -20 }}
        transition={{ duration: 0.3 }}
      >
        {/* Header Row */}
        <div className="flex items-start justify-between mb-6">
          <div>
            <Badge
              variant="secondary"
              className="bg-green-100 text-green-600 hover:bg-green-100 px-3 py-1 mb-3"
            >
              <span className="w-2 h-2 rounded-full bg-green-500 mr-2 inline-block" />
              Ready
            </Badge>
            <h1 className="text-4xl font-medium text-[#1A1A1A]">
              Review Your Video
            </h1>
          </div>

          <div className="flex gap-3">
            {downloadHref ? (
              <a href={downloadHref} download>
                <Button
                  variant="outline"
                  className="rounded-full px-5 py-2 h-10 border-[#E8E0DC] hover:bg-[#FAF8F5]"
                >
                  <Download className="w-4 h-4 mr-2" />
                  Download
                </Button>
              </a>
            ) : (
              <Button
                variant="outline"
                disabled
                className="rounded-full px-5 py-2 h-10 border-[#E8E0DC]"
              >
                <Download className="w-4 h-4 mr-2" />
                Download
              </Button>
            )}
            <Button
              onClick={handlePublish}
              disabled={
                !projectId || connectedAccounts.length === 0 || publishing
              }
              className="rounded-full px-5 py-2 h-10 bg-[#1A1A1A] hover:bg-[#1A1A1A]/90 text-white disabled:opacity-50"
            >
              {publishing ? (
                <>
                  <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                  Publishing…
                </>
              ) : (
                <>
                  Publish
                  <ArrowRight className="w-4 h-4 ml-2" />
                </>
              )}
            </Button>
          </div>
        </div>

        {/* Main Content Grid */}
        <div className="flex gap-6">
          {/* Left Column — 9:16 Video Player */}
          <div className="w-[240px] flex-shrink-0">
            <div className="relative bg-black rounded-2xl aspect-[9/16] overflow-hidden mb-4">
              {videoSrc ? (
                <>
                  <video
                    ref={videoRef}
                    src={videoSrc}
                    className="w-full h-full object-contain"
                    playsInline
                    onTimeUpdate={() =>
                      setCurrentTime(videoRef.current?.currentTime ?? 0)
                    }
                    onLoadedMetadata={() =>
                      setDuration(videoRef.current?.duration ?? 0)
                    }
                    onEnded={() => setIsPlaying(false)}
                  />
                  <motion.button
                    whileHover={{ scale: 1.1 }}
                    whileTap={{ scale: 0.95 }}
                    onClick={togglePlay}
                    className={cn(
                      "absolute inset-0 flex items-center justify-center transition-opacity duration-200",
                      isPlaying ? "opacity-0 hover:opacity-100" : "opacity-100",
                    )}
                  >
                    <div className="w-14 h-14 rounded-full bg-white/90 flex items-center justify-center shadow-lg">
                      {isPlaying ? (
                        <Pause className="w-5 h-5 text-[#1A1A1A]" />
                      ) : (
                        <Play className="w-5 h-5 text-[#1A1A1A] ml-0.5" />
                      )}
                    </div>
                  </motion.button>
                </>
              ) : (
                <div className="w-full h-full flex flex-col items-center justify-center text-white/60">
                  <Play className="w-10 h-10 mb-2 opacity-40" />
                  <p className="text-xs">No video available</p>
                </div>
              )}
              <div className="absolute bottom-3 left-1/2 -translate-x-1/2 text-xs text-white/80 bg-black/40 px-2 py-0.5 rounded-full">
                1080p · 9:16
              </div>
            </div>

            {/* Progress Bar */}
            <div className="flex items-center gap-3 bg-white rounded-xl p-3 border border-[#E8E0DC]">
              <button
                onClick={togglePlay}
                className="w-8 h-8 rounded-full bg-white border border-[#E8E0DC] flex items-center justify-center hover:bg-gray-50 flex-shrink-0"
              >
                {isPlaying ? (
                  <Pause className="w-4 h-4 text-[#6B6B6B]" />
                ) : (
                  <Play className="w-4 h-4 text-[#6B6B6B] ml-0.5" />
                )}
              </button>
              <div className="flex-1 h-1.5 bg-gray-200 rounded-full overflow-hidden">
                <div
                  className="h-full bg-[#1A1A1A] rounded-full transition-all duration-300"
                  style={{ width: `${progressPercent}%` }}
                />
              </div>
              <span className="text-xs text-[#6B6B6B] flex-shrink-0">
                {formatTime(currentTime)} / {formatTime(duration)}
              </span>
            </div>
          </div>

          {/* Right Column — AI Suggestions & Stats */}
          <div className="flex-1 space-y-4">
            <div className="bg-white rounded-2xl border border-[#E8E0DC] p-5">
              <h3 className="text-sm font-semibold text-[#1A1A1A] mb-4">
                AI suggestions
              </h3>
              <div className="space-y-2">
                {aiSuggestions.map((suggestion, index) => (
                  <motion.button
                    key={index}
                    initial={{ opacity: 0, x: 10 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ delay: index * 0.05 }}
                    className="w-full flex items-center gap-3 p-3 rounded-xl border border-[#E8E0DC] text-left hover:border-[#B08D9F]/30 hover:bg-[#B08D9F]/5 transition-all duration-200"
                  >
                    <Sparkles className="w-4 h-4 text-[#B08D9F] shrink-0" />
                    <span className="text-sm text-[#1A1A1A]">{suggestion}</span>
                  </motion.button>
                ))}
              </div>
            </div>

            <div className="bg-white rounded-2xl border border-[#E8E0DC] p-5">
              <h3 className="text-sm font-semibold text-[#1A1A1A] mb-4">
                Generation Stats
              </h3>
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <span className="text-sm text-[#6B6B6B]">Platform</span>
                  <span className="text-sm font-medium text-[#1A1A1A] capitalize">
                    {firstPlatform.replace(/_/g, " ")}
                  </span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-sm text-[#6B6B6B]">Art Style</span>
                  <span className="text-sm font-medium text-[#1A1A1A] capitalize">
                    {state.presetConfig?.art_style?.replace(/_/g, " ") ??
                      state.selectedArtStyle?.replace(/-/g, " ") ??
                      "Comic"}
                  </span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-sm text-[#6B6B6B]">Voice</span>
                  <span className="text-sm font-medium text-[#1A1A1A]">
                    {"Rachel"}
                  </span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-sm text-[#6B6B6B]">Duration</span>
                  <span className="text-sm font-medium text-[#1A1A1A]">
                    {state.presetConfig?.video_duration
                      ? `${state.presetConfig.video_duration}s`
                      : duration > 0
                        ? `${Math.round(duration)}s`
                        : "30s"}
                  </span>
                </div>
              </div>
            </div>

            {state.presetConfig?.nemotron_reasoning && (
              <div className="bg-white rounded-2xl border border-[#E8E0DC] p-5">
                <h3 className="text-sm font-semibold text-[#1A1A1A] mb-3">
                  AI Reasoning
                </h3>
                <p className="text-xs text-[#6B6B6B] leading-relaxed line-clamp-6">
                  {state.presetConfig.nemotron_reasoning}
                </p>
              </div>
            )}
          </div>
        </div>

        {/* Connected Accounts Section */}
        <div className="mt-8 bg-white rounded-2xl border border-[#E8E0DC] p-5">
          <h3 className="text-sm font-semibold text-[#1A1A1A] mb-1">
            Connected Accounts
          </h3>
          <p className="text-xs text-[#9B9B9B] mb-4">
            You can connect multiple accounts to publish this video.
          </p>

          {connectedAccounts.length > 0 && (
            <div className="space-y-2 mb-3">
              {connectedAccounts.map((id) => {
                const platform = PLATFORMS.find((p) => p.id === id);
                if (!platform) return null;
                return (
                  <div
                    key={id}
                    className="flex items-center gap-3 p-3 rounded-xl border border-[#E8E0DC] bg-[#FAF8F5]"
                  >
                    <span className="text-[#B08D9F]">{platform.icon}</span>
                    <span className="text-sm font-medium text-[#1A1A1A] flex-1">
                      {platform.name}
                    </span>
                    <CheckCircle2 className="w-4 h-4 text-green-500" />
                  </div>
                );
              })}
            </div>
          )}

          <button
            onClick={() => setShowModal(true)}
            className="w-full flex items-center justify-center gap-2 p-3 rounded-xl border border-dashed border-[#E8E0DC] text-sm text-[#6B6B6B] hover:border-[#B08D9F]/40 hover:text-[#B08D9F] hover:bg-[#B08D9F]/5 transition-all duration-200"
          >
            <Plus className="w-4 h-4" />
            Connect new account
          </button>
        </div>

        {/* Publish Results */}
        <AnimatePresence>
          {publishResults && (
            <motion.div
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -10 }}
              transition={{ duration: 0.2 }}
              className="mt-4 bg-white rounded-2xl border border-[#E8E0DC] p-5"
            >
              <h3 className="text-sm font-semibold text-[#1A1A1A] mb-3">
                Publish Results
              </h3>
              <div className="space-y-2">
                {publishResults.map((result, i) => {
                  const platform = PLATFORMS.find(
                    (p) => p.id === result.platform,
                  );
                  const isSuccess =
                    result.status === "success" ||
                    result.status === "published";
                  return (
                    <div
                      key={i}
                      className={cn(
                        "flex items-center gap-3 p-3 rounded-xl border",
                        isSuccess
                          ? "border-green-200 bg-green-50"
                          : "border-red-200 bg-red-50",
                      )}
                    >
                      {isSuccess ? (
                        <CheckCircle2 className="w-4 h-4 text-green-500 shrink-0" />
                      ) : (
                        <AlertCircle className="w-4 h-4 text-red-500 shrink-0" />
                      )}
                      <span className="text-sm font-medium text-[#1A1A1A] flex-1 capitalize">
                        {platform?.name ?? result.platform}
                        {isSuccess
                          ? " — Published!"
                          : ` — ${result.error ?? "Failed"}`}
                      </span>
                      {result.post_url && (
                        <a
                          href={result.post_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="flex items-center gap-1 text-xs text-[#B08D9F] hover:underline"
                        >
                          View post
                          <ExternalLink className="w-3 h-3" />
                        </a>
                      )}
                    </div>
                  );
                })}
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </motion.div>
    </>
  );
}
