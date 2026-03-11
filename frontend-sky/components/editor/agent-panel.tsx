"use client";

import type { RefObject } from "react";
import { Loader2, Mic, MicOff, Send, Sparkles, X } from "lucide-react";
import { cn } from "@/lib/utils";
import type { AgentMessage } from "@/components/editor/types";

interface AgentPanelProps {
  agentPanelOpen: boolean;
  agentMessages: AgentMessage[];
  agentInput: string;
  agentLoading: boolean;
  isVoiceActive: boolean;
  agentBottomRef: RefObject<HTMLDivElement | null>;
  setAgentPanelOpen: (open: boolean) => void;
  setAgentInput: (value: string) => void;
  sendAgentInstruction: (instruction: string) => void;
  startVoiceEdit: () => void | Promise<void>;
}

export function AgentPanel({
  agentPanelOpen,
  agentMessages,
  agentInput,
  agentLoading,
  isVoiceActive,
  agentBottomRef,
  setAgentPanelOpen,
  setAgentInput,
  sendAgentInstruction,
  startVoiceEdit,
}: AgentPanelProps) {
  if (!agentPanelOpen) return null;

  const recentActions = agentMessages
    .flatMap((message) => message.actions ?? [])
    .filter((action, index, actions) => actions.indexOf(action) === index)
    .slice(-6)
    .reverse();

  return (
    <div className="flex h-full w-[340px] flex-col border-l border-white/10 bg-[#12141b]">
      <div className="flex items-center justify-between border-b border-white/10 px-4 py-3">
        <div className="flex items-center gap-2">
          <div className="flex h-8 w-8 items-center justify-center rounded-full bg-[#7c3aed]">
            <Sparkles className="h-4 w-4 text-white" />
          </div>
          <div>
            <p className="text-sm font-semibold text-white">AI Copilot</p>
            <p className="text-xs text-white/45">Timeline-first live editing</p>
          </div>
        </div>
        <button
          type="button"
          onClick={() => setAgentPanelOpen(false)}
          className="text-white/40 transition-colors hover:text-white"
        >
          <X className="h-4 w-4" />
        </button>
      </div>

      <div className="flex-1 space-y-3 overflow-y-auto p-3">
        {recentActions.length > 0 && (
          <div className="rounded-2xl border border-white/10 bg-white/[0.03] p-3">
            <p className="text-[11px] font-medium uppercase tracking-[0.18em] text-white/35">Applied Changes</p>
            <div className="mt-2 flex flex-wrap gap-1.5">
              {recentActions.map((action) => (
                <span
                  key={action}
                  className="rounded-full border border-emerald-400/20 bg-emerald-400/10 px-2 py-1 text-[11px] text-emerald-200"
                >
                  {action}
                </span>
              ))}
            </div>
          </div>
        )}

        {agentMessages.map((msg) => (
          <div
            key={msg.id}
            className={cn("flex flex-col gap-1", msg.role === "user" ? "items-end" : "items-start")}
          >
            <div
              className={cn(
                "max-w-[90%] rounded-2xl px-3 py-2 text-sm leading-relaxed",
                msg.role === "user"
                  ? "rounded-br-sm bg-[#7c3aed] text-white"
                  : msg.isError
                    ? "rounded-bl-sm border border-red-500/20 bg-red-900/30 text-red-300"
                    : "rounded-bl-sm bg-white/8 text-white/90"
              )}
            >
              {msg.isThinking && !msg.text ? (
                <div className="flex items-center gap-2 text-white/50">
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  <span>Thinking...</span>
                </div>
              ) : (
                msg.text || <span className="italic text-white/30">Processing...</span>
              )}
            </div>
            {msg.actions && msg.actions.length > 0 && (
              <div className="flex max-w-[90%] flex-wrap gap-1">
                {msg.actions.map((action, index) => (
                  <span
                    key={`${msg.id}-${index}`}
                    className="rounded-full border border-[#7c3aed]/30 bg-[#7c3aed]/20 px-2 py-0.5 text-[10px] font-mono text-[#a78bfa]"
                  >
                    {action}
                  </span>
                ))}
              </div>
            )}
          </div>
        ))}
        <div ref={agentBottomRef} />
      </div>

      <div className="grid grid-cols-2 gap-1.5 border-t border-white/10 px-3 py-2">
        {[
          "Add B-rolls",
          "Add Zooms",
          "Change Theme",
          "Add Music",
        ].map((action) => (
          <button
            key={action}
            type="button"
            onClick={() => sendAgentInstruction(action)}
            disabled={agentLoading}
            className="rounded-lg border border-white/10 bg-white/5 px-2 py-1.5 text-xs text-white/70 transition-colors hover:bg-white/10 hover:text-white disabled:cursor-not-allowed disabled:opacity-40"
          >
            {action}
          </button>
        ))}
      </div>

      <div className="border-t border-white/10 p-3">
        <div className="rounded-xl border border-white/10 bg-white/5 px-3 py-2 transition-colors focus-within:border-[#7c3aed]/50">
          <textarea
            value={agentInput}
            onChange={(event) => setAgentInput(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault();
                sendAgentInstruction(agentInput);
              }
            }}
            placeholder="Describe your edit..."
            rows={2}
            className="w-full resize-none bg-transparent text-sm leading-relaxed text-white placeholder-white/30 focus:outline-none"
          />
          <div className="mt-2 flex items-center justify-between">
            <p className="text-[11px] text-white/35">
              Live edits update the timeline immediately. Export renders the latest saved state.
            </p>
            <div className="flex items-center gap-1.5">
              <button
                type="button"
                onClick={() => {
                  void startVoiceEdit();
                }}
                className={cn(
                  "rounded-lg p-1.5 transition-colors",
                  isVoiceActive
                    ? "animate-pulse bg-red-500/20 text-red-400"
                    : "text-white/40 hover:bg-white/10 hover:text-white"
                )}
              >
                {isVoiceActive ? <MicOff className="h-4 w-4" /> : <Mic className="h-4 w-4" />}
              </button>
              <button
                type="button"
                onClick={() => sendAgentInstruction(agentInput)}
                disabled={!agentInput.trim() || agentLoading}
                className="rounded-lg bg-[#7c3aed] p-1.5 text-white transition-colors hover:bg-[#6d28d9] disabled:cursor-not-allowed disabled:opacity-40"
              >
                {agentLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
