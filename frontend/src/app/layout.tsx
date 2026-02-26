import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
});

export const metadata: Metadata = {
  title: "Content Factory",
  description: "AI-powered content engine.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body
        className={`${inter.variable} antialiased relative`}
      >
        <div className="fixed top-0 right-0 pointer-events-none select-none z-0">
          <img
            src="/Ellipse%201.svg"
            alt=""
            className="w-[600px] h-[600px] object-cover translate-x-1/3 -translate-y-1/4 opacity-80"
          />
        </div>
        <div className="relative z-10">{children}</div>
      </body>
    </html>
  );
}
