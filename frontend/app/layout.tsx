import type { Metadata, Viewport } from "next";
import { Space_Grotesk } from "next/font/google";

import { AppProviders } from "@/components/providers/AppProviders";

import "./globals.css";

const spaceGrotesk = Space_Grotesk({
  subsets: ["latin"],
  variable: "--font-space-grotesk",
  display: "swap",
});

export const metadata: Metadata = {
  metadataBase: new URL("https://fairswarm.app"),
  title: {
    default: "FairSwarm",
    template: "%s | FairSwarm",
  },
  description: "Swarm Intelligence AI Bias Detection Platform",
  applicationName: "FairSwarm",
  icons: {
    icon: "/favicon.ico",
  },
  openGraph: {
    title: "FairSwarm",
    description: "Swarm-based fairness detection across sensitive attributes.",
    type: "website",
    url: "https://fairswarm.app",
    images: [
      {
        url: "/og-fairswarm.png",
        width: 1200,
        height: 630,
        alt: "FairSwarm Dashboard Preview",
      },
    ],
  },
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  maximumScale: 1,
  themeColor: "#040B14",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body className={`${spaceGrotesk.variable} min-h-screen bg-background font-sans antialiased`}>
        <AppProviders>
          <main className="min-h-screen">{children}</main>
        </AppProviders>
      </body>
    </html>
  );
}
