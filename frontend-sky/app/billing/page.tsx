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
          <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} className="mb-10 text-center">
            <h1 className="text-3xl font-medium text-white mb-3">Billing & Plans</h1>
            <p className="text-white/60 text-lg">
              Manage your subscription and billing history.
            </p>
          </motion.div>

          {/* Pricing Toggle */}
          <motion.div 
            initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.1 }}
            className="flex items-center justify-center gap-4 mb-10"
          >
            <span className={cn("text-sm transition-colors", !isAnnual ? "text-white font-medium" : "text-white/50")}>Monthly</span>
            <button 
              onClick={() => setIsAnnual(!isAnnual)}
              className="w-12 h-6 rounded-full bg-white/10 relative cursor-pointer border border-white/20 transition-colors hover:bg-white/20"
            >
              <div className={cn("w-4 h-4 rounded-full bg-[#5a9ab5] absolute top-[-1px] transition-all", isAnnual ? "translate-x-7" : "translate-x-1")} />
            </button>
            <span className={cn("text-sm transition-colors", isAnnual ? "text-white font-medium" : "text-white/50")}>
              Annually <span className="text-[#5a9ab5] text-xs ml-1 font-semibold">Save 20%</span>
            </span>
          </motion.div>

          {/* Pricing Cards */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-12">
            {/* Free Tier */}
            <motion.div 
              initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.2 }}
              className="bg-[#333333] border border-white/10 rounded-2xl p-6 flex flex-col"
            >
              <h3 className="text-xl font-semibold text-white mb-2">Starter</h3>
              <p className="text-white/50 text-sm mb-6 h-10">Perfect for trying out StoryLab and making basic videos.</p>
              <div className="mb-6">
                <span className="text-4xl font-bold text-white">$0</span>
                <span className="text-white/40">/mo</span>
              </div>
              <ul className="space-y-3 mb-8 flex-1">
                {["5 Video Generations", "Standard Definition (720p)", "Community Support", "Basic Voices"].map((item, i) => (
                  <li key={i} className="flex items-center gap-3 text-sm text-white/80">
                    <CheckCircle2 className="w-4 h-4 text-[#5a9ab5] shrink-0" /> {item}
                  </li>
                ))}
              </ul>
              <Button disabled variant="outline" className="w-full bg-white/5 border-white/10 text-white/50 py-6 rounded-xl">
                Current Plan
              </Button>
            </motion.div>

            {/* Pro Tier */}
            <motion.div 
              initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.3 }}
              className="bg-gradient-to-br from-[#333333] to-[#24353d] border border-[#5a9ab5]/50 shadow-[0_0_30px_rgba(90,154,181,0.15)] rounded-2xl p-6 flex flex-col relative"
            >
              <div className="absolute top-0 left-1/2 -translate-x-1/2 -translate-y-1/2 bg-[#5a9ab5] text-white text-xs font-bold px-3 py-1 rounded-full uppercase tracking-wide">
                Most Popular
              </div>
              <h3 className="text-xl font-semibold text-white mb-2 flex items-center gap-2">
                Pro <Zap className="w-4 h-4 text-[#5a9ab5] fill-[#5a9ab5]" />
              </h3>
              <p className="text-white/60 text-sm mb-6 h-10">For serious content creators who need higher quality and volume.</p>
              <div className="mb-6">
                <span className="text-4xl font-bold text-white">${isAnnual ? "19" : "24"}</span>
                <span className="text-white/40">/mo</span>
              </div>
              <ul className="space-y-3 mb-8 flex-1">
                {["50 Video Generations/mo", "High Definition (1080p)", "Premium AI Voices", "Remove Watermarks", "Priority Support"].map((item, i) => (
                  <li key={i} className="flex items-center gap-3 text-sm text-white/90">
                    <CheckCircle2 className="w-4 h-4 text-[#5a9ab5] shrink-0" /> {item}
                  </li>
                ))}
              </ul>
              <Button onClick={() => handleUpgrade("Pro")} className="w-full bg-[#5a9ab5] hover:bg-[#7ab0c8] text-white py-6 rounded-xl font-medium text-base group">
                Upgrade to Pro <ArrowRight className="w-4 h-4 ml-2 group-hover:translate-x-1 transition-transform" />
              </Button>
            </motion.div>

            {/* Enterprise Tier */}
            <motion.div 
              initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.4 }}
              className="bg-[#333333] border border-white/10 rounded-2xl p-6 flex flex-col"
            >
              <h3 className="text-xl font-semibold text-white mb-2">Business</h3>
              <p className="text-white/50 text-sm mb-6 h-10">For teams scaling their video production pipelines.</p>
              <div className="mb-6">
                <span className="text-4xl font-bold text-white">${isAnnual ? "79" : "99"}</span>
                <span className="text-white/40">/mo</span>
              </div>
              <ul className="space-y-3 mb-8 flex-1">
                {["Unlimited Video Generations", "4K Ultra HD Exports", "Custom Branding", "API Access", "Dedicated Account Manager"].map((item, i) => (
                  <li key={i} className="flex items-center gap-3 text-sm text-white/80">
                    <CheckCircle2 className="w-4 h-4 text-white/40 shrink-0" /> {item}
                  </li>
                ))}
              </ul>
              <Button onClick={() => handleUpgrade("Business")} variant="outline" className="w-full bg-transparent border-white/20 hover:bg-white/10 text-white py-6 rounded-xl hover:border-white/30 transition-colors">
                Upgrade to Business
              </Button>
            </motion.div>
          </div>

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
