"use client";

import { Button } from "@/components/ui/button";
import { ArrowLeft, ArrowRight, Loader2 } from "lucide-react";
import { useWizard } from "@/context/WizardContext";
import { motion } from "framer-motion";
import { useState, useRef, useEffect } from "react";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export function FooterNav() {
  const { state, dispatch } = useWizard();
  const [loading, setLoading] = useState(false);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => () => { if (pollRef.current) clearInterval(pollRef.current); }, []);

  const isFirstStep = state.currentStep === 1;
  const isLastStep  = state.currentStep === 9;

  const startPolling = (pid: string) => {
    if (pollRef.current) clearInterval(pollRef.current);
    pollRef.current = setInterval(async () => {
      try {
        const res = await fetch(`${API}/api/v1/projects/${pid}/status`);
        const s = await res.json();
        if (s.status === "completed") {
          clearInterval(pollRef.current!);
          dispatch({
            type: "SET_PIPELINE_RESULT",
            payload: { projectId: s.project_id ?? pid, videoUrls: s.video_urls ?? {} },
          });
        } else if (s.status === "failed") {
          clearInterval(pollRef.current!);
          dispatch({ type: "SET_PIPELINE_RESULT", payload: { projectId: pid, videoUrls: {} } });
        }
      } catch { /* ignore transient poll errors */ }
    }, 5000);
  };

  const handleBack = () => {
    dispatch({ type: "PREV_STEP" });
  };

  // Step 9 (Video Config): generate video using the script already generated at Step 2
  const handleGenerateVideo = () => {
    const projectId = state.scriptProjectId;
    const script = state.generatedScript;
    if (!projectId || !script) return;

    dispatch({ type: "SET_PROCESSING", payload: true });
    setLoading(true);

    const body: Record<string, unknown> = {
      script,
      target_platforms: ["instagram_reels"],
      caption_style: state.selectedCaption?.replace(/-/g, "_") ?? "bold_stroke",
      video_duration: 30,
    };
    if (state.selectedArtStyle) {
      body.art_style_override = state.selectedArtStyle.replace(/-/g, "_");
    }
    if (state.selectedMusic && state.selectedMusic !== "none") {
      body.music_preset_override = state.selectedMusic.replace(/-/g, "_");
    }
    if (state.uploadedPicture) {
      const raw = state.uploadedPicture.includes(",")
        ? state.uploadedPicture.split(",")[1]
        : state.uploadedPicture;
      body.user_reference_image_b64 = raw;
      body.user_character_role = state.pictureRole ?? "main_character";
    }

    fetch(`${API}/api/v1/projects/${projectId}/generate-video`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    })
      .then(async (r) => {
        const result = await r.json();
        if (r.status === 202) {
          // Async / Cloud Run — poll status until pipeline completes
          startPolling(result.project_id ?? projectId);
        } else {
          dispatch({
            type: "SET_PIPELINE_RESULT",
            payload: {
              projectId: result.project_id ?? projectId,
              videoUrls: result.video_urls ?? {},
            },
          });
        }
      })
      .catch((err) => {
        console.error("Generate video failed:", err);
        dispatch({
          type: "SET_PIPELINE_RESULT",
          payload: { projectId: projectId, videoUrls: {} },
        });
      })
      .finally(() => setLoading(false));
  };

  const handleContinue = () => {
    if (isLastStep) {
      handleGenerateVideo();
      return;
    }
    dispatch({ type: "NEXT_STEP" });
  };

  // Hide footer on Review & Publish step (step 10)
  if (state.currentStep === 10) return null;

  let buttonText = "Continue";
  if (isLastStep) {
    buttonText = "Generate Video";
  } else if (state.currentStep === 3 && !state.uploadedPicture) {
    buttonText = "Skip";
  } else if (state.currentStep === 4 && !state.selectedVoice) {
    buttonText = "Skip";
  } else if (state.currentStep === 5 && !state.selectedMusic) {
    buttonText = "Skip";
  } else if (state.currentStep === 7 && !state.selectedCaption) {
    buttonText = "Skip";
  } else if (state.currentStep === 8) {
    if (!Object.values(state.effects).some(Boolean)) buttonText = "Skip";
  }

  const cannotProceed =
    state.isProcessing ||
    loading ||
    (state.currentStep === 2 && !state.generatedScript) ||
    (isLastStep && !state.generatedScript);

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
        className="rounded-full px-6 py-5 text-sm font-medium bg-[#5a9ab5] hover:bg-[#7ab0c8] text-white transition-all duration-200 hover:shadow-lg hover:scale-[1.02]"
      >
        {loading ? (
          <>
            <Loader2 className="w-4 h-4 mr-2 animate-spin" />
            {"Generating Video…"}
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
