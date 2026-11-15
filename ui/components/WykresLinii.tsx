"use client";

// Wykres liniowy tygodni (skill dataviz): zmiana w czasie, jedna oś Y od zera.
// Kolor: forma „wyróżnienie”: metryka w kolorze serii 1 (niebieski), porównanie w szarości kontekstu
// (validate_palette.js: CVD ΔE 15,9, normal 17,8 / 17,0, kontrast >= 3:1 w obu trybach; szarość celowo bez nasycenia).
// Znaczniki: linia 2px (zaokrąglone złącza), kropka końcowa r = 4 z 2px pierścieniem tła, siatka hairline ciągła.
// Linia odniesienia: 1px ciągła w kolorze tekstu wyciszonego, z etykietą (nie seria, bez legendy).
// Etykiety: legenda dla >= 2 serii + etykieta przy końcu każdej linii; tekst w kolorach tekstu, nie serii.
// Interakcja: celownik przyciąga do najbliższego tygodnia, dymek z wartościami wszystkich serii (wartość pogrubiona,
// nazwa wtórna, klucz = krótka kreska koloru serii), klawiatura: strzałki po skupieniu wykresu. Tabela pod wykresem.

import { useRef, useState } from "react";

export type Jednostka = "zl_h" | "udzial" | "godz";

export type Seria = { nazwa: string; kolor: "seria-1" | "kontekst"; wartosci: (number | null)[] };

const SZEROKOSC = 760;
const WYSOKOSC = 250;
const LEWY = 64;
const PRAWY = 190;
const GORA = 14;
const DOL = 30;

// useGrouping "always": pl-PL domyślnie nie rozdziela tysięcy w liczbach czterocyfrowych (5497 -> 5 497).
const liczbaZl = new Intl.NumberFormat("pl-PL", { maximumFractionDigits: 0, useGrouping: "always" } as Intl.NumberFormatOptions);
const liczbaProc = new Intl.NumberFormat("pl-PL", { maximumFractionDigits: 1 });
const liczbaGodz = new Intl.NumberFormat("pl-PL", { maximumFractionDigits: 1 });

export function formatuj(v: number | null | undefined, j: Jednostka): string {
  if (v == null) return "brak";
  if (j === "zl_h") return `${liczbaZl.format(v)} zł/h`;
  if (j === "udzial") return `${liczbaProc.format(100 * v)}%`;
  return `${liczbaGodz.format(v)} h`;
}

function formatOsi(v: number, j: Jednostka): string {
  if (j === "zl_h") return liczbaZl.format(v);
  if (j === "udzial") return `${liczbaProc.format(100 * v)}%`;
  return liczbaGodz.format(v);
}

function ladnyKrok(maks: number, ile = 4): number {
  const surowy = maks / ile;
  const potega = 10 ** Math.floor(Math.log10(surowy));
  const r = surowy / potega;
  return (r <= 1 ? 1 : r <= 2 ? 2 : r <= 2.5 ? 2.5 : r <= 5 ? 5 : 10) * potega;
}

const krotkaData = (iso: string) =>
  new Date(`${iso}T12:00:00`).toLocaleDateString("pl-PL", { day: "numeric", month: "short" });
const miesiac = (iso: string) =>
  new Date(`${iso}T12:00:00`).toLocaleDateString("pl-PL", { month: "short", year: "2-digit" });

export default function WykresLinii({
  tytul,
  tygodnie,
  serie,
  jednostka,
  odniesienie,
  opisyTygodni,
}: {
  tytul: string;
  tygodnie: string[];
  serie: Seria[];
  jednostka: Jednostka;
  odniesienie?: { wartosc: number; etykieta: string };
  opisyTygodni?: string[];
}) {
  const [aktywny, setAktywny] = useState<number | null>(null);
  const ref = useRef<SVGSVGElement>(null);
  const n = tygodnie.length;
  if (n === 0) return <p>Brak danych do wykresu.</p>;

  const wszystkie = serie.flatMap((s) => s.wartosci.filter((v): v is number => v != null));
  if (odniesienie) wszystkie.push(odniesienie.wartosc);
  const krok = ladnyKrok(Math.max(...wszystkie, 0) * 1.05 || 1);
  const maksY = Math.ceil((Math.max(...wszystkie, 0) * 1.05 || 1) / krok) * krok;
  const szer = SZEROKOSC - LEWY - PRAWY;
  const wys = WYSOKOSC - GORA - DOL;
  const x = (i: number) => LEWY + (n === 1 ? szer / 2 : (i / (n - 1)) * szer);
  const y = (v: number) => GORA + wys - (v / maksY) * wys;
  const ticki = Array.from({ length: Math.round(maksY / krok) + 1 }, (_, i) => i * krok);

  // Podpisy osi X: przy długich seriach pierwszy tydzień kwartału (sty, kwi, lip, paź), przy krótkich co drugi tydzień.
  const kwartal = (t: string) => `${t.slice(0, 4)}-${Math.floor((Number(t.slice(5, 7)) - 1) / 3)}`;
  const podpisyX = tygodnie
    .map((t, i) => ({ t, i }))
    .filter(({ t, i }) => (n > 16 ? i > 0 && kwartal(t) !== kwartal(tygodnie[i - 1]) : i % 2 === 0 || i === n - 1));

  const sciezka = (w: (number | null)[]) => {
    let d = "";
    let pioro = false;
    w.forEach((v, i) => {
      if (v == null) {
        pioro = false;
        return;
      }
      d += `${pioro ? "L" : "M"}${x(i).toFixed(1)},${y(v).toFixed(1)}`;
      pioro = true;
    });
    return d;
  };

  // Etykiety na prawym marginesie: koniec każdej linii i linia odniesienia; rozsuwamy, gdy są bliżej niż 14px.
  type Etykieta = { tekst: string; yy: number; s?: Seria; i?: number };
  const etykiety: Etykieta[] = serie
    .map((s): Etykieta | null => {
      const i = s.wartosci.map((v) => v != null).lastIndexOf(true);
      return i < 0 ? null : { tekst: s.nazwa, s, i, yy: y(s.wartosci[i] as number) };
    })
    .filter((e): e is Etykieta => e !== null);
  if (odniesienie) etykiety.push({ tekst: odniesienie.etykieta, yy: y(odniesienie.wartosc) });
  etykiety.sort((a, b) => a.yy - b.yy);
  for (let k = 1; k < etykiety.length; k++) {
    if (etykiety[k].yy - etykiety[k - 1].yy < 14) etykiety[k].yy = etykiety[k - 1].yy + 14;
  }

  const kolor = (s: Seria) => (s.kolor === "seria-1" ? "var(--seria-1)" : "var(--seria-kontekst)");
  const naWskazniku = (e: React.PointerEvent<SVGSVGElement>) => {
    const r = ref.current?.getBoundingClientRect();
    if (!r) return;
    const px = ((e.clientX - r.left) / r.width) * SZEROKOSC;
    const i = n === 1 ? 0 : Math.round(((px - LEWY) / szer) * (n - 1));
    setAktywny(Math.min(n - 1, Math.max(0, i)));
  };
  const klawisz = (e: React.KeyboardEvent) => {
    if (e.key === "ArrowLeft") setAktywny((a) => Math.max(0, (a ?? n) - 1));
    if (e.key === "ArrowRight") setAktywny((a) => Math.min(n - 1, (a ?? -1) + 1));
    if (e.key === "Escape") setAktywny(null);
  };
  const opisDostepny = `${tytul}. ${serie
    .map((s) => {
      const ost = s.wartosci.map((v) => v != null).lastIndexOf(true);
      return `${s.nazwa}: ostatni tydzień ${ost >= 0 ? formatuj(s.wartosci[ost], jednostka) : "brak"}`;
    })
    .join("; ")}${odniesienie ? `; ${odniesienie.etykieta}` : ""}. Strzałki: tydzień po tygodniu.`;

  return (
    <div className="wykres">
      {serie.length >= 2 && (
        <div className="legenda">
          {serie.map((s) => (
            <span key={s.nazwa} className="klucz-linii" style={{ ["--kolor" as string]: kolor(s) }}>
              {s.nazwa}
            </span>
          ))}
        </div>
      )}
      <svg
        ref={ref}
        viewBox={`0 0 ${SZEROKOSC} ${WYSOKOSC}`}
        style={{ width: "100%", maxWidth: SZEROKOSC, display: "block", touchAction: "pan-y" }}
        role="img"
        aria-label={opisDostepny}
        tabIndex={0}
        onPointerMove={naWskazniku}
        onPointerLeave={() => setAktywny(null)}
        onFocus={() => setAktywny((a) => a ?? n - 1)}
        onBlur={() => setAktywny(null)}
        onKeyDown={klawisz}
      >
        {ticki.map((t) => (
          <g key={t}>
            <line x1={LEWY} x2={LEWY + szer} y1={y(t)} y2={y(t)} stroke={t === 0 ? "var(--os)" : "var(--siatka)"} />
            <text x={LEWY - 8} y={y(t)} textAnchor="end" dominantBaseline="middle" fontSize={11} fill="var(--wyciszony)">
              {formatOsi(t, jednostka)}
            </text>
          </g>
        ))}
        {podpisyX.map(({ t, i }) => (
          <text key={t} x={x(i)} y={WYSOKOSC - 10} textAnchor="middle" fontSize={11} fill="var(--wyciszony)">
            {n > 16 ? miesiac(t) : krotkaData(t)}
          </text>
        ))}
        {odniesienie && (
          <g>
            <line
              x1={LEWY}
              x2={LEWY + szer}
              y1={y(odniesienie.wartosc)}
              y2={y(odniesienie.wartosc)}
              stroke="var(--tekst-3)"
              strokeWidth={1}
            />
          </g>
        )}
        {serie.map((s) => (
          <path
            key={s.nazwa}
            d={sciezka(s.wartosci)}
            fill="none"
            stroke={kolor(s)}
            strokeWidth={2}
            strokeLinejoin="round"
            strokeLinecap="round"
          />
        ))}
        {etykiety.map(({ tekst, yy, s, i }) => (
          <g key={tekst}>
            {s && i !== undefined && (
              <circle cx={x(i)} cy={y(s.wartosci[i] as number)} r={4} fill={kolor(s)} stroke="var(--powierzchnia)" strokeWidth={2} />
            )}
            <text x={LEWY + szer + 10} y={yy} dominantBaseline="middle" fontSize={12} fill="var(--tekst-2)">
              {tekst}
            </text>
          </g>
        ))}
        {aktywny !== null && (
          <g pointerEvents="none">
            <line x1={x(aktywny)} x2={x(aktywny)} y1={GORA} y2={GORA + wys} stroke="var(--tekst-3)" strokeWidth={1} />
            {serie.map((s) =>
              s.wartosci[aktywny] == null ? null : (
                <circle
                  key={s.nazwa}
                  cx={x(aktywny)}
                  cy={y(s.wartosci[aktywny] as number)}
                  r={4}
                  fill={kolor(s)}
                  stroke="var(--powierzchnia)"
                  strokeWidth={2}
                />
              ),
            )}
          </g>
        )}
      </svg>
      {aktywny !== null && (
        <div
          className="dymek"
          style={{
            left: `${(x(aktywny) / SZEROKOSC) * 100}%`,
            top: 8,
            transform: x(aktywny) > SZEROKOSC / 2 ? "translateX(calc(-100% - 12px))" : "translateX(12px)",
          }}
        >
          <div className="dymek-tytul">tydzień od {krotkaData(tygodnie[aktywny])}</div>
          {serie.map((s) => (
            <div key={s.nazwa} className="dymek-wiersz">
              <span className="klucz" style={{ background: kolor(s) }} />
              <strong>{formatuj(s.wartosci[aktywny], jednostka)}</strong> <span>{s.nazwa}</span>
            </div>
          ))}
          {odniesienie && <div className="dymek-wiersz wtorny">{odniesienie.etykieta}</div>}
          {opisyTygodni?.[aktywny] && <div className="dymek-wiersz wtorny">{opisyTygodni[aktywny]}</div>}
        </div>
      )}
      <details>
        <summary>Tabela: {tytul.toLowerCase()}</summary>
        <table>
          <thead>
            <tr>
              <th>Tydzień od</th>
              {serie.map((s) => (
                <th key={s.nazwa} className="liczba">
                  {s.nazwa}
                </th>
              ))}
              {opisyTygodni && <th>Uwagi</th>}
            </tr>
          </thead>
          <tbody>
            {tygodnie.map((t, i) => (
              <tr key={t}>
                <td>{t}</td>
                {serie.map((s) => (
                  <td key={s.nazwa} className="liczba">
                    {formatuj(s.wartosci[i], jednostka)}
                  </td>
                ))}
                {opisyTygodni && <td className="powod">{opisyTygodni[i]}</td>}
              </tr>
            ))}
          </tbody>
        </table>
      </details>
    </div>
  );
}
