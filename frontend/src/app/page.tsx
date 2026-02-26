"use client";

import React, { useState } from "react";
import FullScreenMenu from "@/components/FullScreenMenu";
import Hero from "@/components/Hero";
import Intro from "@/components/Intro";
import Services from "@/components/Services";
import Portfolio from "@/components/Portfolio";
import Philosophy from "@/components/Philosophy";
import Orb from "@/components/Orb";
import DataSection from "@/components/DataSection";
import Carousel from "@/components/Carousel";
import Footer from "@/components/Footer";

export default function Home() {
  const [isMenuOpen, setIsMenuOpen] = useState(false);

  return (
    <main className="relative bg-[#faf8f5] text-[#111] overflow-x-hidden">
      <FullScreenMenu isOpen={isMenuOpen} onClose={() => setIsMenuOpen(false)} />
      <Hero onMenuClick={() => setIsMenuOpen(true)} />
      <Intro />
      <Services />
      <Portfolio />
      <Philosophy />
      <Orb />
      <DataSection />
      <Carousel />
      <Footer />
    </main>
  );
}
