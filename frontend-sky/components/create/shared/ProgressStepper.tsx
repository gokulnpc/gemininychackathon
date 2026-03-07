"use client";

import { cn } from "@/lib/utils";
import { useWizard } from "@/context/WizardContext";
import { motion } from "framer-motion";

export function ProgressStepper() {
  const { state } = useWizard();
  const totalSteps = 10; // Show all 10 steps in stepper

  const isStepActuallyCompleted = (stepNum: number) => {
    if (stepNum === 1) return !!state.messageText || !!state.audioBase64 || !!state.selectedPreset;
    if (stepNum === 2) return !!state.selectedPlotOption;
    // Optional steps 3–9: completed once the user has moved past them
    if (stepNum >= 3 && stepNum <= 9) return stepNum < state.currentStep;
    if (stepNum === 10) return !!state.generatedScript;
    return false;
  };

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ duration: 0.4, delay: 0.2 }}
      className="flex items-center justify-center mb-10"
    >
      <div className="flex items-center">
        {Array.from({ length: totalSteps }, (_, i) => {
          const stepNumber = i + 1;
          const isActive = stepNumber === state.currentStep;
          const isCompleted = isStepActuallyCompleted(stepNumber);
          const isLast = stepNumber === totalSteps;

          return (
            <div key={stepNumber} className="flex items-center">
              <motion.div
                initial={{ scale: 0.8, opacity: 0 }}
                animate={{ scale: 1, opacity: 1 }}
                transition={{ delay: i * 0.05 + 0.3 }}
                className={cn(
                  "w-8 h-8 rounded-full flex items-center justify-center text-xs font-medium transition-all duration-300",
                  isActive
                    ? "text-white shadow-md border-2 border-[#90D6F8]"
                    : isCompleted
                      ? "bg-[#5a9ab5]/20 text-[#5a9ab5] border-2 border-[#5a9ab5]"
                      : "bg-white text-[#6B6B6B] border-2 border-[#E8E0DC]"
                )}
                style={
                  isActive
                    ? {
                        background:
                          "linear-gradient(135deg, #F5DBE9 0%, #718FA8 33%, #26688A 66%, #4296BB 100%)",
                      }
                    : undefined
                }
              >
                {isCompleted ? (
                  <svg
                    className="w-4 h-4"
                    fill="none"
                    viewBox="0 0 24 24"
                    stroke="currentColor"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={2}
                      d="M5 13l4 4L19 7"
                    />
                  </svg>
                ) : (
                  stepNumber
                )}
              </motion.div>
              {!isLast && (
                <div
                  className={cn(
                    "w-8 h-0.5 transition-all duration-300",
                    isCompleted ? "bg-[#90D6F8]" : "bg-[#E8E0DC]"
                  )}
                />
              )}
            </div>
          );
        })}
      </div>
    </motion.div>
  );
}
