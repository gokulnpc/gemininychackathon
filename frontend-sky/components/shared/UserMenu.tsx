"use client";

import { useRouter } from "next/navigation";
import { Coins, LayoutDashboard, LogOut, Settings, User } from "lucide-react";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { useAuth } from "@/context/AuthContext";

function getInitials(name: string): string {
  return name
    .split(" ")
    .slice(0, 2)
    .map((w) => w[0]?.toUpperCase() ?? "")
    .join("");
}

export function UserMenu() {
  const router = useRouter();
  const { user, signOut } = useAuth();

  const displayName = user?.displayName ?? user?.email ?? "User";
  const initials = getInitials(displayName);
  const photoURL = user?.photoURL ?? undefined;

  const handleSignOut = async () => {
    await signOut();
    router.push("/login");
  };

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button suppressHydrationWarning className="flex items-center gap-3 bg-white/10 rounded-full px-4 py-2 border border-white/20 hover:bg-white/15 transition-colors">
          <Avatar className="w-8 h-8">
            <AvatarImage src={photoURL} alt={displayName} />
            <AvatarFallback className="bg-[#5a9ab5] text-white text-sm">{initials}</AvatarFallback>
          </Avatar>
          <span className="text-sm font-medium text-white whitespace-nowrap">{displayName}</span>
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-64">
        <div className="px-3 py-3 bg-[#5a9ab5]/5 rounded-lg mx-2 mt-2 mb-2">
          <div className="flex items-center gap-2 mb-1">
            <Coins className="w-4 h-4 text-[#5a9ab5]" />
            <span className="text-sm font-medium text-[#1A1A1A]">Credits</span>
          </div>
          <p className="text-2xl font-semibold text-[#1A1A1A]">1,250</p>
          <p className="text-xs text-[#9B9B9B] mt-0.5">~25 videos remaining</p>
        </div>
        <DropdownMenuSeparator />
        <DropdownMenuItem onClick={() => router.push("/welcome")} className="cursor-pointer">
          <LayoutDashboard className="w-4 h-4 mr-2" />Dashboard
        </DropdownMenuItem>
        <DropdownMenuItem className="cursor-pointer">
          <User className="w-4 h-4 mr-2" />Profile
        </DropdownMenuItem>
        <DropdownMenuItem className="cursor-pointer">
          <Settings className="w-4 h-4 mr-2" />Settings
        </DropdownMenuItem>
        <DropdownMenuSeparator />
        <DropdownMenuItem onClick={handleSignOut} className="cursor-pointer text-red-600">
          <LogOut className="w-4 h-4 mr-2" />Sign out
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
