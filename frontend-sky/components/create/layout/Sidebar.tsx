"use client";

import {
  LayoutDashboard,
  Plus,
  CreditCard,
  Settings,
  Mic,
  Volume2,
  Music,
  Palette,
  Type,
  Zap,
  Clock,
  Eye,
  ChevronDown,
  BookOpen,
  Image as ImageIcon,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useWizard } from "@/context/WizardContext";
import { useRouter } from "next/navigation";
import { motion } from "framer-motion";

const createSubItems = [
  { id: 1, label: "Tell Your Story", icon: Mic },
  { id: 2, label: "Choose the Plot", icon: BookOpen },
  { id: 3, label: "Upload your Picture (opt.)", icon: ImageIcon },
  { id: 4, label: "Language & Voice (opt.)", icon: Volume2 },
  { id: 5, label: "Background Music (opt.)", icon: Music },
  { id: 6, label: "Video Style", icon: Palette },
  { id: 7, label: "Caption Style (opt.)", icon: Type },
  { id: 8, label: "Video Effect (opt.)", icon: Zap },
  { id: 9, label: "Video Config.", icon: Clock },
  { id: 10, label: "Review & Publish", icon: Eye },
];

export function Sidebar() {
  const { state, dispatch } = useWizard();
  const router = useRouter();

  const handleStepClick = (step: number) => {
    if (!state.isProcessing) {
      dispatch({ type: "SET_STEP", payload: step });
    }
  };

  return (
    <motion.aside
      initial={{ opacity: 0, x: -20 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ duration: 0.4, ease: "easeOut" }}
      className="fixed left-0 top-0 h-full w-[240px] bg-[#1B1B1B] z-50 flex flex-col"
    >
      {/* Logo */}
      <div className="p-6 border-b border-white/10">
        <button
          onClick={() => router.push("/welcome")}
          className="hover:opacity-80 transition-opacity"
        >
          <img
            src="/logo_StoryLab_sky.png"
            alt="Story Lab"
            className="h-6"
          />
        </button>
      </div>

      {/* Navigation */}
      <nav className="flex-1 px-3 py-4 overflow-y-auto">
        <ul className="space-y-1">
          {/* Overview */}
          <li>
            <button
              onClick={() => router.push("/welcome")}
              className="w-full flex items-center gap-3 px-4 py-3 rounded-xl text-sm font-medium text-[#9B9B9B] hover:text-white hover:bg-white/10 transition-all duration-200"
            >
              <LayoutDashboard className="w-4 h-4 shrink-0" />
              Overview
            </button>
          </li>

          {/* Create (always expanded on create page) */}
          <li>
            <button
              disabled
              className="w-full flex items-center gap-3 px-4 py-3 rounded-xl text-sm font-medium text-white cursor-default"
            >
              <Plus className="w-4 h-4 shrink-0" />
              <span className="flex-1 text-left">Create</span>
              <ChevronDown className="w-3 h-3" />
            </button>

            {/* Wizard sub-steps */}
            <ul className="mt-1 ml-3 space-y-0.5">
              {createSubItems.map((item, index) => {
                const Icon = item.icon;
                const isActive = state.currentStep === item.id;

                return (
                  <motion.li
                    key={item.id}
                    initial={{ opacity: 0, x: -10 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ delay: index * 0.04 + 0.1 }}
                  >
                    <button
                      onClick={() => handleStepClick(item.id)}
                      disabled={state.isProcessing}
                      className={cn(
                        "w-full flex items-center gap-3 px-4 py-2.5 rounded-xl text-xs font-medium transition-all duration-200",
                        isActive
                          ? "bg-[#5a9ab5] text-white shadow-md"
                          : "text-[#9B9B9B] hover:text-white hover:bg-white/10"
                      )}
                    >
                      <Icon className="w-3.5 h-3.5 shrink-0" />
                      {item.label}
                    </button>
                  </motion.li>
                );
              })}
            </ul>
          </li>

          {/* Billing */}
          <li>
            <button className="w-full flex items-center gap-3 px-4 py-3 rounded-xl text-sm font-medium text-[#9B9B9B] hover:text-white hover:bg-white/10 transition-all duration-200">
              <CreditCard className="w-4 h-4 shrink-0" />
              Billing
            </button>
          </li>

          {/* Settings */}
          <li>
            <button className="w-full flex items-center gap-3 px-4 py-3 rounded-xl text-sm font-medium text-[#9B9B9B] hover:text-white hover:bg-white/10 transition-all duration-200">
              <Settings className="w-4 h-4 shrink-0" />
              Settings
            </button>
          </li>
        </ul>
      </nav>
    </motion.aside>
  );
}
