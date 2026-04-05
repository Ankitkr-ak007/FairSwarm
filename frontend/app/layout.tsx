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
      <head>
        <meta
          httpEquiv="Content-Security-Policy"
          content="default-src 'self'; connect-src 'self'; img-src 'self' data: blob:; script-src 'self' https://cdnjs.cloudflare.com; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://cdnjs.cloudflare.com; font-src 'self' https://fonts.gstatic.com https://cdnjs.cloudflare.com data:; frame-ancestors 'none'; object-src 'none'; base-uri 'self'"
        />
      </head>
      <body className={`${spaceGrotesk.variable} min-h-screen bg-background font-sans antialiased`}>
        <a href="#main-content" className="skip-link">
          Skip to main content
        </a>
        <AppProviders>
          <main id="main-content" className="min-h-screen" tabIndex={-1}>
            {children}
          </main>
        </AppProviders>
      </body>
    </html>
  );
}
