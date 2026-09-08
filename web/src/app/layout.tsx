import type { Metadata } from "next";
import { Spectral, Karla } from "next/font/google";
import "./globals.css";

// Handbook typography: Spectral for narrative and names, Karla for UI.
const spectral = Spectral({
  variable: "--font-spectral",
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  style: ["normal", "italic"],
});

const karla = Karla({
  variable: "--font-karla",
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
});

export const metadata: Metadata = {
  title: "QuestAI",
  description: "A tabletop tale, told one command at a time.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className={`${spectral.variable} ${karla.variable} antialiased`}>
        {children}
      </body>
    </html>
  );
}
