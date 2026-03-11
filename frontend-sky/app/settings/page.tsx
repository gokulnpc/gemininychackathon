"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { motion } from "framer-motion";
import { UserMenu } from "@/components/shared/UserMenu";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { Label } from "@/components/ui/label";
import { AppSidebar } from "@/components/app-sidebar";
import { useSidebar } from "@/context/SidebarContext";
import { cn } from "@/lib/utils";
import { Bell, Key, User, MonitorSmartphone } from "lucide-react";
import { toast } from "sonner";
import { useAuth } from "@/context/AuthContext";
import apiClient from "@/lib/apiClient";

export default function SettingsPage() {
  const router = useRouter();
  const { isCollapsed } = useSidebar();
  const { userProfile, refreshProfile } = useAuth();

  const [activeTab, setActiveTab] = useState("profile");
  const [displayName, setDisplayName] = useState(userProfile?.display_name ?? "");
  const [saving, setSaving] = useState(false);

  const handleSave = async () => {
    setSaving(true);
    try {
      await apiClient.patch("/api/v1/users/me", { display_name: displayName });
      await refreshProfile();
      toast.success("Settings saved successfully!");
    } catch {
      toast.error("Failed to save settings.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="flex min-h-screen bg-[#2B2B2B]">
      <AppSidebar />

      <div className={cn("flex-1 flex flex-col min-h-screen transition-all duration-300", isCollapsed ? "ml-[80px]" : "ml-[280px]")}>
        {/* Header */}
        <header className="flex items-center justify-between px-8 h-[80px] border-b border-white/10">
          <div /> {/* spacer */}
          <div className="flex items-center gap-4">
            <Button
              onClick={() => router.push("/create")}
              className="rounded-full px-6 bg-[#5a9ab5] hover:bg-[#7ab0c8] text-white"
            >
              Create New
            </Button>
            <UserMenu />
          </div>
        </header>

        {/* Main */}
        <main className="px-8 py-8 w-full max-w-5xl mx-auto">
          <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} className="mb-8">
            <h1 className="text-3xl font-medium text-white mb-2">Settings</h1>
            <p className="text-white/50">
              Manage your account preferences and configurations
            </p>
          </motion.div>

          {/* Horizontal tab bar */}
          <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.1 }}
            className="flex gap-1 border-b border-white/10 mb-8"
          >
            {[
              { id: "profile", label: "Profile", icon: User },
              { id: "preferences", label: "Preferences", icon: MonitorSmartphone },
              { id: "notifications", label: "Notifications", icon: Bell },
              { id: "api-keys", label: "API Keys", icon: Key },
            ].map(({ id, label, icon: Icon }) => (
              <button
                key={id}
                onClick={() => setActiveTab(id)}
                className={cn(
                  "flex items-center gap-2 px-5 py-3 text-sm font-medium transition-all border-b-2 -mb-px",
                  activeTab === id
                    ? "border-[#5a9ab5] text-white"
                    : "border-transparent text-white/50 hover:text-white hover:border-white/20"
                )}
              >
                <Icon className="w-4 h-4" />
                {label}
              </button>
            ))}
          </motion.div>

          {/* Content area */}
          <div className="flex flex-col gap-8">
            <motion.div
              key={activeTab}
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.2 }}
              className="bg-[#333333] rounded-2xl border border-white/10 p-8"
            >
              {activeTab === "profile" && (
                <div className="space-y-6">
                  <div>
                    <h2 className="text-xl font-medium text-white mb-1">Profile Information</h2>
                    <p className="text-sm text-white/50 mb-6">Update your account profile details and email address.</p>
                  </div>
                  
                  <div className="space-y-4 max-w-md">
                    <div className="space-y-2">
                      <Label htmlFor="name" className="text-white/80">Full Name</Label>
                      <Input
                        id="name"
                        value={displayName}
                        onChange={(e) => setDisplayName(e.target.value)}
                        className="bg-[#2B2B2B] border-white/10 text-white focus:border-[#5a9ab5]"
                      />
                    </div>

                    <div className="space-y-2">
                      <Label htmlFor="email" className="text-white/80">Email Address</Label>
                      <Input
                        id="email"
                        type="email"
                        value={userProfile?.email ?? ""}
                        readOnly
                        className="bg-[#2B2B2B] border-white/10 text-white/50 focus:border-[#5a9ab5] cursor-not-allowed"
                      />
                    </div>

                    <div className="pt-4">
                      <Button onClick={handleSave} disabled={saving} className="bg-[#5a9ab5] hover:bg-[#7ab0c8] text-white px-6 rounded-xl">
                        {saving ? "Saving..." : "Save Changes"}
                      </Button>
                    </div>
                  </div>
                </div>
              )}

              {activeTab === "preferences" && (
                <div className="space-y-6">
                  <div>
                    <h2 className="text-xl font-medium text-white mb-1">Application Preferences</h2>
                    <p className="text-sm text-white/50 mb-6">Customize your experience and workspace.</p>
                  </div>
                  
                  <div className="space-y-6 max-w-md">
                    <div className="flex items-center justify-between">
                      <div className="space-y-0.5">
                        <Label className="text-base text-white/90">Dark Mode</Label>
                        <p className="text-sm text-white/50">Use dark theme across the application</p>
                      </div>
                      <Switch defaultChecked />
                    </div>
                    <div className="flex items-center justify-between">
                      <div className="space-y-0.5">
                        <Label className="text-base text-white/90">Compact Sidebar</Label>
                        <p className="text-sm text-white/50">Start with sidebar collapsed by default</p>
                      </div>
                      <Switch />
                    </div>
                    
                    <div className="pt-4">
                      <Button onClick={handleSave} className="bg-[#5a9ab5] hover:bg-[#7ab0c8] text-white px-6 rounded-xl">
                        Save Preferences
                      </Button>
                    </div>
                  </div>
                </div>
              )}

              {activeTab === "notifications" && (
                <div className="space-y-6">
                  <div>
                    <h2 className="text-xl font-medium text-white mb-1">Notification Settings</h2>
                    <p className="text-sm text-white/50 mb-6">Choose what updates you want to receive.</p>
                  </div>
                  
                  <div className="space-y-6 max-w-md">
                    <div className="flex items-center justify-between">
                      <div className="space-y-0.5">
                        <Label className="text-base text-white/90">Video Rendered</Label>
                        <p className="text-sm text-white/50">Notify me when my video is ready</p>
                      </div>
                      <Switch defaultChecked />
                    </div>
                    <div className="flex items-center justify-between">
                      <div className="space-y-0.5">
                        <Label className="text-base text-white/90">Marketing Emails</Label>
                        <p className="text-sm text-white/50">Receive product updates and offers</p>
                      </div>
                      <Switch />
                    </div>
                    <div className="flex items-center justify-between">
                      <div className="space-y-0.5">
                        <Label className="text-base text-white/90">Failed Generations</Label>
                        <p className="text-sm text-white/50">Alert me if an AI generation fails</p>
                      </div>
                      <Switch defaultChecked />
                    </div>
                    
                    <div className="pt-4">
                      <Button onClick={handleSave} className="bg-[#5a9ab5] hover:bg-[#7ab0c8] text-white px-6 rounded-xl">
                        Save Notifications
                      </Button>
                    </div>
                  </div>
                </div>
              )}

              {activeTab === "api-keys" && (
                <div className="space-y-6">
                  <div>
                    <h2 className="text-xl font-medium text-white mb-1">API Integrations</h2>
                    <p className="text-sm text-white/50 mb-6">Manage your external API keys and connections.</p>
                  </div>
                  
                  <div className="space-y-4 max-w-md">
                    <div className="space-y-2">
                      <Label htmlFor="gemini-key" className="text-white/80">Gemini API Key</Label>
                      <Input id="gemini-key" type="password" placeholder="AIzaSy..." className="bg-[#2B2B2B] border-white/10 text-white focus:border-[#5a9ab5]" />
                      <p className="text-xs text-white/40">Used for your own custom models overrides (optional).</p>
                    </div>
                    
                    <div className="space-y-2 pt-2">
                      <Label htmlFor="elevenlabs-key" className="text-white/80">ElevenLabs API Key</Label>
                      <Input id="elevenlabs-key" type="password" placeholder="sk_..." className="bg-[#2B2B2B] border-white/10 text-white focus:border-[#5a9ab5]" />
                      <p className="text-xs text-white/40">Optional integration for premium voice clones.</p>
                    </div>
                    
                    <div className="pt-4">
                      <Button onClick={handleSave} className="bg-[#5a9ab5] hover:bg-[#7ab0c8] text-white px-6 rounded-xl">
                        Save Keys
                      </Button>
                    </div>
                  </div>
                </div>
              )}
            </motion.div>
          </div>
        </main>
      </div>
    </div>
  );
}
