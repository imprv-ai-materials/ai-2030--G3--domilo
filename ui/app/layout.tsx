import type { Metadata } from "next";
import Link from "next/link";
import type { ReactNode } from "react";
import "./globals.css";

export const metadata: Metadata = {
  title: "Domilo · panele",
  description: "Panel rzeczoznawcy (wyceny) i panel kierownika zespołu najmu (kolejka zapytań)",
};

export default function Layout({ children }: { children: ReactNode }) {
  return (
    <html lang="pl">
      <body>
        <header className="pasek">
          <strong>Domilo · panele</strong>
          <nav>
            <Link href="/">Kolejka „nie wiem”</Link>
            <Link href="/oferty">Oferty poniżej P10</Link>
            <Link href="/zespol">Zespół najmu</Link>
          </nav>
        </header>
        <main>{children}</main>
      </body>
    </html>
  );
}
