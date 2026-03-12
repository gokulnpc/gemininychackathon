"use client";

export const formatSeconds = (seconds: number | null | undefined): string => {
  if (typeof seconds !== "number" || Number.isNaN(seconds)) return "--:--";
  const minutes = Math.floor(seconds / 60);
  const remainingSeconds = Math.floor(seconds % 60);
  return `${minutes.toString().padStart(2, "0")}:${remainingSeconds.toString().padStart(2, "0")}`;
};

export const getSelectedItemLabel = (selectedItem: unknown): string => {
  if (!selectedItem || typeof selectedItem !== "object") return "Nothing selected";
  if ("getName" in selectedItem && typeof (selectedItem as Record<string, unknown>).getName === "function") {
    const name = (selectedItem as { getName: () => unknown }).getName();
    if (typeof name === "string" && name.trim()) return name;
  }
  if ("getType" in selectedItem && typeof (selectedItem as Record<string, unknown>).getType === "function") {
    const type = (selectedItem as { getType: () => unknown }).getType();
    if (typeof type === "string" && type.trim()) return type;
  }
  return "Selected item";
};
