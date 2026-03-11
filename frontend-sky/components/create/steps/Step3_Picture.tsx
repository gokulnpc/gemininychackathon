"use client";

import { useWizard } from "@/context/WizardContext";
import { motion } from "framer-motion";
import { Upload, X, Loader2, LayoutGrid, Search, ImageIcon } from "lucide-react";
import { useRef, useState, useEffect } from "react";
import { cn } from "@/lib/utils";
import apiClient from "@/lib/apiClient";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";

interface AssetItem {
  id: string;
  filename: string;
  content_type: string;
  uploaded_at: string;
}

export function Step3_Picture() {
  const { state, dispatch } = useWizard();
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [assetDialogOpen, setAssetDialogOpen] = useState(false);
  const [assetSearch, setAssetSearch] = useState("");
  const [assets, setAssets] = useState<AssetItem[]>([]);
  const [assetUrls, setAssetUrls] = useState<Record<string, string>>({});
  const [assetsLoading, setAssetsLoading] = useState(false);
  const [assetsFetched, setAssetsFetched] = useState(false);

  const roles = [
    { id: "main_character", label: "Main Character" },
    { id: "side_character", label: "Supporting Character" },
    { id: "audience", label: "Background Character" },
  ];

  // Fetch assets on first dialog open
  useEffect(() => {
    if (!assetDialogOpen || assetsFetched) return;
    setAssetsLoading(true);
    apiClient
      .get("/api/v1/assets?category=images")
      .then((r) => {
        const list: AssetItem[] = r.data.assets ?? [];
        setAssets(list);
        setAssetsFetched(true);
        return list;
      })
      .then((list) => {
        if (!list.length) return;
        Promise.all(
          list.map((a) =>
            apiClient
              .get(`/api/v1/assets/${a.id}/url?category=images`)
              .then((r) => [a.id, r.data.url] as [string, string])
              .catch(() => [a.id, ""] as [string, string])
          )
        ).then((entries) => setAssetUrls(Object.fromEntries(entries)));
      })
      .catch(() => {
        setAssets([]);
        setAssetsFetched(true);
      })
      .finally(() => setAssetsLoading(false));
  }, [assetDialogOpen, assetsFetched]);

  const filteredAssets = assets.filter((a) =>
    a.filename.toLowerCase().includes(assetSearch.toLowerCase())
  );

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

  const handleAssetSelect = async (asset: AssetItem) => {
    const url = assetUrls[asset.id];
    if (!url) return;
    try {
      const blob = await fetch(url).then((r) => r.blob());
      const reader = new FileReader();
      reader.onloadend = () => {
        dispatch({ type: "SET_UPLOADED_PICTURE", payload: reader.result as string });
        if (!state.pictureRole) {
          dispatch({ type: "SET_PICTURE_ROLE", payload: "main_character" });
        }
        setAssetDialogOpen(false);
        setAssetSearch("");
      };
      reader.readAsDataURL(blob);
    } catch {
      console.error("Failed to load asset image");
    }
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
        {/* Left: upload zone */}
        <div className="flex flex-col space-y-4">
          <h3 className="text-sm font-medium text-white">Upload your picture</h3>

          <div
            className="flex-1 w-full border-2 border-dashed border-white/20 rounded-2xl bg-white/5 transition-colors hover:border-white/30 overflow-hidden"
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
              <div className="relative w-full h-full p-2 flex items-center justify-center min-h-[200px]">
                <img
                  src={state.uploadedPicture}
                  alt="Uploaded"
                  className="max-h-full max-w-full object-contain rounded-xl"
                />
                <button
                  onClick={removePicture}
                  className="absolute top-2 right-2 p-2 bg-black/50 hover:bg-black/70 rounded-full text-white transition-colors"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>
            ) : (
              <div className="flex flex-col items-center justify-center p-8 gap-6">
                <p className="text-sm text-white/50 text-center">
                  Choose a file or drag and drop it here (jpg, png)
                </p>
                <div className="flex items-center gap-3">
                  <button
                    onClick={() => fileInputRef.current?.click()}
                    className="flex items-center gap-2 px-5 py-2.5 rounded-full border border-white/30 hover:bg-white/10 transition-colors text-white text-sm font-medium"
                  >
                    <Upload className="w-4 h-4" />
                    Browse file
                  </button>
                  <span className="text-white/20 text-xs">or</span>
                  <button
                    onClick={() => setAssetDialogOpen(true)}
                    className="flex items-center gap-2 px-5 py-2.5 rounded-full border border-white/30 hover:bg-white/10 transition-colors text-white text-sm font-medium"
                  >
                    <LayoutGrid className="w-4 h-4" />
                    My Assets
                  </button>
                </div>
              </div>
            )}
          </div>

          <input
            type="file"
            ref={fileInputRef}
            onChange={handleFileUpload}
            accept="image/jpeg, image/png"
            className="hidden"
          />
        </div>

        {/* Right: role selector */}
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

      {/* My Assets Dialog */}
      <Dialog open={assetDialogOpen} onOpenChange={(open) => {
        setAssetDialogOpen(open);
        if (!open) setAssetSearch("");
      }}>
        <DialogContent className="max-w-2xl border-white/10 bg-[#2B2B2B] text-white">
          <DialogHeader>
            <DialogTitle className="text-white">Select from My Assets</DialogTitle>
          </DialogHeader>

          {/* Search */}
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-white/40" />
            <Input
              placeholder="Search by filename…"
              value={assetSearch}
              onChange={(e) => setAssetSearch(e.target.value)}
              className="pl-9 bg-[#333333] border-white/10 text-white placeholder:text-white/40 focus-visible:ring-[#5a9ab5]"
            />
          </div>

          {/* Grid */}
          <div className="overflow-y-auto max-h-[420px] pr-1 mt-1">
            {assetsLoading ? (
              <div className="flex items-center justify-center py-16">
                <Loader2 className="w-6 h-6 animate-spin text-[#5a9ab5]" />
              </div>
            ) : filteredAssets.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-16 gap-3">
                <ImageIcon className="w-10 h-10 text-white/20" />
                <p className="text-sm text-white/40 text-center">
                  {assets.length === 0
                    ? "No images in My Assets yet."
                    : "No images match your search."}
                </p>
              </div>
            ) : (
              <div className="grid grid-cols-4 gap-3">
                {filteredAssets.map((asset) => {
                  const url = assetUrls[asset.id];
                  return (
                    <button
                      key={asset.id}
                      onClick={() => handleAssetSelect(asset)}
                      className="group relative rounded-xl overflow-hidden border-2 border-transparent hover:border-[#5a9ab5] transition-all duration-200"
                    >
                      <div className="aspect-square w-full bg-[#333333]">
                        {url ? (
                          <img
                            src={url}
                            alt={asset.filename}
                            className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-200"
                          />
                        ) : (
                          <div className="w-full h-full flex items-center justify-center">
                            <Loader2 className="w-4 h-4 animate-spin text-white/30" />
                          </div>
                        )}
                      </div>
                      <div className="absolute bottom-0 inset-x-0 bg-gradient-to-t from-black/70 to-transparent px-2 py-1.5 opacity-0 group-hover:opacity-100 transition-opacity">
                        <p className="text-xs text-white truncate">{asset.filename}</p>
                      </div>
                    </button>
                  );
                })}
              </div>
            )}
          </div>
        </DialogContent>
      </Dialog>
    </motion.div>
  );
}
