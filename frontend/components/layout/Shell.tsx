"use client";

import { usePathname } from "next/navigation";
import { SmoothScrollProvider } from "@/components/motion/SmoothScrollProvider";
import { PageTransition } from "@/components/motion/PageTransition";
import { Navbar } from "./Navbar";
import { Footer } from "./Footer";
import { PageBackdrop } from "./PageBackdrop";

export interface ShellProps {
  children: React.ReactNode;
}

export function Shell({ children }: ShellProps) {
  const pathname = usePathname();
  const isHome = pathname === "/";

  return (
    <SmoothScrollProvider>
      <div className="min-h-screen flex flex-col bg-[#000000] text-zinc-100 selection:bg-[#00F2FE]/30 selection:text-white relative">
        {/* Shared page backdrop: fixed, behind all content, pointer-events none.
            Home keeps its original faint aurora; app pages get the aurora system. */}
        <PageBackdrop />

        {/* Global Floating Pill Navbar */}
        <Navbar />

        {/* Page Content with Frozen Router Route Transitions */}
        <div className={`flex-1 flex flex-col z-10 ${isHome ? "pt-0" : "pt-36 sm:pt-32"}`}>
          <PageTransition>{children}</PageTransition>
        </div>

        {/* Global Footer */}
        <Footer />
      </div>
    </SmoothScrollProvider>
  );
}
