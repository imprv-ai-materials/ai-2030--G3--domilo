import BladApiKomunikat from "@/components/BladApiKomunikat";
import WykresCzynnikow from "@/components/WykresCzynnikow";
import { BladApi, fmtCzas, fmtM2, fmtZl, kartaWyceny, type KartaWyceny } from "@/lib/api";
import { notFound } from "next/navigation";

export const dynamic = "force-dynamic";

export default async function Karta({ params }: { params: Promise<{ rodzaj: string; id: string }> }) {
  const { rodzaj, id } = await params;
  const idObiektu = decodeURIComponent(id);
  let k: KartaWyceny;
  try {
    k = await kartaWyceny(rodzaj, idObiektu);
  } catch (e) {
    if (e instanceof BladApi && e.status === 404) notFound();
    return <BladApiKomunikat blad={e} />;
  }
  const powody = k.powod ? k.powod.split("; ") : [];

  return (
    <>
      <h1>
        Karta wyceny: {k.rodzaj === "lokal" ? "lokal Domilo" : "oferta"} {k.id_obiektu}
      </h1>
      <p className="podtytul">
        {k.miasto ?? "—"}, {k.dzielnica ?? "—"}, {fmtM2(k.metraz)} · model {k.wersja_modelu} · przebieg{" "}
        {fmtCzas(k.czas_przebiegu)}
      </p>

      {k.odmowa ? (
        <div className="uwaga" role="status">
          <strong>Model nie wycenia tego obiektu („nie wiem”).</strong> Potrzebna wycena rzeczoznawcy. Powody:
          <ul>
            {powody.map((p) => (
              <li key={p}>{p}</li>
            ))}
          </ul>
        </div>
      ) : (
        <div className="kafle">
          <div className="kafel">
            <div className="etykieta">Wycena (P50)</div>
            <div className="wartosc">{fmtZl(k.p50)}</div>
          </div>
          <div className="kafel">
            <div className="etykieta">Przedział 80% (P10–P90)</div>
            <div className="wartosc">
              {fmtZl(k.p10)} – {fmtZl(k.p90)}
            </div>
          </div>
          {k.cena_ofertowa != null && (
            <div className="kafel">
              <div className="etykieta">Cena ofertowa</div>
              <div className="wartosc">{fmtZl(k.cena_ofertowa)}</div>
            </div>
          )}
        </div>
      )}

      {!k.odmowa && (
        <>
          <h2>Co składa się na wycenę</h2>
          <WykresCzynnikow czynniki={k.czynniki} wartoscBazowa={k.wartosc_bazowa} wycena={k.p50} />
        </>
      )}

      <h2>Historia wycen</h2>
      <table>
        <thead>
          <tr>
            <th>Przebieg</th>
            <th className="liczba">P10</th>
            <th className="liczba">P50</th>
            <th className="liczba">P90</th>
            <th>Odmowa</th>
          </tr>
        </thead>
        <tbody>
          {k.historia.map((h) => (
            <tr key={h.czas_przebiegu}>
              <td>{fmtCzas(h.czas_przebiegu)}</td>
              <td className="liczba">{fmtZl(h.p10)}</td>
              <td className="liczba">{fmtZl(h.p50)}</td>
              <td className="liczba">{fmtZl(h.p90)}</td>
              <td>{h.odmowa ? "tak" : "nie"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  );
}
