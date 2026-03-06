"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";
import { AlertCircle, Loader2, Play, X, Download, ArrowLeft } from "lucide-react";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

interface Project {
  project_id: string;
  created_at: string;
  status: "completed" | "failed";
  series_name: string | null;
  hook: string | null;
  scenes_count: number;
  platforms: string[];
  video_urls: Record<string, string>;
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

function title(p: Project): string {
  return p.hook ?? p.series_name ?? p.project_id.slice(0, 8);
}

function streamUrl(projectId: string, platform: string) {
  return `${API}/api/v1/projects/${projectId}/stream/${platform}`;
}

function thumbnailUrl(projectId: string, platform: string) {
  return `${API}/api/v1/projects/${projectId}/thumbnail?platform=${platform}`;
}

export default function GalleryPage() {
  const router = useRouter();
  const [projects, setProjects] = useState<Project[]>([]);
  const [loading, setLoading] = useState(true);
  const [fetchError, setFetchError] = useState<string | null>(null);
  const [selected, setSelected] = useState<Project | null>(null);

  useEffect(() => {
    fetch(`${API}/api/v1/projects`)
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then((d) => setProjects((d.projects ?? []).filter((p: Project) => p.status === "completed")))
      .catch((e) => setFetchError(e.message))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="min-h-screen bg-black text-white grain-overlay">
      {/* Header */}
      <header className="fixed top-0 left-0 right-0 z-40 px-6 py-6 md:px-12 md:py-8 flex justify-between items-center">
        <button
          onClick={() => router.push("/")}
          className="flex items-center gap-2 text-white/60 hover:text-white transition-colors text-sm"
        >
          <ArrowLeft className="w-4 h-4" />
          Story Lab
        </button>
        <span className="text-sm text-white/40 tracking-wide uppercase">Gallery</span>
      </header>

      <main className="pt-32 pb-24 px-6 md:px-12 max-w-screen-xl mx-auto">
        {/* Title */}
        <motion.div
          initial={{ opacity: 0, y: 30 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.8, ease: [0.76, 0, 0.24, 1] }}
          className="mb-16"
        >
          <h1 className="text-6xl md:text-8xl lg:text-9xl font-normal tracking-tighter leading-none mb-4">
            Gallery
          </h1>
          {!loading && !fetchError && (
            <p className="text-white/40 text-lg">
              {projects.length} video{projects.length !== 1 ? "s" : ""} generated
            </p>
          )}
        </motion.div>

        {/* Loading */}
        {loading && (
          <div className="flex items-center justify-center py-40 text-white/40">
            <Loader2 className="w-5 h-5 animate-spin mr-3" /> Loading…
          </div>
        )}

        {/* Error */}
        {!loading && fetchError && (
          <div className="flex items-center justify-center py-40 text-red-400 gap-2">
            <AlertCircle className="w-5 h-5" /> Failed to load: {fetchError}
          </div>
        )}

        {/* Empty */}
        {!loading && !fetchError && projects.length === 0 && (
          <div className="flex flex-col items-center justify-center py-40 text-white/40">
            <p className="text-xl mb-6">No videos yet.</p>
            <button
              onClick={() => router.push("/create")}
              className="px-8 py-3 rounded-full border border-white/20 text-white hover:bg-white hover:text-black transition-colors text-sm"
            >
              Create your first video
            </button>
          </div>
        )}

        {/* Grid */}
        {!loading && !fetchError && projects.length > 0 && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: 0.3 }}
            className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-4"
          >
            {projects.map((project, index) => {
              const platform = project.platforms[0] ?? "master";
              const t = title(project);

              return (
                <motion.button
                  key={project.project_id}
                  initial={{ opacity: 0, y: 20 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: 0.1 + index * 0.04, duration: 0.5 }}
                  onClick={() => setSelected(project)}
                  className="group relative aspect-[9/16] rounded-xl overflow-hidden bg-white/5 border border-white/10 hover:border-white/30 transition-all duration-300 text-left"
                >
                  {/* Thumbnail */}
                  <img
                    src={thumbnailUrl(project.project_id, platform)}
                    alt={t}
                    className="absolute inset-0 w-full h-full object-cover transition-transform duration-500 group-hover:scale-105"
                    onError={(e) => { (e.target as HTMLImageElement).style.display = "none"; }}
                  />

                  {/* Hover overlay */}
                  <div className="absolute inset-0 bg-black/50 opacity-0 group-hover:opacity-100 transition-opacity duration-300 flex items-center justify-center">
                    <div className="w-12 h-12 rounded-full bg-white/90 flex items-center justify-center">
                      <Play className="w-5 h-5 text-black ml-0.5" />
                    </div>
                  </div>

                  {/* Bottom info */}
                  <div className="absolute bottom-0 left-0 right-0 p-3 bg-gradient-to-t from-black/80 to-transparent translate-y-full group-hover:translate-y-0 transition-transform duration-300">
                    <p className="text-xs text-white font-medium line-clamp-2 mb-1">{t}</p>
                    <p className="text-xs text-white/50">{timeAgo(project.created_at)}</p>
                  </div>

                  {/* Scenes badge */}
                  <div className="absolute top-2 right-2 px-2 py-0.5 bg-black/60 rounded text-xs text-white/70">
                    {project.scenes_count}s
                  </div>
                </motion.button>
              );
            })}
          </motion.div>
        )}
      </main>

      {/* Lightbox */}
      <AnimatePresence>
        {selected && (() => {
          const platform = selected.platforms[0] ?? "master";
          const src = streamUrl(selected.project_id, platform);
          const t = title(selected);

          return (
            <motion.div
              key="lightbox"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.3 }}
              className="fixed inset-0 z-50 bg-black/90 backdrop-blur-sm flex items-center justify-center p-6"
              onClick={() => setSelected(null)}
            >
              <motion.div
                initial={{ scale: 0.95, opacity: 0 }}
                animate={{ scale: 1, opacity: 1 }}
                exit={{ scale: 0.95, opacity: 0 }}
                transition={{ duration: 0.3, ease: [0.76, 0, 0.24, 1] }}
                className="relative flex flex-col items-center gap-4 max-h-full"
                onClick={(e) => e.stopPropagation()}
              >
                {/* Close */}
                <button
                  onClick={() => setSelected(null)}
                  className="absolute -top-12 right-0 text-white/60 hover:text-white transition-colors"
                >
                  <X className="w-6 h-6" />
                </button>

                {/* Video */}
                <div className="aspect-[9/16] max-h-[75vh] bg-black rounded-2xl overflow-hidden shadow-2xl">
                  <video
                    key={src}
                    src={src}
                    controls
                    autoPlay
                    className="w-full h-full object-contain"
                  />
                </div>

                {/* Meta + actions */}
                <div className="flex items-center justify-between w-full px-1">
                  <div>
                    <p className="text-white text-sm font-medium line-clamp-1">{t}</p>
                    <p className="text-white/40 text-xs mt-0.5">
                      {timeAgo(selected.created_at)} · {selected.scenes_count} scenes · {selected.platforms.join(", ")}
                    </p>
                  </div>
                  <a
                    href={src}
                    download
                    className="flex items-center gap-2 px-4 py-2 rounded-full border border-white/20 text-white text-sm hover:bg-white hover:text-black transition-colors"
                  >
                    <Download className="w-4 h-4" />
                    Download
                  </a>
                </div>
              </motion.div>
            </motion.div>
          );
        })()}
      </AnimatePresence>
    </div>
  );
}
