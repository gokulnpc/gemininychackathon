"use client";

import React from "react";
import Link from "next/link";
import TextReveal from "./TextReveal";

export default function Footer() {
  return (
    <footer className="bg-black text-white pt-24 px-6 md:px-12 pb-6 relative overflow-hidden">
      <div className="flex flex-col md:flex-row justify-between items-start mb-32 md:mb-48 max-w-[1800px] mx-auto">
        <div className="mb-12 md:mb-0">
          <TextReveal
            as="h3"
            className="text-3xl md:text-4xl tracking-tight mb-8"
          >
            Relax. We got you.
          </TextReveal>
          <Link
            href="/login"
            className="inline-block border border-white/30 rounded-full px-8 py-4 hover:bg-white hover:text-black transition-colors text-sm font-medium"
          >
            Get started — it&apos;s free
          </Link>
        </div>

        <div className="flex gap-16 md:gap-32 text-lg font-medium leading-loose">
          <ul className="space-y-1">
            <li>
              <Link href="#" className="hover:text-gray-400">
                Home
              </Link>
            </li>
            <li>
              <Link href="#" className="hover:text-gray-400">
                How it works
              </Link>
            </li>
            <li>
              <Link href="#" className="hover:text-gray-400">
                Use Cases
              </Link>
            </li>
            <li>
              <Link href="#" className="hover:text-gray-400">
                Pricing
              </Link>
            </li>
            <li>
              <Link href="#" className="hover:text-gray-400">
                Contact
              </Link>
            </li>
          </ul>
          <ul className="space-y-1">
            <li>
              <Link href="#" className="hover:text-gray-400 flex items-center gap-1">
                X <span className="text-[10px] align-top">↗</span>
              </Link>
            </li>
            <li>
              <Link href="#" className="hover:text-gray-400 flex items-center gap-1">
                Instagram <span className="text-[10px] align-top">↗</span>
              </Link>
            </li>
            <li>
              <Link href="#" className="hover:text-gray-400 flex items-center gap-1">
                Tiktok <span className="text-[10px] align-top">↗</span>
              </Link>
            </li>
          </ul>
        </div>
      </div>

      <div className="flex flex-col md:flex-row justify-between items-end text-sm text-gray-400 mb-6 max-w-[1800px] mx-auto">
        <div className="mb-4 md:mb-0">
          <p>AI-powered · Video-first · Creator-ready</p>
        </div>
        <div className="flex gap-8">
          <Link href="#" className="hover:text-white">
            tien.nguyen@columbia.edu
          </Link>
          <span>©2026 | Tech @ NYU Startup Hackathon</span>
        </div>
      </div>

      <div className="w-full flex justify-center items-end">
        <h1 className="text-[15vw] leading-[0.7] tracking-tighter font-normal text-white select-none flex justify-center gap-[0.2em]">
          <TextReveal className="text-[#ff5a1f]">Content</TextReveal>
          <TextReveal>Factory</TextReveal>
        </h1>
      </div>
    </footer>
  );
}
