"use client";

// Pominięcia według powodu: poziome słupki od wspólnej osi (wielkość, jedna seria -> jeden kolor, bez legendy).
// Znaczniki wg skilla dataviz: słupek 18 px (<= 24), 4 px zaokrąglenia tylko na końcu z danymi, kwadratowo przy osi;
// wartość przy końcu słupka w kolorze tekstu; cały wiersz jest celem najechania i skupienia (dymek z udziałem).

import { useState } from "react";
import type { PowodPominiecia } from "@/lib/api";

const WIERSZ = 30;
const GRUBOSC = 18;
const PROMIEN = 4;
const SZEROKOSC = 760;
const ETYKIETY = 270;
const MARGINES = 80;

function slupek(x0: number, x1: number, y: number, h: number): string {
  const r = Math.min(PROMIEN, x1 - x0, h / 2);
  if (x1 - x0 <= 0) return "";
  return `M${x0},${y} H${x1 - r} Q${x1},${y} ${x1},${y + r} V${y + h - r} Q${x1},${y + h} ${x1 - r},${y + h} H${x0} Z`;
}

export default function WykresPowodow({ powody }: { powody: PowodPominiecia[] }) {
  const [aktywny, setAktywny] = useState<number | null>(null);
  const suma = powody.reduce((s, p) => s + p.pominiecia, 0);
  const maks = Math.max(...powody.map((p) => p.pominiecia), 1);
  const skala = (v: number) => ETYKIETY + (v / maks) * (SZEROKOSC - ETYKIETY - MARGINES);
  const wysokosc = powody.length * WIERSZ + 4;
  const proc = (v: number) => `${((100 * v) / Math.max(suma, 1)).toFixed(1).replace(".", ",")}%`;

  return (
    <div className="wykres">
      <svg
        viewBox={`0 0 ${SZEROKOSC} ${wysokosc}`}
        style={{ width: "100%", maxWidth: SZEROKOSC, display: "block" }}
        role="img"
        aria-label={`Pominięcia według powodu: ${powody.map((p) => `${p.opis} ${p.pominiecia}`).join("; ")}`}
        onMouseLeave={() => setAktywny(null)}
      >
        <line x1={ETYKIETY} x2={ETYKIETY} y1={0} y2={wysokosc} stroke="var(--os)" />
        {powody.map((p, i) => {
          const y = i * WIERSZ + (WIERSZ - GRUBOSC) / 2;
          const x1 = skala(p.pominiecia);
          return (
            <g
              key={p.powod}
              tabIndex={0}
              onMouseEnter={() => setAktywny(i)}
              onFocus={() => setAktywny(i)}
              onBlur={() => setAktywny(null)}
            >
              <rect x={0} y={i * WIERSZ} width={SZEROKOSC} height={WIERSZ} fill="transparent" />
              <text x={ETYKIETY - 10} y={y + GRUBOSC / 2} textAnchor="end" dominantBaseline="middle" fontSize={13} fill="var(--tekst)">
                {p.opis}
              </text>
              <path d={slupek(ETYKIETY, x1, y, GRUBOSC)} fill="var(--seria-1)" opacity={aktywny === null || aktywny === i ? 1 : 0.5} />
              <text x={x1 + 8} y={y + GRUBOSC / 2} dominantBaseline="middle" fontSize={12} fill="var(--tekst-2)">
                {p.pominiecia}
              </text>
            </g>
          );
        })}
      </svg>
      {aktywny !== null && (
        <div className="dymek" style={{ left: `${(ETYKIETY / SZEROKOSC) * 100}%`, top: aktywny * WIERSZ + 30 }}>
          <strong>{powody[aktywny].pominiecia}</strong> {powody[aktywny].opis} ({proc(powody[aktywny].pominiecia)} pominięć;{" "}
          w górnym decylu: {powody[aktywny].w_gornym_decylu})
        </div>
      )}
    </div>
  );
}
