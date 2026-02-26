"use client";

import { useEffect } from "react";
import { useSearchParams } from "next/navigation";
import { WizardProvider, useWizard } from "@/context/WizardContext";
import { Sidebar } from "@/components/create/layout/Sidebar";
import { Header } from "@/components/create/layout/Header";
import { FooterNav } from "@/components/create/layout/FooterNav";
import { ProgressStepper } from "@/components/create/shared/ProgressStepper";
import { Step1_Message } from "@/components/create/steps/Step1_Message";
import { Step2_Language } from "@/components/create/steps/Step2_Language";
import { Step3_Music } from "@/components/create/steps/Step3_Music";
import { Step4_ArtStyle } from "@/components/create/steps/Step4_ArtStyle";
import { Step5_Caption } from "@/components/create/steps/Step5_Caption";
import { Step6_Effects } from "@/components/create/steps/Step6_Effects";
import { Step7_VideoDetails } from "@/components/create/steps/Step7_VideoDetails";
import { Step8_ReviewVideo } from "@/components/create/steps/Step8_ReviewVideo";
import { Processing } from "@/components/create/steps/Processing";
import { ScriptReview } from "@/components/create/steps/ScriptReview";
import { AnimatePresence, motion } from "framer-motion";
import { Suspense } from "react";

function WizardContent() {
  const { state, dispatch } = useWizard();
  const searchParams = useSearchParams();

  useEffect(() => {
    const tab = searchParams.get("tab");
    const step = searchParams.get("step");

    if (tab) {
      dispatch({
        type: "SET_MESSAGE_TAB",
        payload: tab as "speech" | "text" | "preset",
      });
    }
    if (step) {
      dispatch({ type: "SET_STEP", payload: parseInt(step) });
    }
  }, [searchParams, dispatch]);

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
        return <Step2_Language />;
      case 3:
        return <Step3_Music />;
      case 4:
        return <Step4_ArtStyle />;
      case 5:
        return <Step5_Caption />;
      case 6:
        return <Step6_Effects />;
      case 7:
        return <Step7_VideoDetails />;
      case 8:
        return <Step8_ReviewVideo />;
      default:
        return <Step1_Message />;
    }
  };

  return (
    <div className="min-h-screen relative overflow-hidden">
      <Sidebar />

      <main className="ml-[240px] min-h-screen relative z-10">
        <div className="max-w-4xl mx-auto px-8 py-8">
          <Header />

          {!state.isProcessing && !state.showScriptReview && state.currentStep <= 7 && (
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
      </main>
    </div>
  );
}

export default function CreatePage() {
  return (
    <WizardProvider>
      <Suspense>
        <WizardContent />
      </Suspense>
    </WizardProvider>
  );
}
