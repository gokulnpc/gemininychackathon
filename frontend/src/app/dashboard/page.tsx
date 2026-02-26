"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  AlertCircle,
  CheckCircle2,
  Coins,
  Download,
  Filter,
  Grid3X3,
  LayoutDashboard,
  List,
  Loader2,
  LogOut,
  MoreVertical,
  Play,
  Search,
  Settings,
  Share2,
  Trash2,
  User,
  XCircle,
} from "lucide-react";
import { motion } from "framer-motion";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";

// ── Config ─────────────────────────────────────────────────────────────────
const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

// ── Types ───────────────────────────────────────────────────────────────────
interface Project {
  project_id: string;
  created_at: string;
  status: "completed" | "failed";
  series_id: string | null;
  series_name: string | null;
  hook: string | null;
  scenes_count: number;
  voiceover_duration: number | null;
  platforms: string[];
  video_urls: Record<string, string>;
  error: string | null;
}

// ── Helpers ─────────────────────────────────────────────────────────────────
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

function title(p: Project): string {
  return p.hook ?? p.series_name ?? p.project_id.slice(0, 8);
}

const GRADIENTS = [
  "from-purple-900 to-indigo-900",
  "from-rose-900 to-pink-900",
  "from-amber-900 to-orange-900",
  "from-teal-900 to-emerald-900",
  "from-sky-900 to-blue-900",
  "from-fuchsia-900 to-violet-900",
];
function gradient(id: string) {
  return GRADIENTS[(id.charCodeAt(0) + id.charCodeAt(1)) % GRADIENTS.length];
}

function streamUrl(projectId: string, platform: string) {
  return `${API}/api/v1/projects/${projectId}/stream/${platform}`;
}

function thumbnailUrl(projectId: string, platform: string) {
  return `${API}/api/v1/projects/${projectId}/thumbnail?platform=${platform}`;
}

// ── Page ────────────────────────────────────────────────────────────────────
export default function DashboardPage() {
  const router = useRouter();

  const [projects, setProjects] = useState<Project[]>([]);
  const [loading, setLoading] = useState(true);
  const [fetchError, setFetchError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [viewMode, setViewMode] = useState<"grid" | "list">("grid");
  const [selected, setSelected] = useState<Project | null>(null);

  // Publish flow
  type PlatformKey = "youtube" | "instagram" | "tiktok";
  type PublishResult = { platform: string; status: string; post_url?: string; error?: string };
  const [publishing, setPublishing] = useState(false);
  const [publishPlatforms, setPublishPlatforms] = useState<Record<PlatformKey, boolean>>({
    youtube: false,
    instagram: true,
    tiktok: true,
  });
  const [publishLoading, setPublishLoading] = useState(false);
  const [publishResults, setPublishResults] = useState<PublishResult[] | null>(null);

  function togglePlatform(p: PlatformKey) {
    setPublishPlatforms((prev) => ({ ...prev, [p]: !prev[p] }));
  }

  async function handlePublish(projectId: string) {
    const platforms = (Object.keys(publishPlatforms) as PlatformKey[]).filter(
      (p) => publishPlatforms[p]
    );
    if (!platforms.length) return;
    setPublishLoading(true);
    setPublishResults(null);
    try {
      const resp = await fetch(`${API}/api/v1/projects/${projectId}/publish`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ platforms }),
      });
      const data = await resp.json();
      setPublishResults(data.posts ?? []);
    } catch (e) {
      setPublishResults([{ platform: "all", status: "failed", error: String(e) }]);
    } finally {
      setPublishLoading(false);
    }
  }

  function openShare() {
    setPublishing(true);
    setPublishResults(null);
  }

  function closeShare() {
    setPublishing(false);
    setPublishResults(null);
  }

  // Fetch projects on mount
  useEffect(() => {
    fetch(`${API}/api/v1/projects`)
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then((d) => setProjects(d.projects ?? []))
      .catch((e) => setFetchError(e.message))
      .finally(() => setLoading(false));
  }, []);

  async function deleteProject(id: string) {
    await fetch(`${API}/api/v1/projects/${id}`, { method: "DELETE" });
    setProjects((prev) => prev.filter((p) => p.project_id !== id));
    if (selected?.project_id === id) setSelected(null);
  }

  const filtered = projects.filter((p) =>
    title(p).toLowerCase().includes(search.toLowerCase())
  );

  return (
    <div className="min-h-screen">
      {/* ── Header ──────────────────────────────────────────────────────── */}
      <header className="flex items-center justify-between px-8 py-6 border-b border-[#F0E8E4]">
        <button
          onClick={() => router.push("/welcome")}
          className="hover:opacity-80 transition-opacity"
        >
          <img src="/Logo_ContentFactory.png" alt="Content Factory" className="h-6" />
        </button>

        <div className="flex items-center gap-4">
          <Button
            onClick={() => router.push("/create")}
            className="rounded-full px-6 bg-[#B08D9F] hover:bg-[#C9A9B8] text-white"
          >
            Create New
          </Button>

          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <button className="flex items-center gap-3 bg-white rounded-full px-4 py-2 shadow-sm border border-[#F0E8E4] hover:shadow-md transition-shadow">
                <Avatar className="w-8 h-8">
                  <AvatarImage src="/Avatar.png" alt="An Tran" />
                  <AvatarFallback className="bg-[#B08D9F] text-white text-sm">AT</AvatarFallback>
                </Avatar>
                <span className="text-sm font-medium text-[#1A1A1A]">An Tran</span>
              </button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-64">
              <div className="px-3 py-3 bg-[#B08D9F]/5 rounded-lg mx-2 mt-2 mb-2">
                <div className="flex items-center gap-2 mb-1">
                  <Coins className="w-4 h-4 text-[#B08D9F]" />
                  <span className="text-sm font-medium text-[#1A1A1A]">Credits</span>
                </div>
                <p className="text-2xl font-semibold text-[#1A1A1A]">1,250</p>
                <p className="text-xs text-[#9B9B9B] mt-0.5">~25 videos remaining</p>
              </div>
              <DropdownMenuSeparator />
              <DropdownMenuItem onClick={() => router.push("/dashboard")} className="cursor-pointer">
                <LayoutDashboard className="w-4 h-4 mr-2" /> Dashboard
              </DropdownMenuItem>
              <DropdownMenuItem className="cursor-pointer">
                <User className="w-4 h-4 mr-2" /> Profile
              </DropdownMenuItem>
              <DropdownMenuItem className="cursor-pointer">
                <Settings className="w-4 h-4 mr-2" /> Settings
              </DropdownMenuItem>
              <DropdownMenuSeparator />
              <DropdownMenuItem
                onClick={() => router.push("/login")}
                className="cursor-pointer text-red-600"
              >
                <LogOut className="w-4 h-4 mr-2" /> Sign out
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </header>

      {/* ── Main ────────────────────────────────────────────────────────── */}
      <main className="max-w-7xl mx-auto px-8 py-8">
        {/* Title */}
        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} className="mb-8">
          <h1 className="text-3xl font-medium text-[#1A1A1A] mb-2">Your Videos</h1>
          <p className="text-[#6B6B6B]">
            You have <span className="font-medium text-[#1A1A1A]">{projects.length}</span> videos in your library
          </p>
        </motion.div>

        {/* Search + view toggle */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.1 }}
          className="flex items-center justify-between mb-8"
        >
          <div className="flex items-center gap-4 flex-1">
            <div className="relative flex-1 max-w-md">
              <Search className="absolute left-4 top-1/2 -translate-y-1/2 w-5 h-5 text-[#9B9B9B]" />
              <Input
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Search videos..."
                className="pl-12 h-12 rounded-xl border-[#E8E0DC] bg-white focus:border-[#B08D9F] focus:ring-[#B08D9F]/20"
              />
            </div>
            <Button variant="outline" className="h-12 px-4 rounded-xl border-[#E8E0DC]">
              <Filter className="w-4 h-4 mr-2" /> Filter
            </Button>
          </div>

          <div className="flex items-center gap-2 bg-white rounded-xl border border-[#E8E0DC] p-1">
            <button
              onClick={() => setViewMode("grid")}
              className={`p-2 rounded-lg transition-colors ${viewMode === "grid" ? "bg-gray-100" : "hover:bg-gray-50"}`}
            >
              <Grid3X3 className="w-5 h-5 text-[#6B6B6B]" />
            </button>
            <button
              onClick={() => setViewMode("list")}
              className={`p-2 rounded-lg transition-colors ${viewMode === "list" ? "bg-gray-100" : "hover:bg-gray-50"}`}
            >
              <List className="w-5 h-5 text-[#6B6B6B]" />
            </button>
          </div>
        </motion.div>

        {/* States: loading / error / empty */}
        {loading && (
          <div className="flex items-center justify-center py-24 text-[#9B9B9B]">
            <Loader2 className="w-6 h-6 animate-spin mr-3" /> Loading your videos…
          </div>
        )}
        {!loading && fetchError && (
          <div className="flex items-center justify-center py-24 text-red-500 gap-2">
            <AlertCircle className="w-5 h-5" /> Failed to load: {fetchError}
          </div>
        )}
        {!loading && !fetchError && filtered.length === 0 && (
          <div className="flex flex-col items-center justify-center py-24 text-[#9B9B9B]">
            <p className="text-lg mb-4">No videos yet.</p>
            <Button
              onClick={() => router.push("/create")}
              className="rounded-full px-6 bg-[#B08D9F] hover:bg-[#C9A9B8] text-white"
            >
              Create your first video
            </Button>
          </div>
        )}

        {/* Grid / list */}
        {!loading && !fetchError && filtered.length > 0 && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: 0.2 }}
            className={viewMode === "grid" ? "grid grid-cols-4 gap-6" : "space-y-4"}
          >
            {filtered.map((project, index) => {
              const t = title(project);
              const platform = project.platforms[0] ?? "master";
              const ready = project.status === "completed";

              return (
                <motion.div
                  key={project.project_id}
                  initial={{ opacity: 0, y: 20 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: 0.3 + index * 0.05 }}
                  className={`group bg-white rounded-2xl border border-[#E8E0DC] overflow-hidden transition-all duration-200 hover:shadow-md hover:border-[#B08D9F]/30 ${
                    viewMode === "list" ? "flex items-center gap-4 p-4" : ""
                  }`}
                >
                  {/* Thumbnail */}
                  <div
                    className={`relative overflow-hidden bg-gradient-to-br ${gradient(project.project_id)} ${
                      viewMode === "grid" ? "aspect-[9/16]" : "w-32 h-20 rounded-xl flex-shrink-0"
                    }`}
                  >
                    {ready ? (
                      <>
                        <img
                          src={thumbnailUrl(project.project_id, platform)}
                          alt={t}
                          className="absolute inset-0 w-full h-full object-cover"
                          onError={(e) => { (e.target as HTMLImageElement).style.display = "none"; }}
                        />
                        <div className="absolute inset-0 bg-black/30 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center">
                          <button
                            onClick={() => setSelected(project)}
                            className="w-12 h-12 rounded-full bg-white/90 flex items-center justify-center hover:bg-white transition-colors"
                          >
                            <Play className="w-5 h-5 text-[#1A1A1A] ml-0.5" />
                          </button>
                        </div>
                      </>
                    ) : (
                      <div className="absolute inset-0 flex items-center justify-center">
                        <AlertCircle className="w-8 h-8 text-red-400 opacity-70" />
                      </div>
                    )}
                    <div className="absolute bottom-2 right-2 px-2 py-1 bg-black/60 rounded text-xs text-white">
                      {project.scenes_count} scenes
                    </div>
                  </div>

                  {/* Info */}
                  <div className={viewMode === "grid" ? "p-4" : "flex-1 min-w-0"}>
                    <div className="flex items-start justify-between">
                      <div className="min-w-0 flex-1">
                        <h3 className="text-sm font-medium text-[#1A1A1A] mb-1 line-clamp-2">{t}</h3>
                        <p className="text-xs text-[#9B9B9B]">{timeAgo(project.created_at)}</p>
                      </div>

                      {viewMode === "grid" && (
                        <DropdownMenu>
                          <DropdownMenuTrigger asChild>
                            <button className="p-1 rounded-lg hover:bg-gray-100 opacity-0 group-hover:opacity-100 transition-opacity flex-shrink-0 ml-1">
                              <MoreVertical className="w-4 h-4 text-[#9B9B9B]" />
                            </button>
                          </DropdownMenuTrigger>
                          <DropdownMenuContent align="end" className="w-40">
                            {ready && (
                              <DropdownMenuItem asChild>
                                <a href={streamUrl(project.project_id, platform)} target="_blank" rel="noreferrer">
                                  <Play className="w-4 h-4 mr-2" /> Preview
                                </a>
                              </DropdownMenuItem>
                            )}
                            {ready && (
                              <DropdownMenuItem asChild>
                                <a href={streamUrl(project.project_id, platform)} download>
                                  <Download className="w-4 h-4 mr-2" /> Download
                                </a>
                              </DropdownMenuItem>
                            )}
                            <DropdownMenuItem>
                              <Share2 className="w-4 h-4 mr-2" /> Share
                            </DropdownMenuItem>
                            <DropdownMenuItem
                              className="text-red-600"
                              onClick={() => deleteProject(project.project_id)}
                            >
                              <Trash2 className="w-4 h-4 mr-2" /> Delete
                            </DropdownMenuItem>
                          </DropdownMenuContent>
                        </DropdownMenu>
                      )}
                    </div>

                    {viewMode === "list" && (
                      <div className="flex items-center gap-3 mt-2">
                        <span className="text-xs text-[#9B9B9B]">{project.platforms.join(", ")}</span>
                        <span className={`text-xs px-2 py-0.5 rounded-full ${
                          ready ? "bg-green-100 text-green-600" : "bg-red-100 text-red-500"
                        }`}>
                          {ready ? "ready" : "failed"}
                        </span>
                      </div>
                    )}
                  </div>

                  {/* List actions */}
                  {viewMode === "list" && ready && (
                    <div className="flex items-center gap-2 flex-shrink-0">
                      <Button variant="ghost" size="sm" asChild>
                        <a href={streamUrl(project.project_id, platform)} target="_blank" rel="noreferrer">
                          <Play className="w-4 h-4 mr-2" /> Preview
                        </a>
                      </Button>
                      <Button variant="ghost" size="sm" asChild>
                        <a href={streamUrl(project.project_id, platform)} download>
                          <Download className="w-4 h-4 mr-2" /> Download
                        </a>
                      </Button>
                    </div>
                  )}
                </motion.div>
              );
            })}
          </motion.div>
        )}
      </main>

      {/* ── Video dialog ─────────────────────────────────────────────────── */}
      <Dialog open={!!selected} onOpenChange={() => { setSelected(null); closeShare(); }}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>{selected ? title(selected) : ""}</DialogTitle>
          </DialogHeader>

          {selected && (() => {
            const platform = selected.platforms[0] ?? "master";
            const src = streamUrl(selected.project_id, platform);
            return (
              <>
                <div className="aspect-[9/16] max-h-[60vh] bg-gray-900 rounded-xl overflow-hidden">
                  <video key={src} src={src} controls className="w-full h-full object-contain" />
                </div>
                <div className="flex items-center justify-between">
                  <div className="space-y-1">
                    <p className="text-sm text-[#9B9B9B]">Scenes: {selected.scenes_count}</p>
                    <p className="text-sm text-[#9B9B9B]">Created: {timeAgo(selected.created_at)}</p>
                    <p className="text-sm text-[#9B9B9B]">Platforms: {selected.platforms.join(", ")}</p>
                  </div>
                  <div className="flex gap-2 flex-wrap justify-end">
                    {selected.platforms.map((p) => (
                      <Button key={p} variant="outline" asChild>
                        <a href={streamUrl(selected.project_id, p)} target="_blank" rel="noreferrer">
                          <Download className="w-4 h-4 mr-2" />
                          {p.replace("_", " ")}
                        </a>
                      </Button>
                    ))}
                    {!publishing && (
                      <Button className="bg-[#B08D9F] hover:bg-[#C9A9B8]" onClick={openShare}>
                        <Share2 className="w-4 h-4 mr-2" /> Share
                      </Button>
                    )}
                  </div>
                </div>

                {/* ── Publish panel ─────────────────────────────────────── */}
                {publishing && (
                  <div className="p-4 bg-gray-50 rounded-xl border border-[#E8E0DC] space-y-4">
                    <p className="text-sm font-medium text-[#1A1A1A]">Publish to</p>

                    {/* Platform toggles */}
                    <div className="flex gap-3">
                      {(
                        [
                          { key: "youtube" as PlatformKey, label: "YouTube" },
                          { key: "instagram" as PlatformKey, label: "Instagram" },
                          { key: "tiktok" as PlatformKey, label: "TikTok" },
                        ]
                      ).map(({ key, label }) => (
                        <button
                          key={key}
                          onClick={() => togglePlatform(key)}
                          className={`flex-1 py-2 px-3 rounded-lg border text-sm font-medium transition-colors ${
                            publishPlatforms[key]
                              ? "bg-[#B08D9F]/10 border-[#B08D9F] text-[#B08D9F]"
                              : "bg-white border-[#E8E0DC] text-[#9B9B9B] hover:border-[#B08D9F]/50"
                          }`}
                        >
                          {label}
                        </button>
                      ))}
                    </div>

                    {/* Per-platform results */}
                    {publishResults && (
                      <div className="space-y-1.5">
                        {publishResults.map((r) => (
                          <div key={r.platform} className="flex items-center gap-2 text-sm">
                            {r.status === "success" ? (
                              <CheckCircle2 className="w-4 h-4 text-green-500 flex-shrink-0" />
                            ) : (
                              <XCircle className="w-4 h-4 text-red-500 flex-shrink-0" />
                            )}
                            <span className="capitalize font-medium">{r.platform}</span>
                            {r.post_url && (
                              <a
                                href={r.post_url}
                                target="_blank"
                                rel="noreferrer"
                                className="text-[#B08D9F] underline text-xs ml-auto"
                              >
                                View post
                              </a>
                            )}
                            {r.error && (
                              <span className="text-red-400 text-xs ml-auto truncate max-w-[140px]" title={r.error}>
                                {r.error}
                              </span>
                            )}
                          </div>
                        ))}
                      </div>
                    )}

                    {/* Actions */}
                    <div className="flex gap-2">
                      <Button
                        className="bg-[#B08D9F] hover:bg-[#C9A9B8] flex-1"
                        disabled={
                          publishLoading ||
                          !Object.values(publishPlatforms).some(Boolean)
                        }
                        onClick={() => handlePublish(selected.project_id)}
                      >
                        {publishLoading ? (
                          <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                        ) : (
                          <Share2 className="w-4 h-4 mr-2" />
                        )}
                        {publishLoading ? "Publishing…" : "Publish"}
                      </Button>
                      <Button variant="outline" onClick={closeShare} disabled={publishLoading}>
                        Cancel
                      </Button>
                    </div>
                  </div>
                )}
              </>
            );
          })()}
        </DialogContent>
      </Dialog>
    </div>
  );
}
