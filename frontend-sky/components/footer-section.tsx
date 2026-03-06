"use client";

import { ArrowUpRight } from "lucide-react";
import Link from "next/link";
import { useScrollReveal } from "@/hooks/use-scroll-reveal";

export default function FooterSection() {
  const ref = useScrollReveal();

  return (
    <footer className="bg-black relative overflow-hidden">
      {/* Giant watermark text */}
      <div className="absolute inset-0 flex items-center justify-center pointer-events-none select-none overflow-hidden">
        <span
          className="text-[12vw] font-black tracking-tight whitespace-nowrap leading-none opacity-90"
          style={{
            background: "linear-gradient(to bottom, #FFFFFF, #999999)",
            WebkitBackgroundClip: "text",
            WebkitTextFillColor: "transparent",
          }}
          aria-hidden="true"
        >
          STORY LAB
        </span>
      </div>

      <div
        ref={ref as React.RefObject<HTMLDivElement>}
        className="reveal relative z-10 px-8 md:px-12 pt-16 pb-10"
      >
        {/* Top section */}
        <div className="flex flex-col md:flex-row justify-between items-start gap-10">
          {/* Left: CTA */}
          <div className="flex flex-col gap-6">
            <p className="text-white/60 text-base font-medium">
              Ready to build?
            </p>
            <Link href="/login" className="btn-scale bg-white/10 border border-white/20 text-white text-sm font-medium px-5 py-2.5 rounded-full hover:bg-white/20 transition-colors w-fit inline-block">
              Get Started
            </Link>

            <nav className="flex flex-col gap-2 mt-4">
              <Link
                href="#"
                className="text-white/40 text-sm hover:text-white transition-colors"
              >
                Home
              </Link>
              <Link
                href="#"
                className="text-white/40 text-sm hover:text-white transition-colors"
              >
                Create
              </Link>
              <Link
                href="#"
                className="text-white/40 text-sm hover:text-white transition-colors"
              >
                Dashboard
              </Link>
            </nav>
          </div>

          {/* Right: Social links */}
          <div className="flex flex-col gap-3 text-right">
            <a
              href="https://x.com"
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center gap-1 text-white/40 text-sm hover:text-white transition-colors justify-end"
            >
              X <ArrowUpRight size={12} />
            </a>
            <a
              href="https://instagram.com"
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center gap-1 text-white/40 text-sm hover:text-white transition-colors justify-end"
            >
              Instagram <ArrowUpRight size={12} />
            </a>
            <a
              href="https://linkedin.com"
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center gap-1 text-white/40 text-sm hover:text-white transition-colors justify-end"
            >
              LinkedIn <ArrowUpRight size={12} />
            </a>
          </div>
        </div>

        {/* Bottom bar */}
        <div className="mt-24 pt-6 border-t border-white/10 flex flex-col md:flex-row justify-between items-center gap-2">
          <p className="text-white/25 text-xs">
            AI-powered · Movie-first · Built for everyone
          </p>
          <p className="text-white/25 text-xs">©2026 | New York City</p>
        </div>
      </div>
    </footer>
  );
}
