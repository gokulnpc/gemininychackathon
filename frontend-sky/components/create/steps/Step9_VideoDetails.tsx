"use client";

import { useWizard } from "@/context/WizardContext";
import { motion } from "framer-motion";
import { cn } from "@/lib/utils";

const DURATION_OPTIONS = [
  { label: "Less than 20 seconds", value: "20" },
  { label: "30 to 60 seconds", value: "60" },
  { label: "60 to 90 seconds", value: "90" },
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
          {DURATION_OPTIONS.map((option, index) => {
            const isSelected = state.videoDuration === option.value;
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
                  "w-full flex items-center gap-4 p-4 rounded-xl border transition-all duration-200 text-left",
                  isSelected
                    ? "border-[#5a9ab5] bg-[#5a9ab5]/20"
                    : "border-white/20 bg-white/10 hover:border-[#5a9ab5]/40 hover:bg-white/15"
                )}
              >
                <div
                  className={cn(
                    "w-5 h-5 rounded-full border-2 flex items-center justify-center shrink-0 transition-colors",
                    isSelected ? "border-[#5a9ab5] bg-[#5a9ab5]" : "border-white/30"
                  )}
                >
                  {isSelected && <div className="w-1.5 h-1.5 rounded-full bg-white" />}
                </div>
                <span className="text-sm font-medium text-white">{option.label}</span>
              </motion.button>
            );
          })}
        </div>
      </div>

    </motion.div>
  );
}
