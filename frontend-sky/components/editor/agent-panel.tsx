"use client";

import type { RefObject } from "react";
import { Loader2, Mic, MicOff, Send, Sparkles, X } from "lucide-react";
import { cn } from "@/lib/utils";
import type { AgentMessage, CreativeBlock, CreativePreviewOption, EditProposal } from "@/components/editor/types";

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
  confirmProposal: (proposal: EditProposal) => void;
  rejectProposal: (proposal: EditProposal) => void;
  revertLastEdit: () => void;
  hasUndo: boolean;
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
  confirmProposal,
  rejectProposal,
  revertLastEdit,
  hasUndo,
}: AgentPanelProps) {
  if (!agentPanelOpen) return null;

  const confirmedActions = agentMessages
    .filter((m) => m.proposal?.state === "confirmed")
    .map((m) => m.proposal!.summary)
    .slice(-6)
    .reverse();

  const recentActions = confirmedActions.length > 0
    ? confirmedActions
    : agentMessages
        .flatMap((message) => message.actions ?? [])
        .filter((action, index, actions) => actions.indexOf(action) === index)
        .slice(-6)
        .reverse();

  return (
    <div className="flex h-full w-[340px] flex-col border-l border-editor-border bg-editor-surface">
      <div className="flex items-center justify-between border-b border-editor-border px-4 py-3">
        <div className="flex items-center gap-2">
          <div className="flex h-8 w-8 items-center justify-center rounded-full bg-primary/20">
            <Sparkles className="h-4 w-4 text-primary-foreground" />
          </div>
          <div>
            <p className="text-sm font-semibold text-editor-text">AI Copilot</p>
            <p className="text-xs text-editor-text-muted">Live edits · Creative preview · Screen analysis</p>
          </div>
        </div>
        <button
          type="button"
          onClick={() => setAgentPanelOpen(false)}
          className="text-editor-text-dim transition-colors hover:text-editor-text"
        >
          <X className="h-4 w-4" />
        </button>
      </div>

      <div className="editor-scroll flex-1 space-y-3 overflow-y-auto p-3">
        {recentActions.length > 0 && (
          <div className="rounded-2xl border border-editor-border bg-editor-surface-raised p-3">
            <p className="text-[11px] font-medium uppercase tracking-[0.18em] text-editor-text-dim">Applied Changes</p>
            <div className="mt-2 flex flex-wrap gap-1.5">
              {recentActions.map((action) => (
                <span
                  key={action}
                  className="rounded-full border border-primary/30 bg-primary/15 px-2 py-1 text-[11px] text-editor-text"
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
                  ? "rounded-br-sm bg-primary text-primary-foreground"
                  : msg.isError
                    ? "rounded-bl-sm border border-destructive/20 bg-destructive/20 text-destructive-foreground"
                    : msg.isInspection
                      ? "rounded-bl-sm border border-amber-500/20 bg-amber-500/5 text-foreground/90"
                      : "rounded-bl-sm bg-editor-surface-raised text-foreground/90",
              )}
            >
              {msg.isInspection && !msg.isThinking && (
                <p className="mb-1 text-[10px] font-medium uppercase tracking-widest text-amber-400/70">
                  Screen analysis
                </p>
              )}
              {msg.isThinking && !msg.text ? (
                <div className="flex items-center gap-2 text-muted-foreground">
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  <span>Thinking...</span>
                </div>
              ) : (
                msg.text || <span className="italic text-muted-foreground">Processing...</span>
              )}
              {msg.previewOptions && msg.previewOptions.length > 0 && (
                <div className="mt-2">
                  <p className="mb-1.5 text-[10px] font-medium uppercase tracking-widest text-editor-text-dim">
                    {msg.previewOptions.length} style option{msg.previewOptions.length !== 1 ? "s" : ""}
                  </p>
                  <div className="flex flex-col gap-2">
                    {msg.previewOptions.map((opt: CreativePreviewOption) => (
                      <div key={opt.option_id} className="group overflow-hidden rounded-lg border border-editor-border">
                        <div className="relative">
                          <img
                            src={`data:${opt.image.mime_type ?? "image/png"};base64,${opt.image.content}`}
                            alt={opt.title}
                            className="w-full object-cover"
                          />
                          <div className="absolute inset-0 flex items-end bg-gradient-to-t from-black/60 to-transparent p-2">
                            <span className="text-xs font-semibold text-white">{opt.title}</span>
                          </div>
                        </div>
                        <button
                          type="button"
                          onClick={() => sendAgentInstruction(`Use the "${opt.title}" style (option ${opt.index + 1} from the last preview)`)}
                          className="w-full border-t border-editor-border bg-editor-surface-raised py-1.5 text-xs text-foreground/70 transition-colors hover:bg-editor-surface hover:text-foreground"
                        >
                          Use this style →
                        </button>
                      </div>
                    ))}
                  </div>
                </div>
              )}
              {msg.creativeBlocks && msg.creativeBlocks.length > 0 && (
                <div className="mt-2 flex flex-col gap-2">
                  {msg.creativeBlocks.filter((b: CreativeBlock) => b.type === "image").map((block: CreativeBlock, i: number) => (
                    <div key={i} className="group relative overflow-hidden rounded-lg border border-editor-border">
                      <img
                        src={`data:${block.mime_type ?? "image/png"};base64,${block.content}`}
                        alt={`Preview ${i + 1}`}
                        className="w-full object-cover"
                      />
                      <button
                        type="button"
                        onClick={() => sendAgentInstruction(`Apply the style from preview ${i + 1}`)}
                        className="absolute inset-x-0 bottom-0 bg-black/70 py-1.5 text-xs font-medium text-white opacity-0 transition-opacity group-hover:opacity-100"
                      >
                        Use this style →
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </div>
            {msg.actions && msg.actions.length > 0 && !msg.proposal && (
              <div className="flex max-w-[90%] flex-wrap gap-1">
                {msg.actions.map((action, index) => (
                  <span
                    key={`${msg.id}-${index}`}
                    className="rounded-full border border-primary/30 bg-primary/15 px-2 py-0.5 text-[10px] font-mono text-editor-accent-glow"
                  >
                    {action}
                  </span>
                ))}
              </div>
            )}
            {msg.proposal && (
              <div
                className={cn(
                  "mt-1 w-[90%] rounded-xl border p-3",
                  msg.proposal.state === "pending"
                    ? "border-primary/30 bg-editor-surface-raised"
                    : msg.proposal.state === "confirmed"
                      ? "border-emerald-500/30 bg-emerald-500/10"
                      : "border-editor-border bg-editor-surface opacity-60"
                )}
              >
                {msg.proposal.state === "pending" && (
                  <>
                    <p className="mb-2 text-[11px] font-medium uppercase tracking-[0.15em] text-editor-text-dim">
                      {msg.proposal.commands.length} suggested change{msg.proposal.commands.length !== 1 ? "s" : ""}
                    </p>
                    <ul className="mb-3 space-y-1">
                      {msg.proposal.commands.map((cmd, i) => (
                        <li key={i} className="text-xs font-mono text-foreground/70">
                          {cmd.kind.replace(/_/g, " ")}
                          {Object.keys(cmd.args).length > 0 && (
                            <span className="ml-1 text-editor-text-dim">
                              ({Object.values(cmd.args).filter(Boolean).join(", ")})
                            </span>
                          )}
                        </li>
                      ))}
                    </ul>
                    <div className="flex gap-2">
                      <button
                        type="button"
                        onClick={() => confirmProposal(msg.proposal!)}
                        disabled={agentLoading}
                        className="flex-1 rounded-lg bg-primary py-1.5 text-xs font-semibold text-primary-foreground disabled:opacity-40"
                      >
                        Apply
                      </button>
                      <button
                        type="button"
                        onClick={() => rejectProposal(msg.proposal!)}
                        disabled={agentLoading}
                        className="flex-1 rounded-lg border border-editor-border py-1.5 text-xs text-foreground/70 hover:border-primary/30"
                      >
                        Discard
                      </button>
                    </div>
                  </>
                )}
                {msg.proposal.state === "confirmed" && (
                  <p className="text-xs font-medium text-emerald-300">Applied</p>
                )}
                {msg.proposal.state === "rejected" && (
                  <p className="text-xs italic text-editor-text-dim">Discarded</p>
                )}
              </div>
            )}
          </div>
        ))}
        <div ref={agentBottomRef} />
      </div>

      <div className="grid grid-cols-2 gap-1.5 border-t border-editor-border px-3 py-2">
        {["Show me horror looks", "Change caption style", "Add hook title", "Change music mood"].map((action) => (
          <button
            key={action}
            type="button"
            onClick={() => sendAgentInstruction(action)}
            disabled={agentLoading}
            className="rounded-lg border border-editor-border bg-editor-surface-raised px-2 py-1.5 text-xs text-foreground/70 transition-colors hover:border-primary/45 hover:bg-editor-surface hover:text-foreground disabled:cursor-not-allowed disabled:opacity-40"
          >
            {action}
          </button>
        ))}
      </div>

      {hasUndo && (
        <div className="border-t border-editor-border px-3 py-2">
          <button
            type="button"
            onClick={revertLastEdit}
            className="w-full rounded-lg border border-amber-500/30 bg-amber-500/10 py-1.5 text-xs font-medium text-amber-200 hover:bg-amber-500/20"
          >
            Undo last edit
          </button>
        </div>
      )}

      <div className="border-t border-editor-border p-3">
        <div className="rounded-xl border border-editor-border bg-editor-surface-raised px-3 py-2 transition-colors focus-within:border-primary/55">
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
            className="w-full resize-none bg-transparent text-sm leading-relaxed text-foreground placeholder-muted-foreground focus:outline-none"
          />
          <div className="mt-2 flex items-center justify-between">
            <p className="text-[11px] text-editor-text-dim">
              Live edits update the timeline immediately.
            </p>
            <div className="flex items-center gap-1.5">
              <button
                type="button"
                onClick={() => { void startVoiceEdit(); }}
                className={cn(
                  "rounded-lg p-1.5 transition-colors",
                  isVoiceActive
                    ? "animate-pulse bg-destructive/20 text-destructive"
                    : "text-editor-text-dim hover:bg-muted hover:text-foreground"
                )}
              >
                {isVoiceActive ? <MicOff className="h-4 w-4" /> : <Mic className="h-4 w-4" />}
              </button>
              <button
                type="button"
                onClick={() => sendAgentInstruction(agentInput)}
                disabled={!agentInput.trim() || agentLoading}
                className="rounded-lg bg-primary p-1.5 text-primary-foreground transition-colors hover:bg-primary/80 disabled:cursor-not-allowed disabled:opacity-40"
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
