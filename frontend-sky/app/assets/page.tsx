"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import {
  AlertCircle,
  Image as ImageIcon,
  Loader2,
  Mic,
  Music,
  Trash2,
  Upload,
  FileAudio,
} from "lucide-react";
import { motion } from "framer-motion";
import { Button } from "@/components/ui/button";
import { AppSidebar } from "@/components/app-sidebar";
import { useSidebar } from "@/context/SidebarContext";
import { cn } from "@/lib/utils";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

type Category = "images" | "music" | "voice_memos";

interface Asset {
  id: string;
  filename: string;
  content_type: string;
  uploaded_at: string;
  gcs_key: string;
  size_bytes: number;
}

const TABS: { key: Category; label: string; icon: typeof ImageIcon; accept: string }[] = [
  { key: "images", label: "Images", icon: ImageIcon, accept: "image/jpeg,image/png,image/webp" },
  { key: "music", label: "Music", icon: Music, accept: "audio/mpeg,audio/wav,audio/mp4" },
  { key: "voice_memos", label: "Voice Memos", icon: Mic, accept: "audio/mpeg,audio/wav,audio/mp4,audio/webm" },
];

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function timeAgo(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const m = Math.floor(diff / 60_000);
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  const d = Math.floor(h / 24);
  if (d < 7) return `${d}d ago`;
  return new Date(iso).toLocaleDateString();
}

export default function AssetsPage() {
  const router = useRouter();
  const { isCollapsed } = useSidebar();
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [category, setCategory] = useState<Category>("images");
  const [assets, setAssets] = useState<Asset[]>([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Fetch assets when category changes
  useEffect(() => {
    setLoading(true);
    setError(null);
    fetch(`${API}/api/v1/assets?category=${category}`)
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then((d) => setAssets(d.assets ?? []))
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [category]);

  async function handleUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;

    setUploading(true);
    setError(null);

    const formData = new FormData();
    formData.append("file", file);
    formData.append("category", category);

    try {
      const resp = await fetch(`${API}/api/v1/assets/upload`, {
        method: "POST",
        body: formData,
      });
      if (!resp.ok) {
        const detail = await resp.json().catch(() => ({}));
        throw new Error(detail.detail || `Upload failed (HTTP ${resp.status})`);
      }
      const newAsset: Asset = await resp.json();
      setAssets((prev) => [newAsset, ...prev]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed");
    } finally {
      setUploading(false);
      // Reset file input
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  }

  async function handleDelete(assetId: string) {
    try {
      await fetch(`${API}/api/v1/assets/${assetId}?category=${category}`, {
        method: "DELETE",
      });
      setAssets((prev) => prev.filter((a) => a.id !== assetId));
    } catch (err) {
      setError("Failed to delete asset");
    }
  }

  // Get URL for image thumbnail preview
  function assetUrl(assetId: string) {
    return `${API}/api/v1/assets/${assetId}/url?category=${category}`;
  }

  const currentTab = TABS.find((t) => t.key === category)!;

  return (
    <div className="flex min-h-screen bg-[#2B2B2B]">
      <AppSidebar />

      <div
        className={cn(
          "flex-1 flex flex-col min-h-screen transition-all duration-300",
          isCollapsed ? "ml-[80px]" : "ml-[280px]"
        )}
      >
        <main className="max-w-5xl mx-auto px-8 py-8 w-full">
          {/* Header */}
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            className="mb-8"
          >
            <h1 className="text-3xl font-medium text-white mb-2">My Assets</h1>
            <p className="text-white/50">
              Upload and manage your images, music, and voice memos
            </p>
          </motion.div>

          {/* Tabs + Upload */}
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.1 }}
            className="flex items-center justify-between mb-8"
          >
            <div className="flex items-center gap-2 bg-[#333333] rounded-xl border border-white/10 p-1">
              {TABS.map((tab) => {
                const Icon = tab.icon;
                const isActive = category === tab.key;
                return (
                  <button
                    key={tab.key}
                    onClick={() => setCategory(tab.key)}
                    className={cn(
                      "flex items-center gap-2 px-4 py-2.5 rounded-lg text-sm font-medium transition-colors",
                      isActive
                        ? "bg-[#5a9ab5] text-white"
                        : "text-white/50 hover:text-white hover:bg-white/10"
                    )}
                  >
                    <Icon className="w-4 h-4" />
                    {tab.label}
                  </button>
                );
              })}
            </div>

            <div>
              <input
                ref={fileInputRef}
                type="file"
                accept={currentTab.accept}
                onChange={handleUpload}
                className="hidden"
              />
              <Button
                onClick={() => fileInputRef.current?.click()}
                disabled={uploading}
                className="rounded-full px-6 bg-[#5a9ab5] hover:bg-[#7ab0c8] text-white"
              >
                {uploading ? (
                  <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                ) : (
                  <Upload className="w-4 h-4 mr-2" />
                )}
                {uploading ? "Uploading..." : "Upload"}
              </Button>
            </div>
          </motion.div>

          {/* Error banner */}
          {error && (
            <div className="flex items-center gap-2 text-red-400 bg-red-500/10 border border-red-500/20 rounded-xl px-4 py-3 mb-6">
              <AlertCircle className="w-4 h-4 shrink-0" />
              <span className="text-sm">{error}</span>
            </div>
          )}

          {/* Loading */}
          {loading && (
            <div className="flex items-center justify-center py-24 text-white/40">
              <Loader2 className="w-6 h-6 animate-spin mr-3" /> Loading assets...
            </div>
          )}

          {/* Empty state */}
          {!loading && !error && assets.length === 0 && (
            <div className="flex flex-col items-center justify-center py-24 text-white/40">
              <currentTab.icon className="w-12 h-12 mb-4 opacity-30" />
              <p className="text-lg mb-4">
                No {currentTab.label.toLowerCase()} uploaded yet
              </p>
              <Button
                onClick={() => fileInputRef.current?.click()}
                className="rounded-full px-6 bg-[#5a9ab5] hover:bg-[#7ab0c8] text-white"
              >
                <Upload className="w-4 h-4 mr-2" /> Upload your first{" "}
                {category === "images"
                  ? "image"
                  : category === "music"
                    ? "track"
                    : "memo"}
              </Button>
            </div>
          )}

          {/* Asset Grid */}
          {!loading && assets.length > 0 && (
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ delay: 0.2 }}
              className={
                category === "images"
                  ? "grid grid-cols-4 gap-4"
                  : "grid grid-cols-2 gap-4"
              }
            >
              {assets.map((asset, index) => (
                <AssetCard
                  key={asset.id}
                  asset={asset}
                  category={category}
                  index={index}
                  onDelete={handleDelete}
                />
              ))}
            </motion.div>
          )}
        </main>
      </div>
    </div>
  );
}

function AssetCard({
  asset,
  category,
  index,
  onDelete,
}: {
  asset: Asset;
  category: Category;
  index: number;
  onDelete: (id: string) => void;
}) {
  const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
  const [imageUrl, setImageUrl] = useState<string | null>(null);

  // For images, fetch the presigned URL for preview
  useEffect(() => {
    if (category !== "images") return;
    fetch(`${API}/api/v1/assets/${asset.id}/url?category=images`)
      .then((r) => r.json())
      .then((d) => setImageUrl(d.url))
      .catch(() => {});
  }, [asset.id, category]);

  if (category === "images") {
    return (
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.05 * index }}
        className="group relative bg-[#333333] rounded-2xl border border-white/10 overflow-hidden transition-all duration-200 hover:border-[#5a9ab5]/40"
      >
        <div className="aspect-square bg-[#2a2a2a] flex items-center justify-center">
          {imageUrl ? (
            <img
              src={imageUrl}
              alt={asset.filename}
              className="w-full h-full object-cover"
            />
          ) : (
            <ImageIcon className="w-8 h-8 text-white/20" />
          )}
        </div>
        <div className="p-3">
          <p className="text-xs text-white font-medium truncate">
            {asset.filename}
          </p>
          <p className="text-xs text-white/40">
            {formatSize(asset.size_bytes)} &middot; {timeAgo(asset.uploaded_at)}
          </p>
        </div>
        <button
          onClick={() => onDelete(asset.id)}
          className="absolute top-2 right-2 p-1.5 rounded-lg bg-black/50 text-white/60 hover:text-red-400 hover:bg-black/70 opacity-0 group-hover:opacity-100 transition-all"
        >
          <Trash2 className="w-4 h-4" />
        </button>
      </motion.div>
    );
  }

  // Music / Voice Memos
  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: 0.05 * index }}
      className="group bg-[#333333] rounded-2xl border border-white/10 p-4 flex items-center gap-4 transition-all duration-200 hover:border-[#5a9ab5]/40"
    >
      <div className="w-12 h-12 rounded-xl bg-[#1A1A1A] flex items-center justify-center border border-white/5 shrink-0">
        <FileAudio className="w-5 h-5 text-[#5a9ab5]" />
      </div>
      <div className="flex-1 min-w-0">
        <p className="text-sm text-white font-medium truncate">
          {asset.filename}
        </p>
        <p className="text-xs text-white/40">
          {formatSize(asset.size_bytes)} &middot; {timeAgo(asset.uploaded_at)}
        </p>
      </div>
      <button
        onClick={() => onDelete(asset.id)}
        className="p-2 rounded-lg text-white/40 hover:text-red-400 hover:bg-white/10 opacity-0 group-hover:opacity-100 transition-all shrink-0"
      >
        <Trash2 className="w-4 h-4" />
      </button>
    </motion.div>
  );
}
