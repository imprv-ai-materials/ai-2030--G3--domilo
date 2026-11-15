import type { Metadata } from "next";
import Link from "next/link";
import type { ReactNode } from "react";
import "./globals.css";

export const metadata: Metadata = {
  title: "Domilo · panel rzeczoznawcy",
  description: "Kolejka „nie wiem”, oferty poniżej P10 i karty wycen modelu wyceny Domilo",
};

export default function Layout({ children }: { children: ReactNode }) {
  return (
    <html lang="pl">
      <body>
        <header className="pasek">
          <strong>Domilo · panel rzeczoznawcy</strong>
          <nav>
            <Link href="/">Kolejka „nie wiem”</Link>
            <Link href="/oferty">Oferty poniżej P10</Link>
          </nav>
        </header>
        <main>{children}</main>
      </body>
    </html>
  );
}
