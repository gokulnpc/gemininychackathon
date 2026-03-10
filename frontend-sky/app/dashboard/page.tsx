"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  AlertCircle,
  CheckCircle2,
  Download,
  Filter,
  Grid3X3,
  List,
  Loader2,
  MoreVertical,
  Pencil,
  Play,
  Search,
  Share2,
  Trash2,
  XCircle,
} from "lucide-react";
import { motion } from "framer-motion";
import { UserMenu } from "@/components/shared/UserMenu";
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
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { AppSidebar } from "@/components/app-sidebar";
import { useSidebar } from "@/context/SidebarContext";
import { useAuth } from "@/context/AuthContext";
import { cn } from "@/lib/utils";
import apiClient from "@/lib/apiClient";

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

function streamUrl(projectId: string, platform: string, token: string | null) {
  const base = `${API}/api/v1/projects/${projectId}/stream/${platform}`;
  return token ? `${base}?token=${token}` : base;
}

function thumbnails(projectId: string, platform: string, token: string | null) {
  const base = `${API}/api/v1/projects/${projectId}/thumbnail?platform=${platform}`;
  return token ? `${base}&token=${token}` : base;
}

function StatusPill({ status }: { status: string }) {
  const config: Record<string, { label: string; className: string }> = {
    queued: { label: "Queued", className: "bg-blue-500/20 text-blue-300 border-blue-500/30" },
    generating_script: { label: "Scripting", className: "bg-blue-500/20 text-blue-300 border-blue-500/30" },
    script_ready: { label: "Script Ready", className: "bg-yellow-500/20 text-yellow-300 border-yellow-500/30" },
    generating_video: { label: "Generating", className: "bg-orange-500/20 text-orange-300 border-orange-500/30" },
    in_progress: { label: "Generating", className: "bg-orange-500/20 text-orange-300 border-orange-500/30" },
    completed: { label: "Completed", className: "bg-green-500/20 text-green-300 border-green-500/30" },
    failed: { label: "Failed", className: "bg-red-500/20 text-red-300 border-red-500/30" },
  };
  const { label, className } = config[status] ?? config.failed;
  return (
    <span className={cn("text-[10px] px-2 py-0.5 rounded-full border font-medium whitespace-nowrap", className)}>
      {label}
    </span>
  );
}

// ── Page ────────────────────────────────────────────────────────────────────
export default function DashboardPage() {
  const router = useRouter();
  const { isCollapsed } = useSidebar();
  const { user, idToken, loading: authLoading } = useAuth();

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
      const resp = await apiClient.post(`/api/v1/projects/${projectId}/publish`, { platforms });
      setPublishResults(resp.data.posts ?? []);
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
    if (authLoading || !user) return;

    apiClient.get("/api/v1/projects")
      .then((r) => setProjects(r.data.projects ?? []))
      .catch((e) => setFetchError(e.message))
      .finally(() => setLoading(false));
  }, [user, authLoading]);

  async function deleteProject(id: string) {
    await apiClient.delete(`/api/v1/projects/${id}`);
    setProjects((prev) => prev.filter((p) => p.project_id !== id));
    if (selected?.project_id === id) setSelected(null);
  }

  const filtered = projects
    .filter((p) => p.status === "completed")
    .filter((p) => title(p).toLowerCase().includes(search.toLowerCase()));

  return (
    <div className="flex min-h-screen bg-[#2B2B2B]">
      <AppSidebar />

      <div className={cn("flex-1 flex flex-col min-h-screen transition-all duration-300", isCollapsed ? "ml-[80px]" : "ml-[280px]")}>
        {/* ── Header ──────────────────────────────────────────────────────── */}
        <header className="flex items-center justify-between px-8 h-[80px] border-b border-white/10">
          <div /> {/* spacer */}

          <div className="flex items-center gap-4">
            <Button
              onClick={() => router.push("/create")}
              className="rounded-full px-6 bg-[#5a9ab5] hover:bg-[#7ab0c8] text-white"
            >
              Create New
            </Button>

            <UserMenu />
          </div>
        </header>

        {/* ── Main ────────────────────────────────────────────────────────── */}
        <main className="px-8 py-8 w-full">
          {/* Title */}
          <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} className="mb-8">
            <h1 className="text-3xl font-medium text-white mb-2">Your Videos</h1>
            <p className="text-white/50">
              You have <span className="font-medium text-white">{projects.length}</span> videos in your library
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
                <Search className="absolute left-4 top-1/2 -translate-y-1/2 w-5 h-5 text-white/30" />
                <Input
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  placeholder="Search videos..."
                  className="pl-12 h-12 rounded-xl bg-[#333333] border-white/10 text-white placeholder:text-white/30 focus:border-[#5a9ab5] focus:ring-[#5a9ab5]/20"
                />
              </div>
              <Button variant="outline" className="h-12 px-4 rounded-xl bg-transparent border-white/10 text-white/70 hover:bg-white/10 hover:text-white">
                <Filter className="w-4 h-4 mr-2" /> Filter
              </Button>
            </div>

            <div className="flex items-center gap-2 bg-[#333333] rounded-xl border border-white/10 p-1">
              <button
                onClick={() => setViewMode("grid")}
                className={`p-2 rounded-lg transition-colors ${viewMode === "grid" ? "bg-white/15" : "hover:bg-white/10"}`}
              >
                <Grid3X3 className="w-5 h-5 text-white/60" />
              </button>
              <button
                onClick={() => setViewMode("list")}
                className={`p-2 rounded-lg transition-colors ${viewMode === "list" ? "bg-white/15" : "hover:bg-white/10"}`}
              >
                <List className="w-5 h-5 text-white/60" />
              </button>
            </div>
          </motion.div>

          {/* States: loading / error / empty */}
          {loading && (
            <div className="flex items-center justify-center py-24 text-white/40">
              <Loader2 className="w-6 h-6 animate-spin mr-3" /> Loading your videos…
            </div>
          )}
          {!loading && fetchError && (
            <div className="flex items-center justify-center py-24 text-red-400 gap-2">
              <AlertCircle className="w-5 h-5" /> Failed to load: {fetchError}
            </div>
          )}
          {!loading && !fetchError && filtered.length === 0 && (
            <div className="flex flex-col items-center justify-center py-24 text-white/40">
              <p className="text-lg mb-4">No videos yet.</p>
              <Button
                onClick={() => router.push("/create")}
                className="rounded-full px-6 bg-[#5a9ab5] hover:bg-[#7ab0c8] text-white"
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
              className={viewMode === "grid" ? "grid grid-cols-5 gap-4" : "space-y-4"}
            >
              {filtered.map((project, index) => {
                const t = title(project);
                const platform = (project.platforms ?? [])[0] ?? "master";
                const ready = project.status === "completed";

                return (
                  <motion.div
                    key={project.project_id}
                    initial={{ opacity: 0, y: 20 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: 0.3 + index * 0.05 }}
                    className={cn(
                      "group relative transition-all duration-200",
                      viewMode === "list" ? "flex items-center gap-4 p-4 bg-[#333333] rounded-2xl border border-white/10" : ""
                    )}
                  >
                    {/* Thumbnail Container */}
                    <div
                      className={cn(
                        "relative overflow-hidden bg-[#1a1a1a] transition-all duration-300",
                        viewMode === "grid"
                          ? "aspect-9/16 rounded-2xl border border-white/10 group-hover:border-[#5a9ab5]/50 group-hover:shadow-xl cursor-pointer"
                          : "w-32 h-20 rounded-xl shrink-0"
                      )}
                      onClick={viewMode === "grid" ? () => setSelected(project) : undefined}
                    >
                      {ready ? (
                        <>
                          <img
                            src={thumbnails(project.project_id, platform, idToken)}
                            alt={t}
                            className="absolute inset-0 w-full h-full object-cover transition-transform duration-500 group-hover:scale-105"
                            onError={(e) => { (e.target as HTMLImageElement).style.display = "none"; }}
                          />
                          {/* Play overlay */}
                          <div className="absolute inset-0 bg-black/40 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center">
                            <div className="w-12 h-12 rounded-full bg-white/20 flex items-center justify-center backdrop-blur-sm">
                              <Play className="w-5 h-5 text-white ml-0.5 fill-white/20" />
                            </div>
                          </div>
                        </>
                      ) : (
                        <div className="absolute inset-0 flex items-center justify-center">
                          {project.status === "failed" ? (
                            <AlertCircle className="w-8 h-8 text-red-400 opacity-70" />
                          ) : (
                            <Loader2 className="w-8 h-8 text-[#5a9ab5] animate-spin opacity-50" />
                          )}
                        </div>
                      )}

                      {/* Top Left Badge */}
                      <div className="absolute top-2 left-2 pointer-events-none">
                        <StatusPill status={project.status} />
                      </div>

                      {/* Top Right Options (Grid) */}
                      {viewMode === "grid" && (
                        <div className="absolute top-2 right-2 opacity-0 group-hover:opacity-100 transition-opacity" onClick={(e) => e.stopPropagation()}>
                          <DropdownMenu>
                            <DropdownMenuTrigger asChild>
                              <button className="p-1.5 rounded-lg bg-black/60 text-white/70 hover:text-white hover:bg-black/80 transition-colors">
                                <MoreVertical className="w-4 h-4" />
                              </button>
                            </DropdownMenuTrigger>
                            <DropdownMenuContent align="end" className="w-40">
                              {ready && (
                                <DropdownMenuItem asChild>
                                  <a href={streamUrl(project.project_id, platform, idToken)} target="_blank" rel="noreferrer">
                                    <Play className="w-4 h-4 mr-2" /> Preview
                                  </a>
                                </DropdownMenuItem>
                              )}
                              {ready && (
                                <DropdownMenuItem asChild>
                                  <a href={streamUrl(project.project_id, platform, idToken)} download>
                                    <Download className="w-4 h-4 mr-2" /> Download
                                  </a>
                                </DropdownMenuItem>
                              )}
                              <DropdownMenuItem onClick={() => router.push(`/projects/${project.project_id}/edit`)}>
                                <Pencil className="w-4 h-4 mr-2" /> Edit project
                              </DropdownMenuItem>
                              <DropdownMenuItem onClick={openShare}>
                                <Share2 className="w-4 h-4 mr-2" /> Share
                              </DropdownMenuItem>
                              <DropdownMenuItem
                                className="text-red-400"
                                onClick={() => deleteProject(project.project_id)}
                              >
                                <Trash2 className="w-4 h-4 mr-2" /> Delete
                              </DropdownMenuItem>
                            </DropdownMenuContent>
                          </DropdownMenu>
                        </div>
                      )}

                      <div className="absolute bottom-2 right-2 px-2 py-1 bg-black/60 rounded text-[10px] text-white/70">
                        {project.scenes_count}s
                      </div>
                    </div>

                    {/* Info */}
                    <div className={cn(
                      viewMode === "grid" ? "mt-2 px-1" : "flex-1 min-w-0"
                    )}>
                      <div className="flex items-start justify-between">
                        <div className="min-w-0 flex-1">
                          <h3 className={cn(
                            "text-white font-medium line-clamp-2",
                            viewMode === "grid" ? "text-sm" : "text-base mb-1"
                          )}>{t}</h3>
                          <p className="text-xs text-white/40">{timeAgo(project.created_at)}</p>
                        </div>

                        {viewMode === "list" && (
                          <div className="flex items-center gap-2 shrink-0">
                            {ready && (
                              <>
                                <Button variant="ghost" size="sm" className="text-white/60 hover:text-white hover:bg-white/10" asChild>
                                  <a href={streamUrl(project.project_id, platform, idToken)} target="_blank" rel="noreferrer">
                                    <Play className="w-4 h-4 mr-2" /> Preview
                                  </a>
                                </Button>
                                <Button variant="ghost" size="sm" className="text-white/60 hover:text-white hover:bg-white/10" asChild>
                                  <a href={streamUrl(project.project_id, platform, idToken)} download>
                                    <Download className="w-4 h-4" />
                                  </a>
                                </Button>
                              </>
                            )}
                            <DropdownMenu>
                                <DropdownMenuTrigger asChild>
                                  <button className="p-2 rounded-lg hover:bg-white/10 transition-colors">
                                    <MoreVertical className="w-4 h-4 text-white/50" />
                                  </button>
                                </DropdownMenuTrigger>
                                <DropdownMenuContent align="end" className="w-40">
                                  <DropdownMenuItem onClick={() => router.push(`/projects/${project.project_id}`)}>
                                    <p>View detail</p>
                                  </DropdownMenuItem>
                                  <DropdownMenuItem onClick={() => router.push(`/projects/${project.project_id}/edit`)}>
                                    <p>Edit in studio</p>
                                  </DropdownMenuItem>
                                  <DropdownMenuItem onClick={openShare}>
                                    <Share2 className="w-4 h-4 mr-2" /> Share
                                  </DropdownMenuItem>
                                  <DropdownMenuItem
                                    className="text-red-400"
                                    onClick={() => deleteProject(project.project_id)}
                                  >
                                    <Trash2 className="w-4 h-4 mr-2" /> Delete
                                  </DropdownMenuItem>
                                </DropdownMenuContent>
                            </DropdownMenu>
                          </div>
                        )}
                      </div>
                    </div>
                  </motion.div>
                );
              })}
            </motion.div>
          )}
        </main>
      </div>

      {/* ── Video dialog ─────────────────────────────────────────────────── */}
      <Dialog open={!!selected} onOpenChange={() => { setSelected(null); closeShare(); }}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>{selected ? title(selected) : ""}</DialogTitle>
          </DialogHeader>

          {selected && (() => {
            const platform = (selected.platforms ?? [])[0] ?? "master";
            const src = streamUrl(selected.project_id, platform, idToken);
            return (
              <>
                <div className="aspect-9/16 max-h-[60vh] bg-gray-900 rounded-xl overflow-hidden">
                  <video key={src} src={src} controls className="w-full h-full object-contain" />
                </div>
                <div className="flex items-center justify-between">
                  <div className="space-y-1">
                    <p className="text-sm text-[#9B9B9B]">Scenes: {selected.scenes_count}</p>
                    <p className="text-sm text-[#9B9B9B]">Created: {timeAgo(selected.created_at)}</p>
                    <p className="text-sm text-[#9B9B9B]">Platforms: {(selected.platforms ?? []).join(", ")}</p>
                  </div>
                  <div className="flex gap-2 flex-wrap justify-end">
                    {(selected.platforms ?? []).map((p) => (
                      <Button key={p} variant="outline" asChild>
                        <a href={streamUrl(selected.project_id, p, idToken)} target="_blank" rel="noreferrer">
                          <Download className="w-4 h-4 mr-2" />
                          {p.replace("_", " ")}
                        </a>
                      </Button>
                    ))}
                    {!publishing && (
                      <Button className="bg-[#5a9ab5] hover:bg-[#7ab0c8]" onClick={openShare}>
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
                              ? "bg-[#5a9ab5]/10 border-[#5a9ab5] text-[#5a9ab5]"
                              : "bg-white border-[#E8E0DC] text-[#9B9B9B] hover:border-[#5a9ab5]/50"
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
                              <CheckCircle2 className="w-4 h-4 text-green-500 shrink-0" />
                            ) : (
                              <XCircle className="w-4 h-4 text-red-500 shrink-0" />
                            )}
                            <span className="capitalize font-medium">{r.platform}</span>
                            {r.post_url && (
                              <a
                                href={r.post_url}
                                target="_blank"
                                rel="noreferrer"
                                className="text-[#5a9ab5] underline text-xs ml-auto"
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
                        className="bg-[#5a9ab5] hover:bg-[#7ab0c8] flex-1"
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
