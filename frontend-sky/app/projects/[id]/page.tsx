"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import {
  AlertCircle,
  ArrowLeft,
  CheckCircle2,
  Clock,
  Download,
  Loader2,
  RefreshCw,
  Settings,
  Share2,
  ThumbsUp,
  Video,
} from "lucide-react";
import { motion } from "framer-motion";
import { Button } from "@/components/ui/button";
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
  editor_export_history?: Array<{
    export_id: string;
    completed_at: string;
    download_url: string;
    thumbnail_url?: string | null;
    project_json_snapshot?: Record<string, unknown> | null;
  }>;
}

const ACTIVE_STATUSES: ProjectStatus[] = [
  "queued",
  "generating_script",
  "generating_video",
  "in_progress",
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

function StatusPill({ status }: { status: ProjectStatus }) {
  const config: Record<ProjectStatus, { label: string; className: string }> = {
    draft: {
      label: "Draft",
      className: "bg-zinc-500/20 text-zinc-300 border-zinc-500/30",
    },
    editing: {
      label: "Editing",
      className: "bg-sky-500/20 text-sky-300 border-sky-500/30",
    },
    queued: {
      label: "Queued",
      className: "bg-blue-500/20 text-blue-300 border-blue-500/30",
    },
    generating_script: {
      label: "Generating Script",
      className: "bg-blue-500/20 text-blue-300 border-blue-500/30",
    },
    script_ready: {
      label: "Script Ready",
      className: "bg-yellow-500/20 text-yellow-300 border-yellow-500/30",
    },
    generating_video: {
      label: "Generating Video",
      className: "bg-orange-500/20 text-orange-300 border-orange-500/30",
    },
    in_progress: {
      label: "Generating Video",
      className: "bg-orange-500/20 text-orange-300 border-orange-500/30",
    },
    completed: {
      label: "Completed",
      className: "bg-green-500/20 text-green-300 border-green-500/30",
    },
    failed: {
      label: "Failed",
      className: "bg-red-500/20 text-red-300 border-red-500/30",
    },
  };
  const { label, className } = config[status] ?? config.failed;
  return (
    <span
      className={cn(
        "text-xs px-2.5 py-1 rounded-full border font-medium",
        className,
      )}
    >
      {label}
    </span>
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
  const [voiceover, setVoiceover] = useState(
    project.voiceover_full_script ?? "",
  );
  const [saving, setSaving] = useState(false);
  const [regenerating, setRegenerating] = useState(false);
  const [approving, setApproving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const saveTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const scheduleAutoSave = useCallback(() => {
    if (saveTimeoutRef.current) clearTimeout(saveTimeoutRef.current);
    saveTimeoutRef.current = setTimeout(async () => {
      setSaving(true);
      setSaveError(null);
      const updatedScript = {
        ...(project.script ?? {}),
        hook: {
          ...((project.script?.hook as Record<string, unknown>) ?? {}),
          text: hook,
        },
        voiceover_full_script: voiceover,
      };
      try {
        await apiClient.put(`/api/v1/projects/${project.project_id}/script`, {
          script: updatedScript,
        });
      } catch {
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
          <label className="text-xs font-medium text-white/50 uppercase tracking-wider">
            Hook
          </label>
          {saving && <span className="text-xs text-white/30">Saving...</span>}
          {saveError && (
            <span className="text-xs text-red-400">{saveError}</span>
          )}
        </div>
        <textarea
          value={hook}
          onChange={(e) => {
            setHook(e.target.value);
            scheduleAutoSave();
          }}
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
          onChange={(e) => {
            setVoiceover(e.target.value);
            scheduleAutoSave();
          }}
          className="w-full bg-[#2a2a2a] border border-white/10 rounded-xl px-4 py-3 text-sm text-white/80 placeholder-white/30 resize-none focus:outline-none focus:border-[#5a9ab5]/50 transition-colors leading-relaxed"
          rows={10}
        />
      </div>

      <div className="flex gap-3">
        <Button
          variant="outline"
          disabled={regenerating}
          onClick={async () => {
            setRegenerating(true);
            try {
              await onRegenerate();
            } finally {
              setRegenerating(false);
            }
          }}
          className="flex-1 rounded-full border-white/20 text-white/70 hover:text-white hover:bg-white/10 bg-transparent"
        >
          {regenerating ? (
            <Loader2 className="w-4 h-4 mr-2 animate-spin" />
          ) : (
            <RefreshCw className="w-4 h-4 mr-2" />
          )}
          Regenerate Script
        </Button>
        <Button
          disabled={approving}
          onClick={async () => {
            setApproving(true);
            try {
              await onApprove();
            } finally {
              setApproving(false);
            }
          }}
          className="flex-1 rounded-full bg-[#5a9ab5] hover:bg-[#7ab0c8] text-white"
        >
          {approving ? (
            <Loader2 className="w-4 h-4 mr-2 animate-spin" />
          ) : (
            <ThumbsUp className="w-4 h-4 mr-2" />
          )}
          Approve & Generate Video
        </Button>
      </div>
    </div>
  );
}

function CompletedPanel({
  project,
}: {
  project: Project;
}) {
  const platforms = Object.keys(project.video_urls ?? {});
  const { idToken } = useAuth();

  return (
    <div className="flex flex-col gap-6">
      {project.hook && (
        <div className="bg-[#2a2a2a] rounded-xl px-4 py-3 text-sm text-white/80 italic border border-white/10">
          "{project.hook}"
        </div>
      )}

      <div className="grid grid-cols-2 gap-3">
        {typeof project.scenes_count === "number" && (
          <div className="bg-[#2a2a2a] rounded-xl p-3 border border-white/10">
            <p className="text-xs text-white/40 mb-1">Scenes</p>
            <p className="text-lg font-medium text-white">
              {project.scenes_count}
            </p>
          </div>
        )}
        {platforms.length > 0 && (
          <div className="bg-[#2a2a2a] rounded-xl p-3 border border-white/10">
            <p className="text-xs text-white/40 mb-1">Platforms</p>
            <p className="text-lg font-medium text-white">{platforms.length}</p>
          </div>
        )}
      </div>

      {project.voiceover_full_script && (
        <div className="flex flex-col gap-2">
          <label className="text-xs font-medium text-white/50 uppercase tracking-wider">
            Voiceover Script
          </label>
          <div className="bg-[#2a2a2a] rounded-xl p-4 border border-white/10 text-sm text-white/70 leading-relaxed max-h-[200px] overflow-y-auto custom-scrollbar">
            {project.voiceover_full_script}
          </div>
        </div>
      )}

      {platforms.filter((p) => p !== "master").length > 0 && (
        <div className="flex flex-col gap-2">
          <label className="text-xs font-medium text-white/50 uppercase tracking-wider">
            Download
          </label>
          {platforms
            .filter((p) => p !== "master")
            .map((platform) => (
              <a
                key={platform}
                href={`${API}/api/v1/projects/${project.project_id}/stream/${platform}${idToken ? `?token=${idToken}` : ""}`}
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center justify-between px-4 py-2.5 rounded-xl bg-[#2a2a2a] border border-white/10 hover:border-[#5a9ab5]/40 transition-colors group"
              >
                <span className="text-sm text-white/70 group-hover:text-white capitalize transition-colors">
                  {platform.replace(/_/g, " ")}
                </span>
                <Download className="w-4 h-4 text-white/40 group-hover:text-[#5a9ab5] transition-colors" />
              </a>
            ))}
        </div>
      )}
    </div>
  );
}

function VideoConfigPanel({ project }: { project: Project }) {
  const cfg = project.pipeline_config ?? {};

  // Format helpers
  const formatKey = (key: string) =>
    key.replace(/_/g, " ").replace(/\b\w/g, (l) => l.toUpperCase());

  // Group configuration items
  const visualSettings = [];
  if (cfg.art_style_override)
    visualSettings.push({ label: "Art Style", value: cfg.art_style_override });
  if (cfg.caption_style)
    visualSettings.push({ label: "Captions", value: cfg.caption_style });

  const contentSettings = [];
  if (cfg.video_duration)
    contentSettings.push({
      label: "Duration",
      value: `${cfg.video_duration}s`,
    });
  if (cfg.voice_id)
    contentSettings.push({ label: "Voice Profile", value: cfg.voice_id });
  const platforms = cfg.target_platforms as string[] | undefined;
  if (platforms && platforms.length > 0) {
    contentSettings.push({ label: "Platforms", value: platforms.join(", ") });
  }

  return (
    <div className="flex flex-col gap-6">
      <div className="bg-[#2a2a2a] rounded-xl p-5 border border-white/10">
        <h3 className="text-white font-medium mb-4 flex items-center gap-2">
          <Settings className="w-4 h-4 text-[#5a9ab5]" />
          Video Configuration
        </h3>

        <div className="grid grid-cols-2 gap-y-6 gap-x-4">
          {/* Visual Profile */}
          {visualSettings.length > 0 && (
            <div>
              <p className="text-xs font-medium text-white/40 uppercase tracking-wider mb-2">
                Visual Profile
              </p>
              <ul className="space-y-2">
                {visualSettings.map((s) => (
                  <li key={s.label} className="flex justify-between text-sm">
                    <span className="text-white/60">{s.label}</span>
                    <span className="text-white text-right capitalize">
                      {String(s.value).replace(/_/g, " ")}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Content Rules */}
          {contentSettings.length > 0 && (
            <div>
              <p className="text-xs font-medium text-white/40 uppercase tracking-wider mb-2">
                Content Rules
              </p>
              <ul className="space-y-2">
                {contentSettings.map((s) => (
                  <li key={s.label} className="flex justify-between text-sm">
                    <span className="text-white/60">{s.label}</span>
                    <span className="text-white text-right capitalize">
                      {String(s.value).replace(/_/g, " ")}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default function ProjectDetailPage() {
  const params = useParams();
  const projectId = params.id as string;
  const router = useRouter();
  const { isCollapsed } = useSidebar();
  const { idToken, user, loading: authLoading } = useAuth();

  const [project, setProject] = useState<Project | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [thumbOk, setThumbOk] = useState(false);
  
  const [restoringExportId, setRestoringExportId] = useState<string | null>(null);
  const [restoreError, setRestoreError] = useState<string | null>(null);
  const [shareExportId, setShareExportId] = useState<string | null>(null);
  
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const isActive = project ? ACTIVE_STATUSES.includes(project.status) : false;
  const isCompleted = project?.status === "completed";

  const fetchProject = useCallback(async () => {
    try {
      const res = await apiClient.get(`/api/v1/projects/${projectId}`);
      setProject(res.data);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load project");
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  useEffect(() => {
    if (authLoading || !user) return;
    void fetchProject();
  }, [fetchProject, authLoading, user]);

  useEffect(() => {
    if (!project) return;
    if (isActive) {
      pollRef.current = setInterval(fetchProject, 5000);
    } else {
      if (pollRef.current) clearInterval(pollRef.current);
    }
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [project, fetchProject, isActive]);

  async function handleRegenerate() {
    if (!project) return;
    const cfg = project.pipeline_config ?? {};
    await apiClient.post(
      `/api/v1/projects/${project.project_id}/queue-script`,
      { ...cfg },
    );
    await fetchProject();
  }

  async function handleApprove() {
    if (!project) return;
    await apiClient.post(
      `/api/v1/projects/${project.project_id}/approve-script`,
    );
    await fetchProject();
  }

  async function handleRetryScript() {
    if (!project) return;
    await apiClient.post(`/api/v1/projects/${project.project_id}/retry-script`);
    await fetchProject();
  }

  async function handleEditFromVersion(exportId: string, newTab = false) {
    if (!project) throw new Error("Project is not loaded");
    await apiClient.post(
      `/api/v1/projects/${project.project_id}/restore-export-version`,
      {
        export_id: exportId,
      },
    );
    const url = `/projects/${project.project_id}/edit`;
    if (newTab) {
      window.open(url, "_blank");
    } else {
      router.push(url);
    }
  }

  const firstPlatform = project
    ? (Object.keys(project.video_urls ?? {})[0] ?? "master")
    : "master";

  return (
    <div className="flex min-h-screen bg-[#2B2B2B]">
      <AppSidebar />

      <div
        className={cn(
          "flex-1 flex flex-col min-h-screen transition-all duration-300",
          isCollapsed ? "ml-[80px]" : "ml-[280px]",
        )}
      >
        {/* Header */}
        <header className="flex items-center justify-between px-8 h-[80px] border-b border-white/10">
          <button
            onClick={() => router.push("/projects")}
            className="flex items-center gap-2 text-white/60 hover:text-white transition-colors"
          >
            <ArrowLeft className="w-4 h-4" />
            <span className="text-sm">Projects</span>
          </button>
          <div className="flex items-center gap-4">
            <UserMenu />
          </div>
        </header>

        <main className="px-8 py-8 flex-1">
          {loading && (
            <div className="flex items-center justify-center py-24 text-white/40">
              <Loader2 className="w-6 h-6 animate-spin mr-3" /> Loading
              project...
            </div>
          )}

          {error && (
            <div className="flex items-center gap-2 text-red-400 bg-red-500/10 border border-red-500/20 rounded-xl px-4 py-3">
              <AlertCircle className="w-4 h-4 shrink-0" />
              <span className="text-sm">{error}</span>
            </div>
          )}

          {!loading && project && (
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
            >
              {/* Top meta row */}
              <div className="flex items-center gap-3 mb-2">
                <StatusPill status={project.status} />
                <span className="text-xs text-white/30 font-mono">
                  {project.project_id}
                </span>
                <span className="text-xs text-white/30">
                  {timeAgo(project.queued_at ?? project.created_at)}
                </span>
              </div>

              {project.hook && (
                <h1 className="text-2xl font-medium text-white mb-8 leading-snug">
                  "{project.hook}"
                </h1>
              )}

              {/* Two-column layout */}
              <div className="flex gap-8 items-start">
                {/* Left: video / placeholder (fixed width, 9:16) */}
                <div className="w-[260px] shrink-0">
                  <div className="relative aspect-[9/16] rounded-2xl overflow-hidden bg-[#1a1a1a] border border-white/10">
                    {isCompleted ? (
                      <video
                        src={`${API}/api/v1/projects/${projectId}/stream/${firstPlatform}${idToken ? `?token=${idToken}` : ""}`}
                        controls
                        className="w-full h-full object-contain"
                        poster={`${API}/api/v1/projects/${projectId}/thumbnail${idToken ? `?token=${idToken}` : ""}`}
                      />
                    ) : (
                      <>
                        <img
                          src={`${API}/api/v1/projects/${projectId}/thumbnail${idToken ? `?token=${idToken}` : ""}`}
                          alt={project.hook ?? "Video"}
                          className={cn("absolute inset-0 w-full h-full object-cover", !thumbOk && "hidden")}
                          onLoad={() => setThumbOk(true)}
                          onError={() => setThumbOk(false)}
                        />
                        {!thumbOk && (
                          <div className="absolute inset-0 flex flex-col items-center justify-center gap-3 px-4">
                            {isActive ? (
                              <>
                                <Loader2 className="w-10 h-10 text-[#5a9ab5] animate-spin" />
                                <p className="text-xs text-white/40 text-center leading-relaxed">
                                  {project.current_stage ?? "Processing..."}
                                </p>
                              </>
                            ) : project.status === "script_ready" ? (
                              <>
                                <CheckCircle2 className="w-10 h-10 text-yellow-400/60" />
                                <p className="text-xs text-white/40 text-center">
                                  Script ready — review and approve to generate
                                  video
                                </p>
                              </>
                            ) : project.status === "failed" ? (
                              <AlertCircle className="w-10 h-10 text-red-400/60" />
                            ) : (
                              <Video className="w-10 h-10 text-white/20" />
                            )}
                          </div>
                        )}
                      </>
                    )}

                    {/* Progress bar */}
                    {isActive &&
                      typeof project.progress_pct === "number" &&
                      project.progress_pct > 0 && (
                        <div className="absolute bottom-0 left-0 right-0 h-1 bg-white/10">
                          <div
                            className="h-full bg-[#5a9ab5] transition-all duration-500"
                            style={{ width: `${project.progress_pct}%` }}
                          />
                        </div>
                      )}
                  </div>
                </div>

                {/* Right: status-specific panel */}
                <div className="flex-1 min-w-0">
                  {(project.status === "queued" ||
                    project.status === "generating_script" ||
                    project.status === "generating_video" ||
                    project.status === "in_progress") && (
                    <VideoConfigPanel project={project} />
                  )}

                  {project.status === "script_ready" && (
                    <ScriptReadyPanel
                      project={project}
                      onRegenerate={handleRegenerate}
                      onApprove={handleApprove}
                    />
                  )}

                  {project.status === "completed" && (
                    <CompletedPanel
                      project={project}
                    />
                  )}

                  </div>
                </div>

                {/* NEW: Version History Section (Full Width) */}
                {isCompleted && project.editor_export_history && project.editor_export_history.length > 0 && (
                  <div className="mt-12 pt-12 border-t border-white/10">
                    <div className="flex items-center justify-between mb-8">
                      <div>
                        <h2 className="text-xl font-medium text-white flex items-center gap-2">
                          <Clock className="w-5 h-5 text-[#5a9ab5]" />
                          Version History
                        </h2>
                        <p className="text-sm text-white/40 mt-1">
                          Review and edit previous export versions of your video.
                        </p>
                      </div>
                    </div>

                    {restoreError && (
                      <div className="flex items-center gap-2 text-red-400 bg-red-500/10 border border-red-500/20 rounded-xl px-4 py-3 mb-4">
                        <AlertCircle className="w-4 h-4 shrink-0" />
                        <span className="text-sm">{restoreError}</span>
                      </div>
                    )}

                    <div className="grid grid-cols-1 gap-4">
                      {(project.editor_export_history ?? [])
                        .filter((entry) => !!entry?.export_id && !!entry?.completed_at && !!entry?.download_url)
                        .filter((entry) => entry.export_id !== project.editor_export?.export_id)
                        .map((entry, index, arr) => (
                          <motion.div
                            key={entry.export_id}
                            initial={{ opacity: 0, x: -10 }}
                            animate={{ opacity: 1, x: 0 }}
                            transition={{ delay: index * 0.05 }}
                            className="group relative flex items-center gap-6 p-4 rounded-2xl bg-[#2a2a2a] border border-white/5 hover:border-white/10 hover:bg-[#323232] transition-all"
                          >
                            {/* Version Thumbnail (Using main project thumbnail since export thumbnails may not be ready) */}
                            <div className="w-32 aspect-video rounded-lg overflow-hidden bg-black/40 border border-white/10 relative shrink-0">
                              <img 
                                src={`${API}/api/v1/projects/${project.project_id}/thumbnail${idToken ? `?token=${idToken}` : ""}`}
                                alt={`Version ${arr.length - index}`}
                                className="w-full h-full object-cover"
                              />
                            </div>

                            {/* Info */}
                            <div className="flex-1 min-w-0">
                              <div className="flex items-center gap-2 mb-1">
                                <h4 className="text-sm font-semibold text-white">
                                  Version {arr.length - index}
                                </h4>
                                <span className="text-[10px] px-1.5 py-0.5 rounded bg-white/5 border border-white/10 text-white/40 font-mono uppercase">
                                  {entry.export_id.slice(0, 8)}
                                </span>
                              </div>
                              <div className="flex items-center gap-4 text-xs text-white/40">
                                <span className="flex items-center gap-1">
                                  <Clock className="w-3 h-3" />
                                  Exported {timeAgo(entry.completed_at)}
                                </span>
                              </div>
                            </div>

                            {/* Actions */}
                            <div className="flex items-center gap-2">
                              <a
                                href={entry.download_url}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="h-10 px-4 flex items-center justify-center rounded-xl border border-white/10 bg-white/5 text-sm font-medium text-white hover:bg-white/10 transition-colors"
                              >
                                <Download className="w-4 h-4 mr-2 text-white/50" />
                                Download
                              </a>
                              <Button
                                variant="outline"
                                size="sm"
                                onClick={() => setShareExportId(entry.export_id)}
                                className="h-10 px-4 rounded-xl border-white/10 bg-white/5 text-sm font-medium text-white hover:bg-white/10 transition-colors"
                              >
                                <Share2 className="w-4 h-4 mr-2 text-white/50" />
                                Share
                              </Button>
                              <Button
                                variant="outline"
                                size="sm"
                                disabled={!entry.project_json_snapshot || restoringExportId === entry.export_id}
                                onClick={async () => {
                                  if (!entry.project_json_snapshot) return;

                                  setRestoreError(null);
                                  setRestoringExportId(entry.export_id);
                                  try {
                                    await handleEditFromVersion(entry.export_id, true);
                                    setRestoringExportId(null);
                                  } catch (err) {
                                    setRestoreError(err instanceof Error ? err.message : "Failed to open version for editing");
                                    setRestoringExportId(null);
                                  }
                                }}
                                className="h-10 px-4 rounded-xl border-[#5a9ab5]/30 bg-[#5a9ab5]/10 text-[#5a9ab5] hover:bg-[#5a9ab5] hover:text-white transition-all transition-colors"
                              >
                                {restoringExportId === entry.export_id ? (
                                  <Loader2 className="w-4 h-4 animate-spin mr-2" />
                                ) : (
                                  <Settings className="w-4 h-4 mr-2" />
                                )}
                                Edit
                              </Button>
                            </div>
                          </motion.div>
                        ))}
                    </div>
                  </div>
                )}

                <ShareDialog
                  open={!!shareExportId}
                  onOpenChange={(open) => { if (!open) setShareExportId(null); }}
                  projectId={projectId}
                  exportId={shareExportId ?? undefined}
                />

                {project.status === "failed" && (
                  <div className="flex flex-col items-center justify-center py-12 gap-4 text-center">
                    <AlertCircle className="w-12 h-12 text-red-400 opacity-70" />
                    <p className="text-white font-medium">Generation Failed</p>
                    {project.error && (
                      <p className="text-red-400/80 text-sm max-w-sm">
                        {project.error}
                      </p>
                    )}
                    {project.error_code && (
                      <p className="text-white/35 text-xs">
                        Error code: {project.error_code}
                        {typeof project.script_attempt_count === "number"
                          ? ` • Attempts: ${project.script_attempt_count}`
                          : ""}
                      </p>
                    )}
                    {project.retryable && (
                      <Button
                        onClick={handleRetryScript}
                        className="rounded-full bg-[#5a9ab5] hover:bg-[#7ab0c8] text-white"
                      >
                        <RefreshCw className="w-4 h-4 mr-2" />
                        Retry Script
                      </Button>
                    )}
                  </div>
                )}
              </motion.div>
            )}
          </main>
        </div>
      </div>
    );
  }
