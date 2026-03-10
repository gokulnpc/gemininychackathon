"use client";

import { cn } from "@/lib/utils";
import { useWizard } from "@/context/WizardContext";
import { motion } from "framer-motion";
import { Loader2, Check } from "lucide-react";
import { useState, useEffect } from "react";
import apiClient from "@/lib/apiClient";

interface ArtStyle {
  key: string;
  name: string;
  image_url: string;
}

export function Step6_ArtStyle() {
  const { state, dispatch } = useWizard();
  const [styles, setStyles] = useState<ArtStyle[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const baseUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
    apiClient.get(`/api/v1/art-styles?base_url=${encodeURIComponent(baseUrl)}`)
      .then(r => setStyles(r.data.art_styles ?? []))
      .catch(() => setStyles([]))
      .finally(() => setLoading(false));
  }, []);

  const handleStyleSelect = (key: string) => {
    dispatch({ type: "SET_SELECTED_ART_STYLE", payload: key });
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -20 }}
      transition={{ duration: 0.3 }}
    >
      {loading ? (
        <div className="flex items-center justify-center py-12">
          <Loader2 className="w-6 h-6 animate-spin text-[#5a9ab5]" />
        </div>
      ) : (
        <div className="grid grid-cols-4 gap-3 overflow-y-auto max-h-[62vh]">
          {styles.map((style, index) => {
            const isSelected = state.selectedArtStyle === style.key;
            return (
              <motion.button
                key={style.key}
                initial={{ opacity: 0, scale: 0.95 }}
                animate={{ opacity: 1, scale: 1 }}
                transition={{ delay: index * 0.025 }}
                onClick={() => handleStyleSelect(style.key)}
                className={cn(
                  "relative group rounded-xl overflow-hidden border-2 transition-all duration-200",
                  isSelected
                    ? "border-[#5a9ab5] shadow-lg shadow-[#5a9ab5]/20"
                    : "border-transparent hover:border-white/30"
                )}
              >
                {/* Image */}
                <div className="aspect-[3/4] w-full overflow-hidden">
                  <img
                    src={style.image_url}
                    alt={style.name}
                    className="w-full h-full object-cover transition-transform duration-300 group-hover:scale-105"
                  />
                </div>

                {/* Name overlay at bottom */}
                <div className="absolute bottom-0 inset-x-0 bg-gradient-to-t from-black/70 to-transparent px-2 py-2">
                  <p className="text-xs font-medium text-white truncate">
                    {style.name}
                  </p>
                </div>

                {/* Selected checkmark */}
                {isSelected && (
                  <motion.div
                    initial={{ scale: 0 }}
                    animate={{ scale: 1 }}
                    className="absolute top-2 right-2 w-5 h-5 rounded-full bg-[#5a9ab5] flex items-center justify-center shadow-lg"
                  >
                    <Check className="w-3 h-3 text-white" />
                  </motion.div>
                )}
              </motion.button>
            );
          })}
        </div>
      )}
    </motion.div>
  );
}
