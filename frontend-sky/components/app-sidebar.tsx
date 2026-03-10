"use client";

import { useRouter, usePathname } from "next/navigation";
import { motion } from "framer-motion";
import {
  LayoutDashboard,
  Home,
  Plus,
  CreditCard,
  Settings,
  Mic,
  Volume2,
  Music,
  Palette,
  Type,
  Zap,
  Clock,
  Eye,
  PanelLeftClose,
  FolderOpen,
  Image as ImageIcon,
  PanelLeft,
  BookOpen,
  ClipboardList,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useSidebar } from "@/context/SidebarContext";

const createSubItems = [
  { id: 1, label: "Tell Your Story", icon: Mic },
  { id: 2, label: "Choose the Plot", icon: BookOpen },
  { id: 3, label: "Upload your Picture (opt.)", icon: ImageIcon },
  { id: 4, label: "Language & Voice (opt.)", icon: Volume2 },
  { id: 5, label: "Background Music (opt.)", icon: Music },
  { id: 6, label: "Video Style", icon: Palette },
  { id: 7, label: "Caption Style (opt.)", icon: Type },
  { id: 8, label: "Video Effect (opt.)", icon: Zap },
  { id: 9, label: "Video Config.", icon: Clock },
  { id: 10, label: "Review & Publish", icon: Eye },
];

interface AppSidebarProps {
  activeStep?: number;
}

export function AppSidebar({ activeStep }: AppSidebarProps) {
  const router = useRouter();
  const pathname = usePathname();
  const { isCollapsed, toggleSidebar } = useSidebar();

  const isOverview = pathname === "/welcome";
  const isDashboard = pathname === "/dashboard";
  const isCreate = pathname.startsWith("/create");
  const isSettings = pathname === "/settings";
  const isBilling = pathname === "/billing";

  return (
    <motion.aside
      initial={false}
      animate={{ width: isCollapsed ? 80 : 280 }}
      transition={{ duration: 0.3, ease: [0.4, 0, 0.2, 1] }}
      className="fixed left-0 top-0 h-full bg-[#1B1B1B] z-50 flex flex-col border-r border-white/5"
    >
      {/* Logo */}
      <div className={cn(
        "h-[80px] border-b border-white/10 flex items-center transition-all duration-300",
        isCollapsed ? "justify-center px-4" : "justify-between px-6"
      )}>
        {!isCollapsed && (
          <button
            onClick={() => router.push("/welcome")}
            className="hover:opacity-80 transition-opacity"
          >
            <img
              src="/logo_StoryLab_sky.png"
              alt="Story Lab"
              className="h-6"
            />
          </button>
        )}
        <button 
          onClick={toggleSidebar}
          className="text-white/50 hover:text-white transition-colors"
        >
          {isCollapsed ? (
            <PanelLeft className="w-5 h-5" />
          ) : (
            <PanelLeftClose className="w-5 h-5" />
          )}
        </button>
      </div>

      {/* Navigation */}
      <nav className="flex-1 px-3 py-4 overflow-y-auto">
        <ul className="space-y-1">
          {/* Overview */}
          <li>
            <button
              onClick={() => router.push("/welcome")}
              className={cn(
                "w-full flex items-center gap-3 px-4 py-3 rounded-xl text-sm font-medium transition-all duration-200",
                isOverview
                  ? "bg-[#5a9ab5] text-white"
                  : "text-[#9B9B9B] hover:text-white hover:bg-white/10",
                isCollapsed && "justify-center px-0",
                !isCollapsed && "text-left"
              )}
            >
              <Home className="w-4 h-4 shrink-0" />
              {!isCollapsed && <span>Overview</span>}
            </button>
          </li>

          {/* Dashboard */}
          <li>
            <button
              onClick={() => router.push("/dashboard")}
              className={cn(
                "w-full flex items-center gap-3 px-4 py-3 rounded-xl text-sm font-medium transition-all duration-200",
                isDashboard
                  ? "bg-[#5a9ab5] text-white"
                  : "text-[#9B9B9B] hover:text-white hover:bg-white/10",
                isCollapsed && "justify-center px-0",
                !isCollapsed && "text-left"
              )}
            >
              <LayoutDashboard className="w-4 h-4 shrink-0" />
              {!isCollapsed && <span>Dashboard</span>}
            </button>
          </li>

          {/* Create */}
          <li>
            <button
              onClick={() => router.push("/create")}
              className={cn(
                "w-full flex items-center gap-3 px-4 py-3 rounded-xl text-sm font-medium transition-all duration-200",
                isCreate && !activeStep
                  ? "bg-[#5a9ab5] text-white"
                  : isCreate
                  ? "text-white"
                  : "text-[#9B9B9B] hover:text-white hover:bg-white/10",
                isCollapsed && "justify-center px-0",
                !isCollapsed && "text-left"
              )}
            >
              <Plus className="w-4 h-4 shrink-0" />
              {!isCollapsed && <span>Create</span>}
            </button>

            {/* Sub-items — always visible on create page */}
            {isCreate && !isCollapsed && (
              <ul className="mt-1 ml-3 space-y-0.5">
                {createSubItems.map((item, index) => {
                  const Icon = item.icon;
                  const isActive = activeStep === item.id;
                  return (
                    <motion.li
                      key={item.id}
                      initial={{ opacity: 0, x: -8 }}
                      animate={{ opacity: 1, x: 0 }}
                      transition={{ delay: index * 0.03 }}
                    >
                      <button
                        onClick={() => router.push(`/create?step=${item.id}`)}
                        className={cn(
                          "w-full flex items-center gap-3 px-4 py-2.5 rounded-xl text-xs font-medium transition-all duration-200",
                          isActive
                            ? "bg-[#5a9ab5] text-white shadow-md"
                            : "text-[#9B9B9B] hover:text-white hover:bg-white/10",
                          "text-left"
                        )}
                      >
                        <Icon className="w-3.5 h-3.5 shrink-0" />
                        {item.label}
                      </button>
                    </motion.li>
                  );
                })}
              </ul>
            )}
          </li>

          {/* Projects */}
          <li>
            <button
              onClick={() => router.push("/projects")}
              className={cn(
                "w-full flex items-center gap-3 px-4 py-3 rounded-xl text-sm font-medium transition-all duration-200",
                pathname.startsWith("/projects")
                  ? "bg-[#5a9ab5] text-white"
                  : "text-[#9B9B9B] hover:text-white hover:bg-white/10",
                isCollapsed && "justify-center px-0",
                !isCollapsed && "text-left"
              )}
            >
              <ClipboardList className="w-4 h-4 shrink-0" />
              {!isCollapsed && <span>Projects</span>}
            </button>
          </li>

          {/* My Assets */}
          <li>
            <button
              onClick={() => router.push("/assets")}
              className={cn(
                "w-full flex items-center gap-3 px-4 py-3 rounded-xl text-sm font-medium transition-all duration-200",
                pathname === "/assets"
                  ? "bg-[#5a9ab5] text-white"
                  : "text-[#9B9B9B] hover:text-white hover:bg-white/10",
                isCollapsed && "justify-center px-0",
                !isCollapsed && "text-left"
              )}
            >
              <FolderOpen className="w-4 h-4 shrink-0" />
              {!isCollapsed && <span>My Assets</span>}
            </button>
          </li>

          {/* Billing */}
          <li>
            <button 
              onClick={() => router.push("/billing")}
              className={cn(
              "w-full flex items-center gap-3 px-4 py-3 rounded-xl text-sm font-medium transition-all duration-200",
              isBilling ? "bg-[#5a9ab5] text-white" : "text-[#9B9B9B] hover:text-white hover:bg-white/10",
              isCollapsed ? "justify-center px-0" : "text-left"
            )}>
              <CreditCard className="w-4 h-4 shrink-0" />
              {!isCollapsed && <span>Billing</span>}
            </button>
          </li>

          {/* Settings */}
          <li>
            <button 
              onClick={() => router.push("/settings")}
              className={cn(
              "w-full flex items-center gap-3 px-4 py-3 rounded-xl text-sm font-medium transition-all duration-200",
              isSettings ? "bg-[#5a9ab5] text-white" : "text-[#9B9B9B] hover:text-white hover:bg-white/10",
              isCollapsed ? "justify-center px-0" : "text-left"
            )}>
              <Settings className="w-4 h-4 shrink-0" />
              {!isCollapsed && <span>Settings</span>}
            </button>
          </li>
        </ul>
      </nav>
    </motion.aside>
  );
}
