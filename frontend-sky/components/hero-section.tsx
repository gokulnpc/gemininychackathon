"use client";

import Image from "next/image";
import Link from "next/link";
import { ChevronDown, Sliders } from "lucide-react";

export default function HeroSection() {
  return (
    <section className="relative left-1/2 right-1/2 -ml-[50vw] -mr-[50vw] w-screen max-w-none min-h-screen overflow-hidden bg-[#1a2a3a] flex flex-col">
      {/* Background video */}
      <video
        autoPlay
        loop
        muted
        playsInline
        className="absolute inset-0 w-full h-full object-cover pointer-events-none"
      >
        <source src="/Background_Video.mp4" type="video/mp4" />
      </video>
      <div className="absolute inset-0 bg-black/30 pointer-events-none" />

      {/* Main content area */}
      <div className="relative flex-1 flex flex-col pt-24 pb-10">
        {/* Personalization — left-center */}
        <div
          className="hero-chips hidden md:block absolute left-8 lg:left-12 top-[42%] -translate-y-1/2"
          style={{ animation: "floatChip 5.2s ease-in-out infinite" }}
        >
          <div className="flex items-center gap-2 bg-white/60 backdrop-blur-md border border-white/20 rounded-full px-4 py-2 shadow-sm hover:bg-white/70 transition-colors cursor-default">
            <Sliders size={14} className="text-[#414141]" />
            <span className="text-[#414141] text-xs font-medium tracking-wide">
              Personalization
            </span>
          </div>
        </div>

        {/* Creativity chip + description — top right */}
        <div className="hero-chips hidden md:flex flex-col gap-3 absolute right-8 lg:right-16 top-[18%]">
          <div
            className="flex items-center gap-2 bg-white/60 backdrop-blur-md border border-white/20 rounded-full px-4 py-2 self-start shadow-sm hover:bg-white/70 transition-colors cursor-default"
            style={{ animation: "floatChip 4.6s ease-in-out infinite 0.4s" }}
          >
            <Image
              src="/creativity.svg"
              alt="Creativity"
              width={14}
              height={14}
            />
            <span className="text-[#414141] text-xs font-medium tracking-wide">
              Creativity
            </span>
          </div>
          <p className="text-white/70 text-sm max-w-[360px] leading-relaxed">
            Speak your idea, type a story, or choose a preset. Our AI agent
            crafts it into a polished short film in minutes — movie-making made
            simple for everyone.
          </p>
        </div>

        {/* Speed chip — mid right */}
        <div
          className="hero-chips hidden md:block absolute right-8 lg:right-16 top-[62%]"
          style={{ animation: "floatChip 6s ease-in-out infinite 1.1s" }}
        >
          <div className="flex items-center gap-2 bg-white/60 backdrop-blur-md border border-white/20 rounded-full px-4 py-2 shadow-sm hover:bg-white/70 transition-colors cursor-default">
            <Image src="/speed.svg" alt="Speed" width={14} height={14} />
            <span className="text-[#414141] text-xs font-medium tracking-wide">
              Speed
            </span>
          </div>
        </div>

        {/* Center column: headline + CTA */}
        <div className="flex-1 flex flex-col items-center justify-center px-6 text-center">
          {/* Headline */}
          <h1 className="hero-title text-5xl sm:text-6xl md:text-7xl lg:text-8xl font-bold text-white leading-[1.05] tracking-tight text-balance text-center">
            Your Story.
            <br />
            One Click Away.
          </h1>

          {/* CTA button */}
          <div className="hero-cta mt-8 sm:mt-10">
            <Link
              href="/login"
              className="btn-scale flex items-center gap-2 bg-white/15 backdrop-blur-md border border-white/25 text-white font-medium px-7 py-3.5 rounded-full hover:bg-white/25 transition-all text-base"
            >
              Get Started - It&apos;s Free
            </Link>
          </div>

          {/* Feature tags — staggered rows */}
          <div className="hero-tags mt-10 sm:mt-12 flex flex-col gap-2.5 items-start self-start md:self-auto md:items-start ml-2 sm:ml-8 md:ml-0 md:absolute md:left-8 lg:left-12 md:bottom-[14%]">
            {/* Row 1: Text-to-video + */}
            <div
              className="flex items-center gap-2"
              style={{ animation: "floatChip 5s ease-in-out infinite 0s" }}
            >
              <span className="bg-[#111111]/50 backdrop-blur-sm text-white text-xs font-medium px-4 py-1.5 rounded-full border border-white hover:border-white/80 transition-colors cursor-default">
                Text-to-video
              </span>
              <span className="bg-[#111111]/50 backdrop-blur-sm text-white text-xs w-6 h-6 flex items-center justify-center rounded-full border border-white hover:border-white/80 transition-colors cursor-default font-bold">
                +
              </span>
            </div>
            {/* Row 2: + Speech-to-video — indented right */}
            <div
              className="flex items-center gap-2 ml-10"
              style={{ animation: "floatChip 5.8s ease-in-out infinite 0.7s" }}
            >
              <span className="bg-[#111111]/50 backdrop-blur-sm text-white text-xs w-6 h-6 flex items-center justify-center rounded-full border border-white hover:border-white/80 transition-colors cursor-default font-bold">
                +
              </span>
              <span className="bg-[#111111]/50 backdrop-blur-sm text-white text-xs font-medium px-4 py-1.5 rounded-full border border-white hover:border-white/80 transition-colors cursor-default">
                Speech-to-video
              </span>
            </div>
            {/* Row 3: Pre-built Presets + */}
            <div
              className="flex items-center gap-2"
              style={{ animation: "floatChip 4.4s ease-in-out infinite 1.4s" }}
            >
              <span className="bg-[#111111]/50 backdrop-blur-sm text-white text-xs font-medium px-4 py-1.5 rounded-full border border-white hover:border-white/80 transition-colors cursor-default">
                Pre-built Presets
              </span>
              <span className="bg-[#111111]/50 backdrop-blur-sm text-white text-xs w-6 h-6 flex items-center justify-center rounded-full border border-white hover:border-white/80 transition-colors cursor-default font-bold">
                +
              </span>
            </div>
          </div>
        </div>
      </div>

      {/* Bottom bar: scroll mouse centered */}
      <div className="relative pb-6 px-6 flex items-end justify-center">
        {/* Scrolling mouse indicator */}
        <div className="flex flex-col items-center gap-1.5">
          <div className="w-7 h-11 rounded-full border-2 border-white/40 flex items-start justify-center pt-2">
            <div className="w-1.5 h-2.5 rounded-full bg-white/60 wheel-dot" />
          </div>
          <ChevronDown size={14} className="text-white/50 chevron-pulse" />
        </div>
      </div>
    </section>
  );
}
