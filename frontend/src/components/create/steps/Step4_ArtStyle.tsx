"use client";

import { cn } from "@/lib/utils";
import { useWizard } from "@/context/WizardContext";
import { artStyles } from "@/data/staticData";
import { motion, AnimatePresence } from "framer-motion";
import { Palette } from "lucide-react";

const artStyleImageMap: Record<string, string> = {
  realism: "/ArtStyle_Cinematic.png",
  comic: "/ArtStyle_Comic.png",
  "creepy-comic": "/ArtStyle_CreepyComic.png",
  painting: "/ArtStyle_Elegant.png",
  ghibli: "/ArtStyle_ModernComic.png",
  disney: "/ArtStyle_ModernComic.png",
  polaroid: "/ArtStyle_Cinematic.png",
};

export function Step4_ArtStyle() {
  const { state, dispatch } = useWizard();

  const handleStyleSelect = (styleId: string) => {
    dispatch({ type: "SET_SELECTED_ART_STYLE", payload: styleId });
  };

  const selectedImage = state.selectedArtStyle
    ? artStyleImageMap[state.selectedArtStyle]
    : null;

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -20 }}
      transition={{ duration: 0.3 }}
      className="flex gap-6"
    >
      {/* Style List */}
      <div className="flex-1 space-y-3">
        {artStyles.map((style, index) => (
          <motion.button
            key={style.id}
            initial={{ opacity: 0, x: -10 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ delay: index * 0.05 }}
            onClick={() => handleStyleSelect(style.id)}
            className={cn(
              "w-full flex items-center gap-4 p-4 rounded-2xl border transition-all duration-200 text-left",
              state.selectedArtStyle === style.id
                ? "border-[#B08D9F] bg-[#B08D9F]/5"
                : "border-[#E8E0DC] bg-white hover:border-[#B08D9F]/30"
            )}
          >
            <img
              src={artStyleImageMap[style.id] ?? "/Avatar.png"}
              alt={style.name}
              className="w-10 h-10 rounded-full shrink-0 object-cover"
            />
            <div>
              <h4 className="text-sm font-medium text-[#1A1A1A]">
                {style.name}
              </h4>
              <p className="text-sm text-[#6B6B6B] mt-0.5">
                {style.description}
              </p>
            </div>
          </motion.button>
        ))}
      </div>

      {/* Preview Panel */}
      <div className="w-[280px] shrink-0">
        <div className="bg-gray-100 rounded-2xl border border-[#E8E0DC] h-full overflow-hidden relative">
          <AnimatePresence mode="wait">
            {selectedImage ? (
              <motion.img
                key={state.selectedArtStyle ?? "empty"}
                src={selectedImage}
                alt={state.selectedArtStyle ?? ""}
                initial={{ opacity: 0, scale: 1.05 }}
                animate={{ opacity: 1, scale: 1 }}
                exit={{ opacity: 0, scale: 0.95 }}
                transition={{ duration: 0.3 }}
                className="w-full h-full object-cover"
              />
            ) : (
              <motion.div
                key="placeholder"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                className="w-full h-full flex items-center justify-center"
              >
                <div className="text-center">
                  <div className="w-16 h-16 rounded-full bg-gray-200 flex items-center justify-center mx-auto mb-3">
                    <Palette className="w-7 h-7 text-gray-400" />
                  </div>
                  <p className="text-sm text-[#9B9B9B]">Preview</p>
                </div>
              </motion.div>
            )}
          </AnimatePresence>

          {state.selectedArtStyle && (
            <div className="absolute bottom-3 left-1/2 -translate-x-1/2">
              <span className="text-xs text-white bg-black/50 px-3 py-1 rounded-full capitalize">
                {state.selectedArtStyle.replace(/-/g, " ")}
              </span>
            </div>
          )}
        </div>
      </div>
    </motion.div>
  );
}
