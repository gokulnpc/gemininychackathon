"use client";

import { useCallback, useEffect, useRef, useState, type ChangeEvent } from "react";
import { Clapperboard, Image as ImageIcon, Loader2, Plus, Search, Trash2, Upload } from "lucide-react";

import type { Asset } from "@/components/editor/types";
import apiClient from "@/lib/apiClient";
import { cn } from "@/lib/utils";

type MediaTab = "my-assets" | "upload" | "public";

const PUBLIC_IMAGES = [
  { id: "pub-1", label: "Mountain Lake", url: "https://images.unsplash.com/photo-1506744038136-46273834b3fb?w=576&h=1024&fit=crop" },
  { id: "pub-2", label: "City Skyline", url: "https://images.unsplash.com/photo-1477959858617-67f85cf4f1df?w=576&h=1024&fit=crop" },
  { id: "pub-3", label: "Ocean Waves", url: "https://images.unsplash.com/photo-1507525428034-b723cf961d3e?w=576&h=1024&fit=crop" },
  { id: "pub-4", label: "Forest Path", url: "https://images.unsplash.com/photo-1441974231531-c6227db76b6e?w=576&h=1024&fit=crop" },
  { id: "pub-5", label: "Sunset Clouds", url: "https://images.unsplash.com/photo-1495616811223-4d98c6e9c869?w=576&h=1024&fit=crop" },
  { id: "pub-6", label: "Neon Lights", url: "https://images.unsplash.com/photo-1514525253161-7a46d19cd819?w=576&h=1024&fit=crop" },
  { id: "pub-7", label: "Desert Dunes", url: "https://images.unsplash.com/photo-1509316975850-ff9c5deb0cd9?w=576&h=1024&fit=crop" },
  { id: "pub-8", label: "Abstract Gradient", url: "https://images.unsplash.com/photo-1557682250-33bd709cbe85?w=576&h=1024&fit=crop" },
];

interface MediaPanelProps {
  onInsertImage: (src: string, label: string) => void | Promise<void>;
}

export function MediaPanel({ onInsertImage }: MediaPanelProps) {
  const [mediaTab, setMediaTab] = useState<MediaTab>("my-assets");
  const [search, setSearch] = useState("");
  const [assets, setAssets] = useState<Asset[]>([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [urls, setUrls] = useState<Record<string, string>>({});
  const fileInputRef = useRef<HTMLInputElement>(null);

  const fetchAssets = useCallback(async () => {
    try {
      setLoading(true);
      const data = (await apiClient.get("/api/v1/assets", { params: { category: "images" } })).data as
        | Asset[]
        | { assets: Asset[] };
      const list: Asset[] = Array.isArray(data) ? data : (data as { assets: Asset[] }).assets ?? [];
      setAssets(list);
      const urlMap: Record<string, string> = {};
      await Promise.all(
        list.map(async (asset) => {
          try {
            const response = (await apiClient.get(`/api/v1/assets/${asset.id}/url`, { params: { category: "images" } })).data as {
              url: string;
            };
            urlMap[asset.id] = response.url;
          } catch {
            // Skip asset URLs that fail to resolve.
          }
        })
      );
      setUrls(urlMap);
    } catch (error) {
      console.warn("[MediaPanel] Failed to list assets; using empty state.", error);
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
        setMediaTab("my-assets");
      } catch (error) {
        console.error("[MediaPanel] Upload failed:", error);
      } finally {
        setUploading(false);
        if (fileInputRef.current) fileInputRef.current.value = "";
      }
    },
    [fetchAssets]
  );

  const handleDelete = useCallback(async (id: string) => {
    try {
      await apiClient.delete(`/api/v1/assets/${id}`, { params: { category: "images" } });
      setAssets((prev) => prev.filter((asset) => asset.id !== id));
    } catch (error) {
      console.error("[MediaPanel] Delete failed:", error);
    }
  }, []);

  const mediaTabs: { key: MediaTab; label: string; icon: typeof ImageIcon }[] = [
    { key: "my-assets", label: "My Assets", icon: Clapperboard },
    { key: "upload", label: "Upload", icon: Upload },
    { key: "public", label: "Public", icon: ImageIcon },
  ];
  const filteredAssets = assets.filter((asset) => asset.filename.toLowerCase().includes(search.toLowerCase()));

  return (
    <div className="space-y-3">
      <div className="flex gap-1 rounded-lg border border-editor-border bg-editor-card p-1">
        {mediaTabs.map((tab) => {
          const Icon = tab.icon;
          return (
            <button
              key={tab.key}
              type="button"
              onClick={() => setMediaTab(tab.key)}
              className={cn(
                "flex flex-1 items-center justify-center gap-1 rounded-md px-2 py-1.5 text-[11px] font-medium transition-all",
                mediaTab === tab.key
                  ? "bg-primary/18 text-primary shadow-sm"
                  : "bg-editor-control text-muted-foreground hover:bg-editor-control-hover hover:text-foreground"
              )}
            >
              <Icon className="h-3 w-3" />
              {tab.label}
            </button>
          );
        })}
      </div>

      {mediaTab === "my-assets" ? (
        <div className="space-y-3">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-editor-text-dim" />
            <input
              type="text"
              placeholder="Search images..."
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
              <ImageIcon className="mx-auto h-8 w-8 text-muted-foreground/25" />
              <p className="mt-2 text-sm text-editor-text-muted">No assets yet.</p>
              <button
                type="button"
                onClick={() => setMediaTab("upload")}
                className="mt-3 rounded-lg bg-primary px-4 py-1.5 text-xs font-semibold text-primary-foreground transition hover:bg-primary/90"
              >
                Upload your first
              </button>
            </div>
          ) : filteredAssets.length === 0 ? (
            <div className="rounded-xl border border-dashed border-editor-border bg-editor-card/60 px-3 py-6 text-center">
              <ImageIcon className="mx-auto h-8 w-8 text-muted-foreground/25" />
              <p className="mt-2 text-sm text-editor-text-muted">No images match "{search}".</p>
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
                      <img src={urls[asset.id]} alt={asset.filename} className="aspect-video w-full object-cover" loading="lazy" />
                    ) : (
                      <div className="flex aspect-video items-center justify-center bg-editor-card">
                        <ImageIcon className="h-5 w-5 text-editor-text-dim" />
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

      {mediaTab === "upload" ? (
        <div className="space-y-3">
          <div
            onClick={() => !uploading && fileInputRef.current?.click()}
            className={cn(
              "cursor-pointer rounded-xl border-2 border-dashed border-editor-border bg-editor-card/60 px-4 py-10 text-center transition hover:border-primary/40 hover:bg-primary/5",
              uploading && "pointer-events-none opacity-60"
            )}
          >
            {uploading ? (
              <>
                <Loader2 className="mx-auto h-8 w-8 animate-spin text-primary" />
                <p className="mt-3 text-sm font-medium text-foreground">Uploading...</p>
              </>
            ) : (
              <>
                <Upload className="mx-auto h-8 w-8 text-muted-foreground/30" />
                <p className="mt-3 text-sm font-medium text-foreground">Click to upload</p>
                <p className="mt-1 text-xs text-editor-text-muted">Images & videos supported</p>
              </>
            )}
          </div>
          <input ref={fileInputRef} type="file" accept="image/*" className="hidden" onChange={(event) => void handleUpload(event)} />
        </div>
      ) : null}

      {mediaTab === "public" ? (
        <div className="grid grid-cols-2 gap-2">
          {PUBLIC_IMAGES.map((image) => (
            <div
              key={image.id}
              className="group relative overflow-hidden rounded-xl border border-editor-border transition hover:border-primary/40 hover:ring-1 hover:ring-primary/20"
            >
              <img
                src={image.url}
                alt={image.label}
                className="aspect-video w-full object-cover transition-transform duration-300 group-hover:scale-110"
                loading="lazy"
              />
              <div className="absolute inset-0 bg-gradient-to-t from-black/80 via-transparent to-transparent" />
              <button
                type="button"
                onClick={() => void onInsertImage(image.url, image.label)}
                className="absolute left-1 top-1 flex h-6 w-6 items-center justify-center rounded-full bg-editor-control text-foreground/80 opacity-0 transition group-hover:opacity-100 hover:bg-editor-control-hover hover:text-foreground"
                title="Add to timeline"
              >
                <Plus className="h-3 w-3" />
              </button>
              <p className="absolute bottom-0 w-full truncate px-2 py-1.5 text-[10px] font-medium text-foreground">{image.label}</p>
            </div>
          ))}
        </div>
      ) : null}
    </div>
  );
}
