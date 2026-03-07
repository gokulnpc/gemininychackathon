"use client";

import { ArrowUpRight } from "lucide-react";
import { useScrollReveal } from "@/hooks/use-scroll-reveal";

export default function HowItWorksSection() {
  const headerRef = useScrollReveal();
  const cardsRef = useScrollReveal({ threshold: 0.08 });

  return (
    <section className="bg-[#0a0a0a]" id="features">
      {/* Header */}
      <div
        ref={headerRef as React.RefObject<HTMLDivElement>}
        className="reveal py-20 px-6 text-center"
      >
        <p className="text-[10px] font-semibold tracking-widest text-white/50 uppercase mb-5 flex items-center justify-center gap-2">
          Your First Video{" "}
          <span className="bg-white text-black text-[9px] px-2 py-0.5 rounded-full uppercase tracking-wider font-bold">
            FREE
          </span>
          <span className="text-white/40">↓</span>
        </p>
        <h2
          className="text-4xl md:text-6xl font-light leading-tight text-balance"
          style={{
            background: "linear-gradient(to bottom, #FFFFFF, #999999)",
            WebkitBackgroundClip: "text",
            WebkitTextFillColor: "transparent",
          }}
        >
          Explore how Story Lab works
        </h2>
      </div>

      {/* Blue dotted divider */}
      <div className="w-full border-t border-dashed border-blue-500/40 mb-12" />

      {/* Cards area */}
      <div
        ref={cardsRef as React.RefObject<HTMLDivElement>}
        className="reveal px-6 pb-20"
      >
        <div className="max-w-6xl mx-auto">
          <div className="flex items-center justify-between mb-8">
            <p className="text-sm text-white/80">
              Transforming any idea into a short film.
            </p>
            <a
              href="/login"
              className="flex items-center gap-1 text-sm text-white/60 hover:text-white/80 transition-colors"
            >
              <ArrowUpRight size={12} />
              Try It Now
            </a>
          </div>

          {/* Cards grid */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {/* Step 01 */}
            <div
              className="card-hover rounded-2xl p-6 flex flex-col min-h-[480px] stagger-1 relative overflow-hidden"
              style={{
                border: "1.5px solid rgba(255,255,255,0.20)",
                boxShadow:
                  "inset 0 2px 0 rgba(255,255,255,0.20), inset 1px 0 0 rgba(255,255,255,0.08), 0 24px 80px rgba(0,0,0,0.7)",
              }}
            >
              <div
                className="absolute inset-0 bg-cover bg-center"
                style={{ backgroundImage: "url('/card1.avif')" }}
              />
              <div className="absolute inset-0 bg-gradient-to-b from-black/60 via-black/40 to-black/80" />
              <div className="relative z-10 flex flex-col flex-1">
                <p className="text-[96px] font-bold text-white/50 leading-none mb-1 select-none">
                  01
                </p>
                <div className="w-8 h-0.5 bg-blue-500 mb-5" />
                <h3 className="text-white font-extrabold text-xl mb-2 tracking-tight">
                  VOICE → VIDEO
                </h3>
                <p className="text-white/85 text-xs mb-6">
                  Record your idea. We handle the rest.
                </p>
                <div className="flex-1 bg-white rounded-xl p-3 mt-auto overflow-hidden">
                  <div className="flex gap-1.5 mb-3 flex-wrap">
                    {["Speech to Movie", "Text to Movie", "Presets"].map(
                      (t, i) => (
                        <span
                          key={t}
                          className={`text-[9px] px-2 py-0.5 rounded-full ${i === 0 ? "bg-pink-100 text-pink-600" : "text-gray-400 bg-gray-100"}`}
                        >
                          {t}
                        </span>
                      )
                    )}
                  </div>
                  <p className="text-[9px] text-gray-500 font-medium mb-2">
                    Record your message
                  </p>
                  <div className="bg-gray-50 rounded-lg p-2 flex items-center justify-center h-12 mb-2">
                    <div className="flex gap-0.5 items-center">
                      {[2, 4, 6, 8, 5, 3, 7, 5, 3, 6, 4, 2].map((h, i) => (
                        <div
                          key={i}
                          className="w-0.5 bg-pink-400 rounded-full"
                          style={{ height: `${h * 2}px` }}
                        />
                      ))}
                    </div>
                  </div>
                  <p className="text-[9px] text-gray-400 text-center mb-2">
                    Speak naturally about your product, idea, or story.
                  </p>
                  <div className="flex gap-2">
                    <button className="flex-1 bg-gray-800 text-white text-[9px] py-1 rounded-full">
                      Start Recording
                    </button>
                    <span className="text-[9px] text-gray-400 self-center">
                      or
                    </span>
                    <button className="flex-1 border border-gray-300 text-gray-500 text-[9px] py-1 rounded-full">
                      ↑ Upload Audio
                    </button>
                  </div>
                </div>
              </div>
            </div>

            {/* Step 02 */}
            <div
              className="card-hover rounded-2xl p-6 flex flex-col min-h-[480px] stagger-2 relative overflow-hidden"
              style={{
                border: "1.5px solid rgba(255,255,255,0.16)",
                boxShadow:
                  "inset 0 2px 0 rgba(255,255,255,0.16), inset 1px 0 0 rgba(255,255,255,0.06), 0 24px 80px rgba(0,0,0,0.72)",
              }}
            >
              <div
                className="absolute inset-0 bg-cover bg-center"
                style={{ backgroundImage: "url('/card2.jpg')" }}
              />
              <div className="absolute inset-0 bg-gradient-to-b from-black/60 via-black/40 to-black/80" />
              <div className="relative z-10 flex flex-col flex-1">
                <p className="text-[96px] font-bold text-white/50 leading-none mb-6 select-none">
                  02
                </p>
                <h3 className="text-white font-extrabold text-xl mb-2 tracking-tight">
                  TEXT → STORY
                </h3>
                <p className="text-white/85 text-xs mb-6">
                  Paste your draft. AI shapes the narrative.
                </p>
                <div className="flex-1 bg-white rounded-xl p-3 mt-auto overflow-hidden">
                  <p className="text-[9px] text-gray-500 font-medium mb-1">
                    Type your idea
                  </p>
                  <div className="bg-gray-50 rounded-lg p-2 mb-3 border border-gray-200">
                    <p className="text-[9px] text-gray-400 italic">
                      E.g, a video showcasing the marketing campaign for a
                      vegan-friendly skincare p...
                    </p>
                  </div>
                  <p className="text-[9px] text-gray-500 font-medium mb-2">
                    Ideas for you
                  </p>
                  <div className="space-y-2">
                    {[
                      "Close-up ASMR-style film of hands refilling a ceramic skincare jar from a glass pouch.",
                      "A poetic environmental brand film.",
                      "A slow cinematic commercial for a vegan probiotic skincare brand.",
                    ].map((idea, i) => (
                      <div key={i} className="flex items-start gap-1.5">
                        <span className="text-pink-400 text-[10px] mt-0.5 flex-shrink-0">
                          ✦
                        </span>
                        <p className="text-[9px] text-gray-500 leading-relaxed">
                          {idea}
                        </p>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            </div>

            {/* Step 03 */}
            <div
              className="card-hover rounded-2xl p-6 flex flex-col min-h-[480px] stagger-3 relative overflow-hidden"
              style={{
                border: "1.5px solid rgba(255,255,255,0.20)",
                boxShadow:
                  "inset 0 2px 0 rgba(255,255,255,0.20), inset 1px 0 0 rgba(255,255,255,0.07), 0 24px 80px rgba(0,0,0,0.68)",
              }}
            >
              <div
                className="absolute inset-0 bg-cover bg-center"
                style={{ backgroundImage: "url('/card3.jpg')" }}
              />
              <div className="absolute inset-0 bg-gradient-to-b from-black/60 via-black/40 to-black/80" />
              <div className="relative z-10 flex flex-col flex-1">
                <p className="text-[96px] font-bold text-white/50 leading-none mb-6 select-none">
                  03
                </p>
                <h3 className="text-white font-extrabold text-xl mb-2 tracking-tight">
                  PRESET → MOVIE
                </h3>
                <p className="text-white/85 text-xs mb-6">
                  Save time with our Pre-built Presetss.
                </p>
                <div className="flex-1 bg-white rounded-xl p-3 mt-auto overflow-hidden">
                  <div className="flex gap-1.5 mb-3 flex-wrap">
                    {["Speech to Movie", "Text to Movie", "Presets"].map(
                      (t, i) => (
                        <span
                          key={t}
                          className={`text-[9px] px-2 py-0.5 rounded-full ${i === 2 ? "bg-pink-100 text-pink-600" : "text-gray-400 bg-gray-100"}`}
                        >
                          {t}
                        </span>
                      )
                    )}
                  </div>
                  <div className="space-y-2.5">
                    {[
                      {
                        title: "Horror stories",
                        desc: "Horror stories that give you goosebumps",
                      },
                      {
                        title: "History",
                        desc: "Viral videos about history spanning from ancient times to the modern day",
                      },
                      {
                        title: "True Crime",
                        desc: "Viral videos about true crime stories",
                      },
                      {
                        title: "Stoic Motivation",
                        desc: "Short videos about stoic philosophy and life lessons",
                      },
                      {
                        title: "Marketing & Business",
                        desc: "Product launches, business tips, and growth strategies",
                      },
                    ].map((preset, i) => (
                      <div
                        key={preset.title}
                        className={`${i < 4 ? "border-b border-gray-100" : ""} pb-2`}
                      >
                        <p className="text-[9px] font-semibold text-gray-700">
                          {preset.title}
                        </p>
                        <p className="text-[8px] text-gray-400 leading-relaxed">
                          {preset.desc}
                        </p>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
