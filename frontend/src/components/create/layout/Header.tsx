"use client";

import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { useWizard } from "@/context/WizardContext";
import { stepTitles } from "@/data/staticData";
import { useRouter } from "next/navigation";
import { motion } from "framer-motion";
import { Badge } from "@/components/ui/badge";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  Coins,
  LayoutDashboard,
  LogOut,
  Settings,
  User,
} from "lucide-react";

export function Header() {
  const { state } = useWizard();
  const router = useRouter();
  const { title, subtitle } = stepTitles[state.currentStep] || {
    title: "",
    subtitle: "",
  };

  const isOptional = state.currentStep === 3 || state.currentStep === 6;

  // Don't render header during processing or on review step (has its own header)
  if (state.isProcessing || state.currentStep === 8) return null;

  return (
    <motion.header
      initial={{ opacity: 0, y: -10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, delay: 0.1 }}
      className="flex items-start justify-between mb-8"
    >
      <div>
        <div className="flex items-center gap-4 mb-2">
          <h1 className="text-[42px] font-medium text-[#1A1A1A] leading-tight tracking-tight">
            {title}
          </h1>
          {isOptional && (
            <Badge
              variant="secondary"
              className="bg-[#F0F0F0] text-[#6B6B6B] hover:bg-[#F0F0F0] text-sm font-normal px-4 py-1.5 rounded-full border-none"
            >
              Optional
            </Badge>
          )}
        </div>
        {subtitle && <p className="text-lg text-[#6B6B6B]">{subtitle}</p>}
      </div>

      {/* User Profile Dropdown */}
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <button className="flex items-center gap-3 bg-white rounded-full px-4 py-2 shadow-sm border border-[#F0E8E4] hover:shadow-md transition-shadow">
            <Avatar className="w-8 h-8">
              <AvatarImage src="/Avatar.png" alt="An Tran" />
              <AvatarFallback className="bg-[#B08D9F] text-white text-sm">
                AT
              </AvatarFallback>
            </Avatar>
            <span className="text-sm font-medium text-[#1A1A1A]">
              An Tran
            </span>
          </button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" className="w-64">
          {/* Credits Section */}
          <div className="px-3 py-3 bg-[#B08D9F]/5 rounded-lg mx-2 mt-2 mb-2">
            <div className="flex items-center gap-2 mb-1">
              <Coins className="w-4 h-4 text-[#B08D9F]" />
              <span className="text-sm font-medium text-[#1A1A1A]">
                Credits
              </span>
            </div>
            <p className="text-2xl font-semibold text-[#1A1A1A]">1,250</p>
            <p className="text-xs text-[#9B9B9B] mt-0.5">
              ~25 videos remaining
            </p>
          </div>

          <DropdownMenuSeparator />

          <DropdownMenuItem
            onClick={() => router.push("/dashboard")}
            className="cursor-pointer"
          >
            <LayoutDashboard className="w-4 h-4 mr-2" />
            Dashboard
          </DropdownMenuItem>
          <DropdownMenuItem className="cursor-pointer">
            <User className="w-4 h-4 mr-2" />
            Profile
          </DropdownMenuItem>
          <DropdownMenuItem className="cursor-pointer">
            <Settings className="w-4 h-4 mr-2" />
            Settings
          </DropdownMenuItem>

          <DropdownMenuSeparator />

          <DropdownMenuItem
            onClick={() => router.push("/login")}
            className="cursor-pointer text-red-600"
          >
            <LogOut className="w-4 h-4 mr-2" />
            Sign out
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
    </motion.header>
  );
}
