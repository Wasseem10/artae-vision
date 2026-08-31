import type { Metadata } from "next";
import { Geist } from "next/font/google";

import "./globals.css";

const bodyFont = Geist({ subsets: ["latin"], variable: "--font-body" });
const displayFont = Geist({ subsets: ["latin"], variable: "--font-display" });

export const metadata: Metadata = {
  title: "Artae Vision · Tell your cameras what to watch for",
  description: "Turn live cameras and uploaded video into plain-language visual alerts and real actions.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" data-scroll-behavior="smooth">
      <body className={`${bodyFont.variable} ${displayFont.variable}`}>{children}</body>
    </html>
  );
}
