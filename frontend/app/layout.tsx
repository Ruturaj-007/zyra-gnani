// @ts-ignore
import "./globals.css";
import type { Metadata } from "next";
import { Mona_Sans } from "next/font/google";

const monaSans = Mona_Sans({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "Zyra.ai",
  description: "Agentic AI voice interviewer that adapts to every answer",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" className="dark">
      <body className={`${monaSans.className} antialiased pattern`}>
        {children}
      </body>
    </html>
  );
}