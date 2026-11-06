"use client";

import React, { useContext, useRef, useState, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { usePathname } from "next/navigation";
import { LayoutRouterContext } from "next/dist/shared/lib/app-router-context.shared-runtime";

/**
 * FrozenRoute freezes the Next.js App Router context during the exit animation,
 * allowing AnimatePresence mode="wait" to render the outgoing route's visual tree
 * while it animates out over 0.25s, before unmounting and mounting the incoming route.
 */
function FrozenRoute({ children }: { children: React.ReactNode }) {
  const context = useContext(LayoutRouterContext ?? {});
  const frozenContext = useRef(context).current;
  const frozenChildren = useRef(children).current;

  return (
    <LayoutRouterContext.Provider value={frozenContext}>
      {frozenChildren}
    </LayoutRouterContext.Provider>
  );
}

export interface PageTransitionProps {
  children: React.ReactNode;
}

export function PageTransition({ children }: PageTransitionProps) {
  const pathname = usePathname();
  const [isReduced, setIsReduced] = useState<boolean>(false);

  useEffect(() => {
    const q = window.matchMedia("(prefers-reduced-motion: reduce)");
    setIsReduced(q.matches);
    const handler = (e: MediaQueryListEvent) => setIsReduced(e.matches);
    q.addEventListener("change", handler);
    return () => q.removeEventListener("change", handler);
  }, []);

  // Respect prefers-reduced-motion
  if (isReduced) {
    return <main className="flex-1 w-full">{children}</main>;
  }

  return (
    <AnimatePresence mode="wait" initial={false}>
      <motion.main
        key={pathname}
        className="flex-1 w-full"
        initial={{ opacity: 0, y: 12, filter: "blur(4px)" }}
        animate={{
          opacity: 1,
          y: 0,
          filter: "blur(0px)",
          transition: { duration: 0.35, ease: "easeOut" },
          transitionEnd: { transform: "none", filter: "none" },
        }}
        exit={{
          opacity: 0,
          y: -12,
          filter: "blur(4px)",
          transition: { duration: 0.25, ease: "easeIn" },
        }}
      >
        <FrozenRoute>{children}</FrozenRoute>
      </motion.main>
    </AnimatePresence>
  );
}
