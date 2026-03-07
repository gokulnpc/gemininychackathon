"use client";

import { Button } from "@/components/ui/button";
import { ArrowLeft, ArrowRight, Loader2, Rocket } from "lucide-react";
import { useWizard } from "@/context/WizardContext";
import { motion } from "framer-motion";
import { useState, useRef, useEffect } from "react";
import { useRouter } from "next/navigation";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export function FooterNav() {
  const { state, dispatch } = useWizard();
  const router = useRouter();
  const [loading, setLoading] = useState(false);
  const [launchError, setLaunchError] = useState<string | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => () => { if (pollRef.current) clearInterval(pollRef.current); }, []);

  const isFirstStep = state.currentStep === 1;
  const isLastStep  = state.currentStep === 10;

  const handleBack = () => {
    dispatch({ type: "PREV_STEP" });
  };

  // Step 10 (Launch): queue async script generation and redirect to Projects tab
  const handleLaunch = async () => {
    setLaunchError(null);
    setLoading(true);

    const projectId = crypto.randomUUID();

    // Determine source
    let source = "text";
    if (state.messageTab === "speech") source = "voice";
    else if (state.messageTab === "preset") source = "preset";

    const body: Record<string, unknown> = {
      source,
      target_platforms: ["instagram_reels"],
      caption_style: state.selectedCaption?.replace(/-/g, "_") ?? "bold_stroke",
      video_duration: parseInt(state.videoDuration) || 30,
    };

    if (source === "voice" && state.audioBase64) {
      body.audio_base64 = state.audioBase64;
      body.audio_format = state.audioFormat ?? "webm";
    } else if (source === "text" && state.messageText) {
      body.transcript = state.messageText;
    } else if (source === "preset" && state.selectedPreset) {
      body.preset = state.selectedPreset.replace(/-/g, "_");
    }

    if (state.selectedPlotOption) {
      body.plot_summary = state.selectedPlotOption.summary;
    }
    if (state.uploadedPicture) {
      const raw = state.uploadedPicture.includes(",")
        ? state.uploadedPicture.split(",")[1]
        : state.uploadedPicture;
      body.user_reference_image_b64 = raw;
      body.user_character_role = state.pictureRole ?? "main_character";
    }
    if (state.selectedVoice) body.voice_id = state.selectedVoice;
    if (state.selectedArtStyle) body.art_style_override = state.selectedArtStyle.replace(/-/g, "_");
    if (state.selectedMusic && state.selectedMusic !== "none") {
      body.music_preset_override = state.selectedMusic.replace(/-/g, "_");
    }

    try {
      const res = await fetch(`${API}/api/v1/projects/${projectId}/queue-script`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (res.status === 202) {
        router.push(`/projects?new=${projectId}`);
      } else {
        const detail = await res.json().catch(() => ({}));
        const errDetail = detail.detail;
        const errMessage =
          typeof errDetail === "string"
            ? errDetail
            : Array.isArray(errDetail)
            ? errDetail.map((e: { msg?: string }) => e.msg ?? JSON.stringify(e)).join("; ")
            : `Launch failed (HTTP ${res.status})`;
        setLaunchError(errMessage);
      }
    } catch (err) {
      setLaunchError(err instanceof Error ? err.message : "Launch failed");
    } finally {
      setLoading(false);
    }
  };

  const handleContinue = () => {
    if (isLastStep) {
      handleLaunch();
      return;
    }
    dispatch({ type: "NEXT_STEP" });
  };

  // Hide footer on Review & Publish step (step 11)
  if (state.currentStep === 11) return null;

  let buttonText = "Continue";
  if (isLastStep) {
    buttonText = "Launch";
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
    loading ||
    (state.currentStep === 2 && !state.selectedPlotOption);

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, delay: 0.3 }}
      className="flex flex-col gap-3 mt-12"
    >
      {launchError && (
        <p className="text-sm text-red-400 text-center">{launchError}</p>
      )}
      <div className="flex items-center justify-between">
        <Button
          variant="outline"
          onClick={handleBack}
          disabled={isFirstStep || loading}
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
              {"Launching…"}
            </>
          ) : isLastStep ? (
            <>
              <Rocket className="w-4 h-4 mr-2" />
              {buttonText}
            </>
          ) : (
            <>
              {buttonText}
              <ArrowRight className="w-4 h-4 ml-2" />
            </>
          )}
        </Button>
      </div>
    </motion.div>
  );
}
