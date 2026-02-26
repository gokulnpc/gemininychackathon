"use client";

import { Button } from "@/components/ui/button";
import { ArrowLeft, ArrowRight, Loader2 } from "lucide-react";
import { useWizard } from "@/context/WizardContext";
import { motion } from "framer-motion";
import { useState } from "react";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export function FooterNav() {
  const { state, dispatch } = useWizard();
  const [loading, setLoading] = useState(false);

  const isPresetMode = state.messageTab === "preset";
  const isSpeechMode = state.messageTab === "speech";
  const isTextMode = state.messageTab === "text";

  const handleBack = () => {
    dispatch({ type: "PREV_STEP" });
  };

  // Preset step 7: configure (Reddit + Databricks + Nemotron) → generate script → show review
  const handlePresetGenerateScript = async () => {
    if (!state.selectedPreset) return;
    setLoading(true);
    const projectId = crypto.randomUUID();
    try {
      // Phase 1: Nemotron auto-configure (runs Reddit research + Databricks + Nemotron)
      const presetKey = state.selectedPreset.replace(/-/g, "_");
      const configRes = await fetch(`${API}/api/v1/presets/${presetKey}/configure`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ preset: presetKey, target_platforms: ["instagram_reels"] }),
      });
      if (!configRes.ok) throw new Error("Configure failed");
      const config = await configRes.json();
      dispatch({ type: "SET_PRESET_CONFIG", payload: config });

      // Phase 2: Generate Claude script using Nemotron's transcript
      const scriptRes = await fetch(`${API}/api/v1/projects/${projectId}/generate-script`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          transcript: config.transcript,
          target_platforms: ["instagram_reels"],
          style: "modern_energetic",
          video_duration: 30,
        }),
      });
      if (!scriptRes.ok) throw new Error("Script generation failed");
      const script = await scriptRes.json();

      dispatch({ type: "SET_SCRIPT_PROJECT_ID", payload: projectId });
      dispatch({ type: "SET_GENERATED_SCRIPT", payload: script });
      dispatch({ type: "SET_SHOW_SCRIPT_REVIEW", payload: true });
    } catch (e) {
      console.error("Preset generate script failed:", e);
    } finally {
      setLoading(false);
    }
  };

  // Speech step 7: generate script from audio → show review
  const handleSpeechGenerateScript = async () => {
    if (!state.audioBase64) return;
    const projectId = crypto.randomUUID();
    setLoading(true);
    try {
      const res = await fetch(`${API}/api/v1/projects/${projectId}/generate-script`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          audio_base64: state.audioBase64,
          audio_format: state.audioFormat || "webm",
          target_platforms: ["instagram_reels"],
          style: "modern_energetic",
          video_duration: 30,
        }),
      });
      if (!res.ok) throw new Error("Script generation failed");
      const script = await res.json();
      dispatch({ type: "SET_SCRIPT_PROJECT_ID", payload: projectId });
      dispatch({ type: "SET_GENERATED_SCRIPT", payload: script });
      dispatch({ type: "SET_SHOW_SCRIPT_REVIEW", payload: true });
    } catch (e) {
      console.error("Speech generate script failed:", e);
    } finally {
      setLoading(false);
    }
  };

  // Text step 7: Reddit + Databricks + Nemotron configure → generate script → show review
  const handleTextGenerateScript = async () => {
    if (!state.messageText.trim()) return;
    const projectId = crypto.randomUUID();
    setLoading(true);
    try {
      // Phase 1: Reddit + Databricks + Nemotron on user's typed idea
      const configRes = await fetch(`${API}/api/v1/text/configure`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          transcript: state.messageText,
          target_platforms: ["instagram_reels"],
        }),
      });
      if (!configRes.ok) throw new Error("Configure failed");
      const config = await configRes.json();
      dispatch({ type: "SET_PRESET_CONFIG", payload: config });

      // Phase 2: Claude script generation using Nemotron-enriched transcript
      const scriptRes = await fetch(`${API}/api/v1/projects/${projectId}/generate-script`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          transcript: config.transcript,
          target_platforms: ["instagram_reels"],
          style: "modern_energetic",
          video_duration: 30,
        }),
      });
      if (!scriptRes.ok) throw new Error("Script generation failed");
      const script = await scriptRes.json();

      dispatch({ type: "SET_SCRIPT_PROJECT_ID", payload: projectId });
      dispatch({ type: "SET_GENERATED_SCRIPT", payload: script });
      dispatch({ type: "SET_SHOW_SCRIPT_REVIEW", payload: true });
    } catch (e) {
      console.error("Text generate script failed:", e);
    } finally {
      setLoading(false);
    }
  };

  const handleContinue = () => {
    if (isPresetMode && state.currentStep === 7) { handlePresetGenerateScript(); return; }
    if (isSpeechMode && state.currentStep === 7)  { handleSpeechGenerateScript(); return; }
    if (isTextMode && state.currentStep === 7)    { handleTextGenerateScript();   return; }
    if (state.currentStep === 7) {
      dispatch({ type: "SET_PROCESSING", payload: true });
    } else {
      dispatch({ type: "NEXT_STEP" });
    }
  };

  const isFirstStep = state.currentStep === 1;
  const isLastStep  = state.currentStep === 7;

  if (state.currentStep === 8) return null;

  let buttonText = "Continue";
  if (isLastStep) {
    buttonText = "Generate Script";
  } else if (state.currentStep === 3 && !state.selectedMusic) {
    buttonText = "Skip";
  } else if (state.currentStep === 6) {
    if (!Object.values(state.effects).some(Boolean)) buttonText = "Skip";
  }

  const cannotProceed =
    state.isProcessing ||
    loading ||
    (isPresetMode && isFirstStep && !state.selectedPreset) ||
    (isPresetMode && isLastStep && !state.selectedPreset) ||
    (isSpeechMode && isLastStep && !state.audioBase64) ||
    (isTextMode && isLastStep && !state.messageText.trim());

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, delay: 0.3 }}
      className="flex items-center justify-between mt-12"
    >
      <Button
        variant="outline"
        onClick={handleBack}
        disabled={isFirstStep || state.isProcessing || loading}
        className="rounded-full px-6 py-5 text-sm font-medium border-[#E8E0DC] bg-white hover:bg-[#FDF6F3] transition-all duration-200"
      >
        <ArrowLeft className="w-4 h-4 mr-2" />
        Back
      </Button>

      <Button
        onClick={handleContinue}
        disabled={cannotProceed}
        className="rounded-full px-6 py-5 text-sm font-medium bg-[#B08D9F] hover:bg-[#C9A9B8] text-white transition-all duration-200 hover:shadow-lg hover:scale-[1.02]"
      >
        {loading ? (
          <>
            <Loader2 className="w-4 h-4 mr-2 animate-spin" />
            Generating Script…
          </>
        ) : (
          <>
            {buttonText}
            <ArrowRight className="w-4 h-4 ml-2" />
          </>
        )}
      </Button>
    </motion.div>
  );
}
