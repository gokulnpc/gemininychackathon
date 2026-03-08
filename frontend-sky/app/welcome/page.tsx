"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Loader2, Search, Play, Video, FileText, TrendingUp, ChevronDown, Coins, LayoutDashboard, LogOut, Settings, User } from "lucide-react";
import { motion } from "framer-motion";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { ResponsiveContainer, LineChart, Line, BarChart, Bar, XAxis, CartesianGrid, YAxis } from "recharts";
import { AppSidebar } from "@/components/app-sidebar";
import { useSidebar } from "@/context/SidebarContext";
import { Music, Image as LucideImage, Mic as VoiceMemo, ArrowRight } from "lucide-react";

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
    title: "Speech to Movie",
    description: "Upload a voice memo or record audio to generate a short film",
    image: "/SpeechToVid.png",
  },
  {
    id: "text",
    title: "Text to Movie",
    description: "Manually input text to create a professional short film",
    image: "/TextToVid.png",
  },
  {
    id: "preset",
    title: "Presets",
    description: "Choose from pre-configured templates and workflows",
    image: "/Presets.png",
  },
];

const performanceData = [
  { name: 'Mon', value: 8 },
  { name: 'Tue', value: 12 },
  { name: 'Wed', value: 9 },
  { name: 'Thu', value: 16 },
  { name: 'Fri', value: 17 },
  { name: 'Sat', value: 11 },
  { name: 'Sun', value: 13 },
];

const distributionData = [
  { name: 'Speech', value: 45 },
  { name: 'Text', value: 85 },
  { name: 'Presets', value: 130 },
];

export default function WelcomePage() {
  const router = useRouter();

  const [recents, setRecents] = useState<Project[]>([]);
  const [totalVideos, setTotalVideos] = useState(0);
  const [recentsLoading, setRecentsLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [assetFilter, setAssetFilter] = useState("All");

  const [assets, setAssets] = useState<{ images: any[]; music: any[]; voice_memos: any[] }>({ images: [], music: [], voice_memos: [] });
  const [assetsLoading, setAssetsLoading] = useState(true);

  const assetFilters = ["All", "Voice Memos", "Images", "Music"];

  const allAssets = [
    ...assets.voice_memos.map((a: any) => ({ ...a, category: "voice_memos" })),
    ...assets.images.map((a: any) => ({ ...a, category: "images" })),
    ...assets.music.map((a: any) => ({ ...a, category: "music" })),
  ].sort((a, b) => new Date(b.uploaded_at).getTime() - new Date(a.uploaded_at).getTime());

  const filteredAssets = assetFilter === "All" 
    ? allAssets 
    : allAssets.filter(a => {
        if (assetFilter === "Voice Memos" && a.category === "voice_memos") return true;
        if (assetFilter === "Images" && a.category === "images") return true;
        if (assetFilter === "Music" && a.category === "music") return true;
        return false;
      });
  const displayAssets = filteredAssets.slice(0, 4);

  useEffect(() => {
    fetch(`${API}/api/v1/projects`)
      .then((r) => r.json())
      .then((d) => {
        setRecents((d.projects ?? []).filter((p: Project) => p.status === "completed").slice(0, 5));
        setTotalVideos(d.total ?? 0);
      })
      .catch(() => setRecents([]))
      .finally(() => setRecentsLoading(false));

    Promise.all([
      fetch(`${API}/api/v1/assets?category=images`).then((r) => r.json()),
      fetch(`${API}/api/v1/assets?category=music`).then((r) => r.json()),
      fetch(`${API}/api/v1/assets?category=voice_memos`).then((r) => r.json()),
    ])
      .then(([img, mus, vcm]) => {
        setAssets({
          images: img.assets ?? [],
          music: mus.assets ?? [],
          voice_memos: vcm.assets ?? [],
        });
      })
      .catch(() => {})
      .finally(() => setAssetsLoading(false));
  }, []);

  const filteredRecents = recents.filter((p) =>
    projectTitle(p).toLowerCase().includes(search.toLowerCase())
  );

  const handleCreateClick = (type: string) => {
    router.push(`/create?tab=${type}`);
  };

  const { isCollapsed } = useSidebar();

  return (
    <div className="flex min-h-screen bg-[#2B2B2B]">
      <AppSidebar />

      <div className={cn(
        "flex-1 flex flex-col min-h-screen transition-all duration-300",
        isCollapsed ? "ml-[80px]" : "ml-[280px]"
      )}>
        {/* Header */}
        <header className="flex items-center justify-end px-8 py-6">
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <button className="flex items-center gap-3 bg-white/10 rounded-full px-4 py-2 border border-white/20 hover:bg-white/15 transition-colors">
                <Avatar className="w-8 h-8">
                  <AvatarImage src="/Avatar.png" alt="An Tran" />
                  <AvatarFallback className="bg-[#5a9ab5] text-white text-sm">
                    AT
                  </AvatarFallback>
                </Avatar>
                <span className="text-sm font-medium text-white">An Tran</span>
              </button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-64">
              <div className="px-3 py-3 bg-[#5a9ab5]/5 rounded-lg mx-2 mt-2 mb-2">
                <div className="flex items-center gap-2 mb-1">
                  <Coins className="w-4 h-4 text-[#5a9ab5]" />
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
        <main className="max-w-8xl mx-auto px-12 py-8 w-full">
          {/* Welcome Section */}
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5 }}
            className="mb-12"
          >
            <h1 className="text-4xl font-medium text-white mb-2">
              Welcome <span className="text-[#5a9ab5]">An</span>!
            </h1>
            <p className="text-2xl text-white/70">
              What would you like to build?
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
                  boxShadow: "0 8px 24px rgba(0,0,0,0.3)",
                }}
                onClick={() => handleCreateClick(option.id)}
                className="bg-[#333333] rounded-2xl border border-white/10 p-6 text-left transition-all duration-200 hover:border-[#5a9ab5]/50"
              >
                <div className="w-16 h-16 mb-4">
                  <img
                    src={option.image}
                    alt={option.title}
                    className="w-full h-full object-contain"
                  />
                </div>
                <h3 className="text-lg font-medium text-white mb-2">
                  {option.title}
                </h3>
                <p className="text-sm text-white/80 leading-relaxed">
                  {option.description}
                </p>
              </motion.button>
            ))}
          </motion.div>

          {/* Overview Section */}
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5, delay: 0.3 }}
            className="mb-16"
          >
            <h2 className="text-xl font-medium text-white mb-6">Overview</h2>
            <div className="grid grid-cols-3 gap-6">
              {/* Column 1: Stats */}
              <div className="flex flex-col gap-6">
                {/* Total Videos */}
                <div className="rounded-2xl border border-white/10 p-6 flex-1 relative overflow-hidden flex flex-col justify-between" style={{ backgroundImage: "url('/card2.jpg')", backgroundSize: "cover", backgroundPosition: "center" }}>
                  <div className="absolute inset-0 bg-black/40 pointer-events-none" />
                  <div className="flex items-center justify-between relative z-10 w-full">
                    <div className="w-10 h-10 rounded-xl bg-[#1A1A1A] flex items-center justify-center border border-white/5">
                      <Video className="w-5 h-5 text-[#5a9ab5]" />
                    </div>
                    <div className="text-right">
                      <p className="text-sm text-white/60 mb-1">Total Videos</p>
                      <p className="text-4xl font-semibold text-white">{totalVideos}</p>
                    </div>
                  </div>
                </div>
                
                {/* Credit Used */}
                <div className="rounded-2xl border border-white/10 p-6 flex-1 relative overflow-hidden flex flex-col justify-between" style={{ backgroundImage: "url('/card2.jpg')", backgroundSize: "cover", backgroundPosition: "center" }}>
                  <div className="absolute inset-0 bg-black/40 pointer-events-none" />
                  <div className="flex items-center justify-between relative z-10 w-full">
                    <div className="w-10 h-10 rounded-xl bg-[#1A1A1A] flex items-center justify-center border border-white/5">
                      <FileText className="w-5 h-5 text-[#5a9ab5]" />
                    </div>
                    <div className="text-right">
                      <p className="text-sm text-white/60 mb-1">Credit Used</p>
                      <div className="flex items-baseline gap-2 justify-end">
                        <p className="text-4xl font-semibold text-white">200</p>
                        <p className="text-lg text-white/40">/ 400</p>
                      </div>
                    </div>
                  </div>
                </div>
              </div>

              {/* Column 2: Video Performance */}
              <div className="rounded-2xl border border-white/10 p-6 relative overflow-hidden" style={{ backgroundImage: "url('/card2.jpg')", backgroundSize: "cover", backgroundPosition: "center" }}>
                <div className="absolute inset-0 bg-black/40 pointer-events-none" />
                <div className="flex items-center justify-between mb-6 relative z-10">
                  <h3 className="text-lg font-medium text-white">Video Performance</h3>
                  <button className="flex items-center gap-2 bg-white text-black px-3 py-1.5 rounded-full text-xs font-medium">
                    Weekly <ChevronDown className="w-3 h-3" />
                  </button>
                </div>
                <div className="h-[200px] w-full relative z-10 flex items-center justify-center">
                  <ResponsiveContainer width="100%" height="100%">
                    <LineChart data={performanceData} margin={{ top: 10, right: 30, left: 0, bottom: 0 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" vertical={false} />
                      <XAxis dataKey="name" stroke="rgba(255,255,255,0.4)" fontSize={12} tickLine={false} axisLine={false} />
                      <YAxis stroke="rgba(255,255,255,0.4)" fontSize={12} tickLine={false} axisLine={false} />
                      <Line type="monotone" dataKey="value" stroke="#5a9ab5" strokeWidth={3} dot={false} />
                    </LineChart>
                  </ResponsiveContainer>
                </div>
              </div>

              {/* Column 3: Video Distribution */}
              <div className="rounded-2xl border border-white/10 p-6 relative overflow-hidden" style={{ backgroundImage: "url('/card2.jpg')", backgroundSize: "cover", backgroundPosition: "center" }}>
                <div className="absolute inset-0 bg-black/40 pointer-events-none" />
                <h3 className="text-lg font-medium text-white mb-6 relative z-10">Video Distribution</h3>
                <div className="h-[200px] w-full relative z-10 flex items-center justify-center">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={distributionData} barSize={40} margin={{ top: 10, right: 30, left: 0, bottom: 0 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" vertical={false} />
                      <XAxis dataKey="name" stroke="rgba(255,255,255,0.4)" fontSize={12} tickLine={false} axisLine={false} />
                      <YAxis stroke="rgba(255,255,255,0.4)" fontSize={12} tickLine={false} axisLine={false} />
                      <Bar dataKey="value" fill="#4B88A0" radius={[4, 4, 0, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              </div>
            </div>
          </motion.div>

          {/* Recents Section */}
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5, delay: 0.4 }}
          >
            <div className="flex items-center justify-between mb-6">
              <h2 className="text-xl font-medium text-white">Recents</h2>
              <button
                onClick={() => router.push("/dashboard")}
                className="text-sm font-medium text-[#7ab0c8] hover:text-[#FFFFFF] transition-colors flex items-center gap-1"
              >
                View more <ArrowRight className="w-4 h-4" />
              </button>
            </div>

            <div className="relative mb-6">
              <Search className="absolute left-4 top-1/2 -translate-y-1/2 w-5 h-5 text-white/40" />
              <Input
                type="text"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Search your movies..."
                className="pl-12 h-12 rounded-xl bg-[#333333] border-white/10 text-white placeholder:text-white/30 focus:border-[#5a9ab5] focus:ring-[#5a9ab5]/20"
              />
            </div>

            {recentsLoading ? (
              <div className="flex items-center justify-center py-16 text-white/40">
                <Loader2 className="w-5 h-5 animate-spin mr-2" /> Loading…
              </div>
            ) : filteredRecents.length === 0 ? (
              <p className="text-sm text-white/40 py-8 text-center">
                {recents.length === 0 ? "No movies yet." : "No results."}
              </p>
            ) : (
              <div className="grid grid-cols-5 gap-4">
                {filteredRecents.map((project, index) => {
                  const t = projectTitle(project);
                  const platform = (project.platforms ?? [])[0] ?? "master";
                  return (
                    <motion.button
                      key={project.project_id}
                      initial={{ opacity: 0, y: 20 }}
                      animate={{ opacity: 1, y: 0 }}
                      transition={{ duration: 0.4, delay: 0.5 + index * 0.1 }}
                      whileHover={{ y: -4 }}
                      onClick={() => router.push("/dashboard")}
                      className="bg-[#333333] rounded-2xl border border-white/10 overflow-hidden text-left transition-all duration-200 hover:shadow-lg hover:border-[#5a9ab5]/40"
                    >
                      <div
                        className={`relative aspect-9/16 bg-linear-to-br ${gradient(project.project_id)}`}
                      >
                        <img
                          src={thumbnailUrl(project.project_id, platform)}
                          alt={t}
                          className="absolute inset-0 w-full h-full object-cover"
                          onError={(e) => {
                            (e.target as HTMLImageElement).style.display =
                              "none";
                          }}
                        />
                        <div className="absolute inset-0 bg-black/20 opacity-0 hover:opacity-100 transition-opacity flex items-center justify-center">
                          <div className="w-12 h-12 rounded-full bg-white/90 flex items-center justify-center">
                            <Play className="w-5 h-5 text-[#1A1A1A] ml-0.5" />
                          </div>
                        </div>
                      </div>
                      <div className="p-4">
                        <h3 className="text-sm font-medium text-white mb-1 line-clamp-2">
                          {t}
                        </h3>
                        <p className="text-xs text-white/40">
                          {timeAgo(project.created_at)}
                        </p>
                      </div>
                    </motion.button>
                  );
                })}
              </div>
            )}
          </motion.div>

          {/* My Assets Section */}
          {!assetsLoading && (
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.5, delay: 0.6 }}
              className="mt-16 mb-20"
            >
              <div className="flex items-center justify-between mb-8">
                <h2 className="text-2xl font-medium text-white">My Assets</h2>
                <button
                  onClick={() => router.push("/assets")}
                  className="text-sm font-medium text-[#7ab0c8] hover:text-[#FFFFFF] transition-colors flex items-center gap-1"
                >
                  View all <ArrowRight className="w-4 h-4" />
                </button>
              </div>

              <div className="flex flex-col gap-6">
                {/* Filters */}
                <div className="flex items-center gap-3">
                  {assetFilters.map(filter => (
                    <button
                      key={filter}
                      onClick={() => setAssetFilter(filter)}
                      className={cn(
                        "px-6 py-2 rounded-full text-sm font-medium transition-colors",
                        assetFilter === filter 
                          ? "bg-white text-black" 
                          : "bg-white/15 text-white/80 hover:bg-white/20 hover:text-white"
                      )}
                    >
                      {filter}
                    </button>
                  ))}
                </div>

                {/* Asset Grid or Empty State */}
                {displayAssets.length > 0 ? (
                  <div className="grid grid-cols-4 gap-6">
                    {displayAssets.map(asset => (
                      <AssetPreview key={asset.id} asset={asset} />
                    ))}
                  </div>
                ) : (
                  <div className="py-12 border border-white/10 rounded-2xl border-dashed flex items-center justify-center flex-col gap-2">
                    <p className="text-white/40 text-sm">No {assetFilter.toLowerCase()} found.</p>
                  </div>
                )}
              </div>
            </motion.div>
          )}
        </main>
      </div>
    </div>
  );
}

function AssetPreview({ asset }: { asset: any }) {
  const [imageUrl, setImageUrl] = useState<string | null>(null);

  useEffect(() => {
    if (asset.category !== "images") return;
    fetch(`${API}/api/v1/assets/${asset.id}/url?category=images`)
      .then((r) => r.json())
      .then((d) => setImageUrl(d.url))
      .catch(() => {});
  }, [asset.id, asset.category]);

  if (asset.category === "images") {
    return (
      <div className="flex flex-col gap-3">
        <div className="aspect-[3/2] rounded-2xl overflow-hidden border border-white/5 relative bg-[#1E2532] flex items-center justify-center">
          {imageUrl ? (
            <img src={imageUrl} alt={asset.filename} className="w-full h-full object-cover" />
          ) : (
            <LucideImage className="w-8 h-8 text-white/20" />
          )}
        </div>
        <h3 className="text-sm font-medium text-white truncate">{asset.filename}</h3>
      </div>
    );
  }

  const Icon = asset.category === "music" ? Music : VoiceMemo;
  return (
    <div className="flex flex-col gap-3">
      <div className="aspect-[3/2] rounded-2xl bg-[#1E2532] border border-white/5 p-5 flex flex-col justify-between overflow-hidden relative">
        <div className="absolute left-8 right-8 top-0 bottom-0 bg-[#1A202C] opacity-50 z-0 rounded-lg pointer-events-none mix-blend-multiply" />
        <div className="absolute left-0 right-0 top-0 bottom-0 bg-gradient-to-r from-transparent via-[#1A202C]/20 to-transparent z-0 pointer-events-none" />
        
        {[1, 2, 3, 4].map(i => (
          <div key={i} className="flex items-center gap-4 relative z-10 opacity-80">
            <div className="w-8 h-8 rounded-full bg-[#303B52] flex items-center justify-center shrink-0 border border-white/5">
              <Icon className="w-4 h-4 text-[#5a9ab5]" />
            </div>
            <div className="h-2.5 bg-[#303B52] rounded-full w-24 border border-white/5" />
          </div>
        ))}
      </div>
      <h3 className="text-sm font-medium text-white truncate">{asset.filename}</h3>
    </div>
  );
}
