"use client";

import { Switch } from "@/components/ui/switch";
import { cn } from "@/lib/utils";
import { useWizard } from "@/context/WizardContext";
import { effects } from "@/data/staticData";
import { motion } from "framer-motion";
import { Badge } from "@/components/ui/badge";

export function Step8_Effects() {
  const { state, dispatch } = useWizard();

  const handleEffectToggle = (effectKey: keyof typeof state.effects) => {
    dispatch({
      type: "SET_EFFECT",
      payload: { effect: effectKey, value: !state.effects[effectKey] },
    });
  };

  const getEffectKey = (id: string): keyof typeof state.effects => {
    switch (id) {
      case "shake-effect":
        return "shakeEffect";
      case "film-grain":
        return "filmGrain";
      case "animated-stock":
        return "animatedStock";
      default:
        return "shakeEffect";
    }
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -20 }}
      transition={{ duration: 0.3 }}
      className="space-y-4"
    >
      {effects.map((effect, index) => {
        const effectKey = getEffectKey(effect.id);
        const isEnabled = state.effects[effectKey];

        return (
          <motion.div
            key={effect.id}
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: index * 0.05 }}
            className={cn(
              "flex items-center justify-between p-5 rounded-2xl border transition-all duration-200",
              isEnabled
                ? "border-[#5a9ab5] bg-[#5a9ab5]/20"
                : "border-white/20 bg-white/20"
            )}
          >
            <div className="flex-1">
              <div className="flex items-center gap-2 mb-1">
                <h4 className="text-sm font-medium text-white">
                  {effect.name}
                </h4>
                {effect.tag && (
                  <Badge
                    variant="secondary"
                    className={cn(
                      "text-xs font-medium px-2 py-0.5 text-white",
                      effect.tag === "NEW"
                        ? "bg-[#4296BB] hover:bg-[#4296BB]"
                        : "bg-[#AE82A8] hover:bg-[#AE82A8]"
                    )}
                  >
                    {effect.tag}
                  </Badge>
                )}
              </div>
              <p className="text-sm text-white/50">{effect.description}</p>
            </div>
            <Switch
              checked={isEnabled}
              onCheckedChange={() => handleEffectToggle(effectKey)}
              className="data-[state=checked]:bg-[#5a9ab5] data-[state=unchecked]:bg-white/20 ml-4"
            />
          </motion.div>
        );
      })}
    </motion.div>
  );
}
