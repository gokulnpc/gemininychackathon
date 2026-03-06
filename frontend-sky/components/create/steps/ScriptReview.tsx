"use client";

import { useState } from "react";
import { motion } from "framer-motion";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { RefreshCw, Play, Loader2, ChevronDown, ChevronUp } from "lucide-react";
import { cn } from "@/lib/utils";
import { useWizard } from "@/context/WizardContext";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export function ScriptReview() {
  const { state, dispatch } = useWizard();
  const script = state.generatedScript;
  const [regenerating, setRegenerating] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [expandedScenes, setExpandedScenes] = useState<number[]>([]);

  if (!script) return null;

  const isSpeechMode = state.messageTab === "speech";
  const isPresetMode = state.messageTab === "preset";
  const isTextMode = state.messageTab === "text";

  const toggleScene = (id: number) =>
    setExpandedScenes((prev) =>
      prev.includes(id) ? prev.filter((s) => s !== id) : [...prev, id]
    );

  // ── Regenerate: re-run configure (preset/text) or generate-script (speech) ──
  const handleRegenerate = async () => {
    const projectId = crypto.randomUUID();
    setRegenerating(true);
    try {
      let transcript: string | undefined;

      // Preset mode: re-run Reddit + Databricks + Nemotron for the preset
      if (isPresetMode && state.selectedPreset) {
        const presetKey = state.selectedPreset.replace(/-/g, "_");
        const configRes = await fetch(`${API}/api/v1/presets/${presetKey}/configure`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ preset: presetKey, target_platforms: ["instagram_reels"] }),
        });
        if (!configRes.ok) throw new Error("Configure failed");
        const config = await configRes.json();
        dispatch({ type: "SET_PRESET_CONFIG", payload: config });
        transcript = config.transcript as string;
      }

      // Text mode: re-run Reddit + Databricks + Nemotron on user's typed idea
      if (isTextMode && state.messageText.trim()) {
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
        transcript = config.transcript as string;
      }

      const body: Record<string, unknown> = {
        target_platforms: ["instagram_reels"],
        style: "modern_energetic",
        video_duration: 30,
      };
      if (isPresetMode && transcript) {
        body.source = "preset";
        body.preset = state.selectedPreset?.replace(/-/g, "_");
        body.transcript = transcript;
      } else if (isSpeechMode) {
        body.source = "voice";
        body.audio_base64 = state.audioBase64;
        body.audio_format = state.audioFormat || "webm";
      } else {
        body.source = "text";
        body.transcript = transcript ?? state.messageText;
      }

      const res = await fetch(
        `${API}/api/v1/projects/${projectId}/generate-script`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        }
      );
      if (!res.ok) throw new Error("Regeneration failed");
      const newScript = await res.json();

      dispatch({ type: "SET_SCRIPT_PROJECT_ID", payload: projectId });
      dispatch({ type: "SET_GENERATED_SCRIPT", payload: newScript });
    } catch (e) {
      console.error("Regenerate script failed:", e);
    } finally {
      setRegenerating(false);
    }
  };

  // ── Generate Video: call /generate-video in background, show Processing ─────
  const handleGenerateVideo = () => {
    const projectId = state.scriptProjectId;
    if (!projectId || !script) return;

    // Show Processing screen immediately
    dispatch({ type: "SET_SHOW_SCRIPT_REVIEW", payload: false });
    dispatch({ type: "SET_PROCESSING", payload: true });

    setGenerating(true);

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
      .then((r) => r.json())
      .then((result) => {
        dispatch({
          type: "SET_PIPELINE_RESULT",
          payload: {
            projectId: result.project_id ?? projectId,
            videoUrls: result.video_urls ?? {},
          },
        });
      })
      .catch((err) => {
        console.error("Generate video failed:", err);
        dispatch({
          type: "SET_PIPELINE_RESULT",
          payload: { projectId: projectId, videoUrls: {} },
        });
      })
      .finally(() => setGenerating(false));
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -20 }}
      transition={{ duration: 0.3 }}
    >
      {/* Header */}
      <div className="flex items-start justify-between mb-8">
        <div>
          <Badge
            variant="secondary"
            className="bg-blue-100 text-blue-600 hover:bg-blue-100 px-3 py-1 mb-3"
          >
            <span className="w-2 h-2 rounded-full bg-blue-500 mr-2 inline-block" />
            Script Ready
          </Badge>
          <h1 className="text-4xl font-medium text-[#1A1A1A]">
            Review Your Script
          </h1>
          <p className="text-sm text-[#6B6B6B] mt-2">
            Review the generated script below. If you're not happy, regenerate it.
            When ready, click <span className="font-medium text-[#1A1A1A]">Generate Video</span>.
          </p>
        </div>

        <div className="flex gap-3 flex-shrink-0 ml-6">
          <Button
            variant="outline"
            onClick={handleRegenerate}
            disabled={regenerating || generating}
            className="rounded-full px-5 py-2 h-10 border-[#E8E0DC] hover:bg-[#FAF8F5]"
          >
            {regenerating ? (
              <Loader2 className="w-4 h-4 mr-2 animate-spin" />
            ) : (
              <RefreshCw className="w-4 h-4 mr-2" />
            )}
            {regenerating ? "Regenerating…" : "Regenerate"}
          </Button>
          <Button
            onClick={handleGenerateVideo}
            disabled={regenerating || generating}
            className="rounded-full px-5 py-2 h-10 bg-[#5a9ab5] hover:bg-[#7ab0c8] text-white"
          >
            {generating ? (
              <Loader2 className="w-4 h-4 mr-2 animate-spin" />
            ) : (
              <Play className="w-4 h-4 mr-2" />
            )}
            Generate Video
          </Button>
        </div>
      </div>

      <div className="space-y-4">
        {/* Hook */}
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.1 }}
          className="bg-white rounded-2xl border border-[#5a9ab5]/40 p-5"
        >
          <div className="flex items-center gap-2 mb-2">
            <span className="text-xs font-semibold uppercase tracking-wide text-[#5a9ab5]">
              Hook · {script.hook.duration}s
            </span>
          </div>
          <p className="text-lg font-medium text-[#1A1A1A] leading-relaxed">
            "{script.hook.text}"
          </p>
        </motion.div>

        {/* Scenes */}
        <div className="space-y-3">
          {script.scenes.map((scene, index) => {
            const isExpanded = expandedScenes.includes(scene.scene_id);
            return (
              <motion.div
                key={scene.scene_id}
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.15 + index * 0.06 }}
                className="bg-white rounded-2xl border border-[#E8E0DC] overflow-hidden"
              >
                <button
                  onClick={() => toggleScene(scene.scene_id)}
                  className="w-full flex items-center justify-between p-5 text-left hover:bg-[#FAF8F5] transition-colors"
                >
                  <div className="flex items-center gap-3">
                    <div className="w-7 h-7 rounded-full bg-[#1A1A1A] text-white flex items-center justify-center text-xs font-semibold flex-shrink-0">
                      {scene.scene_id}
                    </div>
                    <div>
                      <p
                        className={cn(
                          "text-sm text-[#1A1A1A] leading-snug",
                          !isExpanded && "line-clamp-1"
                        )}
                      >
                        {scene.voiceover_text}
                      </p>
                      {!isExpanded && (
                        <p className="text-xs text-[#9B9B9B] mt-0.5">
                          {scene.duration_seconds}s · {scene.emotion}
                        </p>
                      )}
                    </div>
                  </div>
                  {isExpanded ? (
                    <ChevronUp className="w-4 h-4 text-[#9B9B9B] flex-shrink-0 ml-3" />
                  ) : (
                    <ChevronDown className="w-4 h-4 text-[#9B9B9B] flex-shrink-0 ml-3" />
                  )}
                </button>

                {isExpanded && (
                  <motion.div
                    initial={{ opacity: 0, height: 0 }}
                    animate={{ opacity: 1, height: "auto" }}
                    exit={{ opacity: 0, height: 0 }}
                    className="px-5 pb-5 pt-0 border-t border-[#E8E0DC] space-y-3"
                  >
                    <div className="grid grid-cols-3 gap-3 mt-3">
                      <div className="bg-[#FAF8F5] rounded-xl p-3">
                        <p className="text-xs text-[#9B9B9B] mb-1">Duration</p>
                        <p className="text-sm font-medium text-[#1A1A1A]">{scene.duration_seconds}s</p>
                      </div>
                      <div className="bg-[#FAF8F5] rounded-xl p-3">
                        <p className="text-xs text-[#9B9B9B] mb-1">Emotion</p>
                        <p className="text-sm font-medium text-[#1A1A1A] capitalize">{scene.emotion}</p>
                      </div>
                      {scene.transition_to_next && (
                        <div className="bg-[#FAF8F5] rounded-xl p-3">
                          <p className="text-xs text-[#9B9B9B] mb-1">Transition</p>
                          <p className="text-sm font-medium text-[#1A1A1A] capitalize">
                            {scene.transition_to_next.replace(/_/g, " ")}
                          </p>
                        </div>
                      )}
                    </div>
                    {scene.visual_prompt && (
                      <div>
                        <p className="text-xs text-[#9B9B9B] mb-1">Visual prompt</p>
                        <p className="text-sm text-[#6B6B6B] italic">{scene.visual_prompt}</p>
                      </div>
                    )}
                  </motion.div>
                )}
              </motion.div>
            );
          })}
        </div>

        {/* CTA */}
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.3 }}
          className="bg-white rounded-2xl border border-[#E8E0DC] p-5"
        >
          <p className="text-xs font-semibold uppercase tracking-wide text-[#9B9B9B] mb-2">
            Call to Action
          </p>
          <p className="text-sm font-medium text-[#1A1A1A]">{script.cta.text}</p>
        </motion.div>

        {/* Full Voiceover Script (collapsed by default) */}
        <motion.details
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 0.35 }}
          className="bg-white rounded-2xl border border-[#E8E0DC] overflow-hidden"
        >
          <summary className="p-5 cursor-pointer text-sm font-medium text-[#6B6B6B] hover:text-[#1A1A1A] hover:bg-[#FAF8F5] transition-colors select-none">
            Full voiceover script
          </summary>
          <div className="px-5 pb-5 pt-2 border-t border-[#E8E0DC]">
            <p className="text-sm text-[#1A1A1A] leading-relaxed whitespace-pre-wrap">
              {script.voiceover_full_script}
            </p>
          </div>
        </motion.details>
      </div>

      {/* Bottom action bar */}
      <div className="flex items-center justify-between mt-10 pt-6 border-t border-[#E8E0DC]">
        <Button
          variant="outline"
          onClick={handleRegenerate}
          disabled={regenerating || generating}
          className="rounded-full px-6 py-5 text-sm font-medium border-[#E8E0DC] bg-white hover:bg-[#FDF6F3]"
        >
          {regenerating ? (
            <Loader2 className="w-4 h-4 mr-2 animate-spin" />
          ) : (
            <RefreshCw className="w-4 h-4 mr-2" />
          )}
          {regenerating ? "Regenerating…" : "Regenerate Script"}
        </Button>

        <Button
          onClick={handleGenerateVideo}
          disabled={regenerating || generating}
          className="rounded-full px-6 py-5 text-sm font-medium bg-[#1A1A1A] hover:bg-[#1A1A1A]/90 text-white"
        >
          {generating ? (
            <Loader2 className="w-4 h-4 mr-2 animate-spin" />
          ) : (
            <Play className="w-4 h-4 mr-2" />
          )}
          Generate Video
        </Button>
      </div>
    </motion.div>
  );
}
