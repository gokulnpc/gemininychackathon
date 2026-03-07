"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import {
  AlertCircle,
  CheckCircle2,
  ChevronRight,
  Clock,
  Loader2,
  Play,
  RefreshCw,
  ThumbsUp,
  Video,
} from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import { Button } from "@/components/ui/button";
import { AppSidebar } from "@/components/app-sidebar";
import { useSidebar } from "@/context/SidebarContext";
import { cn } from "@/lib/utils";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

type ProjectStatus =
  | "queued"
  | "generating_script"
  | "script_ready"
  | "generating_video"
  | "completed"
  | "failed";

interface Project {
  project_id: string;
  status: ProjectStatus;
  current_stage?: string;
  progress_pct?: number;
  queued_at?: string;
  created_at?: string;
  hook?: string;
  scenes_count?: number;
  voiceover_full_script?: string;
  script?: Record<string, unknown>;
  pipeline_config?: Record<string, unknown>;
  video_urls?: Record<string, string>;
  thumbnail_url?: string;
  error?: string;
}

const ACTIVE_STATUSES: ProjectStatus[] = ["queued", "generating_script", "generating_video"];

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

function StatusPill({ status }: { status: ProjectStatus }) {
  const config: Record<ProjectStatus, { label: string; className: string }> = {
    queued: { label: "Queued", className: "bg-blue-500/20 text-blue-300 border-blue-500/30" },
    generating_script: { label: "Generating Script", className: "bg-blue-500/20 text-blue-300 border-blue-500/30" },
    script_ready: { label: "Script Ready", className: "bg-green-500/20 text-green-300 border-green-500/30" },
    generating_video: { label: "Generating Video", className: "bg-orange-500/20 text-orange-300 border-orange-500/30" },
    completed: { label: "Completed", className: "bg-green-500/20 text-green-300 border-green-500/30" },
    failed: { label: "Failed", className: "bg-red-500/20 text-red-300 border-red-500/30" },
  };
  const { label, className } = config[status] ?? config.failed;
  return (
    <span className={cn("text-xs px-2 py-0.5 rounded-full border font-medium", className)}>
      {label}
    </span>
  );
}

function ProjectCard({
  project,
  isSelected,
  onClick,
}: {
  project: Project;
  isSelected: boolean;
  onClick: () => void;
}) {
  const isActive = ACTIVE_STATUSES.includes(project.status);

  return (
    <button
      onClick={onClick}
      className={cn(
        "w-full text-left p-4 rounded-2xl border transition-all duration-200",
        isSelected
          ? "bg-[#5a9ab5]/15 border-[#5a9ab5]/50"
          : "bg-[#333333] border-white/10 hover:border-white/20 hover:bg-[#3a3a3a]"
      )}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1.5">
            <StatusPill status={project.status} />
            {isActive && <Loader2 className="w-3 h-3 text-blue-400 animate-spin shrink-0" />}
          </div>
          <p className="text-xs text-white/40 font-mono truncate">
            {project.project_id.slice(0, 18)}...
          </p>
          {project.current_stage && (
            <p className="text-xs text-white/60 mt-1 truncate">{project.current_stage}</p>
          )}
          {project.hook && (
            <p className="text-xs text-white/50 mt-1 truncate italic">"{project.hook}"</p>
          )}
        </div>
        <div className="flex flex-col items-end gap-1 shrink-0">
          <ChevronRight className={cn("w-4 h-4 transition-colors", isSelected ? "text-[#5a9ab5]" : "text-white/30")} />
          <span className="text-xs text-white/30">{timeAgo(project.queued_at ?? project.created_at)}</span>
        </div>
      </div>

      {/* Progress bar for in-progress */}
      {isActive && typeof project.progress_pct === "number" && project.progress_pct > 0 && (
        <div className="mt-3 h-1 rounded-full bg-white/10 overflow-hidden">
          <div
            className="h-full bg-[#5a9ab5] rounded-full transition-all duration-500"
            style={{ width: `${project.progress_pct}%` }}
          />
        </div>
      )}
    </button>
  );
}

function ScriptReadyPanel({
  project,
  onRegenerate,
  onApprove,
}: {
  project: Project;
  onRegenerate: () => Promise<void>;
  onApprove: () => Promise<void>;
}) {
  const [hook, setHook] = useState(project.hook ?? "");
  const [voiceover, setVoiceover] = useState(project.voiceover_full_script ?? "");
  const [saving, setSaving] = useState(false);
  const [regenerating, setRegenerating] = useState(false);
  const [approving, setApproving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const saveTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Auto-save on blur with debounce
  const scheduleAutoSave = useCallback(() => {
    if (saveTimeoutRef.current) clearTimeout(saveTimeoutRef.current);
    saveTimeoutRef.current = setTimeout(async () => {
      setSaving(true);
      setSaveError(null);
      const updatedScript = {
        ...(project.script ?? {}),
        hook: { ...(project.script?.hook as Record<string, unknown> ?? {}), text: hook },
        voiceover_full_script: voiceover,
      };
      try {
        const res = await fetch(`${API}/api/v1/projects/${project.project_id}/script`, {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ script: updatedScript }),
        });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
      } catch (e) {
        setSaveError("Failed to save edits");
      } finally {
        setSaving(false);
      }
    }, 800);
  }, [hook, voiceover, project]);

  return (
    <div className="flex flex-col gap-6">
      <div>
        <div className="flex items-center justify-between mb-2">
          <label className="text-xs font-medium text-white/50 uppercase tracking-wider">Hook</label>
          {saving && <span className="text-xs text-white/30">Saving...</span>}
          {saveError && <span className="text-xs text-red-400">{saveError}</span>}
        </div>
        <textarea
          value={hook}
          onChange={(e) => { setHook(e.target.value); scheduleAutoSave(); }}
          className="w-full bg-[#2a2a2a] border border-white/10 rounded-xl px-4 py-3 text-sm text-white placeholder-white/30 resize-none focus:outline-none focus:border-[#5a9ab5]/50 transition-colors"
          rows={2}
        />
      </div>

      {typeof project.scenes_count === "number" && (
        <div className="flex items-center gap-2 text-sm text-white/50">
          <Video className="w-4 h-4" />
          <span>{project.scenes_count} scenes</span>
        </div>
      )}

      <div>
        <label className="text-xs font-medium text-white/50 uppercase tracking-wider mb-2 block">
          Voiceover Script
        </label>
        <textarea
          value={voiceover}
          onChange={(e) => { setVoiceover(e.target.value); scheduleAutoSave(); }}
          className="w-full bg-[#2a2a2a] border border-white/10 rounded-xl px-4 py-3 text-sm text-white/80 placeholder-white/30 resize-none focus:outline-none focus:border-[#5a9ab5]/50 transition-colors leading-relaxed"
          rows={8}
        />
      </div>

      <div className="flex gap-3">
        <Button
          variant="outline"
          disabled={regenerating}
          onClick={async () => {
            setRegenerating(true);
            try { await onRegenerate(); } finally { setRegenerating(false); }
          }}
          className="flex-1 rounded-full border-white/20 text-white/70 hover:text-white hover:bg-white/10 bg-transparent"
        >
          {regenerating ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <RefreshCw className="w-4 h-4 mr-2" />}
          Regenerate Script
        </Button>
        <Button
          disabled={approving}
          onClick={async () => {
            setApproving(true);
            try { await onApprove(); } finally { setApproving(false); }
          }}
          className="flex-1 rounded-full bg-[#5a9ab5] hover:bg-[#7ab0c8] text-white"
        >
          {approving ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <ThumbsUp className="w-4 h-4 mr-2" />}
          Approve & Generate Video
        </Button>
      </div>
    </div>
  );
}

function VideoReadyPanel({ project }: { project: Project }) {
  const videoUrl =
    project.video_urls?.master ??
    project.video_urls?.instagram_reels ??
    Object.values(project.video_urls ?? {})[0];

  return (
    <div className="flex flex-col gap-6">
      {videoUrl && (
        <div className="rounded-2xl overflow-hidden bg-black aspect-[9/16] max-h-[480px] mx-auto w-full max-w-[270px]">
          <video src={videoUrl} controls className="w-full h-full object-contain" />
        </div>
      )}
      {project.hook && (
        <div className="bg-[#2a2a2a] rounded-xl px-4 py-3 text-sm text-white/80 italic border border-white/10">
          "{project.hook}"
        </div>
      )}
      {videoUrl && (
        <a
          href={videoUrl}
          download
          target="_blank"
          rel="noopener noreferrer"
          className="flex items-center justify-center gap-2 px-6 py-2.5 rounded-full bg-[#5a9ab5] hover:bg-[#7ab0c8] text-white text-sm font-medium transition-colors"
        >
          <Play className="w-4 h-4" /> Download / View
        </a>
      )}
    </div>
  );
}

function InProgressPanel({ project }: { project: Project }) {
  return (
    <div className="flex flex-col items-center justify-center py-16 gap-6">
      <div className="relative w-20 h-20">
        <div className="absolute inset-0 rounded-full border-4 border-[#5a9ab5]/20" />
        <div className="absolute inset-0 rounded-full border-4 border-transparent border-t-[#5a9ab5] animate-spin" />
        <div className="absolute inset-0 flex items-center justify-center">
          <Clock className="w-7 h-7 text-[#5a9ab5]" />
        </div>
      </div>
      <div className="text-center">
        <p className="text-white font-medium mb-1">{project.current_stage ?? "Processing..."}</p>
        <p className="text-white/40 text-sm">This may take a minute or two</p>
      </div>
      {typeof project.progress_pct === "number" && project.progress_pct > 0 && (
        <div className="w-48 h-1.5 rounded-full bg-white/10 overflow-hidden">
          <div
            className="h-full bg-[#5a9ab5] rounded-full transition-all duration-500"
            style={{ width: `${project.progress_pct}%` }}
          />
        </div>
      )}
    </div>
  );
}

function FailedPanel({ project }: { project: Project }) {
  return (
    <div className="flex flex-col items-center justify-center py-16 gap-4 text-center">
      <AlertCircle className="w-12 h-12 text-red-400 opacity-70" />
      <p className="text-white font-medium">Generation Failed</p>
      {project.error && (
        <p className="text-red-400/80 text-sm max-w-sm">{project.error}</p>
      )}
    </div>
  );
}

export default function ProjectsPage() {
  const { isCollapsed } = useSidebar();
  const searchParams = useSearchParams();
  const newProjectId = searchParams.get("new");

  const [projects, setProjects] = useState<Project[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(newProjectId);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const fetchProjects = useCallback(async () => {
    try {
      const res = await fetch(`${API}/api/v1/projects`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      setProjects(data.projects ?? []);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load projects");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchProjects();
  }, [fetchProjects]);

  // Poll while any project is active
  useEffect(() => {
    const hasActive = projects.some((p) => ACTIVE_STATUSES.includes(p.status));
    if (hasActive) {
      pollRef.current = setInterval(fetchProjects, 5000);
    } else {
      if (pollRef.current) clearInterval(pollRef.current);
    }
    return () => { if (pollRef.current) clearInterval(pollRef.current); };
  }, [projects, fetchProjects]);

  const selectedProject = projects.find((p) => p.project_id === selectedId) ?? null;

  async function handleRegenerate(project: Project) {
    const cfg = project.pipeline_config ?? {};
    const body: Record<string, unknown> = { ...cfg };
    try {
      const res = await fetch(`${API}/api/v1/projects/${project.project_id}/queue-script`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      await fetchProjects();
    } catch (e) {
      alert("Failed to regenerate: " + (e instanceof Error ? e.message : e));
    }
  }

  async function handleApprove(project: Project) {
    try {
      const res = await fetch(`${API}/api/v1/projects/${project.project_id}/approve-script`, {
        method: "POST",
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      await fetchProjects();
    } catch (e) {
      alert("Failed to approve: " + (e instanceof Error ? e.message : e));
    }
  }

  return (
    <div className="flex min-h-screen bg-[#2B2B2B]">
      <AppSidebar />

      <div
        className={cn(
          "flex-1 flex flex-col min-h-screen transition-all duration-300",
          isCollapsed ? "ml-[80px]" : "ml-[280px]"
        )}
      >
        <main className="flex-1 flex flex-col px-8 py-8">
          {/* Header */}
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            className="mb-8"
          >
            <h1 className="text-3xl font-medium text-white mb-2">Projects</h1>
            <p className="text-white/50">Track script and video generation progress</p>
          </motion.div>

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

          {!loading && !error && projects.length === 0 && (
            <div className="flex flex-col items-center justify-center py-24 text-white/40">
              <CheckCircle2 className="w-12 h-12 mb-4 opacity-30" />
              <p className="text-lg">No projects yet</p>
              <p className="text-sm mt-1">Complete the wizard to queue your first video</p>
            </div>
          )}

          {!loading && projects.length > 0 && (
            <div className="flex-1 flex gap-6">
              {/* Left panel — project list */}
              <div className="w-80 shrink-0 flex flex-col gap-3 overflow-y-auto">
                {projects.map((project) => (
                  <ProjectCard
                    key={project.project_id}
                    project={project}
                    isSelected={selectedId === project.project_id}
                    onClick={() => setSelectedId(project.project_id)}
                  />
                ))}
              </div>

              {/* Right panel — project detail */}
              <AnimatePresence mode="wait">
                {selectedProject ? (
                  <motion.div
                    key={selectedProject.project_id + selectedProject.status}
                    initial={{ opacity: 0, x: 20 }}
                    animate={{ opacity: 1, x: 0 }}
                    exit={{ opacity: 0, x: 20 }}
                    className="flex-1 bg-[#333333] rounded-2xl border border-white/10 p-6 overflow-y-auto"
                  >
                    <div className="flex items-center gap-3 mb-6">
                      <StatusPill status={selectedProject.status} />
                      <span className="text-xs text-white/30 font-mono">
                        {selectedProject.project_id}
                      </span>
                    </div>

                    {/* Status-specific content */}
                    {(selectedProject.status === "queued" || selectedProject.status === "generating_script" || selectedProject.status === "generating_video") && (
                      <InProgressPanel project={selectedProject} />
                    )}

                    {selectedProject.status === "script_ready" && (
                      <ScriptReadyPanel
                        project={selectedProject}
                        onRegenerate={() => handleRegenerate(selectedProject)}
                        onApprove={() => handleApprove(selectedProject)}
                      />
                    )}

                    {selectedProject.status === "completed" && (
                      <VideoReadyPanel project={selectedProject} />
                    )}

                    {selectedProject.status === "failed" && (
                      <FailedPanel project={selectedProject} />
                    )}
                  </motion.div>
                ) : (
                  <motion.div
                    key="empty"
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    className="flex-1 flex items-center justify-center text-white/30"
                  >
                    <p>Select a project to view details</p>
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
          )}
        </main>
      </div>
    </div>
  );
}
