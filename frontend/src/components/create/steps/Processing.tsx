"use client";

import { useEffect, useState } from "react";
import { processingSteps } from "@/data/staticData";
import { motion } from "framer-motion";
import { cn } from "@/lib/utils";
import { Check } from "lucide-react";
import { useWizard } from "@/context/WizardContext";

export function Processing() {
  const { state, dispatch } = useWizard();
  const [progress, setProgress] = useState(25);
  const [completedSteps, setCompletedSteps] = useState<number[]>([]);
  const [currentStep, setCurrentStep] = useState(1);

  const isPresetMode = state.presetConfig !== null;

  // Fake progress animation
  useEffect(() => {
    const interval = setInterval(() => {
      setProgress((prev) => {
        if (prev >= 100) {
          clearInterval(interval);
          return 100;
        }
        // In preset mode slow down a bit so the pipeline has time to finish
        return prev + 1;
      });
    }, 600);

    return () => clearInterval(interval);
  }, []);

  // Track visual step completion from progress
  useEffect(() => {
    let nextStep = currentStep;
    const newCompletedSteps = [...completedSteps];
    let stepChanged = false;

    if (progress >= 25 && !newCompletedSteps.includes(1)) {
      newCompletedSteps.push(1);
      stepChanged = true;
    }
    if (progress >= 50 && !newCompletedSteps.includes(2)) {
      newCompletedSteps.push(2);
      nextStep = 2;
      stepChanged = true;
    }
    if (progress >= 75 && !newCompletedSteps.includes(3)) {
      newCompletedSteps.push(3);
      nextStep = 3;
      stepChanged = true;
    }
    if (progress >= 100 && !newCompletedSteps.includes(4)) {
      newCompletedSteps.push(4);
      nextStep = 4;
      stepChanged = true;
    }

    if (stepChanged) {
      setCompletedSteps(newCompletedSteps);
      if (nextStep !== currentStep) {
        setCurrentStep(nextStep);
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [progress]);

  // Navigate to step 8 when animation is done AND pipeline result is ready (preset mode)
  // or immediately after animation in non-preset mode
  useEffect(() => {
    if (progress < 100) return;
    if (isPresetMode && !state.pipelineProjectId) return; // hold until pipeline done

    const timer = setTimeout(() => {
      dispatch({ type: "SET_PROCESSING", payload: false });
      dispatch({ type: "SET_STEP", payload: 8 });
    }, 1000);
    return () => clearTimeout(timer);
  }, [progress, state.pipelineProjectId, isPresetMode, dispatch]);

  // Also trigger navigation when pipeline result arrives after animation completes
  useEffect(() => {
    if (!state.pipelineProjectId || progress < 100) return;

    const timer = setTimeout(() => {
      dispatch({ type: "SET_PROCESSING", payload: false });
      dispatch({ type: "SET_STEP", payload: 8 });
    }, 500);
    return () => clearTimeout(timer);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state.pipelineProjectId]);

  const waitingForPipeline = isPresetMode && progress >= 100 && !state.pipelineProjectId;

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.3 }}
      className="max-w-3xl mx-auto text-left py-8"
    >
      <div className="flex items-center gap-4 mb-3">
        {/* Title */}
        <motion.h1
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.1 }}
          className="text-5xl font-medium text-[#1A1A1A]"
        >
          Creating Magic
        </motion.h1>

        {/* Status Badge */}
        <motion.div
          initial={{ opacity: 0, y: -10 }}
          animate={{ opacity: 1, y: 0 }}
          className="inline-flex items-center gap-2 px-4 py-2 rounded-full border border-[#E8E0DC] bg-white"
        >
          <motion.span
            animate={{ scale: [1, 1.2, 1], opacity: [1, 0.5, 1] }}
            transition={{ duration: 1.5, repeat: Infinity }}
            className="w-2 h-2 rounded-full bg-blue-500"
          />
          <span className="text-sm font-medium text-[#1A1A1A]">
            {waitingForPipeline ? "Finalizing video…" : "Processing"}
          </span>
        </motion.div>
      </div>

      <motion.p
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ delay: 0.2 }}
        className="text-[#6B6B6B] mb-10"
      >
        {waitingForPipeline
          ? "Almost done — composing your final video…"
          : "This usually takes about 60 seconds"}
      </motion.p>

      {/* Progress Bar */}
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ delay: 0.3 }}
        className="mb-10"
      >
        <div className="flex items-center justify-between text-sm mb-2">
          <span className="text-[#6B6B6B]">Overall Progress</span>
          <span className="font-medium text-[#1A1A1A]">{progress}%</span>
        </div>
        <div className="h-2 bg-gray-200 rounded-full overflow-hidden">
          <motion.div
            className="h-full bg-gradient-to-r from-[#EBA9A1] to-[#AC82A9] rounded-full"
            initial={{ width: "0%" }}
            animate={{ width: `${progress}%` }}
            transition={{ duration: 0.5, ease: "easeOut" }}
          />
        </div>
      </motion.div>

      {/* Processing Steps */}
      <div className="space-y-4">
        {processingSteps.map((step, index) => {
          const isCompleted = completedSteps.includes(step.id);
          const isActive = currentStep === step.id && !isCompleted;
          const isPending = step.id > currentStep;

          return (
            <motion.div
              key={step.id}
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.4 + index * 0.1 }}
              className={cn(
                "flex items-center justify-between p-5 rounded-2xl border transition-all duration-300",
                isCompleted
                  ? "border-[#E8E0DC] bg-white"
                  : isActive
                    ? "border-[#1A1A1A] bg-white shadow-md"
                    : "border-[#E8E0DC] bg-white/50"
              )}
            >
              <div className="flex items-center gap-4">
                <div
                  className={cn(
                    "w-10 h-10 rounded-full flex items-center justify-center transition-all duration-300",
                    isCompleted
                      ? "bg-[#B08D9F]"
                      : isActive
                        ? "bg-[#1A1A1A]"
                        : "bg-gray-200"
                  )}
                >
                  {isCompleted ? (
                    <Check className="w-5 h-5 text-white" />
                  ) : isActive ? (
                    <motion.div
                      animate={{ scale: [1, 1.2, 1] }}
                      transition={{ duration: 1, repeat: Infinity }}
                      className="w-3 h-3 rounded-full bg-white"
                    />
                  ) : (
                    <span className="w-3 h-3 rounded-full bg-gray-400" />
                  )}
                </div>
                <div className="text-left">
                  <h4
                    className={cn(
                      "text-base font-medium transition-colors duration-300",
                      isPending ? "text-[#9B9B9B]" : "text-[#1A1A1A]"
                    )}
                  >
                    {step.title}
                  </h4>
                  <p
                    className={cn(
                      "text-sm transition-colors duration-300",
                      isPending ? "text-[#9B9B9B]" : "text-[#6B6B6B]"
                    )}
                  >
                    {step.description}
                  </p>
                </div>
              </div>
              {step.model && (
                <span
                  className={cn(
                    "text-xs font-medium px-3 py-1.5 rounded-full border transition-all duration-300",
                    isPending
                      ? "border-[#E8E0DC] text-[#9B9B9B]"
                      : "border-[#E8E0DC] text-[#6B6B6B]"
                  )}
                >
                  {step.model}
                </span>
              )}
            </motion.div>
          );
        })}
      </div>
    </motion.div>
  );
}
