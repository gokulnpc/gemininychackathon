"use client";

import {
  Mic,
  Sparkles,
  Volume2,
  Music,
  Palette,
  Type,
  Zap,
  Clock,
  Eye,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useWizard } from "@/context/WizardContext";
import { useRouter } from "next/navigation";
import { motion } from "framer-motion";

const iconMap: Record<string, React.ElementType> = {
  Mic,
  Sparkles,
  Volume2,
  Music,
  Palette,
  Type,
  Zap,
  Clock,
  Eye,
};

const sidebarItems = [
  { id: 1, label: "Your Message", icon: "Mic" },
  { id: 2, label: "Language & Voice", icon: "Volume2" },
  { id: 3, label: "Background Music", icon: "Music" },
  { id: 4, label: "Art Style", icon: "Palette" },
  { id: 5, label: "Caption Style", icon: "Type" },
  { id: 6, label: "Effects", icon: "Zap" },
  { id: 7, label: "Video Details", icon: "Clock" },
  { id: 8, label: "Review Outputs", icon: "Eye" },
];

export function Sidebar() {
  const { state, dispatch } = useWizard();
  const router = useRouter();

  const handleItemClick = (step: number) => {
    if (!state.isProcessing) {
      dispatch({ type: "SET_STEP", payload: step });
    }
  };

  const handleLogoClick = () => {
    router.push("/welcome");
  };

  return (
    <motion.aside
      initial={{ opacity: 0, x: -20 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ duration: 0.4, ease: "easeOut" }}
      className="fixed left-0 top-0 h-full w-[240px] bg-white border-r border-[#E8E0DC] z-50 flex flex-col"
    >
      {/* Logo */}
      <div className="p-6">
        <button
          onClick={handleLogoClick}
          className="hover:opacity-80 transition-opacity"
        >
          <img
            src="/Logo_ContentFactory.png"
            alt="Content Factory"
            className="h-6"
          />
        </button>
      </div>

      {/* Navigation Items */}
      <nav className="flex-1 px-4 py-2">
        <ul className="space-y-1">
          {sidebarItems.map((item, index) => {
            const Icon = iconMap[item.icon];
            const isActive = state.currentStep === item.id;

            return (
              <motion.li
                key={item.id}
                initial={{ opacity: 0, x: -10 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: index * 0.05 + 0.2 }}
              >
                <button
                  onClick={() => handleItemClick(item.id)}
                  disabled={state.isProcessing}
                  className={cn(
                    "w-full flex items-center gap-3 px-4 py-3 rounded-xl text-sm font-medium transition-all duration-200",
                    isActive
                      ? "bg-[#B08D9F] text-white shadow-md"
                      : "text-[#6B6B6B] hover:bg-gray-50"
                  )}
                >
                  <Icon className="w-4 h-4" />
                  <span>{item.label}</span>
                </button>
              </motion.li>
            );
          })}
        </ul>
      </nav>

      {/* Upgrade Button */}
      <div className="p-4 border-t border-[#F0E8E4]">
        <button className="w-full flex items-center gap-3 px-4 py-3 rounded-xl text-sm font-medium text-[#6B6B6B] hover:bg-gray-50 transition-all duration-200">
          <Sparkles className="w-4 h-4" />
          <span>Upgrade</span>
        </button>
      </div>
    </motion.aside>
  );
}
