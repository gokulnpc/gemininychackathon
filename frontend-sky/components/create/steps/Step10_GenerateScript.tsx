"use client";

import { motion } from "framer-motion";
import {
  BookOpen,
  Clock,
  Mic,
  Music,
  Palette,
  Rocket,
  Type,
  Volume2,
} from "lucide-react";
import { useWizard } from "@/context/WizardContext";
import { cn } from "@/lib/utils";

export function Step10_GenerateScript() {
  const { state } = useWizard();

  const summaryItems = [
    {
      icon: BookOpen,
      label: "Plot Direction",
      value: state.selectedPlotOption
        ? state.selectedPlotOption.title
        : "Not selected",
      sub: state.selectedPlotOption?.summary,
    },
    {
      icon: Volume2,
      label: "Voice",
      value: state.selectedVoice ?? "Aoede (default)",
    },
    {
      icon: Palette,
      label: "Art Style",
      value: state.selectedArtStyle ?? "Not set",
    },
    {
      icon: Clock,
      label: "Duration",
      value: state.videoDuration
        ? state.videoDuration === "20"
          ? "Less than 20 seconds"
          : state.videoDuration === "60"
          ? "30 to 60 seconds"
          : "60 to 90 seconds"
        : "30 seconds (default)",
    },
    {
      icon: Music,
      label: "Background Music",
      value: state.selectedMusic ?? "None",
    },
    {
      icon: Type,
      label: "Caption Style",
      value: state.selectedCaption ?? "Bold Stroke (default)",
    },
    ...(state.messageTab === "speech" || state.messageTab === "preset" || state.messageTab === "text"
      ? [
          {
            icon: Mic,
            label: "Input Mode",
            value:
              state.messageTab === "speech"
                ? "Voice Memo"
                : state.messageTab === "preset"
                ? `Preset: ${state.selectedPreset ?? "—"}`
                : "Text",
          },
        ]
      : []),
  ];

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      className="max-w-2xl mx-auto"
    >
      {/* Heading */}
      <div className="mb-8">
        <div className="flex items-center gap-3 mb-3">
          <div className="w-10 h-10 rounded-xl bg-[#5a9ab5]/20 flex items-center justify-center border border-[#5a9ab5]/30">
            <Rocket className="w-5 h-5 text-[#5a9ab5]" />
          </div>
          <h2 className="text-2xl font-medium text-white">Ready to Launch</h2>
        </div>
        <p className="text-white/50 text-sm leading-relaxed">
          Everything looks good. Review your configuration below, then click{" "}
          <span className="text-white/80 font-medium">Launch</span> to queue
          your script generation. You'll be taken to the Projects tab where you
          can review and approve the script before video generation begins.
        </p>
      </div>

      {/* Config summary */}
      <div className="space-y-3">
        {summaryItems.map((item) => {
          const Icon = item.icon;
          return (
            <motion.div
              key={item.label}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              className="flex items-start gap-4 bg-[#333333] rounded-2xl border border-white/10 px-5 py-4"
            >
              <div className="w-8 h-8 rounded-lg bg-[#2a2a2a] flex items-center justify-center border border-white/5 shrink-0 mt-0.5">
                <Icon className="w-4 h-4 text-white/50" />
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-xs text-white/40 font-medium uppercase tracking-wider mb-0.5">
                  {item.label}
                </p>
                <p
                  className={cn(
                    "text-sm font-medium",
                    item.value === "Not selected" || item.value === "Not set"
                      ? "text-white/30"
                      : "text-white"
                  )}
                >
                  {item.value}
                </p>
                {item.sub && (
                  <p className="text-xs text-white/40 mt-1 leading-relaxed line-clamp-2">
                    {item.sub}
                  </p>
                )}
              </div>
            </motion.div>
          );
        })}
      </div>

      <p className="text-center text-white/30 text-sm mt-8">
        Click <span className="text-white/60 font-medium">Launch</span> in the
        footer to queue your project →
      </p>
    </motion.div>
  );
}
