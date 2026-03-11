import { cn } from "@/lib/utils";

export function StatusPill({ status }: { status: string }) {
  const config: Record<string, { label: string; className: string }> = {
    queued: { label: "Queued", className: "bg-blue-500/20 text-blue-300 border-blue-500/30" },
    generating_script: { label: "Scripting", className: "bg-blue-500/20 text-blue-300 border-blue-500/30" },
    script_ready: { label: "Script Ready", className: "bg-yellow-500/20 text-yellow-300 border-yellow-500/30" },
    generating_video: { label: "Generating", className: "bg-orange-500/20 text-orange-300 border-orange-500/30" },
    in_progress: { label: "Generating", className: "bg-orange-500/20 text-orange-300 border-orange-500/30" },
    completed: { label: "Completed", className: "bg-green-500/20 text-green-300 border-green-500/30" },
    failed: { label: "Failed", className: "bg-red-500/20 text-red-300 border-red-500/30" },
  };
  const { label, className } = config[status] ?? config.failed;
  return (
    <span className={cn("text-[10px] px-2 py-0.5 rounded-full border font-medium whitespace-nowrap", className)}>
      {label}
    </span>
  );
}
