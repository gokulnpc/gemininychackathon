"use client";

import {
  Download,
  ArrowRight,

  Pause,
  Play,
  Plus,
  X,

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
import { voices, artStyles } from "@/data/staticData";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

function streamUrl(projectId: string, platform: string) {
  return `${API}/api/v1/projects/${projectId}/stream/${platform}`;
}

const PLATFORMS = [
  {
    id: "youtube",
    name: "YouTube",
    description: "Share to YouTube as a video",
    icon: (
      <div className="w-10 h-10 bg-[#FF0000] rounded-xl flex items-center justify-center shrink-0">
        <svg viewBox="0 0 24 24" className="w-5 h-5 text-white" fill="currentColor">
          <path d="M23.5 6.19a3.02 3.02 0 0 0-2.12-2.14C19.54 3.5 12 3.5 12 3.5s-7.54 0-9.38.55A3.02 3.02 0 0 0 .5 6.19 31.6 31.6 0 0 0 0 12a31.6 31.6 0 0 0 .5 5.81 3.02 3.02 0 0 0 2.12 2.14C4.46 20.5 12 20.5 12 20.5s7.54 0 9.38-.55a3.02 3.02 0 0 0 2.12-2.14A31.6 31.6 0 0 0 24 12a31.6 31.6 0 0 0-.5-5.81zM9.75 15.02V8.98L15.5 12l-5.75 3.02z" />
        </svg>
      </div>
    ),
    enabled: true,
  },
  {
    id: "instagram",
    name: "Instagram",
    description: "Share as Reel or Post",
    icon: (
      <div className="w-10 h-10 bg-gradient-to-tr from-[#FFB900] via-[#FF0040] to-[#9900FF] rounded-xl flex items-center justify-center shrink-0">
        <svg viewBox="0 0 24 24" className="w-5 h-5 text-white" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <rect x="2" y="2" width="20" height="20" rx="5" ry="5" />
          <circle cx="12" cy="12" r="4" />
          <circle cx="17.5" cy="6.5" r="1" fill="currentColor" stroke="none" />
        </svg>
      </div>
    ),
    enabled: true,
  },
  {
    id: "tiktok",
    name: "TikTok",
    description: "Share as TikTok video",
    icon: (
      <div className="w-10 h-10 bg-black rounded-xl flex items-center justify-center shrink-0">
        <svg viewBox="0 0 24 24" className="w-5 h-5 text-white" fill="currentColor">
          <path d="M19.59 6.69a4.83 4.83 0 0 1-3.77-4.25V2h-3.45v13.67a2.89 2.89 0 0 1-2.88 2.5 2.89 2.89 0 0 1-2.89-2.89 2.89 2.89 0 0 1 2.89-2.89c.28 0 .54.04.79.1V9.01a6.33 6.33 0 0 0-.79-.05 6.34 6.34 0 0 0-6.34 6.34 6.34 6.34 0 0 0 6.34 6.34 6.34 6.34 0 0 0 6.33-6.34V8.69a8.18 8.18 0 0 0 4.78 1.52V6.76a4.85 4.85 0 0 1-1.01-.07z" />
        </svg>
      </div>
    ),
    enabled: true,
  },
];

function ConnectAccountModal({
  onClose,
  connectedAccounts,
  onConnected,
}: {
  onClose: () => void;
  connectedAccounts: string[];
  onConnected: (platformId: string) => void;
}) {
  const [selected, setSelected] = useState<string[]>([]);
  const [connectingId, setConnectingId] = useState<string | null>(null);
  const popupRef = useRef<Window | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const unconnectedPlatforms = PLATFORMS.filter(
    (p) => !connectedAccounts.includes(p.id),
  );

  useEffect(() => {
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
      if (popupRef.current && !popupRef.current.closed) popupRef.current.close();
    };
  }, []);

  const handleToggle = async (platformId: string) => {
    if (selected.includes(platformId)) {
      setSelected(selected.filter((id) => id !== platformId));
      return;
    }

    if (platformId === "youtube") {
      setConnectingId("youtube");
      try {
        const res = await fetch(`${API}/api/v1/auth/youtube`);
        if (!res.ok) throw new Error("Failed to start YouTube auth");
        const { auth_url } = await res.json();

        const popup = window.open(auth_url, "youtube-auth", "width=520,height=640,left=200,top=100");
        popupRef.current = popup;

        pollRef.current = setInterval(async () => {
          if (popup?.closed) {
            clearInterval(pollRef.current!);
            setConnectingId(null);
            return;
          }
          try {
            const statusRes = await fetch(`${API}/api/v1/auth/status`);
            const status = await statusRes.json();
            if (status.youtube) {
              clearInterval(pollRef.current!);
              popup?.close();
              setConnectingId(null);
              onConnected("youtube");
            }
          } catch {}
        }, 2000);
      } catch {
        setConnectingId(null);
      }
    } else {
      setSelected([...selected, platformId]);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4">
      <motion.div
        initial={{ opacity: 0, scale: 0.95 }}
        animate={{ opacity: 1, scale: 1 }}
        exit={{ opacity: 0, scale: 0.95 }}
        transition={{ duration: 0.2 }}
        className="bg-[#3A3A3A] rounded-2xl shadow-xl w-full max-w-md p-6 border border-white/10"
      >
        <div className="flex items-start justify-between mb-2">
          <div>
            <h2 className="text-xl font-medium text-white">Connect Account</h2>
            <p className="text-xs text-[#A0A0A0] mt-1">Select platforms to share your video</p>
          </div>
          <button onClick={onClose} className="p-1.5 rounded-full hover:bg-white/10 text-white/50 transition-colors">
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="space-y-3 mt-6 mb-6">
          {unconnectedPlatforms.length === 0 ? (
            <p className="text-sm text-white/50 text-center py-4">All platforms are connected</p>
          ) : (
            unconnectedPlatforms.map((platform) => {
              const isSelected = selected.includes(platform.id);
              const isConnecting = connectingId === platform.id;
              return (
                <button
                  key={platform.id}
                  onClick={() => handleToggle(platform.id)}
                  className={cn(
                    "w-full flex items-center justify-between p-4 rounded-xl border transition-all duration-200",
                    isSelected ? "border-[#5a9ab5] bg-white/5" : "border-white/10 hover:border-white/20 hover:bg-white/5"
                  )}
                >
                  <div className="flex items-center gap-4">
                    {platform.icon}
                    <div className="text-left">
                      <div className="text-sm font-medium text-white flex items-center gap-2">
                        {platform.name}
                        {isConnecting && <Loader2 className="w-3 h-3 animate-spin text-white/50" />}
                      </div>
                      <div className="text-xs text-white/50 mt-0.5">{platform.description}</div>
                    </div>
                  </div>
                  <div className={cn(
                    "w-[22px] h-[22px] rounded-full border-2 flex items-center justify-center transition-colors",
                    isSelected ? "border-[#5a9ab5] bg-[#5a9ab5]" : "border-white/30"
                  )}>
                    {isSelected && <div className="w-2 h-2 bg-white rounded-full" />}
                  </div>
                </button>
              );
            })
          )}
        </div>

        <div className="flex gap-3">
          <Button onClick={onClose} variant="outline" className="flex-1 rounded-full bg-transparent border-white/20 text-white hover:bg-white/10 h-11">
            Cancel
          </Button>
        </div>
      </motion.div>
    </div>
  );
}

export function Step10_ReviewVideo() {
  const { state } = useWizard();
  const videoRef = useRef<HTMLVideoElement>(null);
  const [isPlaying, setIsPlaying] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const [showConnectModal, setShowConnectModal] = useState(false);
  const [connectedAccounts, setConnectedAccounts] = useState<string[]>([]);
  const [selectedPlatforms, setSelectedPlatforms] = useState<string[]>([]);
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

  const togglePlatformSelect = (platformId: string) => {
    setSelectedPlatforms((prev) =>
      prev.includes(platformId)
        ? prev.filter((id) => id !== platformId)
        : [...prev, platformId],
    );
  };

  const handlePublish = async () => {
    const platforms = selectedPlatforms;
    if (!projectId || platforms.length === 0) return;
    setPublishing(true);
    setPublishResults(null);
    try {
      const script = state.generatedScript;

      // Build social_copy from script data — agent often omits it entirely.
      // Hook text → title, CTA text → caption, scenes give hashtag count.
      const hookText = script?.hook?.text ?? "";
      const ctaText = script?.cta?.text ?? "";
      const fullVoiceover = script?.voiceover_full_script ?? "";

      // Try to extract hashtags from any existing social_copy first
      const existingCopy = script?.social_copy ?? {};
      const existingPlatformCopy =
        existingCopy["instagram_reels"] ??
        existingCopy["youtube_shorts"] ??
        existingCopy["youtube"] ??
        Object.values(existingCopy)[0] ??
        {};

      const title =
        (existingPlatformCopy as Record<string, unknown>)?.title as string ||
        hookText.slice(0, 97) ||
        "New Video";

      const caption =
        (existingPlatformCopy as Record<string, unknown>)?.caption as string ||
        (ctaText ? `${ctaText}\n\n${fullVoiceover.slice(0, 200)}` : fullVoiceover.slice(0, 200)) ||
        hookText;

      const hashtags: string[] =
        ((existingPlatformCopy as Record<string, unknown>)?.hashtags as string[]) ?? [];

      const enrichedSocialCopy = {
        instagram_reels: { title, caption, hashtags },
        youtube_shorts:  { title, caption: `${caption}\n\n#Shorts`.trim(), hashtags },
        tiktok:          { title, caption, hashtags },
      };

      const res = await fetch(`${API}/api/v1/projects/${projectId}/publish`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          platforms,
          social_copy: enrichedSocialCopy,
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
    setShowConnectModal(false);
  };

  const progressPercent = duration > 0 ? (currentTime / duration) * 100 : 0;

  const formatTime = (s: number) => {
    const m = Math.floor(s / 60);
    const sec = Math.floor(s % 60);
    return `${m}:${String(sec).padStart(2, "0")}`;
  };

  // Look up static data for display
  const musicPresets: Record<string, string> = {
    breathing_shadows: "Breathing Shadows",
    quiet_before_storm: "Quiet Before Storm",
    brilliant_symphony: "Brilliant Symphony",
    happy_rhythm: "Happy Rhythm",
    peaceful_vibes: "Peaceful Vibes",
    lyria: "AI Generated",
    none: "None",
  };

  const captionStyles: Record<string, string> = {
    beast: "Beast",
    bold_stroke: "Bold Stroke",
    karaoke: "Karaoke",
    majestic: "Majestic",
    red_highlight: "Red Highlight",
    sleek: "Sleek",
    elegant: "Elegant",
  };

  return (
    <>
      <AnimatePresence>
        {showConnectModal && (
          <ConnectAccountModal
            onClose={() => setShowConnectModal(false)}
            connectedAccounts={connectedAccounts}
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
              className="bg-green-500/20 text-green-300 hover:bg-green-500/20 px-3 py-1 mb-3"
            >
              <span className="w-2 h-2 rounded-full bg-green-400 mr-2 inline-block" />
              Ready
            </Badge>
            <h1 className="text-4xl font-medium text-white">
              Review Your Video
            </h1>
          </div>

          <div className="flex gap-3">
            {downloadHref ? (
              <a href={downloadHref} download>
                <Button
                  variant="outline"
                  className="rounded-full px-5 py-2 h-10 border-white/20 hover:bg-white/10 text-white"
                >
                  <Download className="w-4 h-4 mr-2" />
                  Download
                </Button>
              </a>
            ) : (
              <Button
                variant="outline"
                disabled
                className="rounded-full px-5 py-2 h-10 border-white/20 text-white/50"
              >
                <Download className="w-4 h-4 mr-2" />
                Download
              </Button>
            )}
          </div>
        </div>

        {/* Main Content Grid */}
        <div className="flex gap-6">
          {/* Left Column — 9:16 Video Player */}
          <div className="w-[240px] shrink-0">
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
            <div className="flex items-center gap-3 bg-white/20 rounded-xl p-3 border border-white/20">
              <button
                onClick={togglePlay}
                className="w-8 h-8 rounded-full bg-white/20 border border-white/20 flex items-center justify-center hover:bg-white/30 shrink-0"
              >
                {isPlaying ? (
                  <Pause className="w-4 h-4 text-white/60" />
                ) : (
                  <Play className="w-4 h-4 text-white/60 ml-0.5" />
                )}
              </button>
              <div className="flex-1 h-1.5 bg-white/20 rounded-full overflow-hidden">
                <div
                  className="h-full bg-[#5a9ab5] rounded-full transition-all duration-300"
                  style={{ width: `${progressPercent}%` }}
                />
              </div>
              <span className="text-xs text-white/50 shrink-0">
                {formatTime(currentTime)} / {formatTime(duration)}
              </span>
            </div>
          </div>

          {/* Right Column — Stats & Publish */}
          <div className="flex-1 space-y-4">
            {/* Generation Stats */}
            <div className="bg-white/20 rounded-2xl border border-white/20 p-5">
              <h3 className="text-sm font-semibold text-white mb-4">
                Generation Stats
              </h3>
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <span className="text-sm text-white/50">Language &amp; Voices</span>
                  <span className="text-sm font-medium text-[#5a9ab5]">
                    {voices.find(v => v.id === state.selectedVoice)?.name ?? "Rachel"}
                  </span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-sm text-white/50">Background Music</span>
                  <span className="text-sm font-medium text-[#5a9ab5]">
                    {musicPresets[state.selectedMusic ?? ""] ?? state.selectedMusic ?? "None"}
                  </span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-sm text-white/50">Art Style</span>
                  <span className="text-sm font-medium text-[#5a9ab5] capitalize">
                    {artStyles.find(a => a.id === state.selectedArtStyle)?.name ?? "Comic"}
                  </span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-sm text-white/50">Caption Style</span>
                  <span className="text-sm font-medium text-[#5a9ab5]">
                    {captionStyles[state.selectedCaption ?? ""] ?? state.selectedCaption ?? "Bold Stroke"}
                  </span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-sm text-white/50">Duration</span>
                  <span className="text-sm font-medium text-[#5a9ab5]">
                    {duration > 0 ? `${Math.round(duration)} seconds` : "30 seconds"}
                  </span>
                </div>
              </div>
            </div>

            {/* Publish Video */}
            <div className="bg-white/20 rounded-2xl border border-white/20 p-5">
              <div className="flex items-center justify-between mb-1">
                <div>
                  <h3 className="text-sm font-semibold text-white">Publish Video</h3>
                  <p className="text-xs text-white/40 mt-0.5">Select platforms to share your video</p>
                </div>
                <Button
                  onClick={handlePublish}
                  disabled={!projectId || publishing || selectedPlatforms.length === 0}
                  className="rounded-full px-5 py-2 h-9 bg-[#5a9ab5] hover:bg-[#7ab0c8] text-white text-sm disabled:opacity-50"
                >
                  {publishing ? (
                    <>
                      <Loader2 className="w-3.5 h-3.5 mr-1.5 animate-spin" />
                      Publishing…
                    </>
                  ) : (
                    <>
                      Publish
                      <ArrowRight className="w-3.5 h-3.5 ml-1.5" />
                    </>
                  )}
                </Button>
              </div>

              <div className="space-y-2 mt-4">
                {connectedAccounts.length === 0 ? (
                  <div className="flex items-center gap-3 p-3 rounded-xl border border-white/10 bg-white/5">
                    <span className="text-sm text-white/40">No accounts connected yet</span>
                  </div>
                ) : (
                  connectedAccounts.map((accountId) => {
                    const platform = PLATFORMS.find((p) => p.id === accountId);
                    if (!platform) return null;
                    const isSelected = selectedPlatforms.includes(accountId);
                    const publishResult = publishResults?.find(
                      (r) => r.platform === accountId,
                    );
                    const isPublished =
                      publishResult?.status === "success" ||
                      publishResult?.status === "published";
                    return (
                      <button
                        key={accountId}
                        onClick={() => togglePlatformSelect(accountId)}
                        className={cn(
                          "w-full flex items-center justify-between p-3 rounded-xl border transition-all duration-200",
                          isSelected
                            ? "border-[#5a9ab5] bg-white/5"
                            : "border-white/10 hover:border-white/20 hover:bg-white/5",
                        )}
                      >
                        <div className="flex items-center gap-3">
                          {platform.icon}
                          <span className="text-sm font-medium text-white">
                            {platform.name}
                          </span>
                          {isPublished && (
                            <Badge className="bg-green-500/20 text-green-300 hover:bg-green-500/20 text-xs px-2 py-0.5">
                              <span className="w-1.5 h-1.5 rounded-full bg-green-400 mr-1.5 inline-block" />
                              Published
                            </Badge>
                          )}
                        </div>
                        <div className="flex items-center gap-2">
                          {publishResult?.post_url && (
                            <a
                              href={publishResult.post_url}
                              target="_blank"
                              rel="noopener noreferrer"
                              onClick={(e) => e.stopPropagation()}
                              className="p-1.5 rounded-lg hover:bg-white/10 transition-colors"
                            >
                              <ExternalLink className="w-4 h-4 text-white/40" />
                            </a>
                          )}
                          <div
                            className={cn(
                              "w-[22px] h-[22px] rounded-full border-2 flex items-center justify-center transition-colors",
                              isSelected
                                ? "border-[#5a9ab5] bg-[#5a9ab5]"
                                : "border-white/30",
                            )}
                          >
                            {isSelected && (
                              <div className="w-2 h-2 bg-white rounded-full" />
                            )}
                          </div>
                        </div>
                      </button>
                    );
                  })
                )}

                {/* Connect more account */}
                <button
                  onClick={() => setShowConnectModal(true)}
                  className="w-full flex items-center gap-3 p-3 rounded-xl border border-white/10 hover:border-white/20 hover:bg-white/5 transition-all duration-200"
                >
                  <Plus className="w-4 h-4 text-white/50" />
                  <span className="text-sm text-white/50">Connect more account</span>
                </button>
              </div>
            </div>

            {state.presetConfig?.nemotron_reasoning && (
              <div className="bg-white/20 rounded-2xl border border-white/20 p-5">
                <h3 className="text-sm font-semibold text-white mb-3">
                  AI Reasoning
                </h3>
                <p className="text-xs text-white/50 leading-relaxed line-clamp-6">
                  {state.presetConfig.nemotron_reasoning}
                </p>
              </div>
            )}
          </div>
        </div>

        {/* Publish Error Results */}
        <AnimatePresence>
          {publishResults?.some(
            (r) => r.status !== "success" && r.status !== "published",
          ) && (
            <motion.div
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -10 }}
              transition={{ duration: 0.2 }}
              className="mt-4 bg-white/20 rounded-2xl border border-white/20 p-5"
            >
              <h3 className="text-sm font-semibold text-white mb-3">
                Publish Errors
              </h3>
              <div className="space-y-2">
                {publishResults
                  ?.filter(
                    (r) =>
                      r.status !== "success" && r.status !== "published",
                  )
                  .map((result, i) => {
                    const platform = PLATFORMS.find(
                      (p) => p.id === result.platform,
                    );
                    return (
                      <div
                        key={i}
                        className="flex items-center gap-3 p-3 rounded-xl border border-red-500/30 bg-red-500/10"
                      >
                        <AlertCircle className="w-4 h-4 text-red-400 shrink-0" />
                        <span className="text-sm font-medium text-white flex-1 capitalize">
                          {platform?.name ?? result.platform} —{" "}
                          {result.error ?? "Failed"}
                        </span>
                      </div>
                    );
                  })}
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        {/* Not satisfied? Regenerate */}
        <div className="flex items-center justify-end gap-3 mt-6">
          <span className="text-sm text-white/40">Not satisfied?</span>
          <Button
            variant="outline"
            className="rounded-full px-5 py-2 h-10 border-white/20 hover:bg-white/10 text-white"
          >
            <Download className="w-4 h-4 mr-2" />
            Regenerate
          </Button>
        </div>
      </motion.div>
    </>
  );
}
