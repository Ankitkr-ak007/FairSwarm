import type { Metadata } from 'next'
import './globals.css'

export const metadata: Metadata = {
  title: 'FairSwarm',
  description: 'Swarm Intelligence AI Bias Detection Platform',
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en" className="dark">
      <body className="antialiased min-h-screen bg-background">
        <main className="flex min-h-screen flex-col items-center justify-between">
          {children}
        </main>
      </body>
    </html>
  )
}
