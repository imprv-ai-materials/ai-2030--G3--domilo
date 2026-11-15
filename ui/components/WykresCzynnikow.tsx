"use client";

// Wykres wkładów cech (SHAP) w PLN: poziome słupki rozbieżne od wspólnej osi zero.
// Forma: biegunowość (podnosi / obniża wycenę) -> para rozbieżna niebieski / czerwony (globals.css, zwalidowana).
// Znaczniki wg skilla dataviz: słupek 18 px (<= 24), zaokrąglony 4 px tylko na końcu z danymi, kwadratowy przy osi;
// wartość przy końcu słupka w kolorze tekstu; legenda dla dwóch kolorów; podpowiedź po najechaniu (cel = cały wiersz);
// tabela jako widok alternatywny (details pod wykresem).

import { useState } from "react";
import type { Czynnik } from "@/lib/api";

const WYSOKOSC_WIERSZA = 26;
const GRUBOSC = 18;
const PROMIEN = 4;
const SZEROKOSC = 760;
const ETYKIETY = 250;
const MARGINES_WARTOSCI = 96;

const zl = new Intl.NumberFormat("pl-PL", { maximumFractionDigits: 0, signDisplay: "always" });

function sciezkaSlupka(x0: number, x1: number, y: number, h: number): string {
  // Kwadratowo przy osi (x0), zaokrąglenie PROMIEN na końcu z danymi (x1), w obie strony osi.
  const r = Math.min(PROMIEN, Math.abs(x1 - x0), h / 2);
  if (x1 >= x0) {
    return `M${x0},${y} H${x1 - r} Q${x1},${y} ${x1},${y + r} V${y + h - r} Q${x1},${y + h} ${x1 - r},${y + h} H${x0} Z`;
  }
  return `M${x0},${y} H${x1 + r} Q${x1},${y} ${x1},${y + r} V${y + h - r} Q${x1},${y + h} ${x1 + r},${y + h} H${x0} Z`;
}

export default function WykresCzynnikow({
  czynniki,
  wartoscBazowa,
  wycena,
  ile = 10,
}: {
  czynniki: Czynnik[];
  wartoscBazowa: number | null;
  wycena: number | null;
  ile?: number;
}) {
  const [aktywny, setAktywny] = useState<number | null>(null);
  const najwazniejsze = czynniki.slice(0, ile);
  const reszta = czynniki.slice(ile);
  const wiersze: Czynnik[] = reszta.length
    ? [
        ...najwazniejsze,
        {
          cecha: "pozostale",
          opis: `pozostałe cechy (${reszta.length})`,
          wplyw_pln: reszta.reduce((s, c) => s + c.wplyw_pln, 0),
        },
      ]
    : najwazniejsze;
  if (wiersze.length === 0) return <p>Brak czynników: model nie wycenił tego obiektu.</p>;

  const maks = Math.max(...wiersze.map((c) => Math.abs(c.wplyw_pln)), 1);
  const polowa = (SZEROKOSC - ETYKIETY - 2 * MARGINES_WARTOSCI) / 2;
  const os = ETYKIETY + MARGINES_WARTOSCI + polowa;
  const skala = (v: number) => os + (v / maks) * polowa;
  const wysokosc = wiersze.length * WYSOKOSC_WIERSZA + 8;
  const suma = czynniki.reduce((s, c) => s + c.wplyw_pln, 0);
  const opisDostepny = wiersze.map((c) => `${c.opis}: ${zl.format(c.wplyw_pln)} zł`).join("; ");

  return (
    <div className="wykres">
      <div className="legenda">
        <span style={{ ["--kolor" as string]: "var(--wzrost)" }}>podnosi wycenę</span>
        <span style={{ ["--kolor" as string]: "var(--spadek)" }}>obniża wycenę</span>
      </div>
      <svg
        viewBox={`0 0 ${SZEROKOSC} ${wysokosc}`}
        style={{ width: "100%", maxWidth: SZEROKOSC, display: "block" }}
        role="img"
        aria-label={`Wpływ cech na wycenę w złotych: ${opisDostepny}`}
        onMouseLeave={() => setAktywny(null)}
      >
        <line x1={os} x2={os} y1={0} y2={wysokosc} stroke="var(--linia)" strokeWidth={1} />
        {wiersze.map((c, i) => {
          const y = i * WYSOKOSC_WIERSZA + (WYSOKOSC_WIERSZA - GRUBOSC) / 2;
          const x1 = skala(c.wplyw_pln);
          const plus = c.wplyw_pln >= 0;
          return (
            <g key={c.cecha} onMouseEnter={() => setAktywny(i)} onFocus={() => setAktywny(i)} tabIndex={0}>
              <rect x={0} y={i * WYSOKOSC_WIERSZA} width={SZEROKOSC} height={WYSOKOSC_WIERSZA} fill="transparent" />
              <text x={ETYKIETY - 8} y={y + GRUBOSC / 2} dominantBaseline="middle" textAnchor="end" fill="var(--tekst)" fontSize={13}>
                {c.opis}
              </text>
              <path
                d={sciezkaSlupka(os, x1, y, GRUBOSC)}
                fill={plus ? "var(--wzrost)" : "var(--spadek)"}
                opacity={aktywny === null || aktywny === i ? 1 : 0.45}
              />
              <text
                x={plus ? x1 + 6 : x1 - 6}
                y={y + GRUBOSC / 2}
                dominantBaseline="middle"
                textAnchor={plus ? "start" : "end"}
                fill="var(--tekst-2)"
                fontSize={12}
              >
                {zl.format(c.wplyw_pln)} zł
              </text>
            </g>
          );
        })}
      </svg>
      {aktywny !== null && (
        <div className="dymek" style={{ left: `${(ETYKIETY / SZEROKOSC) * 100}%`, top: aktywny * WYSOKOSC_WIERSZA + 40 }}>
          <strong>{wiersze[aktywny].opis}</strong>: {zl.format(wiersze[aktywny].wplyw_pln)} zł
          {wycena ? ` (${((100 * wiersze[aktywny].wplyw_pln) / wycena).toFixed(1).replace(".", ",")}% wyceny)` : ""}
        </div>
      )}
      <p className="podtytul">
        Punkt wyjścia: wycena „przeciętnego” lokalu z treningu{" "}
        {wartoscBazowa != null && `${new Intl.NumberFormat("pl-PL").format(Math.round(wartoscBazowa))} zł`}; suma
        wszystkich wkładów {zl.format(suma)} zł daje wycenę P50
        {wycena != null && ` ${new Intl.NumberFormat("pl-PL").format(Math.round(wycena))} zł`}.
      </p>
      <details>
        <summary>Tabela: wszystkie cechy ({czynniki.length})</summary>
        <table>
          <thead>
            <tr>
              <th>Cecha</th>
              <th className="liczba">Wpływ na wycenę</th>
            </tr>
          </thead>
          <tbody>
            {czynniki.map((c) => (
              <tr key={c.cecha}>
                <td>{c.opis}</td>
                <td className="liczba">{zl.format(c.wplyw_pln)} zł</td>
              </tr>
            ))}
          </tbody>
        </table>
      </details>
    </div>
  );
}
