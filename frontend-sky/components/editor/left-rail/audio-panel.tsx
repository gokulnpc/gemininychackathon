"use client";

import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ChangeEvent,
} from "react";
import { Loader2, Music4, Play, Plus, Search, Upload } from "lucide-react";

import type { Asset } from "@/components/editor/types";
import { musicTracks } from "@/data/staticData";
import apiClient from "@/lib/apiClient";
import { cn } from "@/lib/utils";

type AudioTab = "public" | "my-assets" | "upload";

interface PublicMusicTrack {
  id: string;
  title: string;
  description: string;
  src: string;
}

const PUBLIC_MUSIC_TRACKS: PublicMusicTrack[] = musicTracks
  .filter(
    (track): track is typeof track & { audioFile: string } =>
      typeof track.audioFile === "string" && Boolean(track.audioFile),
  )
  .map((track) => ({
    id: track.id,
    title: track.title,
    description: track.description,
    src: track.audioFile,
  }));

interface AudioPanelProps {
  onInsertAudio: (src: string, label: string) => void | Promise<void>;
  focusedAssetRef?: React.MutableRefObject<{ id: string; category: string } | null>;
}

export function AudioPanel({ onInsertAudio, focusedAssetRef }: AudioPanelProps) {
  const [audioTab, setAudioTab] = useState<AudioTab>("public");
  const [search, setSearch] = useState("");
  const [musicAssets, setMusicAssets] = useState<Asset[]>([]);
  const [assetUrls, setAssetUrls] = useState<Record<string, string>>({});
  const [assetsLoading, setAssetsLoading] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [playingId, setPlayingId] = useState<string | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const stopPreview = useCallback(() => {
    audioRef.current?.pause();
    audioRef.current = null;
    setPlayingId(null);
  }, []);

  const fetchMusicAssets = useCallback(async () => {
    try {
      setAssetsLoading(true);
      const response = (
        await apiClient.get("/api/v1/assets", { params: { category: "music" } })
      ).data as Asset[] | { assets: Asset[] };
      const assets = Array.isArray(response)
        ? response
        : (response.assets ?? []);
      setMusicAssets(assets);

      const nextUrls = Object.fromEntries(
        await Promise.all(
          assets.map(async (asset) => {
            try {
              const urlResponse = (
                await apiClient.get(`/api/v1/assets/${asset.id}/url`, {
                  params: { category: "music" },
                })
              ).data as { url: string };
              return [asset.id, urlResponse.url] as const;
            } catch {
              return [asset.id, ""] as const;
            }
          }),
        ),
      );

      setAssetUrls(nextUrls);
    } catch (error) {
      console.warn("[AudioPanel] Failed to fetch music assets.", error);
      setMusicAssets([]);
      setAssetUrls({});
    } finally {
      setAssetsLoading(false);
    }
  }, []);

  useEffect(() => {
    if (audioTab !== "my-assets") return;
    void fetchMusicAssets();
  }, [audioTab, fetchMusicAssets]);

  useEffect(() => {
    return () => {
      stopPreview();
    };
  }, [stopPreview]);

  const handlePlay = useCallback(
    async (trackId: string, src: string) => {
      if (playingId === trackId) {
        stopPreview();
        return;
      }

      stopPreview();

      try {
        const audio = new Audio(src);
        audio.onended = () => {
          audioRef.current = null;
          setPlayingId((currentId) =>
            currentId === trackId ? null : currentId,
          );
        };
        await audio.play();
        audioRef.current = audio;
        setPlayingId(trackId);
      } catch (error) {
        console.error("[AudioPanel] Failed to preview audio.", error);
      }
    },
    [playingId, stopPreview],
  );

  const handleUpload = useCallback(
    async (event: ChangeEvent<HTMLInputElement>) => {
      const file = event.target.files?.[0];
      if (!file) return;

      try {
        setUploading(true);
        const formData = new FormData();
        formData.append("file", file);
        await apiClient.post("/api/v1/assets/upload", formData, {
          params: { category: "music" },
          headers: { "Content-Type": "multipart/form-data" },
        });
        await fetchMusicAssets();
        setAudioTab("my-assets");
      } catch (error) {
        console.error("[AudioPanel] Upload failed.", error);
      } finally {
        setUploading(false);
        if (fileInputRef.current) {
          fileInputRef.current.value = "";
        }
      }
    },
    [fetchMusicAssets],
  );

  const filteredPublicTracks = useMemo(
    () =>
      PUBLIC_MUSIC_TRACKS.filter(
        (track) =>
          track.title.toLowerCase().includes(search.toLowerCase()) ||
          track.description.toLowerCase().includes(search.toLowerCase()),
      ),
    [search],
  );

  const filteredMusicAssets = useMemo(
    () =>
      musicAssets.filter((asset) =>
        asset.filename.toLowerCase().includes(search.toLowerCase()),
      ),
    [musicAssets, search],
  );

  const audioTabs: { key: AudioTab; label: string; icon: typeof Music4 }[] = [
    { key: "public", label: "Public", icon: Music4 },
    { key: "my-assets", label: "Assets", icon: Music4 },
    { key: "upload", label: "Upload", icon: Upload },
  ];

  return (
    <div className="space-y-3">
      <div className="flex gap-1 rounded-lg border border-editor-border bg-editor-card p-1">
        {audioTabs.map((tab) => {
          const Icon = tab.icon;
          return (
            <button
              key={tab.key}
              type="button"
              onClick={() => setAudioTab(tab.key)}
              className={cn(
                "flex flex-1 items-center justify-center gap-1 rounded-md px-2 py-1 text-[11px] font-medium transition-all",
                audioTab === tab.key
                  ? "bg-primary/18 text-primary shadow-sm"
                  : "bg-editor-control text-muted-foreground hover:bg-editor-control-hover hover:text-foreground",
              )}
            >
              <Icon className="h-3 w-3" />
              {tab.label}
            </button>
          );
        })}
      </div>

      {audioTab !== "upload" ? (
        <div className="relative">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-editor-text-dim" />
          <input
            type="text"
            placeholder="Search audio..."
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            className="w-full rounded-xl border border-editor-border bg-editor-control py-2.5 pl-9 pr-3 text-sm text-foreground placeholder:text-muted-foreground focus:border-primary/50 focus:outline-none focus:ring-1 focus:ring-primary/30"
          />
        </div>
      ) : null}

      {audioTab === "public" ? (
        <div className="space-y-2">
          {filteredPublicTracks.map((track) => {
            const isPlaying = playingId === `public:${track.id}`;
            return (
              <div
                key={track.id}
                className="flex items-center gap-3 rounded-xl border border-editor-border bg-editor-card px-3 py-3 transition hover:border-primary/35"
              >
                <button
                  type="button"
                  onClick={() =>
                    void handlePlay(`public:${track.id}`, track.src)
                  }
                  className={cn(
                    "flex h-10 w-10 shrink-0 items-center justify-center rounded-lg border transition",
                    isPlaying
                      ? "border-primary/50 bg-primary text-primary-foreground"
                      : "border-editor-border bg-editor-control text-foreground hover:border-primary/40 hover:bg-editor-control-hover",
                  )}
                  title={isPlaying ? "Stop preview" : "Preview audio"}
                >
                  {isPlaying ? (
                    <div className="h-3 w-3 rounded-sm bg-primary-foreground" />
                  ) : (
                    <Play className="ml-0.5 h-4 w-4" />
                  )}
                </button>

                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium text-foreground">
                    {track.title}
                  </p>
                  <p className="line-clamp-2 text-xs text-editor-text-muted">
                    {track.description}
                  </p>
                </div>

                <button
                  type="button"
                  onClick={() => void onInsertAudio(track.src, track.title)}
                  className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg border border-editor-border bg-editor-control text-foreground transition hover:border-primary/40 hover:bg-editor-control-hover"
                  title="Add to timeline"
                >
                  <Plus className="h-4 w-4" />
                </button>
              </div>
            );
          })}

          {filteredPublicTracks.length === 0 ? (
            <p className="py-4 text-center text-xs text-editor-text-muted">
              No tracks match "{search}"
            </p>
          ) : null}
        </div>
      ) : null}

      {audioTab === "my-assets" ? (
        <div className="space-y-2">
          {assetsLoading ? (
            <div className="flex items-center justify-center py-8">
              <Loader2 className="h-5 w-5 animate-spin text-editor-text-dim" />
            </div>
          ) : musicAssets.length === 0 ? (
            <div className="rounded-xl border border-dashed border-editor-border bg-editor-card/60 px-3 py-6 text-center text-sm text-editor-text-muted">
              No uploaded music yet.
            </div>
          ) : filteredMusicAssets.length === 0 ? (
            <div className="rounded-xl border border-dashed border-editor-border bg-editor-card/60 px-3 py-6 text-center text-sm text-editor-text-muted">
              No uploaded tracks match "{search}".
            </div>
          ) : (
            filteredMusicAssets.map((asset) => {
              const src = assetUrls[asset.id];
              const isPlaying = playingId === `asset:${asset.id}`;
              const canPreview = Boolean(src);
              return (
                <div
                  key={asset.id}
                  className="flex items-center gap-3 rounded-xl border border-editor-border bg-editor-card px-3 py-3 transition hover:border-primary/35"
                  onMouseEnter={() => {
                    if (focusedAssetRef) focusedAssetRef.current = { id: asset.id, category: "music" };
                  }}
                  onMouseLeave={() => {
                    if (focusedAssetRef && focusedAssetRef.current?.id === asset.id) focusedAssetRef.current = null;
                  }}
                >
                  <button
                    type="button"
                    onClick={() => {
                      if (src) {
                        void handlePlay(`asset:${asset.id}`, src);
                      }
                    }}
                    disabled={!canPreview}
                    className={cn(
                      "flex h-10 w-10 shrink-0 items-center justify-center rounded-lg border transition disabled:opacity-40",
                      isPlaying
                        ? "border-primary/50 bg-primary text-primary-foreground"
                        : "border-editor-border bg-editor-control text-foreground hover:border-primary/40 hover:bg-editor-control-hover",
                    )}
                    title={isPlaying ? "Stop preview" : "Preview audio"}
                  >
                    {isPlaying ? (
                      <div className="h-3 w-3 rounded-sm bg-primary-foreground" />
                    ) : (
                      <Play className="ml-0.5 h-4 w-4" />
                    )}
                  </button>

                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-medium text-foreground">
                      {asset.filename}
                    </p>
                    <p className="text-xs text-editor-text-muted">
                      {asset.content_type || "audio file"}
                    </p>
                  </div>

                  <button
                    type="button"
                    onClick={() => {
                      if (src) {
                        void onInsertAudio(src, asset.filename);
                      }
                    }}
                    disabled={!canPreview}
                    className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg border border-editor-border bg-editor-control text-foreground transition hover:border-primary/40 hover:bg-editor-control-hover disabled:opacity-40"
                    title="Add to timeline"
                  >
                    <Plus className="h-4 w-4" />
                  </button>
                </div>
              );
            })
          )}
        </div>
      ) : null}

      {audioTab === "upload" ? (
        <div className="space-y-3">
          <div
            onClick={() => !uploading && fileInputRef.current?.click()}
            className={cn(
              "cursor-pointer rounded-xl border-2 border-dashed border-editor-border bg-editor-card/60 px-4 py-10 text-center transition hover:border-primary/40 hover:bg-primary/5",
              uploading && "pointer-events-none opacity-60",
            )}
          >
            {uploading ? (
              <>
                <Loader2 className="mx-auto h-8 w-8 animate-spin text-primary" />
                <p className="mt-3 text-sm font-medium text-foreground">
                  Uploading...
                </p>
              </>
            ) : (
              <>
                <Upload className="mx-auto h-8 w-8 text-muted-foreground/30" />
                <p className="mt-3 text-sm font-medium text-foreground">
                  Click to upload
                </p>
                <p className="mt-1 text-xs text-editor-text-muted">
                  MP3, WAV, and other audio files supported
                </p>
              </>
            )}
          </div>
          <input
            ref={fileInputRef}
            type="file"
            accept="audio/*"
            className="hidden"
            onChange={(event) => void handleUpload(event)}
          />
        </div>
      ) : null}
    </div>
  );
}
