import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import { Shell } from "@/components/layout/Shell";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
  display: "swap",
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
  display: "swap",
});

export const metadata: Metadata = {
  title: "Raphael — Materials Demand Forecasting & Reorder Platform",
  description:
    "Intelligent demand forecasting, lead-time uncertainty prediction, and inventory replenishment decision layer for materials catalog.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="en"
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased dark`}
    >
      <body className="min-h-full bg-[#000000] text-zinc-100 selection:bg-[#00F2FE]/30 selection:text-white">
        <Shell>{children}</Shell>
      </body>
    </html>
  );
}
