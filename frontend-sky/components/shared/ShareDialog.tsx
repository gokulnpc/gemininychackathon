"use client";

import { useState } from "react";
import { CheckCircle2, ExternalLink, Loader2, Share2, XCircle } from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { useYoutubeAccount } from "@/hooks/use-youtube-account";
import { cn } from "@/lib/utils";
import apiClient from "@/lib/apiClient";

interface ShareDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  projectId: string;
  exportId?: string;
}

type PublishResult = { platform: string; status: string; post_url?: string; error?: string };

const PLATFORMS = [
  {
    key: "youtube" as const,
    label: "YouTube",
    available: true,
    icon: (
      <div className="w-10 h-10 bg-[#FF0000] rounded-xl flex items-center justify-center shrink-0">
        <svg viewBox="0 0 24 24" className="w-5 h-5 text-white" fill="currentColor">
          <path d="M23.5 6.19a3.02 3.02 0 0 0-2.12-2.14C19.54 3.5 12 3.5 12 3.5s-7.54 0-9.38.55A3.02 3.02 0 0 0 .5 6.19 31.6 31.6 0 0 0 0 12a31.6 31.6 0 0 0 .5 5.81 3.02 3.02 0 0 0 2.12 2.14C4.46 20.5 12 20.5 12 20.5s7.54 0 9.38-.55a3.02 3.02 0 0 0 2.12-2.14A31.6 31.6 0 0 0 24 12a31.6 31.6 0 0 0-.5-5.81zM9.75 15.02V8.98L15.5 12l-5.75 3.02z" />
        </svg>
      </div>
    ),
  },
  {
    key: "instagram" as const,
    label: "Instagram",
    available: false,
    icon: (
      <div className="w-10 h-10 bg-gradient-to-tr from-[#FFB900] via-[#FF0040] to-[#9900FF] rounded-xl flex items-center justify-center shrink-0">
        <svg viewBox="0 0 24 24" className="w-5 h-5 text-white" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <rect x="2" y="2" width="20" height="20" rx="5" ry="5" />
          <circle cx="12" cy="12" r="4" />
          <circle cx="17.5" cy="6.5" r="1" fill="currentColor" stroke="none" />
        </svg>
      </div>
    ),
  },
  {
    key: "tiktok" as const,
    label: "TikTok",
    available: false,
    icon: (
      <div className="w-10 h-10 bg-black rounded-xl flex items-center justify-center shrink-0">
        <svg viewBox="0 0 24 24" className="w-5 h-5 text-white" fill="currentColor">
          <path d="M19.59 6.69a4.83 4.83 0 0 1-3.77-4.25V2h-3.45v13.67a2.89 2.89 0 0 1-2.88 2.5 2.89 2.89 0 0 1-2.89-2.89 2.89 2.89 0 0 1 2.89-2.89c.28 0 .54.04.79.1V9.01a6.33 6.33 0 0 0-.79-.05 6.34 6.34 0 0 0-6.34 6.34 6.34 6.34 0 0 0 6.34 6.34 6.34 6.34 0 0 0 6.33-6.34V8.69a8.18 8.18 0 0 0 4.78 1.52V6.76a4.85 4.85 0 0 1-1.01-.07z" />
        </svg>
      </div>
    ),
  },
];

export function ShareDialog({ open, onOpenChange, projectId, exportId }: ShareDialogProps) {
  const { youtubeConnected, youtubeConnecting, connectYouTube } = useYoutubeAccount();
  const [selectedPlatforms, setSelectedPlatforms] = useState<string[]>([]);
  const [publishing, setPublishing] = useState(false);
  const [results, setResults] = useState<PublishResult[] | null>(null);

  function togglePlatform(key: string) {
    setSelectedPlatforms((prev) =>
      prev.includes(key) ? prev.filter((p) => p !== key) : [...prev, key]
    );
  }

  async function handlePublish() {
    if (!selectedPlatforms.length) return;
    setPublishing(true);
    setResults(null);
    try {
      const resp = await apiClient.post(`/api/v1/projects/${projectId}/publish`, {
        platforms: selectedPlatforms,
        ...(exportId ? { export_id: exportId } : {}),
      });
      setResults((resp.data as { posts?: PublishResult[] }).posts ?? []);
    } catch (e) {
      setResults([{ platform: "all", status: "failed", error: e instanceof Error ? e.message : "Publish failed" }]);
    } finally {
      setPublishing(false);
    }
  }

  function handleClose() {
    setSelectedPlatforms([]);
    setResults(null);
    onOpenChange(false);
  }

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent className="bg-[#1e1e1e] border-white/10 text-white max-w-sm">
        <DialogHeader>
          <DialogTitle className="text-white flex items-center gap-2">
            <Share2 className="w-5 h-5 text-[#5a9ab5]" />
            Share Video
          </DialogTitle>
        </DialogHeader>

        <p className="text-sm text-white/50 -mt-2">Choose where to publish your video</p>

        <div className="grid grid-cols-3 gap-3 mt-2">
          {PLATFORMS.map((platform) => {
            const isYT = platform.key === "youtube";
            const connected = isYT && youtubeConnected;
            const selected = selectedPlatforms.includes(platform.key);
            const available = platform.available;

            return (
              <button
                key={platform.key}
                disabled={!available}
                onClick={() => {
                  if (!available) return;
                  if (isYT && !youtubeConnected) {
                    connectYouTube();
                    return;
                  }
                  togglePlatform(platform.key);
                }}
                className={cn(
                  "flex flex-col items-center gap-2 p-3 rounded-xl border transition-all",
                  available && selected
                    ? "border-[#5a9ab5] bg-[#5a9ab5]/10"
                    : available
                    ? "border-white/10 bg-white/5 hover:border-white/20 hover:bg-white/10"
                    : "border-white/5 bg-white/[0.02] opacity-40 cursor-not-allowed"
                )}
              >
                {platform.icon}
                <span className="text-xs text-white/70 font-medium">{platform.label}</span>
                {isYT ? (
                  <span className={cn(
                    "text-[9px] px-1.5 py-0.5 rounded-full font-medium border",
                    connected
                      ? "bg-green-500/20 text-green-400 border-green-500/30"
                      : youtubeConnecting
                      ? "bg-yellow-500/20 text-yellow-400 border-yellow-500/30"
                      : "bg-white/10 text-white/40 border-white/10"
                  )}>
                    {connected ? "Connected" : youtubeConnecting ? "Connecting…" : "Connect"}
                  </span>
                ) : (
                  <span className="text-[9px] px-1.5 py-0.5 rounded-full bg-white/5 text-white/30 border border-white/10">
                    Soon
                  </span>
                )}
              </button>
            );
          })}
        </div>

        {results && (
          <div className="space-y-2 mt-1">
            {results.map((r) => (
              <div key={r.platform} className="flex items-center gap-2 text-sm bg-white/5 rounded-lg px-3 py-2">
                {r.status === "published" || r.status === "success" ? (
                  <CheckCircle2 className="w-4 h-4 text-green-400 shrink-0" />
                ) : (
                  <XCircle className="w-4 h-4 text-red-400 shrink-0" />
                )}
                <span className="capitalize text-white/80 font-medium">{r.platform}</span>
                {r.post_url && (
                  <a href={r.post_url} target="_blank" rel="noreferrer" className="ml-auto text-[#5a9ab5] hover:underline flex items-center gap-1 text-xs">
                    View <ExternalLink className="w-3 h-3" />
                  </a>
                )}
                {r.error && (
                  <span className="ml-auto text-red-400 text-xs truncate max-w-[120px]" title={r.error}>
                    {r.error}
                  </span>
                )}
              </div>
            ))}
          </div>
        )}

        <div className="flex gap-2 mt-1">
          <Button
            className="flex-1 bg-[#5a9ab5] hover:bg-[#7ab0c8] text-white"
            disabled={publishing || selectedPlatforms.length === 0}
            onClick={handlePublish}
          >
            {publishing ? (
              <><Loader2 className="w-4 h-4 mr-2 animate-spin" />Publishing…</>
            ) : (
              <><Share2 className="w-4 h-4 mr-2" />Publish</>
            )}
          </Button>
          <Button variant="outline" className="bg-transparent border-white/10 text-white/70 hover:bg-white/10 hover:text-white" onClick={handleClose} disabled={publishing}>
            Cancel
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
