"use client";

import { useWizard } from "@/context/WizardContext";
import { stepTitles } from "@/data/staticData";
import { motion } from "framer-motion";
import { Badge } from "@/components/ui/badge";

export function Header() {
  const { state } = useWizard();
  const { title, subtitle } = stepTitles[state.currentStep] || {
    title: "",
    subtitle: "",
  };

  const isOptional = [3, 4, 5, 7, 8].includes(state.currentStep);

  // Don't render header during processing or on review step (has its own header)
  if (state.isProcessing || state.currentStep === 10) return null;

  return (
    <motion.header
      initial={{ opacity: 0, y: -10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, delay: 0.1 }}
      className="mb-8"
    >
      <div className="flex items-center gap-4 mb-2">
        <h1 className="text-[42px] font-medium text-white leading-tight tracking-tight">
          {title}
        </h1>
        {isOptional && (
          <Badge
            variant="secondary"
            className="bg-white/10 text-white/50 hover:bg-white/10 text-sm font-normal px-4 py-1.5 rounded-full border-none"
          >
            Optional
          </Badge>
        )}
      </div>
      {subtitle && <p className="text-lg text-white/50">{subtitle}</p>}
    </motion.header>
  );
}
