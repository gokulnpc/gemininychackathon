"use client";

import { useWizard } from "@/context/WizardContext";
import { motion } from "framer-motion";
import { Upload, X } from "lucide-react";
import { useRef } from "react";
import { cn } from "@/lib/utils";

export function Step3_Picture() {
  const { state, dispatch } = useWizard();
  const fileInputRef = useRef<HTMLInputElement>(null);

  const roles = [
    { id: "main_character", label: "Main Character" },
    { id: "side_character", label: "Supporting Character" },
    { id: "audience", label: "Background Character" },
  ];

  const readAsDataURL = (file: File) => {
    const reader = new FileReader();
    reader.onload = (ev) => {
      const dataUrl = ev.target?.result as string;
      dispatch({ type: "SET_UPLOADED_PICTURE", payload: dataUrl });
      if (!state.pictureRole) {
        dispatch({ type: "SET_PICTURE_ROLE", payload: "main_character" });
      }
    };
    reader.readAsDataURL(file);
  };

  const handleFileUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    readAsDataURL(file);
  };

  const removePicture = () => {
    dispatch({ type: "SET_UPLOADED_PICTURE", payload: null });
    dispatch({ type: "SET_PICTURE_ROLE", payload: null });
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -20 }}
      transition={{ duration: 0.3 }}
      className="space-y-8"
    >
      <div className="grid grid-cols-2 gap-8 items-stretch">
        <div className="flex flex-col space-y-4">
          <h3 className="text-sm font-medium text-white">Upload your picture</h3>
          
          <div 
            className="flex-1 w-full border-2 border-dashed border-white/20 rounded-2xl p-8 bg-white/5 flex flex-col items-center justify-center transition-colors hover:bg-white/10 hover:border-white/30"
            onDragOver={(e) => e.preventDefault()}
            onDrop={(e) => {
              e.preventDefault();
              const file = e.dataTransfer.files?.[0];
              if (file && (file.type === "image/jpeg" || file.type === "image/png")) {
                readAsDataURL(file);
              }
            }}
          >
            {state.uploadedPicture ? (
              <div className="relative w-full h-full p-2 flex items-center justify-center">
                <img 
                  src={state.uploadedPicture} 
                  alt="Uploaded" 
                  className="max-h-full max-w-full object-contain rounded-xl"
                />
                <button 
                  onClick={removePicture}
                  className="absolute top-0 right-0 p-2 bg-black/50 hover:bg-black/70 rounded-full text-white transition-colors"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>
            ) : (
              <>
                <p className="text-sm text-white/50 mb-6 text-center">
                  Choose a file or drag and drop it here (jpg, png)
                </p>
                <button 
                  onClick={() => fileInputRef.current?.click()}
                  className="flex items-center justify-center gap-2 px-6 py-3 rounded-full border border-white/30 hover:bg-white/10 transition-colors text-white text-sm font-medium"
                >
                  <Upload className="w-4 h-4" />
                  Browse file
                </button>
                <input 
                  type="file" 
                  ref={fileInputRef} 
                  onChange={handleFileUpload} 
                  accept="image/jpeg, image/png" 
                  className="hidden" 
                />
              </>
            )}
          </div>
        </div>

        <div className="flex flex-col space-y-4">
          <h3 className="text-sm font-medium text-white">Choose your role</h3>
          <div className="flex flex-col justify-between flex-1 gap-3">
            {roles.map((role) => (
              <button
                key={role.id}
                onClick={() => dispatch({ type: "SET_PICTURE_ROLE", payload: role.id })}
                className={cn(
                  "w-full h-full flex-1 flex items-center px-5 py-4 rounded-xl border transition-all duration-200",
                  state.pictureRole === role.id
                    ? "border-[#5a9ab5] bg-[#5a9ab5]/20 text-white"
                    : "border-white/10 bg-white/5 text-white/70 hover:border-white/30 hover:bg-white/10"
                )}
              >
                <span className="text-sm font-medium">{role.label}</span>
              </button>
            ))}
          </div>
        </div>
      </div>
    </motion.div>
  );
}
