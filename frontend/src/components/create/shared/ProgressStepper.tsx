"use client";

import { cn } from '@/lib/utils';
import { useWizard } from '@/context/WizardContext';
import { motion } from 'framer-motion';

export function ProgressStepper() {
  const { state } = useWizard();
  const totalSteps = 7; // Only show 7 steps in stepper (step 8 is review, shown separately)

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
          const isCompleted = stepNumber < state.currentStep;
          const isLast = stepNumber === totalSteps;

          return (
            <div key={stepNumber} className="flex items-center">
              <motion.div
                initial={{ scale: 0.8, opacity: 0 }}
                animate={{ scale: 1, opacity: 1 }}
                transition={{ delay: i * 0.05 + 0.3 }}
                className={cn(
                  'w-9 h-9 rounded-full flex items-center justify-center text-sm font-medium transition-all duration-300',
                  isActive
                    ? 'text-white shadow-md border-2 border-[#EBA9A1]'
                    : isCompleted
                    ? 'bg-[#B08D9F]/20 text-[#B08D9F] border-2 border-[#B08D9F]'
                    : 'bg-white text-[#6B6B6B] border-2 border-[#E8E0DC]'
                )}
                style={isActive ? { background: 'linear-gradient(to bottom, #AE82A8, #E6A19B)' } : undefined}
              >
                {isCompleted ? (
                  <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                  </svg>
                ) : (
                  stepNumber
                )}
              </motion.div>
              {!isLast && (
                <div
                  className={cn(
                    'w-10 h-0.5 transition-all duration-300',
                    isCompleted ? 'bg-[#EBA9A1]' : 'bg-[#E8E0DC]'
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
