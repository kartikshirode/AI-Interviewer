import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";

const inter = Inter({ subsets: ["latin"] });

export const metadata: Metadata = {
  title: "AI Interviewer",
  description: "Fully automated AI interview platform - free forever",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="dark">
      <body
        suppressHydrationWarning
        className={`${inter.className} antialiased bg-slate-900 text-white min-h-screen`}
      >
        {children}
      </body>
    </html>
  );
}
