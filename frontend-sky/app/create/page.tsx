"use client";

import { useEffect } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import { WizardProvider, useWizard } from "@/context/WizardContext";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Coins, LayoutDashboard, LogOut, Settings, User } from "lucide-react";
import { useSidebar } from "@/context/SidebarContext";
import { cn } from "@/lib/utils";
import { AppSidebar } from "@/components/app-sidebar";
import { Header } from "@/components/create/layout/Header";
import { FooterNav } from "@/components/create/layout/FooterNav";
import { ProgressStepper } from "@/components/create/shared/ProgressStepper";
import { Step1_Message } from "@/components/create/steps/Step1_Message";
import { Step2_ChoosePlot } from "@/components/create/steps/Step2_ChoosePlot";
import { Step3_Picture } from "@/components/create/steps/Step3_Picture";
import { Step4_Language } from "@/components/create/steps/Step4_Language";
import { Step5_Music } from "@/components/create/steps/Step5_Music";
import { Step6_ArtStyle } from "@/components/create/steps/Step6_ArtStyle";
import { Step7_Caption } from "@/components/create/steps/Step7_Caption";
import { Step8_Effects } from "@/components/create/steps/Step8_Effects";
import { Step9_VideoDetails } from "@/components/create/steps/Step9_VideoDetails";
import { Step10_GenerateScript } from "@/components/create/steps/Step10_GenerateScript";
import { Step10_ReviewVideo } from "@/components/create/steps/Step10_ReviewVideo";
import { Processing } from "@/components/create/steps/Processing";
import { ScriptReview } from "@/components/create/steps/ScriptReview";
import { AnimatePresence, motion } from "framer-motion";
import { Suspense } from "react";

function WizardContent() {
  const { state } = useWizard();
  const { isCollapsed } = useSidebar();
  const router = useRouter();

  // Keep URL in sync with wizard state as the user navigates steps.
  // State is already correctly initialized from URL params by WizardInitializer,
  // so this effect only needs to reflect subsequent state changes.
  useEffect(() => {
    router.replace(`/create?tab=${state.messageTab}&step=${state.currentStep}`, { scroll: false });
  }, [state.currentStep, state.messageTab, router]);

  const renderStep = () => {
    if (state.isProcessing) {
      return <Processing />;
    }

    if (state.showScriptReview) {
      return <ScriptReview />;
    }

    switch (state.currentStep) {
      case 1:
        return <Step1_Message />;
      case 2:
        return <Step2_ChoosePlot />;
      case 3:
        return <Step3_Picture />;
      case 4:
        return <Step4_Language />;
      case 5:
        return <Step5_Music />;
      case 6:
        return <Step6_ArtStyle />;
      case 7:
        return <Step7_Caption />;
      case 8:
        return <Step8_Effects />;
      case 9:
        return <Step9_VideoDetails />;
      case 10:
        return <Step10_GenerateScript />;
      case 11:
        return <Step10_ReviewVideo />;
      default:
        return <Step1_Message />;
    }
  };

  return (
    <div className="flex min-h-screen bg-[#2B2B2B]">
      <AppSidebar activeStep={state.isProcessing ? undefined : state.currentStep} />

      <div className={cn(
        "flex-1 flex flex-col min-h-screen transition-all duration-300 relative z-10",
        isCollapsed ? "ml-[80px]" : "ml-[280px]"
      )}>
        <div className="flex justify-end px-8 pt-8">
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <button className="flex items-center gap-3 bg-white/10 rounded-full px-4 py-2 border border-white/20 hover:bg-white/15 transition-colors">
                <Avatar className="w-8 h-8">
                  <AvatarImage src="/Avatar.png" alt="An Tran" />
                  <AvatarFallback className="bg-[#5a9ab5] text-white text-sm">AT</AvatarFallback>
                </Avatar>
                <span className="text-sm font-medium text-white">An Tran</span>
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
              <DropdownMenuItem onClick={() => router.push("/login")} className="cursor-pointer text-red-600">
                <LogOut className="w-4 h-4 mr-2" />Sign out
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
        <div className="max-w-4xl mx-auto px-8 pb-8">
          <Header />

          {!state.isProcessing && !state.showScriptReview && state.currentStep < 11 && (
            <ProgressStepper />
          )}

          <AnimatePresence mode="wait">
            <motion.div
              key={state.isProcessing ? "processing" : state.showScriptReview ? "script-review" : state.currentStep}
              initial={{ opacity: 0, x: 20 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -20 }}
              transition={{ duration: 0.3 }}
            >
              {renderStep()}
            </motion.div>
          </AnimatePresence>

          {!state.isProcessing && !state.showScriptReview && <FooterNav />}
        </div>
      </div>
    </div>
  );
}

// Reads URL params inside the Suspense boundary (required for useSearchParams),
// then initialises WizardProvider with the correct values before the first render.
// This avoids any useEffect-based seeding and the race conditions that come with it.
function WizardInitializer() {
  const searchParams = useSearchParams();
  const rawTab = searchParams.get("tab");
  const rawStep = searchParams.get("step");

  const initialTab = (["speech", "text", "preset"].includes(rawTab ?? "")
    ? rawTab
    : "speech") as "speech" | "text" | "preset";
  const initialStep = rawStep ? Math.max(1, parseInt(rawStep) || 1) : 1;

  return (
    <WizardProvider initialTab={initialTab} initialStep={initialStep}>
      <WizardContent />
    </WizardProvider>
  );
}

export default function CreatePage() {
  return (
    <Suspense>
      <WizardInitializer />
    </Suspense>
  );
}
