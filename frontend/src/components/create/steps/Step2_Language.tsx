"use client";

import { Play, Pause, ChevronRight, Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";
import { useWizard } from "@/context/WizardContext";
import { motion } from "framer-motion";
import { useState, useEffect, useRef } from "react";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

const voiceAvatarMap: Record<string, string> = {
  rachel: "/Avatar.png",
  adam: "/Voice_Adam.png",
  josh: "/Voice_John.png",
  bella: "/Voice_Emma.png",
  arnold: "/Voice_Sarah.png",
};

interface VoiceOption {
  id: string;
  name: string;
  gender: string;
  description: string;
}

const YOUR_OWN_VOICE: VoiceOption = {
  id: "your-own",
  name: "Your Own",
  gender: "Coming soon",
  description: "Clone your own voice",
};

export function Step2_Language() {
  const { state, dispatch } = useWizard();
  const [voices, setVoices] = useState<VoiceOption[]>([]);
  const [loadingVoices, setLoadingVoices] = useState(true);
  const [previewingId, setPreviewingId] = useState<string | null>(null);
  const [playingId, setPlayingId] = useState<string | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);

  useEffect(() => {
    fetch(`${API}/api/v1/voices`)
      .then((r) => r.json())
      .then((data: VoiceOption[]) => setVoices(data))
      .catch(() => setVoices([]))
      .finally(() => setLoadingVoices(false));
  }, []);

  const handleVoiceSelect = (voiceId: string) => {
    dispatch({ type: "SET_SELECTED_VOICE", payload: voiceId });
  };

  const handlePreview = async (e: React.MouseEvent, voiceId: string) => {
    e.stopPropagation();

    // If already playing this voice, pause it
    if (playingId === voiceId) {
      audioRef.current?.pause();
      setPlayingId(null);
      return;
    }

    // Stop any currently playing audio
    if (audioRef.current) {
      audioRef.current.pause();
      audioRef.current = null;
    }

    setPreviewingId(voiceId);
    try {
      const res = await fetch(`${API}/api/v1/voices/${voiceId}/preview`);
      if (!res.ok) throw new Error("Preview failed");
      const data = await res.json();
      const audio = new Audio(`data:audio/mp3;base64,${data.audio_base64}`);
      audioRef.current = audio;
      audio.play();
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

  const allVoices = [...voices, YOUR_OWN_VOICE];

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
        <h3 className="text-base font-semibold text-[#1A1A1A] mb-3">
          Language
        </h3>
        <button className="w-full flex items-center justify-between p-4 rounded-2xl border border-[#E8E0DC] bg-white hover:border-[#B08D9F]/30 transition-all duration-200">
          <div className="flex items-center gap-3">
            <span className="text-2xl">🇺🇸</span>
            <span className="text-sm font-medium text-[#1A1A1A]">English</span>
          </div>
          <ChevronRight className="w-5 h-5 text-[#9B9B9B]" />
        </button>
      </div>

      {/* Voice Style Section */}
      <div>
        <h3 className="text-base font-semibold text-[#1A1A1A] mb-3">
          Voice Style
        </h3>
        {loadingVoices ? (
          <div className="flex items-center justify-center py-12">
            <Loader2 className="w-6 h-6 animate-spin text-[#B08D9F]" />
          </div>
        ) : (
          <div className="space-y-3">
            {allVoices.map((voice, index) => (
              <motion.button
                key={voice.id}
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: index * 0.05 }}
                onClick={() => handleVoiceSelect(voice.id)}
                className={cn(
                  "w-full flex items-center justify-between p-4 rounded-2xl border transition-all duration-200",
                  state.selectedVoice === voice.id
                    ? "border-[#B08D9F] bg-[#B08D9F]/5"
                    : "border-[#E8E0DC] bg-white hover:border-[#B08D9F]/30",
                )}
              >
                <div className="flex items-center gap-4">
                  <img
                    src={
                      voiceAvatarMap[voice.name.toLowerCase()] ?? "/Avatar.png"
                    }
                    alt={voice.name}
                    className="w-10 h-10 rounded-full shrink-0 object-cover"
                  />
                  <div className="text-left">
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-medium text-[#1A1A1A]">
                        {voice.name}
                      </span>
                      <span
                        className={cn(
                          "text-xs px-2 py-0.5 rounded-full",
                          voice.gender === "Me"
                            ? "bg-[#B08D9F]/20 text-[#B08D9F]"
                            : voice.gender === "Male"
                              ? "bg-blue-100 text-blue-600"
                              : "bg-pink-100 text-pink-600",
                        )}
                      >
                        {voice.gender}
                      </span>
                    </div>
                    <p className="text-sm text-[#6B6B6B] mt-0.5">
                      {voice.description}
                    </p>
                  </div>
                </div>
                {voice.id !== "your-own" && (
                  <motion.div
                    whileHover={{ scale: 1.1 }}
                    whileTap={{ scale: 0.95 }}
                    onClick={(e) => handlePreview(e, voice.id)}
                    className="w-10 h-10 rounded-full bg-white border border-[#E8E0DC] flex items-center justify-center hover:bg-gray-50 transition-colors cursor-pointer flex-shrink-0"
                  >
                    {previewingId === voice.id ? (
                      <Loader2 className="w-4 h-4 animate-spin text-[#B08D9F]" />
                    ) : playingId === voice.id ? (
                      <Pause className="w-4 h-4 text-[#B08D9F]" />
                    ) : (
                      <Play className="w-4 h-4 text-[#6B6B6B] ml-0.5" />
                    )}
                  </motion.div>
                )}
              </motion.button>
            ))}
          </div>
        )}
      </div>
    </motion.div>
  );
}
