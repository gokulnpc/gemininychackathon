"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import { motion } from "framer-motion";
import { Button } from "@/components/ui/button";
import { RefreshCw, Loader2, ChevronDown, ChevronUp, AlertCircle, Check } from "lucide-react";
import { cn } from "@/lib/utils";
import { useWizard } from "@/context/WizardContext";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export function Step2_ChoosePlot() {
  const { state, dispatch } = useWizard();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [expandedScenes, setExpandedScenes] = useState<number[]>([]);
  const [agentSteps, setAgentSteps] = useState<string[]>([]);
  const [currentStepMsg, setCurrentStepMsg] = useState<string | null>(null);
  const autoGenTriggered = useRef(false);

  const isSpeechMode = state.messageTab === "speech";
  const isPresetMode = state.messageTab === "preset";

  const generateScript = useCallback(async () => {
    // Guard: speech mode needs audio, preset needs a preset selected
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
    setAgentSteps([]);
    setCurrentStepMsg(null);
    try {
      const body: Record<string, unknown> = {
        target_platforms: ["instagram_reels"],
        style: "modern_energetic",
        video_duration: 30,
      };

      if (isPresetMode && state.selectedPreset) {
        const presetKey = state.selectedPreset.replace(/-/g, "_");
        body.source = "preset";
        body.preset = presetKey;
      } else if (isSpeechMode) {
        body.source = "voice";
        body.audio_base64 = state.audioBase64;
        body.audio_format = state.audioFormat || "webm";
      } else {
        body.source = "text";
        body.transcript = state.messageText;
      }

      const res = await fetch(`${API}/api/v1/projects/${projectId}/generate-script-stream`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!res.ok || !res.body) {
        const errBody = await res.json().catch(() => ({}));
        const detail = typeof errBody?.detail === "string"
          ? errBody.detail
          : JSON.stringify(errBody?.detail ?? "Script generation failed");
        throw new Error(detail);
      }

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buf = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buf += decoder.decode(value, { stream: true });
        const chunks = buf.split("\n\n");
        buf = chunks.pop() ?? "";
        for (const chunk of chunks) {
          if (!chunk.startsWith("data: ")) continue;
          const evt = JSON.parse(chunk.slice(6));
          if (evt.type === "agent_step") {
            setAgentSteps(prev => [...prev, evt.message]);
            setCurrentStepMsg(evt.message);
          } else if (evt.type === "complete") {
            const newScript = { ...evt.script, project_id: projectId };
            dispatch({ type: "SET_SCRIPT_PROJECT_ID", payload: projectId });
            dispatch({ type: "SET_GENERATED_SCRIPT", payload: newScript });
            setCurrentStepMsg(null);
          } else if (evt.type === "error") {
            throw new Error(evt.message);
          }
        }
      }
    } catch (e) {
      console.error("Generate script failed:", e);
      setError(e instanceof Error ? e.message : "Script generation failed");
    } finally {
      setLoading(false);
    }
  }, [
    isPresetMode,
    isSpeechMode,
    state.selectedPreset,
    state.audioBase64,
    state.audioFormat,
    state.messageText,
    dispatch,
  ]);

  // Auto-generate on mount if no script yet
  useEffect(() => {
    if (!state.generatedScript && !autoGenTriggered.current) {
      autoGenTriggered.current = true;
      generateScript();
    }
  }, [state.generatedScript, generateScript]);

  const script = state.generatedScript;

  const toggleScene = (id: number) =>
    setExpandedScenes((prev) =>
      prev.includes(id) ? prev.filter((s) => s !== id) : [...prev, id]
    );

  if (error && !script) {
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
          onClick={generateScript}
          className="rounded-full px-5 py-2 h-10 border-white/20 bg-white/10 hover:bg-white/20 text-white"
        >
          <RefreshCw className="w-4 h-4 mr-2" />
          Retry
        </Button>
      </motion.div>
    );
  }

  if (loading && !script) {
    return (
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0, y: -20 }}
        transition={{ duration: 0.3 }}
        className="flex flex-col items-center py-12 gap-2"
      >
        <Loader2 className="w-8 h-8 animate-spin text-[#5a9ab5] mb-2" />
        <p className="text-white/60 text-sm">Scout is crafting your script…</p>
        <div className="w-full max-w-sm space-y-2 mt-6">
          {agentSteps.map((msg, i) => (
            <motion.div
              key={i}
              initial={{ opacity: 0, x: -10 }}
              animate={{ opacity: 1, x: 0 }}
              className="flex items-center gap-3 text-sm text-white/70"
            >
              <Check className="w-4 h-4 text-green-400 shrink-0" />
              <span>{msg}</span>
            </motion.div>
          ))}
          {currentStepMsg && (
            <motion.div
              initial={{ opacity: 0, x: -10 }}
              animate={{ opacity: 1, x: 0 }}
              className="flex items-center gap-3 text-sm text-white"
            >
              <Loader2 className="w-4 h-4 animate-spin text-[#5a9ab5] shrink-0" />
              <span>{currentStepMsg}</span>
            </motion.div>
          )}
        </div>
      </motion.div>
    );
  }

  if (!script) return null;

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -20 }}
      transition={{ duration: 0.3 }}
    >
      {/* Regenerate button */}
      <div className="flex justify-end mb-6">
        <Button
          variant="outline"
          onClick={generateScript}
          disabled={loading}
          className="rounded-full px-5 py-2 h-10 border-white/20 bg-white/10 hover:bg-white/20 text-white"
        >
          {loading ? (
            <Loader2 className="w-4 h-4 mr-2 animate-spin" />
          ) : (
            <RefreshCw className="w-4 h-4 mr-2" />
          )}
          {loading ? "Regenerating…" : "Regenerate"}
        </Button>
      </div>

      <div className="space-y-4">
        {/* Hook */}
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.1 }}
          className="bg-white/10 rounded-2xl border border-[#5a9ab5]/40 p-5"
        >
          <div className="flex items-center gap-2 mb-2">
            <span className="text-xs font-semibold uppercase tracking-wide text-[#5a9ab5]">
              Hook · {script.hook.duration}s
            </span>
          </div>
          <p className="text-lg font-medium text-white leading-relaxed">
            &ldquo;{script.hook.text}&rdquo;
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
                className="bg-white/10 rounded-2xl border border-white/20 overflow-hidden"
              >
                <button
                  onClick={() => toggleScene(scene.scene_id)}
                  className="w-full flex items-center justify-between p-5 text-left hover:bg-white/5 transition-colors"
                >
                  <div className="flex items-center gap-3">
                    <div className="w-7 h-7 rounded-full bg-white text-[#1A1A1A] flex items-center justify-center text-xs font-semibold flex-shrink-0">
                      {scene.scene_id}
                    </div>
                    <div>
                      <p
                        className={cn(
                          "text-sm text-white leading-snug",
                          !isExpanded && "line-clamp-1"
                        )}
                      >
                        {scene.voiceover_text}
                      </p>
                      {!isExpanded && (
                        <p className="text-xs text-white/40 mt-0.5">
                          {scene.duration_seconds}s · {scene.emotion}
                        </p>
                      )}
                    </div>
                  </div>
                  {isExpanded ? (
                    <ChevronUp className="w-4 h-4 text-white/40 flex-shrink-0 ml-3" />
                  ) : (
                    <ChevronDown className="w-4 h-4 text-white/40 flex-shrink-0 ml-3" />
                  )}
                </button>

                {isExpanded && (
                  <motion.div
                    initial={{ opacity: 0, height: 0 }}
                    animate={{ opacity: 1, height: "auto" }}
                    exit={{ opacity: 0, height: 0 }}
                    className="px-5 pb-5 pt-0 border-t border-white/10 space-y-3"
                  >
                    <div className="grid grid-cols-3 gap-3 mt-3">
                      <div className="bg-white/10 rounded-xl p-3">
                        <p className="text-xs text-white/40 mb-1">Duration</p>
                        <p className="text-sm font-medium text-white">
                          {scene.duration_seconds}s
                        </p>
                      </div>
                      <div className="bg-white/10 rounded-xl p-3">
                        <p className="text-xs text-white/40 mb-1">Emotion</p>
                        <p className="text-sm font-medium text-white capitalize">
                          {scene.emotion}
                        </p>
                      </div>
                      {scene.transition_to_next && (
                        <div className="bg-white/10 rounded-xl p-3">
                          <p className="text-xs text-white/40 mb-1">
                            Transition
                          </p>
                          <p className="text-sm font-medium text-white capitalize">
                            {scene.transition_to_next.replace(/_/g, " ")}
                          </p>
                        </div>
                      )}
                    </div>
                    {scene.visual_prompt && (
                      <div>
                        <p className="text-xs text-white/40 mb-1">
                          Visual prompt
                        </p>
                        <p className="text-sm text-white/50 italic">
                          {scene.visual_prompt}
                        </p>
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
          className="bg-white/10 rounded-2xl border border-white/20 p-5"
        >
          <p className="text-xs font-semibold uppercase tracking-wide text-white/40 mb-2">
            Call to Action
          </p>
          <p className="text-sm font-medium text-white">{script.cta.text}</p>
        </motion.div>

        {/* Full Voiceover Script */}
        <motion.details
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 0.35 }}
          className="bg-white/10 rounded-2xl border border-white/20 overflow-hidden"
        >
          <summary className="p-5 cursor-pointer text-sm font-medium text-white/50 hover:text-white hover:bg-white/5 transition-colors select-none">
            Full voiceover script
          </summary>
          <div className="px-5 pb-5 pt-2 border-t border-white/10">
            <p className="text-sm text-white leading-relaxed whitespace-pre-wrap">
              {script.voiceover_full_script}
            </p>
          </div>
        </motion.details>
      </div>
    </motion.div>
  );
}
