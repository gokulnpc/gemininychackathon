"use client";

import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type ChangeEvent,
} from "react";
import {
  Clapperboard,
  Film,
  Loader2,
  Plus,
  Search,
  Trash2,
  Upload,
  type LucideIcon,
} from "lucide-react";

import type { Asset } from "@/components/editor/types";
import apiClient from "@/lib/apiClient";
import { cn } from "@/lib/utils";

type MediaTab = "my-assets" | "upload" | "public";

interface VideoPanelProps {
  onInsertImage: (src: string, label: string) => void | Promise<void>;
}

export function VideoPanel({ onInsertImage }: VideoPanelProps) {
  const [videoTab, setVideoTab] = useState<MediaTab>("public");
  const [search, setSearch] = useState("");
  const [assets, setAssets] = useState<Asset[]>([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [urls, setUrls] = useState<Record<string, string>>({});
  const fileInputRef = useRef<HTMLInputElement>(null);

  const fetchAssets = useCallback(async () => {
    try {
      setLoading(true);
      const data = (
        await apiClient.get("/api/v1/assets", {
          params: { category: "images" },
        })
      ).data as Asset[] | { assets: Asset[] };
      const allAssets: Asset[] = Array.isArray(data)
        ? data
        : ((data as { assets: Asset[] }).assets ?? []);
      const videos = allAssets.filter((asset) =>
        asset.content_type.startsWith("video/"),
      );
      setAssets(videos);
      const urlMap: Record<string, string> = {};
      await Promise.all(
        videos.map(async (asset) => {
          try {
            const response = (
              await apiClient.get(`/api/v1/assets/${asset.id}/url`, {
                params: { category: "images" },
              })
            ).data as {
              url: string;
            };
            urlMap[asset.id] = response.url;
          } catch {
            // Skip asset URLs that fail to resolve.
          }
        }),
      );
      setUrls(urlMap);
    } catch (error) {
      console.warn(
        "[VideoPanel] Failed to list assets; using empty state.",
        error,
      );
      setAssets([]);
      setUrls({});
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void fetchAssets();
  }, [fetchAssets]);

  const handleUpload = useCallback(
    async (event: ChangeEvent<HTMLInputElement>) => {
      const file = event.target.files?.[0];
      if (!file) return;
      try {
        setUploading(true);
        const formData = new FormData();
        formData.append("file", file);
        await apiClient.post("/api/v1/assets/upload", formData, {
          params: { category: "images" },
          headers: { "Content-Type": "multipart/form-data" },
        });
        await fetchAssets();
        setVideoTab("my-assets");
      } catch (error) {
        console.error("[VideoPanel] Upload failed:", error);
      } finally {
        setUploading(false);
        if (fileInputRef.current) fileInputRef.current.value = "";
      }
    },
    [fetchAssets],
  );

  const handleDelete = useCallback(async (id: string) => {
    try {
      await apiClient.delete(`/api/v1/assets/${id}`, {
        params: { category: "images" },
      });
      setAssets((prev) => prev.filter((asset) => asset.id !== id));
    } catch (error) {
      console.error("[VideoPanel] Delete failed:", error);
    }
  }, []);

  const videoTabs: { key: MediaTab; label: string; icon: LucideIcon }[] = [
    { key: "public", label: "Public", icon: Film },
    { key: "my-assets", label: "Assets", icon: Clapperboard },
    { key: "upload", label: "Upload", icon: Upload },
  ];
  const filteredAssets = assets.filter((asset) =>
    asset.filename.toLowerCase().includes(search.toLowerCase()),
  );

  return (
    <div className="space-y-3">
      <div className="flex gap-1 rounded-lg border border-editor-border bg-editor-card p-1">
        {videoTabs.map((tab) => {
          const Icon = tab.icon;
          return (
            <button
              key={tab.key}
              type="button"
              onClick={() => setVideoTab(tab.key)}
              className={cn(
                "flex flex-1 items-center justify-center gap-1 rounded-md px-2 py-1.5 text-[11px] font-medium transition-all",
                videoTab === tab.key
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

      {videoTab === "public" ? (
        <div className="rounded-xl border border-dashed border-editor-border bg-editor-card/60 px-3 py-6 text-center">
          <Film className="mx-auto h-8 w-8 text-muted-foreground/25" />
          <p className="mt-2 text-sm text-editor-text-muted">
            Public videos coming soon
          </p>
        </div>
      ) : null}

      {videoTab === "my-assets" ? (
        <div className="space-y-3">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-editor-text-dim" />
            <input
              type="text"
              placeholder="Search videos..."
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              className="w-full rounded-xl border border-editor-border bg-editor-control py-2.5 pl-9 pr-3 text-sm text-foreground placeholder:text-muted-foreground focus:border-primary/50 focus:outline-none focus:ring-1 focus:ring-primary/30"
            />
          </div>
          {loading ? (
            <div className="flex items-center justify-center py-8">
              <Loader2 className="h-5 w-5 animate-spin text-editor-text-dim" />
            </div>
          ) : assets.length === 0 ? (
            <div className="rounded-xl border border-dashed border-editor-border bg-editor-card/60 px-3 py-6 text-center">
              <Film className="mx-auto h-8 w-8 text-muted-foreground/25" />
              <p className="mt-2 text-sm text-editor-text-muted">
                No videos yet.
              </p>
              <button
                type="button"
                onClick={() => setVideoTab("upload")}
                className="mt-3 rounded-lg bg-primary px-4 py-1.5 text-xs font-semibold text-primary-foreground transition hover:bg-primary/90"
              >
                Upload your first
              </button>
            </div>
          ) : filteredAssets.length === 0 ? (
            <div className="rounded-xl border border-dashed border-editor-border bg-editor-card/60 px-3 py-6 text-center">
              <Film className="mx-auto h-8 w-8 text-muted-foreground/25" />
              <p className="mt-2 text-sm text-editor-text-muted">
                No videos match "{search}".
              </p>
            </div>
          ) : (
            <div className="grid grid-cols-2 gap-2">
              {filteredAssets.map((asset) => (
                <div
                  key={asset.id}
                  className="group relative overflow-hidden rounded-xl border border-editor-border transition hover:border-primary/40"
                >
                  <div className="block w-full">
                    {urls[asset.id] ? (
                      <video
                        src={urls[asset.id]}
                        className="aspect-video w-full object-cover"
                        muted
                        preload="metadata"
                      />
                    ) : (
                      <div className="flex aspect-video items-center justify-center bg-editor-card">
                        <Film className="h-5 w-5 text-editor-text-dim" />
                      </div>
                    )}
                  </div>
                  <button
                    type="button"
                    onClick={() => {
                      const url = urls[asset.id];
                      if (url) void onInsertImage(url, asset.filename);
                    }}
                    className="absolute left-1 top-1 flex h-6 w-6 items-center justify-center rounded-full bg-editor-control text-foreground/80 opacity-0 transition group-hover:opacity-100 hover:bg-editor-control-hover hover:text-foreground"
                    title="Add to timeline"
                  >
                    <Plus className="h-3 w-3" />
                  </button>
                  <button
                    type="button"
                    onClick={() => void handleDelete(asset.id)}
                    className="absolute right-1 top-1 flex h-6 w-6 items-center justify-center rounded-full bg-editor-toolbar/95 text-red-400/70 opacity-0 transition group-hover:opacity-100 hover:text-red-400"
                    title="Delete"
                  >
                    <Trash2 className="h-3 w-3" />
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
      ) : null}

      {videoTab === "upload" ? (
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
                  Video files supported
                </p>
              </>
            )}
          </div>
          <input
            ref={fileInputRef}
            type="file"
            accept="video/*"
            className="hidden"
            onChange={(event) => void handleUpload(event)}
          />
        </div>
      ) : null}
    </div>
  );
}
