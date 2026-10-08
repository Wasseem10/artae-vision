import type { Metadata } from "next";
import { Geist } from "next/font/google";

import "@fontsource/ibm-plex-sans/400.css";
import "./globals.css";

const bodyFont = Geist({ subsets: ["latin"], variable: "--font-body" });
const displayFont = Geist({ subsets: ["latin"], variable: "--font-display" });

export const metadata: Metadata = {
  title: "Artae Vision · Video, evidence, human review",
  description: "Explore an experimental computer-vision monitor with on-device pose detection, recorded evidence, human review, and reproducible fall-detection evaluation.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" data-scroll-behavior="smooth">
      <body className={`${bodyFont.variable} ${displayFont.variable}`}>{children}</body>
    </html>
  );
}
