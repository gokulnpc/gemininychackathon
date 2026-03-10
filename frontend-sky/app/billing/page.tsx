"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { motion } from "framer-motion";
import { UserMenu } from "@/components/shared/UserMenu";
import { Button } from "@/components/ui/button";
import { AppSidebar } from "@/components/app-sidebar";
import { useSidebar } from "@/context/SidebarContext";
import { cn } from "@/lib/utils";
import { CreditCard, CheckCircle2, Zap, ArrowRight, Download, Receipt } from "lucide-react";
import { toast } from "sonner";

export default function BillingPage() {
  const router = useRouter();
  const { isCollapsed } = useSidebar();
  
  const [isAnnual, setIsAnnual] = useState(false);

  const handleUpgrade = (tier: string) => {
    toast.success(`Upgrading to ${tier}... redirecting to checkout.`);
  };

  const handleDownloadInvoice = (id: string) => {
    toast(`Downloading invoice #${id}`);
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

        {/* Main Content */}
        <main className="px-8 py-8 w-full max-w-6xl mx-auto">
          {/* Current Usage */}
          <motion.div 
            initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.5 }}
            className="bg-[#333333] rounded-2xl border border-white/10 p-6 mb-12"
          >
            <h2 className="text-lg font-medium text-white mb-4">Current Usage</h2>
            <div className="bg-[#2B2B2B] rounded-xl p-4 border border-white/5">
              <div className="flex justify-between text-sm mb-2">
                <span className="text-white/70">Video Generations</span>
                <span className="text-white font-medium">3 / 5</span>
              </div>
              <div className="w-full bg-white/10 rounded-full h-2 mb-2 overflow-hidden">
                <div className="bg-[#5a9ab5] h-2 rounded-full" style={{ width: "60%" }}></div>
              </div>
              <div className="flex justify-between text-xs text-white/40">
                <span>Resets on Apr 10, 2026</span>
                <a href="#plans" className="text-[#5a9ab5] hover:underline">Need more?</a>
              </div>
            </div>
          </motion.div>

          {/* Billing History */}
          <motion.div 
            initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.6 }}
          >
            <h2 className="text-lg font-medium text-white mb-4">Billing History</h2>
            <div className="bg-[#333333] rounded-2xl border border-white/10 overflow-hidden text-sm">
              <div className="grid grid-cols-4 px-6 py-4 border-b border-white/10 text-white/50 font-medium">
                <div>Date</div>
                <div>Amount</div>
                <div>Status</div>
                <div className="text-right">Invoice</div>
              </div>
              {/* Dummy data */}
              {[
                { id: "INV-2026-03", date: "Mar 10, 2026", amount: "$0.00", status: "Paid" },
                { id: "INV-2026-02", date: "Feb 10, 2026", amount: "$0.00", status: "Paid" },
                { id: "INV-2026-01", date: "Jan 10, 2026", amount: "$0.00", status: "Paid" }
              ].map((invoice, i) => (
                <div key={i} className="grid grid-cols-4 px-6 py-4 border-b border-white/5 text-white/80 hover:bg-white/5 transition-colors items-center">
                  <div>{invoice.date}</div>
                  <div className="font-medium">{invoice.amount}</div>
                  <div>
                    <span className="px-2 py-1 rounded bg-green-500/10 text-green-400 text-xs">
                      {invoice.status}
                    </span>
                  </div>
                  <div className="text-right flex justify-end">
                    <button 
                      onClick={() => handleDownloadInvoice(invoice.id)}
                      className="text-[#5a9ab5] p-2 rounded-lg hover:bg-white/10 transition-colors flex items-center justify-center"
                      title="Download Invoice"
                    >
                      <Download className="w-4 h-4" />
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </motion.div>

        </main>
      </div>
    </div>
  );
}
