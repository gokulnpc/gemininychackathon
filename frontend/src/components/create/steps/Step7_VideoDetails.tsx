"use client";

import { Info } from "lucide-react";
import { useWizard } from "@/context/WizardContext";
import { motion } from "framer-motion";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";

export function Step7_VideoDetails() {
  const { state, dispatch } = useWizard();

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -20 }}
      transition={{ duration: 0.3 }}
      className="space-y-6"
    >
      {/* Series Name */}
      <div>
        <label className="block text-sm font-medium text-[#1A1A1A] mb-2">
          Video Name
        </label>
        <input
          type="text"
          value={state.seriesName}
          onChange={(e) =>
            dispatch({ type: "SET_SERIES_NAME", payload: e.target.value })
          }
          placeholder="Enter a name for your series"
          className="w-full p-4 rounded-xl border border-[#E8E0DC] bg-white text-sm text-[#1A1A1A] placeholder:text-[#9B9B9B] focus:outline-none focus:ring-2 focus:ring-[#B08D9F]/20 focus:border-[#B08D9F] transition-all duration-200"
        />
      </div>

      {/* Video Duration */}
      <div>
        <div className="flex items-center gap-2 mb-2">
          <label className="text-sm font-medium text-[#1A1A1A]">
            Video Duration
          </label>
          <TooltipProvider>
            <Tooltip>
              <TooltipTrigger>
                <Info className="w-4 h-4 text-[#9B9B9B]" />
              </TooltipTrigger>
              <TooltipContent>
                <p>Set the target duration for your videos</p>
              </TooltipContent>
            </Tooltip>
          </TooltipProvider>
        </div>
        <input
          type="text"
          value={state.videoDuration}
          onChange={(e) =>
            dispatch({ type: "SET_VIDEO_DURATION", payload: e.target.value })
          }
          className="w-full p-4 rounded-xl border border-[#E8E0DC] bg-white text-sm text-[#1A1A1A] focus:outline-none focus:ring-2 focus:ring-[#B08D9F]/20 focus:border-[#B08D9F] transition-all duration-200"
        />
      </div>

      {/* Schedule */}
      <div>
        <label className="block text-sm font-medium text-[#1A1A1A] mb-2">
          Schedule
        </label>
        <p className="text-sm text-[#6B6B6B] mb-4">
          Set when you want your videos to be published.
        </p>

        <div className="mb-3">
          <label className="block text-xs text-[#9B9B9B] mb-2">
            Publish time:
          </label>
          <div className="flex items-center gap-3">
            <input
              type="time"
              value={state.publishTime}
              onChange={(e) =>
                dispatch({ type: "SET_PUBLISH_TIME", payload: e.target.value })
              }
              className="p-3 rounded-xl border border-[#E8E0DC] bg-white text-sm text-[#1A1A1A] focus:outline-none focus:ring-2 focus:ring-[#B08D9F]/20 focus:border-[#B08D9F] transition-all duration-200"
            />
            <span className="text-sm text-[#9B9B9B]">(Your local time)</span>
          </div>
        </div>

        <div className="bg-[#EFF6FF] rounded-xl p-4 border border-[#DBEAFE]">
          <p className="text-sm text-[#6B6B6B]">
            <span className="font-medium text-[#1A1A1A]">Note:</span> Videos
            will be generated 1 hour before the scheduled publish time so you
            have time to review them.
          </p>
        </div>
      </div>
    </motion.div>
  );
}
