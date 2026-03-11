"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { motion } from "framer-motion";
import { UserMenu } from "@/components/shared/UserMenu";
import { Button } from "@/components/ui/button";
import { AppSidebar } from "@/components/app-sidebar";
import { useSidebar } from "@/context/SidebarContext";
import { cn } from "@/lib/utils";
import { CreditCard, CheckCircle2, Zap, ArrowRight, Download, Receipt } from "lucide-react";
import { toast } from "sonner";
import apiClient from "@/lib/apiClient";
import { useAuth } from "@/context/AuthContext";
import { Input } from "@/components/ui/input";

const STARTING_CREDITS = 300;
const COST_PER_VIDEO = 100;
const CREDITS_PER_DOLLAR = 10;

const PACKAGES = [
  { dollars: 10,  credits: 100  },
  { dollars: 25,  credits: 250  },
  { dollars: 50,  credits: 500  },
  { dollars: 100, credits: 1000 },
];

export default function BillingPage() {
  const router = useRouter();
  const { isCollapsed } = useSidebar();
  const { user } = useAuth();
  const [credits, setCredits] = useState<number | null>(null);
  const [isAnnual, setIsAnnual] = useState(false);
  const [customAmount, setCustomAmount] = useState("");

  useEffect(() => {
    if (!user) return;
    apiClient
      .get<{ credits: number }>("/api/v1/credits")
      .then((r) => setCredits(r.data.credits))
      .catch(() => setCredits(null));
  }, [user]);

  const handleUpgrade = (tier: string) => {
    toast.success(`Upgrading to ${tier}... redirecting to checkout.`);
  };

  const handleBuy = (dollars: number, credits: number) => {
    toast.success(`Purchase coming soon — $${dollars} for ${credits} credits`);
  };

  const handleCustomBuy = () => {
    const dollars = parseInt(customAmount);
    if (!dollars || dollars < 1) {
      toast.error("Enter a valid dollar amount (minimum $1)");
      return;
    }
    handleBuy(dollars, dollars * CREDITS_PER_DOLLAR);
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
                <span className="text-white/70">Credits Remaining</span>
                <span className="text-white font-medium">
                  {credits !== null ? credits : "…"} / {STARTING_CREDITS}
                </span>
              </div>
              <div className="w-full bg-white/10 rounded-full h-2 mb-2 overflow-hidden">
                <div
                  className="bg-[#5a9ab5] h-2 rounded-full transition-all duration-500"
                  style={{ width: credits !== null ? `${Math.max(0, (credits / STARTING_CREDITS) * 100)}%` : "0%" }}
                />
              </div>
              <div className="flex justify-between text-xs text-white/40">
                <span>{COST_PER_VIDEO} credits per video generation</span>
                <span>{credits !== null ? Math.floor(credits / COST_PER_VIDEO) : "…"} videos remaining</span>
              </div>
            </div>
          </motion.div>

          {/* Purchase Credits */}
          <motion.div
            initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.55 }}
            className="bg-[#333333] rounded-2xl border border-white/10 p-6 mb-8"
          >
            <div className="flex items-center justify-between mb-1">
              <h2 className="text-lg font-medium text-white">Purchase Credits</h2>
              <span className="text-xs text-white/40">$1 = 10 credits</span>
            </div>
            <p className="text-sm text-white/50 mb-5">Top up your balance to keep creating videos.</p>

            {/* Preset packages */}
            <div className="grid grid-cols-4 gap-3 mb-6">
              {PACKAGES.map((pkg) => {
                const isSelected = customAmount === pkg.dollars.toString();
                return (
                  <button
                    key={pkg.dollars}
                    onClick={() => setCustomAmount(pkg.dollars.toString())}
                    className={cn(
                      "rounded-xl border p-4 text-center transition-all duration-200 flex flex-col gap-1",
                      isSelected
                        ? "border-[#5a9ab5] bg-[#5a9ab5]/15"
                        : "border-white/10 bg-[#2B2B2B] hover:border-white/30"
                    )}
                  >
                    <span className="text-white font-semibold text-xl">${pkg.dollars}</span>
                    <span className="text-[#5a9ab5] text-sm font-medium">{pkg.credits} credits</span>
                  </button>
                );
              })}
            </div>

            {/* Custom amount */}
            <div className="flex items-center gap-3">
              <span className="text-sm text-white/50 shrink-0">Custom amount</span>
              <div className="relative max-w-[160px]">
                <span className="absolute left-3 top-1/2 -translate-y-1/2 text-white/40 text-sm">$</span>
                <Input
                  type="number"
                  min="1"
                  placeholder="0"
                  value={customAmount}
                  onChange={(e) => setCustomAmount(e.target.value.replace(/[^0-9]/g, ""))}
                  className="pl-7 bg-[#2B2B2B] border-white/10 text-white placeholder:text-white/20 focus:border-[#5a9ab5] [appearance:textfield] [&::-webkit-inner-spin-button]:appearance-none [&::-webkit-outer-spin-button]:appearance-none"
                />
              </div>
              {customAmount && parseInt(customAmount) >= 1 && (
                <span className="text-white/40 text-sm shrink-0">
                  = {parseInt(customAmount) * CREDITS_PER_DOLLAR} credits
                </span>
              )}
              <Button
                onClick={handleCustomBuy}
                disabled={!customAmount || parseInt(customAmount) < 1}
                className="rounded-lg bg-[#5a9ab5] hover:bg-[#7ab0c8] text-white disabled:opacity-40"
              >
                Buy
              </Button>
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
