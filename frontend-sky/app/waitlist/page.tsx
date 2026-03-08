"use client";

import { useState } from "react";
import Image from "next/image";
import Link from "next/link";
import { ArrowUpRight, Check, Sliders } from "lucide-react";

export default function WaitlistPage() {
  const [email, setEmail] = useState("");
  const [submitted, setSubmitted] = useState(false);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!email.trim()) return;
    setSubmitted(true);
  };

  return (
    <main>
      {/* ── Navbar ── */}
      <header className="fixed top-0 left-0 right-0 z-50 flex items-center justify-between px-6 py-4 border-b border-white/15">
        <Link href="/">
          <Image
            src="/logo_StoryLab_sky.png"
            alt="Story Lab"
            width={140}
            height={32}
            className="h-8 w-auto"
          />
        </Link>

        <nav className="hidden md:flex items-center gap-6 text-xs font-medium text-white/80">
          <Link
            href="/#features"
            className="nav-link hover:text-white transition-colors"
          >
            FEATURES
          </Link>
          <Link
            href="/"
            className="nav-link hover:text-white transition-colors"
          >
            HOME
          </Link>
        </nav>

        <Link
          href="/login"
          className="hidden md:flex items-center gap-1 text-white text-xs font-medium hover:opacity-80 transition-opacity btn-scale"
        >
          Sign In/ Up
          <ArrowUpRight size={14} />
        </Link>
      </header>

      {/* ── Hero ── */}
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

          {/* Center column: headline + waitlist form */}
          <div className="flex-1 flex flex-col items-center justify-center px-6 text-center">
            {/* Early access badge */}
            <div className="hero-chips flex items-center gap-2 bg-white/60 backdrop-blur-md border border-white/20 rounded-full px-4 py-1.5 mb-6">
              <span className="w-2 h-2 rounded-full bg-[#3a829b] animate-pulse" />
              <span className="text-[#414141] text-xs font-medium tracking-wide">
                Early Access — Limited Spots
              </span>
            </div>

            {/* Headline */}
            <h1 className="hero-title text-5xl sm:text-6xl md:text-7xl lg:text-8xl font-bold text-white leading-[1.05] tracking-tight text-balance text-center">
              Join the Waitlist
            </h1>

            {/* Subtitle */}
            <p className="hero-cta text-white/60 text-sm sm:text-base mt-5 max-w-md leading-relaxed">
              Be the first to know when we launch. Join our community of early
              supporters and get exclusive updates.
            </p>

            {/* Waitlist form */}
            <div className="hero-cta mt-8 sm:mt-10 w-full max-w-md">
              {!submitted ? (
                <form onSubmit={handleSubmit} className="flex gap-2">
                  <input
                    type="email"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    placeholder="Enter your email"
                    required
                    className="flex-1 bg-white/10 backdrop-blur-md border border-white/25 text-white text-sm px-5 py-3.5 rounded-full placeholder:text-white/40 focus:outline-none focus:border-white/50 focus:ring-1 focus:ring-white/20 transition-all"
                  />
                  <button
                    type="submit"
                    className="btn-scale bg-white/15 backdrop-blur-md border border-white/25 text-white font-medium px-7 py-3.5 rounded-full hover:bg-white/25 transition-all text-sm shrink-0"
                  >
                    Join Waitlist
                  </button>
                </form>
              ) : (
                <div className="flex items-center justify-center gap-3 bg-white/10 backdrop-blur-md border border-white/25 rounded-full px-6 py-3.5">
                  <div className="w-7 h-7 rounded-full bg-white/20 flex items-center justify-center">
                    <Check size={14} className="text-white" />
                  </div>
                  <div className="text-left">
                    <p className="text-white text-sm font-medium">
                      You&apos;re on the list!
                    </p>
                    <p className="text-white/50 text-xs">
                      We&apos;ll notify you when early access opens.
                    </p>
                  </div>
                </div>
              )}
              <p className="text-white/30 text-xs mt-3">
                No spam. Unsubscribe anytime.
              </p>
            </div>
          </div>

          {/* Feature tags — staggered rows */}
          <div className="hero-tags flex flex-col gap-2.5 items-start ml-2 sm:ml-8 md:ml-0 md:absolute md:left-8 lg:left-12 md:bottom-[14%]">
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
      </section>
    </main>
  );
}
