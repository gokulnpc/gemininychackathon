"use client";

import { Play, Pause, ChevronRight, Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";
import { useWizard } from "@/context/WizardContext";
import { motion } from "framer-motion";
import { useState, useRef, useEffect } from "react";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

interface VoiceOption {
  id: string;
  description: string;
  tags: string[];
  default: boolean;
}

// Initials avatar colors per voice (cycles if more voices added)
const AVATAR_COLORS = [
  "bg-violet-500",
  "bg-sky-500",
  "bg-emerald-500",
  "bg-rose-500",
  "bg-amber-500",
  "bg-indigo-500",
  "bg-teal-500",
  "bg-fuchsia-500",
  "bg-orange-500",
];

export function Step4_Language() {
  const { state, dispatch } = useWizard();
  const [voices, setVoices] = useState<VoiceOption[]>([]);
  const [loadingVoices, setLoadingVoices] = useState(true);
  const [previewingId, setPreviewingId] = useState<string | null>(null);
  const [playingId, setPlayingId] = useState<string | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);

  useEffect(() => {
    fetch(`${API}/api/v1/voices`)
      .then((r) => r.json())
      .then((data: VoiceOption[]) => {
        setVoices(data);
        // Auto-select default voice if none selected yet
        if (!state.selectedVoice) {
          const defaultVoice = data.find((v) => v.default);
          if (defaultVoice) {
            dispatch({ type: "SET_SELECTED_VOICE", payload: defaultVoice.id });
          }
        }
      })
      .catch(() => setVoices([]))
      .finally(() => setLoadingVoices(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleVoiceSelect = (voiceId: string) => {
    dispatch({ type: "SET_SELECTED_VOICE", payload: voiceId });
  };

  const handlePreview = async (e: React.MouseEvent, voiceId: string) => {
    e.stopPropagation();

    if (playingId === voiceId) {
      audioRef.current?.pause();
      setPlayingId(null);
      return;
    }

    if (audioRef.current) {
      audioRef.current.pause();
      audioRef.current = null;
    }
    setPlayingId(null);
    setPreviewingId(voiceId);

    try {
      const res = await fetch(`${API}/api/v1/voices/${voiceId}/preview`);
      if (!res.ok) throw new Error("Preview failed");
      const data = await res.json();
      const audio = new Audio(`data:audio/wav;base64,${data.audio_base64}`);
      audioRef.current = audio;
      await audio.play();
      setPlayingId(voiceId);
      audio.onended = () => {
        setPlayingId(null);
        audioRef.current = null;
      };
    } catch {
      console.error("Voice preview failed");
    } finally {
      setPreviewingId(null);
    }
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -20 }}
      transition={{ duration: 0.3 }}
      className="space-y-6"
    >
      {/* Language Section */}
      <div>
        <h3 className="text-base font-semibold text-white mb-3">Language</h3>
        <button className="w-full flex items-center justify-between p-4 rounded-2xl border border-white/20 bg-white/20 hover:bg-white/25 hover:border-[#5a9ab5]/40 transition-all duration-200">
          <div className="flex items-center gap-3">
            <span className="text-2xl">🇺🇸</span>
            <span className="text-sm font-medium text-white">English</span>
          </div>
          <ChevronRight className="w-5 h-5 text-white/40" />
        </button>
      </div>

      {/* Voice Style Section */}
      <div>
        <h3 className="text-base font-semibold text-white mb-3">Voice Style</h3>

        {loadingVoices ? (
          <div className="flex items-center justify-center py-12">
            <Loader2 className="w-6 h-6 animate-spin text-[#5a9ab5]" />
          </div>
        ) : (
          <div className="space-y-3">
            {voices.map((voice, index) => (
              <motion.button
                key={voice.id}
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: index * 0.05 }}
                onClick={() => handleVoiceSelect(voice.id)}
                className={cn(
                  "w-full flex items-center justify-between p-4 rounded-2xl border transition-all duration-200",
                  state.selectedVoice === voice.id
                    ? "border-[#5a9ab5] bg-[#5a9ab5]/20"
                    : "border-white/20 bg-white/20 hover:border-[#5a9ab5]/40 hover:bg-white/25",
                )}
              >
                <div className="flex items-center gap-4">
                  {/* Initials avatar */}
                  <div
                    className={cn(
                      "w-10 h-10 rounded-full flex items-center justify-center text-sm font-bold text-white shrink-0",
                      AVATAR_COLORS[index % AVATAR_COLORS.length],
                    )}
                  >
                    {voice.id.slice(0, 2).toUpperCase()}
                  </div>
                  <div className="text-left">
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-medium text-white">{voice.id}</span>
                      {(voice.tags ?? []).filter(t => t === "female" || t === "male").map((tag) => (
                        <span
                          key={tag}
                          className={cn(
                            "text-xs px-2 py-0.5 rounded-full",
                            tag === "female" ? "bg-pink-500/20 text-pink-300" : "bg-blue-500/20 text-blue-300"
                          )}
                        >
                          {tag}
                        </span>
                      ))}
                    </div>
                    <div className="flex items-center gap-1.5 flex-wrap mt-1">
                      {(voice.tags ?? []).filter(t => t !== "female" && t !== "male").map((tag) => (
                        <span key={tag} className="text-xs px-2 py-0.5 rounded-full bg-white/10 text-white/60">
                          {tag}
                        </span>
                      ))}
                    </div>
                  </div>
                </div>

                {/* Preview button */}
                <motion.div
                  whileHover={{ scale: 1.1 }}
                  whileTap={{ scale: 0.95 }}
                  onClick={(e) => handlePreview(e, voice.id)}
                  className="w-10 h-10 rounded-full bg-white/10 border border-white/20 flex items-center justify-center hover:bg-white/20 transition-colors cursor-pointer shrink-0"
                >
                  {previewingId === voice.id ? (
                    <Loader2 className="w-4 h-4 animate-spin text-[#5a9ab5]" />
                  ) : playingId === voice.id ? (
                    <Pause className="w-4 h-4 text-[#5a9ab5]" />
                  ) : (
                    <Play className="w-4 h-4 text-white/60 ml-0.5" />
                  )}
                </motion.div>
              </motion.button>
            ))}
          </div>
        )}
      </div>
    </motion.div>
  );
}
