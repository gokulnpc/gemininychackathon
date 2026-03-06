"use client";

import React, { useEffect, useRef } from "react";
import TextReveal from "./TextReveal";

interface HeroProps {
  onMenuClick: () => void;
}

export default function Hero({ onMenuClick }: HeroProps) {
  const heroImgRef = useRef<HTMLImageElement>(null);

  useEffect(() => {
    const handleScroll = () => {
      if (heroImgRef.current) {
        const scrollPosition = window.scrollY;
        if (scrollPosition < window.innerHeight) {
          heroImgRef.current.style.transform = `translateY(${
            scrollPosition * 0.4
          }px)`;
        }
      }
    };

    window.addEventListener("scroll", handleScroll);
    return () => window.removeEventListener("scroll", handleScroll);
  }, []);

  return (
    <header className="relative w-full h-screen overflow-hidden bg-black text-white">
      {/* Background Image with Parallax */}
      <div className="absolute inset-0 overflow-hidden">
        <img
          ref={heroImgRef}
          src="https://hoirqrkdgbmvpwutwuwj.supabase.co/storage/v1/object/public/assets/assets/917d6f93-fb36-439a-8c48-884b67b35381_1600w.jpg"
          alt="Mossy Rocks"
          className="w-full h-[120%] object-cover opacity-80"
          style={{ willChange: "transform" }}
        />
      </div>

      {/* Navigation */}
      <nav className="absolute top-0 left-0 w-full px-6 py-6 md:px-12 md:py-8 flex justify-between items-center z-10 text-lg font-medium tracking-tight">
        <div className="reveal-on-load">
          <span style={{ color: "#ff5a1f" }}>Content</span> Factory
        </div>
        <button
          onClick={onMenuClick}
          className="cursor-pointer hover:opacity-70 transition-opacity reveal-on-load"
        >
          Menu
        </button>
      </nav>

      {/* Main Logo Overlay */}
      <div className="absolute bottom-0 left-0 w-full flex justify-center items-end pb-12 z-10 pointer-events-none">
        <h1 className="text-[15vw] leading-[0.8] tracking-tighter font-normal select-none flex justify-center gap-[0.2em]">
          <TextReveal className="text-[#ff5a1f]">Content</TextReveal>
          <TextReveal>Factory</TextReveal>
        </h1>
      </div>
    </header>
  );
}
