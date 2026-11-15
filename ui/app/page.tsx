import BladApiKomunikat from "@/components/BladApiKomunikat";
import { fmtCzas, fmtM2, fmtZl, kolejkaNieWiem, type PozycjaKolejki } from "@/lib/api";
import Link from "next/link";

export const dynamic = "force-dynamic";

const liczba = (x: number) => x.toLocaleString("pl-PL", { useGrouping: "always" } as Intl.NumberFormatOptions);

const FILTRY = [
  { wartosc: "", etykieta: "Wszystkie" },
  { wartosc: "lokal", etykieta: "Lokale Domilo" },
  { wartosc: "oferta", etykieta: "Oferty" },
];

export default async function KolejkaNieWiem({ searchParams }: { searchParams: Promise<{ rodzaj?: string }> }) {
  const { rodzaj = "" } = await searchParams;
  let pozycje: PozycjaKolejki[];
  try {
    pozycje = await kolejkaNieWiem();
  } catch (e) {
    return (
      <>
        <h1>Kolejka „nie wiem”</h1>
        <BladApiKomunikat blad={e} />
      </>
    );
  }
  const widoczne = rodzaj ? pozycje.filter((p) => p.rodzaj === rodzaj) : pozycje;
  const lokale = pozycje.filter((p) => p.rodzaj === "lokal").length;

  return (
    <>
      <h1>Kolejka „nie wiem”</h1>
      <p className="podtytul">
        Obiekty, których model nie wycenił w ostatnim przebiegu nocnym: {liczba(pozycje.length)} ({liczba(lokale)} lokali Domilo,{" "}
        {liczba(pozycje.length - lokale)} ofert). Każdy wymaga wyceny rzeczoznawcy; powód podaje detektor danych spoza zakresu.
        {pozycje[0] && ` Stan: ${fmtCzas(pozycje[0].czas_przebiegu)}.`}
      </p>
      <nav className="filtry" aria-label="Rodzaj obiektu">
        {FILTRY.map((f) => (
          <Link key={f.wartosc} href={f.wartosc ? `/?rodzaj=${f.wartosc}` : "/"} aria-current={f.wartosc === rodzaj ? "page" : undefined}>
            {f.etykieta}
          </Link>
        ))}
      </nav>
      {widoczne.length === 0 ? (
        <p>Brak pozycji w kolejce.</p>
      ) : (
        <table>
          <thead>
            <tr>
              <th>Rodzaj</th>
              <th>Obiekt</th>
              <th>Miasto</th>
              <th>Dzielnica</th>
              <th className="liczba">Metraż</th>
              <th className="liczba">Cena ofertowa</th>
              <th>Powód</th>
            </tr>
          </thead>
          <tbody>
            {widoczne.map((p) => (
              <tr key={`${p.rodzaj}-${p.id_obiektu}`}>
                <td>{p.rodzaj === "lokal" ? "lokal" : "oferta"}</td>
                <td className="id">
                  <Link href={`/karta/${p.rodzaj}/${encodeURIComponent(p.id_obiektu)}`}>{p.id_obiektu}</Link>
                </td>
                <td>{p.miasto ?? "—"}</td>
                <td>{p.dzielnica ?? "—"}</td>
                <td className="liczba">{fmtM2(p.metraz)}</td>
                <td className="liczba">{fmtZl(p.cena_ofertowa)}</td>
                <td className="powod">{p.powod ?? "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </>
  );
}
