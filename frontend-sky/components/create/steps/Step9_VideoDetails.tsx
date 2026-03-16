"use client";

import { useWizard } from "@/context/WizardContext";
import { motion } from "framer-motion";
import { cn } from "@/lib/utils";
import { Timer, Clock, Hourglass } from "lucide-react";
import type { LucideIcon } from "lucide-react";

const DURATION_OPTIONS: { label: string; value: string; icon: LucideIcon }[] = [
  { label: "Less than 30 seconds", value: "20", icon: Timer },
  { label: "30 to 60 seconds", value: "60", icon: Clock },
  { label: "60 to 90 seconds", value: "90", icon: Hourglass },
];

export function Step9_VideoDetails() {
  const { state, dispatch } = useWizard();

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -20 }}
      transition={{ duration: 0.3 }}
      className="space-y-6"
    >
      {/* Video Duration */}
      <div>
        <label className="block text-sm font-medium text-white mb-3">
          Video Duration
        </label>
        <div className="space-y-3">
          <div className="grid grid-cols-3 gap-3">
            {DURATION_OPTIONS.map((option, index) => {
              const isSelected = state.videoDuration === option.value;
              const Icon = option.icon;
              return (
                <motion.button
                  key={option.value}
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: index * 0.06 }}
                  onClick={() =>
                    dispatch({ type: "SET_VIDEO_DURATION", payload: option.value })
                  }
                  className={cn(
                    "flex flex-col items-center gap-3 p-5 rounded-2xl border transition-all duration-200 text-center",
                    isSelected
                      ? "border-[#5a9ab5] bg-[#5a9ab5]/20"
                      : "border-white/20 bg-white/10 hover:border-[#5a9ab5]/40 hover:bg-white/15"
                  )}
                >
                  <Icon className={cn(
                    "w-6 h-6 transition-colors",
                    isSelected ? "text-[#5a9ab5]" : "text-white/50"
                  )} />
                  <span className="text-sm font-medium text-white">{option.label}</span>
                </motion.button>
              );
            })}
          </div>
        </div>
      </div>

    </motion.div>
  );
}
