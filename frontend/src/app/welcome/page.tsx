"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Loader2, Search, Play } from "lucide-react";
import { motion } from "framer-motion";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { Input } from "@/components/ui/input";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Coins, LayoutDashboard, LogOut, Settings, User } from "lucide-react";

// ── Config ──────────────────────────────────────────────────────────────────
const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

// ── Types ────────────────────────────────────────────────────────────────────
interface Project {
  project_id: string;
  created_at: string;
  status: "completed" | "failed";
  series_name: string | null;
  hook: string | null;
  scenes_count: number;
  platforms: string[];
}

// ── Helpers ──────────────────────────────────────────────────────────────────
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

function projectTitle(p: Project): string {
  return p.hook ?? p.series_name ?? p.project_id.slice(0, 8);
}

function thumbnailUrl(projectId: string, platform: string) {
  return `${API}/api/v1/projects/${projectId}/thumbnail?platform=${platform}`;
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

// ── Static options ───────────────────────────────────────────────────────────
const createOptions = [
  {
    id: "speech",
    title: "Speech to Video",
    description:
      "Upload a voice memo or record audio to generate a marketing video",
    image: "/SpeechToVid.png",
  },
  {
    id: "text",
    title: "Text to Video",
    description: "Manually input text to create a professional marketing video",
    image: "/TextToVid.png",
  },
  {
    id: "preset",
    title: "Presets",
    description: "Choose from pre-configured templates and workflows",
    image: "/Presets.png",
  },
];

export default function WelcomePage() {
  const router = useRouter();

  const [recents, setRecents] = useState<Project[]>([]);
  const [recentsLoading, setRecentsLoading] = useState(true);
  const [search, setSearch] = useState("");

  useEffect(() => {
    fetch(`${API}/api/v1/projects`)
      .then((r) => r.json())
      .then((d) => setRecents((d.projects ?? []).slice(0, 3)))
      .catch(() => setRecents([]))
      .finally(() => setRecentsLoading(false));
  }, []);

  const filteredRecents = recents.filter((p) =>
    projectTitle(p).toLowerCase().includes(search.toLowerCase())
  );

  const handleCreateClick = (type: string) => {
    router.push(`/create?tab=${type}`);
  };

  return (
    <div className="min-h-screen">
      {/* Header */}
      <header className="flex items-center justify-between px-8 py-6">
        <button onClick={() => router.push("/welcome")}>
          <img
            src="/Logo_ContentFactory.png"
            alt="Content Factory"
            className="h-6"
          />
        </button>

        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <button className="flex items-center gap-3 bg-white rounded-full px-4 py-2 shadow-sm border border-[#F0E8E4] hover:shadow-md transition-shadow">
              <Avatar className="w-8 h-8">
                <AvatarImage src="/Avatar.png" alt="An Tran" />
                <AvatarFallback className="bg-[#B08D9F] text-white text-sm">
                  AT
                </AvatarFallback>
              </Avatar>
              <span className="text-sm font-medium text-[#1A1A1A]">
                An Tran
              </span>
            </button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-64">
            <div className="px-3 py-3 bg-[#B08D9F]/5 rounded-lg mx-2 mt-2 mb-2">
              <div className="flex items-center gap-2 mb-1">
                <Coins className="w-4 h-4 text-[#B08D9F]" />
                <span className="text-sm font-medium text-[#1A1A1A]">
                  Credits
                </span>
              </div>
              <p className="text-2xl font-semibold text-[#1A1A1A]">1,250</p>
              <p className="text-xs text-[#9B9B9B] mt-0.5">
                ~25 videos remaining
              </p>
            </div>
            <DropdownMenuSeparator />
            <DropdownMenuItem
              onClick={() => router.push("/dashboard")}
              className="cursor-pointer"
            >
              <LayoutDashboard className="w-4 h-4 mr-2" />
              Dashboard
            </DropdownMenuItem>
            <DropdownMenuItem className="cursor-pointer">
              <User className="w-4 h-4 mr-2" />
              Profile
            </DropdownMenuItem>
            <DropdownMenuItem className="cursor-pointer">
              <Settings className="w-4 h-4 mr-2" />
              Settings
            </DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem
              onClick={() => router.push("/login")}
              className="cursor-pointer text-red-600"
            >
              <LogOut className="w-4 h-4 mr-2" />
              Sign out
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </header>

      {/* Main Content */}
      <main className="max-w-5xl mx-auto px-8 py-8">
        {/* Welcome Section */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5 }}
          className="mb-12"
        >
          <h1 className="text-4xl font-medium text-[#1A1A1A] mb-2">
            Welcome <span className="text-[#B08D9F]">An</span>!
          </h1>
          <p className="text-2xl text-[#1A1A1A]">
            What would you like to create?
          </p>
        </motion.div>

        {/* Create Options */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, delay: 0.1 }}
          className="grid grid-cols-3 gap-6 mb-16"
        >
          {createOptions.map((option, index) => (
            <motion.button
              key={option.id}
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.4, delay: 0.2 + index * 0.1 }}
              whileHover={{
                y: -4,
                boxShadow: "0 8px 24px rgba(0,0,0,0.08)",
              }}
              onClick={() => handleCreateClick(option.id)}
              className="bg-white rounded-2xl border border-[#E8E0DC] p-6 text-left transition-all duration-200 hover:border-[#B08D9F]/30"
            >
              <div className="w-16 h-16 mb-4">
                <img
                  src={option.image}
                  alt={option.title}
                  className="w-full h-full object-contain"
                />
              </div>
              <h3 className="text-lg font-medium text-[#1A1A1A] mb-2">
                {option.title}
              </h3>
              <p className="text-sm text-[#6B6B6B] leading-relaxed">
                {option.description}
              </p>
            </motion.button>
          ))}
        </motion.div>

        {/* Recents Section */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, delay: 0.4 }}
        >
          <div className="flex items-center justify-between mb-6">
            <h2 className="text-xl font-medium text-[#1A1A1A]">Recents</h2>
            <button
              onClick={() => router.push("/dashboard")}
              className="text-sm font-medium text-[#B08D9F] hover:text-[#9A7B8C] transition-colors"
            >
              View more
            </button>
          </div>

          <div className="relative mb-6">
            <Search className="absolute left-4 top-1/2 -translate-y-1/2 w-5 h-5 text-[#9B9B9B]" />
            <Input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search your videos..."
              className="pl-12 h-12 rounded-xl border-[#E8E0DC] bg-white focus:border-[#B08D9F] focus:ring-[#B08D9F]/20"
            />
          </div>

          {recentsLoading ? (
            <div className="flex items-center justify-center py-16 text-[#9B9B9B]">
              <Loader2 className="w-5 h-5 animate-spin mr-2" /> Loading…
            </div>
          ) : filteredRecents.length === 0 ? (
            <p className="text-sm text-[#9B9B9B] py-8 text-center">
              {recents.length === 0 ? "No videos yet." : "No results."}
            </p>
          ) : (
            <div className="grid grid-cols-3 gap-6">
              {filteredRecents.map((project, index) => {
                const t = projectTitle(project);
                const platform = project.platforms[0] ?? "master";
                return (
                  <motion.button
                    key={project.project_id}
                    initial={{ opacity: 0, y: 20 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ duration: 0.4, delay: 0.5 + index * 0.1 }}
                    whileHover={{ y: -4 }}
                    onClick={() => router.push("/dashboard")}
                    className="bg-white rounded-2xl border border-[#E8E0DC] overflow-hidden text-left transition-all duration-200 hover:shadow-md hover:border-[#B08D9F]/30"
                  >
                    <div className={`relative aspect-[9/16] bg-gradient-to-br ${gradient(project.project_id)}`}>
                      <img
                        src={thumbnailUrl(project.project_id, platform)}
                        alt={t}
                        className="absolute inset-0 w-full h-full object-cover"
                        onError={(e) => { (e.target as HTMLImageElement).style.display = "none"; }}
                      />
                      <div className="absolute inset-0 bg-black/20 opacity-0 hover:opacity-100 transition-opacity flex items-center justify-center">
                        <div className="w-12 h-12 rounded-full bg-white/90 flex items-center justify-center">
                          <Play className="w-5 h-5 text-[#1A1A1A] ml-0.5" />
                        </div>
                      </div>
                    </div>
                    <div className="p-4">
                      <h3 className="text-sm font-medium text-[#1A1A1A] mb-1 line-clamp-2">{t}</h3>
                      <p className="text-xs text-[#9B9B9B]">{timeAgo(project.created_at)}</p>
                    </div>
                  </motion.button>
                );
              })}
            </div>
          )}
        </motion.div>
      </main>
    </div>
  );
}
