// @ts-ignore
import "./globals.css";
import type { Metadata } from "next";
import { Mona_Sans } from "next/font/google";

const monaSans = Mona_Sans({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "Zyra on Gnani",
  description: "Agentic AI voice interviewer in English, Hindi, Hinglish and Marathi, powered by Gnani Prisma and Timbre",
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