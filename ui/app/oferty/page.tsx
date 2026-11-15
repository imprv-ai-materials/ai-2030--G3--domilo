import BladApiKomunikat from "@/components/BladApiKomunikat";
import { fmtCzas, fmtM2, fmtProc, fmtZl, ofertyPonizejP10, type OfertaPonizejP10 } from "@/lib/api";
import Link from "next/link";

export const dynamic = "force-dynamic";

export default async function OfertyPonizejP10() {
  let oferty: OfertaPonizejP10[];
  try {
    oferty = await ofertyPonizejP10();
  } catch (e) {
    return (
      <>
        <h1>Oferty z ceną poniżej P10</h1>
        <BladApiKomunikat blad={e} />
      </>
    );
  }
  return (
    <>
      <h1>Oferty z ceną poniżej P10</h1>
      <p className="podtytul">
        Oferty, których cena ofertowa jest niższa od dolnej granicy przedziału wyceny (P10): {oferty.length}. Według
        modelu tylko 10% podobnych lokali sprzedaje się taniej, więc to kandydaci do sprawdzenia (okazja albo wada,
        której model nie widzi). Kolejność: od największego rabatu.
        {oferty[0] && ` Stan: ${fmtCzas(oferty[0].czas_przebiegu)}.`}
      </p>
      {oferty.length === 0 ? (
        <p>Brak takich ofert w ostatnich wycenach.</p>
      ) : (
        <table>
          <thead>
            <tr>
              <th>Oferta</th>
              <th>Miasto</th>
              <th>Dzielnica</th>
              <th className="liczba">Metraż</th>
              <th className="liczba">Cena ofertowa</th>
              <th className="liczba">P10</th>
              <th className="liczba">Wycena P50</th>
              <th className="liczba">P90</th>
              <th className="liczba">Cena poniżej P10 o</th>
            </tr>
          </thead>
          <tbody>
            {oferty.map((o) => (
              <tr key={o.id_obiektu}>
                <td className="id">
                  <Link href={`/karta/oferta/${encodeURIComponent(o.id_obiektu)}`}>{o.id_obiektu}</Link>
                </td>
                <td>{o.miasto ?? "—"}</td>
                <td>{o.dzielnica ?? "—"}</td>
                <td className="liczba">{fmtM2(o.metraz)}</td>
                <td className="liczba">{fmtZl(o.cena_ofertowa)}</td>
                <td className="liczba">{fmtZl(o.p10)}</td>
                <td className="liczba">{fmtZl(o.p50)}</td>
                <td className="liczba">{fmtZl(o.p90)}</td>
                <td className="liczba">{fmtProc(100 * (1 - o.cena_do_p10))}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </>
  );
}
