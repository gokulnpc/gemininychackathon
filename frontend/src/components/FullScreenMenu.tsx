"use client";

import Link from "next/link";

interface FullScreenMenuProps {
  isOpen: boolean;
  onClose: () => void;
}

const NAV_ITEMS: { label: string; href: string }[] = [
  { label: "About",      href: "#" },
  { label: "Gallery",    href: "/gallery" },
  { label: "News",       href: "#" },
  { label: "Contact Us", href: "#" },
];

export default function FullScreenMenu({ isOpen, onClose }: FullScreenMenuProps) {
  return (
    <div
      id="fullscreen-menu"
      className={`fixed inset-0 z-50 flex flex-col justify-between bg-black/95 text-white transition-transform duration-[800ms] ease-[cubic-bezier(0.76,0,0.24,1)] overflow-hidden grain-overlay backdrop-blur-sm ${
        isOpen ? "menu-open" : "menu-closed"
      }`}
    >
      {/* Menu Header */}
      <div className="relative z-10 w-full px-6 py-6 md:px-12 md:py-8 flex justify-between items-center text-lg font-medium tracking-tight">
        <div>Content Factory</div>
        <button
          onClick={onClose}
          className="cursor-pointer hover:opacity-70 transition-opacity"
        >
          Close
        </button>
      </div>

      {/* Menu Links */}
      <div className="relative z-10 flex-1 flex flex-col justify-center items-center gap-2 md:gap-6">
        {NAV_ITEMS.map(({ label, href }) => (
          <Link key={label} href={href} onClick={onClose} className="group relative overflow-hidden">
            <span className="block text-5xl md:text-7xl lg:text-8xl tracking-tighter font-normal hover:text-gray-400 transition-colors duration-300">
              {label}
            </span>
          </Link>
        ))}
      </div>

      {/* Menu Footer */}
      <div className="relative z-10 w-full px-6 py-6 md:px-12 md:pb-12 flex flex-col md:flex-row justify-between items-end text-sm md:text-base text-white/60">
        <div className="flex gap-4 md:gap-8 mb-4 md:mb-0">
          <Link href="#" className="hover:text-white transition-colors">
            X
          </Link>
          <Link href="#" className="hover:text-white transition-colors">
            Instagram
          </Link>
          <Link href="#" className="hover:text-white transition-colors">
            LinkedIn
          </Link>
        </div>
        <div>
          <p>San Diego — Paris</p>
        </div>
      </div>
    </div>
  );
}
