import type { Metadata, Viewport } from "next";
import "./globals.css";
import Nav from "@/components/Nav";

export const metadata: Metadata = {
  title: "TradingAgents",
  description: "Transparent multi-agent trading analysis — backtests, journal, and decisions.",
  manifest: "/manifest.webmanifest",
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  maximumScale: 1,
  themeColor: "#0e1117",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <div className="app">
          <header className="topbar">
            <span className="logo">📈 TradingAgents</span>
          </header>
          <main className="content">{children}</main>
          <Nav />
        </div>
      </body>
    </html>
  );
}
