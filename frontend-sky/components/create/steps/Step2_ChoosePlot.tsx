"use client";

import { useState, useEffect, useRef } from "react";
import { motion } from "framer-motion";
import { Button } from "@/components/ui/button";
import { RefreshCw, Loader2, AlertCircle } from "lucide-react";
import { cn } from "@/lib/utils";
import { useWizard } from "@/context/WizardContext";
import type { PlotOption } from "@/types";
import apiClient from "@/lib/apiClient";

export function Step2_ChoosePlot() {
  const { state, dispatch } = useWizard();
  const [options, setOptions] = useState<PlotOption[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const autoFetchTriggered = useRef(false);

  const isSpeechMode = state.messageTab === "speech";
  const isPresetMode = state.messageTab === "preset";

  const fetchOptions = async (previousOptions: string[] = []) => {
    if (isSpeechMode && !state.audioBase64) {
      setError("No audio recorded. Go back and record your voice memo.");
      return;
    }
    if (isPresetMode && !state.selectedPreset) {
      setError("No preset selected. Go back and choose a preset.");
      return;
    }

    const projectId = crypto.randomUUID();
    setLoading(true);
    setError(null);
    dispatch({ type: "SET_SELECTED_PLOT_OPTION", payload: null });

    try {
      const body: Record<string, unknown> = {};

      if (isPresetMode && state.selectedPreset) {
        body.source = "preset";
        body.preset = state.selectedPreset.replace(/-/g, "_");
      } else if (isSpeechMode) {
        body.source = "voice";
        body.audio_base64 = state.audioBase64;
        body.audio_format = state.audioFormat || "webm";
      } else {
        body.source = "text";
        body.transcript = state.messageText;
      }

      if (previousOptions.length > 0) {
        body.previous_options = previousOptions;
      }

      if (state.uploadedPicture) {
        const b64 = state.uploadedPicture.includes(",")
          ? state.uploadedPicture.split(",")[1]
          : state.uploadedPicture;
        body.user_reference_image_b64 = b64;
      }

      const data = await apiClient.post(`/api/v1/projects/${projectId}/generate-plot-options`, body).then(r => r.data);
      setOptions(data.options ?? []);
    } catch (e) {
      console.error("Plot options fetch failed:", e);
      setError(e instanceof Error ? e.message : "Failed to generate options");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (!autoFetchTriggered.current) {
      autoFetchTriggered.current = true;
      fetchOptions();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleSelect = (option: PlotOption) => {
    dispatch({ type: "SET_SELECTED_PLOT_OPTION", payload: option });
  };

  if (error && options.length === 0) {
    return (
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        className="flex flex-col items-center justify-center py-16 gap-4"
      >
        <AlertCircle className="w-8 h-8 text-red-400" />
        <p className="text-red-400 text-sm text-center max-w-sm">{error}</p>
        <Button
          variant="outline"
          onClick={() => fetchOptions()}
          className="rounded-full px-5 py-2 h-10 border-white/20 bg-white/10 hover:bg-white/20 text-white"
        >
          <RefreshCw className="w-4 h-4 mr-2" />
          Retry
        </Button>
      </motion.div>
    );
  }

  if (loading) {
    return (
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        className="flex flex-col items-center justify-center py-16 gap-3"
      >
        <Loader2 className="w-8 h-8 animate-spin text-[#5a9ab5]" />
        <p className="text-white/60 text-sm">Generating story directions…</p>
      </motion.div>
    );
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -20 }}
      transition={{ duration: 0.3 }}
      className="space-y-4"
    >
      <div className="flex items-center justify-between mb-2">
        <p className="text-sm text-white/60">
          Pick the story direction that resonates most.
        </p>
        <Button
          variant="outline"
          onClick={() => fetchOptions(options.map(o => `${o.title}: ${o.summary}`))}
          disabled={loading}
          className="rounded-full px-4 py-2 h-9 border-white/20 bg-white/10 hover:bg-white/20 text-white text-xs"
        >
          <RefreshCw className="w-3.5 h-3.5 mr-1.5" />
          Regenerate
        </Button>
      </div>

      <div className="space-y-3">
        {options.map((option, index) => {
          const isSelected = state.selectedPlotOption?.id === option.id;
          return (
            <motion.button
              key={option.id}
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: index * 0.08 }}
              onClick={() => handleSelect(option)}
              className={cn(
                "w-full text-left p-5 rounded-2xl border transition-all duration-200",
                isSelected
                  ? "border-[#5a9ab5] bg-[#5a9ab5]/20"
                  : "border-white/20 bg-white/10 hover:border-[#5a9ab5]/40 hover:bg-white/15"
              )}
            >
              <div className="flex items-start gap-3">
                <div
                  className={cn(
                    "w-6 h-6 rounded-full border-2 flex items-center justify-center shrink-0 mt-0.5 transition-colors",
                    isSelected
                      ? "border-[#5a9ab5] bg-[#5a9ab5]"
                      : "border-white/30"
                  )}
                >
                  {isSelected && (
                    <div className="w-2 h-2 rounded-full bg-white" />
                  )}
                </div>
                <div>
                  <p className="text-sm font-semibold text-white mb-1">
                    {option.title}
                  </p>
                  <p className="text-sm text-white/60 leading-relaxed">
                    {option.summary}
                  </p>
                </div>
              </div>
            </motion.button>
          );
        })}
      </div>
    </motion.div>
  );
}
