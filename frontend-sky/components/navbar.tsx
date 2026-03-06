"use client"

import { useState } from "react"
import Link from "next/link"
import Image from "next/image"
import { ChevronDown, ArrowUpRight } from "lucide-react"

export default function Navbar() {
  const [featuresOpen, setFeaturesOpen] = useState(false)
  const [aboutOpen, setAboutOpen] = useState(false)

  return (
    <header className="fixed top-0 left-0 right-0 z-50 flex items-center justify-between px-6 py-4 border-b border-white/15">
      <Link href="/">
        <Image src="/logo_StoryLab_sky.png" alt="Story Lab" width={140} height={32} className="h-8 w-auto" />
      </Link>

      <nav className="hidden md:flex items-center gap-6 text-xs font-medium text-white/80">
        <div
          className="nav-link relative flex items-center gap-0.5 cursor-pointer hover:text-white transition-colors"
          onMouseEnter={() => setFeaturesOpen(true)}
          onMouseLeave={() => setFeaturesOpen(false)}
        >
          FEATURES
          <ChevronDown size={12} className={`transition-transform duration-200 ${featuresOpen ? "rotate-180" : ""}`} />
        </div>
        <div
          className="nav-link relative flex items-center gap-0.5 cursor-pointer hover:text-white transition-colors"
          onMouseEnter={() => setAboutOpen(true)}
          onMouseLeave={() => setAboutOpen(false)}
        >
          ABOUT US
          <ChevronDown size={12} className={`transition-transform duration-200 ${aboutOpen ? "rotate-180" : ""}`} />
        </div>
        <Link href="#pricing" className="nav-link hover:text-white transition-colors">
          PRICING
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
  )
}
