"use client";

import { Suspense, useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import {
  AlertCircle,
  Archive,
  CheckCircle2,
  Copy,
  LayoutTemplate,
  Loader2,
  MoreVertical,
  Pencil,
  Play,
  Search,
  Share2,
  Trash2,
  Video,
  X,
} from "lucide-react";
import { motion } from "framer-motion";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { AppSidebar } from "@/components/app-sidebar";
import { UserMenu } from "@/components/shared/UserMenu";
import { useSidebar } from "@/context/SidebarContext";
import { useAuth } from "@/context/AuthContext";
import { cn } from "@/lib/utils";
import apiClient from "@/lib/apiClient";
import { ShareDialog } from "@/components/shared/ShareDialog";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

type ProjectStatus =
  | "draft"
  | "editing"
  | "queued"
  | "generating_script"
  | "script_ready"
  | "generating_video"
  | "in_progress"
  | "completed"
  | "failed";

interface Project {
  project_id: string;
  status: ProjectStatus;
  current_stage?: string;
  progress_pct?: number;
  queued_at?: string;
  created_at?: string;
  title?: string;
  hook?: string;
  scenes_count?: number;
  voiceover_full_script?: string;
  script?: Record<string, unknown>;
  pipeline_config?: Record<string, unknown>;
  video_urls?: Record<string, string>;
  thumbnail_url?: string;
  error?: string;
  error_code?: string;
  retryable?: boolean;
  failure_stage?: string;
  failed_at?: string;
  script_attempt_count?: number;
  editor_export?: {
    export_id?: string | null;
    status?: string;
    current_stage?: string | null;
    progress_pct?: number | null;
    queued_at?: string | null;
    started_at?: string | null;
    completed_at?: string | null;
    download_url?: string | null;
    thumbnail_url?: string | null;
    error?: string | null;
  } | null;
}

const ACTIVE_STATUSES: ProjectStatus[] = ["queued", "generating_script", "generating_video", "in_progress"];

const STATUS_FILTERS: { key: ProjectStatus | "all"; label: string }[] = [
  { key: "all",               label: "All" },
  { key: "editing",           label: "Editing" },
  { key: "queued",            label: "Queued" },
  { key: "generating_script", label: "Scripting" },
  { key: "script_ready",      label: "Script Ready" },
  { key: "generating_video",  label: "Generating" },
  { key: "in_progress",       label: "In Progress" },
  { key: "completed",         label: "Completed" },
  { key: "failed",            label: "Failed" },
];

function timeAgo(iso?: string): string {
  if (!iso) return "";
  const diff = Date.now() - new Date(iso).getTime();
  const m = Math.floor(diff / 60_000);
  if (m < 1) return "just now";
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
}

export function StatusPill({ status }: { status: ProjectStatus }) {
  const config: Record<ProjectStatus, { label: string; className: string }> = {
    draft:   { label: "Draft",   className: "bg-zinc-500/20 text-zinc-300 border-zinc-500/30" },
    editing: { label: "Editing", className: "bg-sky-500/20 text-sky-300 border-sky-500/30" },
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
    <span className={cn("text-xs px-2 py-0.5 rounded-full border font-medium whitespace-nowrap", className)}>
      {label}
    </span>
  );
}

function ProjectCard({
  project,
  index,
  isArchived,
  onDelete,
  onArchive,
  onUnarchive,
  onShare,
}: {
  project: Project;
  index: number;
  isArchived: boolean;
  onDelete: (id: string) => void;
  onArchive: (id: string) => void;
  onUnarchive: (id: string) => void;
  onShare: (id: string) => void;
}) {
  const router = useRouter();
  const { idToken } = useAuth();
  const isActive = ACTIVE_STATUSES.includes(project.status);
  const isCompleted = project.status === "completed";
  const [thumbOk, setThumbOk] = useState(false);

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: 0.04 * index }}
      className="group relative cursor-pointer"
      onClick={() => router.push(`/projects/${project.project_id}`)}
    >
      {/* Thumbnail */}
      <div className="relative aspect-[9/16] rounded-2xl overflow-hidden bg-[#1a1a1a] border border-white/10 group-hover:border-[#5a9ab5]/50 transition-all duration-200">
        <img
          src={`${API}/api/v1/projects/${project.project_id}/thumbnail${idToken ? `?token=${idToken}` : ''}`}
          alt={project.hook ?? "Video"}
          className={cn("w-full h-full object-cover", !thumbOk && "invisible absolute")}
          onLoad={() => setThumbOk(true)}
          onError={() => setThumbOk(false)}
        />

        {/* Status placeholder when no thumbnail loaded */}
        {!thumbOk && (
          <div className="absolute inset-0 flex flex-col items-center justify-center gap-3 px-4">
            {isActive ? (
              <>
                <Loader2 className="w-8 h-8 text-[#5a9ab5] animate-spin" />
                <p className="text-xs text-white/40 text-center leading-relaxed">
                  {project.current_stage ?? "Processing..."}
                </p>
              </>
            ) : project.status === "script_ready" ? (
              <>
                <Video className="w-8 h-8 text-white/20" />
                <p className="text-xs text-white/40">Script ready</p>
              </>
            ) : project.status === "editing" || project.status === "draft" ? (
              <>
                <Pencil className="w-8 h-8 text-white/20" />
                <p className="text-xs text-white/30">Editing in progress</p>
              </>
            ) : project.status === "failed" ? (
              <AlertCircle className="w-8 h-8 text-red-400/50" />
            ) : null}
          </div>
        )}

        {/* Play hover overlay (completed only) */}
        {isCompleted && (
          <div className="absolute inset-0 bg-black/50 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center">
            <div className="w-12 h-12 rounded-full bg-white/20 flex items-center justify-center backdrop-blur-sm">
              <Play className="w-5 h-5 text-white ml-0.5" />
            </div>
          </div>
        )}

        {/* Status badge — top left */}
        <div className="absolute top-2 left-2 pointer-events-none">
          <StatusPill status={project.status} />
        </div>

        {/* Options menu — top right */}
        <div
          className="absolute top-2 right-2 opacity-0 group-hover:opacity-100 transition-opacity"
          onClick={(e) => e.stopPropagation()}
        >
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <button className="p-1.5 rounded-lg bg-black/60 text-white/70 hover:text-white hover:bg-black/80 transition-colors">
                <MoreVertical className="w-4 h-4" />
              </button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-44">
              <DropdownMenuItem
                onClick={() => router.push(`/projects/${project.project_id}/edit`)}
                className="cursor-pointer"
              >
                <Pencil className="w-4 h-4 mr-2" /> Edit
              </DropdownMenuItem>
              <DropdownMenuItem
                onClick={() => onShare(project.project_id)}
                className="cursor-pointer"
              >
                <Share2 className="w-4 h-4 mr-2" /> Share
              </DropdownMenuItem>
              <DropdownMenuItem
                onClick={() => alert("Duplicate coming soon")}
                className="cursor-pointer"
              >
                <Copy className="w-4 h-4 mr-2" /> Duplicate
              </DropdownMenuItem>
              <DropdownMenuSeparator />
              {isArchived ? (
                <DropdownMenuItem
                  onClick={() => onUnarchive(project.project_id)}
                  className="cursor-pointer"
                >
                  <Archive className="w-4 h-4 mr-2" /> Unarchive
                </DropdownMenuItem>
              ) : (
                <DropdownMenuItem
                  onClick={() => onArchive(project.project_id)}
                  className="cursor-pointer"
                >
                  <Archive className="w-4 h-4 mr-2" /> Archive
                </DropdownMenuItem>
              )}
              <DropdownMenuItem
                onClick={() => onDelete(project.project_id)}
                className="cursor-pointer text-red-500 focus:text-red-500"
              >
                <Trash2 className="w-4 h-4 mr-2" /> Delete
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>

        {/* Progress bar at bottom */}
        {isActive && typeof project.progress_pct === "number" && project.progress_pct > 0 && (
          <div className="absolute bottom-0 left-0 right-0 h-1 bg-white/10">
            <div
              className="h-full bg-[#5a9ab5] transition-all duration-500"
              style={{ width: `${project.progress_pct}%` }}
            />
          </div>
        )}
      </div>

      {/* Below-card info */}
      <div className="mt-2 px-1">
        <p className="text-sm text-white font-medium truncate">
          {project.title ?? project.hook ?? "Untitled Project"}
        </p>
        <p className="text-xs text-white/40 mt-0.5">
          {timeAgo(project.queued_at ?? project.created_at)}
        </p>
        {project.status === "failed" && project.error && (
          <p className="text-xs text-red-400/70 mt-1 line-clamp-2">
            {project.error}
          </p>
        )}
      </div>
    </motion.div>
  );
}

function ProjectsContent() {
  const { isCollapsed } = useSidebar();
  const router = useRouter();
  const { user, loading: authLoading } = useAuth();

  const [tab, setTab] = useState<"active" | "archive">("active");
  const [creatingEditor, setCreatingEditor] = useState(false);
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<ProjectStatus | "all">("all");
  const [projects, setProjects] = useState<Project[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [shareProjectId, setShareProjectId] = useState<string | null>(null);
  const [archived, setArchived] = useState<string[]>(() => {
    if (typeof window === "undefined") return [];
    try {
      return JSON.parse(localStorage.getItem("archivedProjects") ?? "[]");
    } catch {
      return [];
    }
  });

  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const fetchProjects = useCallback(async () => {
    if (authLoading || !user) return;
    try {
      const res = await apiClient.get("/api/v1/projects");
      setProjects(res.data.projects ?? []);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load projects");
    } finally {
      setLoading(false);
    }
  }, [authLoading, user]);

  useEffect(() => {
    void fetchProjects();
  }, [fetchProjects]);

  useEffect(() => {
    const hasActive = projects.some((p) => ACTIVE_STATUSES.includes(p.status));
    if (hasActive) {
      pollRef.current = setInterval(fetchProjects, 5000);
    } else {
      if (pollRef.current) clearInterval(pollRef.current);
    }
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [projects, fetchProjects]);

  async function handleDelete(id: string) {
    try {
      await apiClient.delete(`/api/v1/projects/${id}`);
      setProjects((prev) => prev.filter((p) => p.project_id !== id));
    } catch {
      alert("Failed to delete project");
    }
  }

  function handleArchive(id: string) {
    const updated = [...archived, id];
    setArchived(updated);
    localStorage.setItem("archivedProjects", JSON.stringify(updated));
  }

  function handleUnarchive(id: string) {
    const updated = archived.filter((a) => a !== id);
    setArchived(updated);
    localStorage.setItem("archivedProjects", JSON.stringify(updated));
  }

  const visibleProjects = (
    tab === "active"
      ? projects.filter((p) => !archived.includes(p.project_id))
      : projects.filter((p) => archived.includes(p.project_id))
  )
    .filter((p) => statusFilter === "all" || p.status === statusFilter)
    .filter((p) => {
      if (!search.trim()) return true;
      const q = search.toLowerCase();
      return (
        p.title?.toLowerCase().includes(q) ||
        p.hook?.toLowerCase().includes(q) ||
        p.project_id.toLowerCase().includes(q) ||
        p.current_stage?.toLowerCase().includes(q)
      );
    });

  return (
    <div className="flex min-h-screen bg-[#2B2B2B]">
      <AppSidebar />

      <div
        className={cn(
          "flex-1 flex flex-col min-h-screen transition-all duration-300",
          isCollapsed ? "ml-[80px]" : "ml-[280px]"
        )}
      >
        <header className="flex items-center justify-between px-8 h-[80px] border-b border-white/10">
          <div />
          <div className="flex items-center gap-4">
            <Button
              onClick={async () => {
                setCreatingEditor(true);
                try {
                  const res = await apiClient.post<{ project_id: string }>("/api/v1/projects/create-empty");
                  router.push(`/projects/${res.data.project_id}/edit`);
                } catch (err) {
                  console.error("Failed to create editor project", err);
                } finally {
                  setCreatingEditor(false);
                }
              }}
              disabled={creatingEditor}
              className="rounded-full px-5 bg-[#5a9ab5] hover:bg-[#7ab0c8] text-white disabled:opacity-50"
            >
              {creatingEditor ? (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              ) : (
                <LayoutTemplate className="mr-2 h-4 w-4" />
              )}
              Open Editor
            </Button>
            <Button
              onClick={() => router.push("/create")}
              className="rounded-full px-6 bg-[#5a9ab5] hover:bg-[#7ab0c8] text-white"
            >
              Create New
            </Button>
            <UserMenu />
          </div>
        </header>

        <main className="px-8 py-8 flex-1">
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            className="flex items-start justify-between mb-8"
          >
            <div>
              <h1 className="text-3xl font-medium text-white mb-2">Projects</h1>
              <p className="text-white/50">Track script and video generation progress</p>
            </div>
            <div className="flex items-center gap-1 bg-white/5 rounded-full p-1 border border-white/10 mt-1">
              <button
                onClick={() => setTab("active")}
                className={cn(
                  "px-5 py-1.5 rounded-full text-sm font-medium transition-colors",
                  tab === "active" ? "bg-white/15 text-white" : "text-white/40 hover:text-white"
                )}
              >
                Active
              </button>
              <button
                onClick={() => setTab("archive")}
                className={cn(
                  "px-5 py-1.5 rounded-full text-sm font-medium transition-colors",
                  tab === "archive" ? "bg-white/15 text-white" : "text-white/40 hover:text-white"
                )}
              >
                Archive
              </button>
            </div>
          </motion.div>

          {/* Search + Filter bar */}
          <div className="flex items-center gap-4 mb-6">
            <div className="relative flex-1 max-w-xs">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-white/30 pointer-events-none" />
              <input
                type="text"
                placeholder="Search projects..."
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                className="w-full bg-white/5 border border-white/10 rounded-full pl-9 pr-9 py-2 text-sm text-white placeholder-white/30 focus:outline-none focus:border-[#5a9ab5]/50 transition-colors"
              />
              {search && (
                <button
                  onClick={() => setSearch("")}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-white/30 hover:text-white transition-colors"
                >
                  <X className="w-3.5 h-3.5" />
                </button>
              )}
            </div>
            <div className="flex items-center gap-2 flex-wrap">
              {STATUS_FILTERS.map(({ key, label }) => (
                <button
                  key={key}
                  onClick={() => setStatusFilter(key === statusFilter ? "all" : key)}
                  className={cn(
                    "px-3 py-1.5 rounded-full text-xs font-medium border transition-colors whitespace-nowrap",
                    statusFilter === key
                      ? "bg-[#5a9ab5]/20 border-[#5a9ab5]/50 text-[#5a9ab5]"
                      : "bg-white/5 border-white/10 text-white/50 hover:text-white hover:border-white/20"
                  )}
                >
                  {label}
                </button>
              ))}
            </div>
          </div>

          {loading && (
            <div className="flex items-center justify-center py-24 text-white/40">
              <Loader2 className="w-6 h-6 animate-spin mr-3" /> Loading projects...
            </div>
          )}

          {error && (
            <div className="flex items-center gap-2 text-red-400 bg-red-500/10 border border-red-500/20 rounded-xl px-4 py-3 mb-6">
              <AlertCircle className="w-4 h-4 shrink-0" />
              <span className="text-sm">{error}</span>
            </div>
          )}

          {!loading && !error && visibleProjects.length === 0 && (
            <div className="flex flex-col items-center justify-center py-24 text-white/40">
              {search.trim() || statusFilter !== "all" ? (
                <>
                  <CheckCircle2 className="w-12 h-12 mb-4 opacity-30" />
                  <p className="text-lg">No matching projects</p>
                  <p className="text-sm mt-1">Try a different search or filter</p>
                </>
              ) : tab === "active" ? (
                <>
                  <p className="text-lg mb-4">No videos yet.</p>
                  <Button
                    onClick={() => router.push("/create")}
                    className="rounded-full px-6 bg-[#5a9ab5] hover:bg-[#7ab0c8] text-white"
                  >
                    Create Project
                  </Button>
                </>
              ) : (
                <>
                  <CheckCircle2 className="w-12 h-12 mb-4 opacity-30" />
                  <p className="text-lg">No archived projects</p>
                  <p className="text-sm mt-1">Archived projects will appear here</p>
                </>
              )}
            </div>
          )}

          {!loading && visibleProjects.length > 0 && (
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ delay: 0.1 }}
              className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-4"
            >
              {visibleProjects.map((project, index) => (
                <ProjectCard
                  key={project.project_id}
                  project={project}
                  index={index}
                  isArchived={tab === "archive"}
                  onDelete={handleDelete}
                  onArchive={handleArchive}
                  onUnarchive={handleUnarchive}
                  onShare={(id) => setShareProjectId(id)}
                />
              ))}
            </motion.div>
          )}
        </main>
      </div>

      <ShareDialog
        open={!!shareProjectId}
        onOpenChange={(open) => { if (!open) setShareProjectId(null); }}
        projectId={shareProjectId ?? ""}
      />
    </div>
  );
}

export default function ProjectsPage() {
  return (
    <Suspense>
      <ProjectsContent />
    </Suspense>
  );
}
