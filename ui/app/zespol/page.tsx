import BladApiKomunikat from "@/components/BladApiKomunikat";
import WykresLinii from "@/components/WykresLinii";
import WykresPowodow from "@/components/WykresPowodow";
import {
  fmtCzas,
  fmtData,
  fmtGodz,
  fmtUdzial,
  fmtZl,
  panelKierownika,
  type PanelKierownika,
  type ZrodloKolejki,
} from "@/lib/api";
import Link from "next/link";

// Panel kierownika zespołu najmu. Wszystkie liczby z modeli dbt (schemat metryki, api/api/data_platform/dbt/models/
// panel) przez GET /team/dashboard; tu tylko wybór okresu i formatowanie. Opis metryk: docs/kolejka_panel.md.

export const dynamic = "force-dynamic";

const ZRODLA: Record<ZrodloKolejki, string> = {
  symulacja_wstecz: "Symulacja wstecz (przed wdrożeniem)",
  zadanie: "Kolejka w CRM (zadanie 05:30)",
};

// useGrouping "always": pl-PL domyślnie nie rozdziela tysięcy w liczbach czterocyfrowych.
const calkowita = new Intl.NumberFormat("pl-PL", { maximumFractionDigits: 0, useGrouping: "always" } as Intl.NumberFormatOptions);
const liczba = (x: number | null | undefined) => (x == null ? "—" : calkowita.format(x));
const zlh = (x: number | null | undefined) => (x == null ? "—" : `${calkowita.format(x)} zł/h`);

function Kafel({ etykieta, wartosc, opis }: { etykieta: string; wartosc: string; opis: string }) {
  return (
    <div className="kafel">
      <div className="etykieta">{etykieta}</div>
      <div className="wartosc">{wartosc}</div>
      <div className="opis">{opis}</div>
    </div>
  );
}

export default async function PanelZespolu({ searchParams }: { searchParams: Promise<{ zrodlo?: string }> }) {
  const { zrodlo: wybrane } = await searchParams;
  let d: PanelKierownika;
  try {
    d = await panelKierownika();
  } catch (e) {
    return (
      <>
        <h1>Panel kierownika zespołu najmu</h1>
        <BladApiKomunikat blad={e} />
      </>
    );
  }

  const okresy = d.okresy.adopcja;
  const domyslne = (okresy.find((o) => o.dni_z_kontaktami > 0) ?? okresy[0])?.zrodlo_kolejki;
  const zrodlo = (okresy.some((o) => o.zrodlo_kolejki === wybrane) ? wybrane : domyslne) as ZrodloKolejki | undefined;
  const okres = okresy.find((o) => o.zrodlo_kolejki === zrodlo);
  const zadanie = okresy.find((o) => o.zrodlo_kolejki === "zadanie");
  const decyl = d.okresy.decyl.find((x) => x.zrodlo_kolejki === zrodlo && x.gorny_decyl);
  const reszta = d.okresy.decyl.find((x) => x.zrodlo_kolejki === zrodlo && !x.gorny_decyl);
  const tygodnie = d.tygodnie.filter((t) => zrodlo && t.zrodlo_kolejki.split(",").includes(zrodlo));
  const zKontaktami = tygodnie.filter((t) => t.pierwsze_kontakty != null);

  const wyjsciowa = d.przychod.wartosc_wyjsciowa;
  const przychodPelne = d.przychod.tygodnie.filter((t) => t.pelny_tydzien_przychodu);
  const przychodOkresu = d.okresy.przychod.find((o) => o.zrodlo_kolejki === zrodlo);
  const zmiana =
    przychodOkresu?.przychod_na_godzine_doradcy != null && wyjsciowa
      ? (100 * (przychodOkresu.przychod_na_godzine_doradcy - wyjsciowa.przychod_na_godzine_doradcy)) /
        wyjsciowa.przychod_na_godzine_doradcy
      : null;

  const sumaPominiec = d.pominiecia.powody.reduce((s, p) => s + p.pominiecia, 0);
  const najczestszy = [...d.pominiecia.powody].sort((a, b) => b.pominiecia - a.pominiecia)[0];
  const doradcy = d.doradcy.filter((x) => x.zrodlo_kolejki === zrodlo);

  return (
    <>
      <h1>Panel kierownika zespołu najmu</h1>
      <p className="podtytul">
        Czy doradcy pracują według kolejki i czy kolejka wskazuje zapytania, które kończą się umową. Liczby z modeli
        dbt (schemat <code>metryki</code>); tydzień = poniedziałek–niedziela, czas warszawski.
      </p>

      {zadanie && zadanie.dni_z_kontaktami === 0 && (
        <div className="uwaga" role="status">
          <strong>Kolejka działa w CRM od {fmtData(zadanie.od)}</strong>, ale kontakty i umowy w danych kończą się
          30 wrz 2026, więc dla dni wdrożenia adopcja, konwersja i czas do kontaktu: brak w danych.
          {okresy.some((o) => o.zrodlo_kolejki === "symulacja_wstecz") && (
            <>
              {" "}
              Wykresy kolejki pokazują <strong>symulację wstecz</strong>: ranking policzony tym samym kodem dla dni, w
              których doradcy go nie widzieli. To punkt odniesienia przed wdrożeniem, a nie efekt kolejki.
            </>
          )}
        </div>
      )}

      {okresy.length > 1 && (
        <nav className="filtry" aria-label="Okres kolejki">
          {okresy.map((o) => (
            <Link
              key={o.zrodlo_kolejki}
              href={`/zespol?zrodlo=${o.zrodlo_kolejki}`}
              aria-current={o.zrodlo_kolejki === zrodlo ? "page" : undefined}
            >
              {ZRODLA[o.zrodlo_kolejki]}: {fmtData(o.od)} – {fmtData(o.do)}
            </Link>
          ))}
        </nav>
      )}

      <div className="kafle">
        <Kafel
          etykieta="Adopcja: pierwsze kontakty z top 20 kolejki"
          wartosc={fmtUdzial(okres?.adopcja)}
          opis={
            okres?.adopcja != null
              ? `${liczba(okres.z_top)} z ${liczba(okres.pierwsze_kontakty)}; przy losowym wyborze ${fmtUdzial(okres.adopcja_losowa)}`
              : "brak w danych"
          }
        />
        <Kafel
          etykieta="Przychód na godzinę doradcy w tygodniach z kolejką"
          wartosc={przychodOkresu ? zlh(przychodOkresu.przychod_na_godzine_doradcy) : "brak w danych"}
          opis={
            (przychodOkresu ? `${przychodOkresu.tygodnie} pełnych tygodni; ` : "") +
            (wyjsciowa
              ? `wartość wyjściowa 2026-Q2: ${zlh(wyjsciowa.przychod_na_godzine_doradcy)}${zmiana != null ? ` (${zmiana >= 0 ? "+" : ""}${zmiana.toFixed(1).replace(".", ",")}%)` : ""}`
              : "brak wartości wyjściowej")
          }
        />
        <Kafel
          etykieta="Konwersja górnego decyla kolejki"
          wartosc={fmtUdzial(decyl?.konwersja)}
          opis={decyl ? `${liczba(decyl.umowy)} umów z ${liczba(decyl.zapytania)} zapytań; pozostałe ${fmtUdzial(reszta?.konwersja)}` : "brak w danych"}
        />
        <Kafel
          etykieta="Mediana czasu do kontaktu, górne 10%"
          wartosc={fmtGodz(decyl?.mediana_godz_kontaktu)}
          opis={decyl ? `pozostałe ${fmtGodz(reszta?.mediana_godz_kontaktu)}; bez kontaktu w 45 dni ${fmtUdzial(decyl.bez_kontaktu)}` : "brak w danych"}
        />
        <Kafel
          etykieta="Pominięcia z CRM"
          wartosc={liczba(sumaPominiec)}
          opis={sumaPominiec ? `najczęściej: ${najczestszy.opis} (${najczestszy.pominiecia})` : "brak zgłoszonych pominięć"}
        />
      </div>

      <h2>Przychód na godzinę doradcy</h2>
      <p className="podtytul">
        Wartość umów z zapytań podpisanych w tygodniu / godziny pracy doradców z grafiku. Linia: wartość wyjściowa z
        2026-Q2 ({wyjsciowa && `${fmtZl(wyjsciowa.wartosc_umow_z_zapytan)} / ${liczba(wyjsciowa.godziny_doradcow)} h`}).
        Tylko pełne tygodnie od lipca 2025.
      </p>
      <WykresLinii
        tytul="Przychód na godzinę doradcy według tygodnia"
        tygodnie={przychodPelne.map((t) => t.tydzien)}
        serie={[{ nazwa: "przychód / godzinę", kolor: "seria-1", wartosci: przychodPelne.map((t) => t.przychod_na_godzine_doradcy) }]}
        jednostka="zl_h"
        odniesienie={
          wyjsciowa
            ? { wartosc: wyjsciowa.przychod_na_godzine_doradcy, etykieta: `wyjściowa Q2 2026: ${zlh(wyjsciowa.przychod_na_godzine_doradcy)}` }
            : undefined
        }
        opisyTygodni={przychodPelne.map(
          (t) => `${liczba(t.podpisania_z_zapytan)} podpisań, umowy ${fmtZl(t.wartosc_umow_z_zapytan)}, ${liczba(t.godziny_doradcow)} h`,
        )}
      />

      {zKontaktami.length === 0 ? (
        <p>Brak tygodni z kontaktami doradców dla wybranego okresu kolejki.</p>
      ) : (
        <>
          <h2>Adopcja kolejki</h2>
          <p className="podtytul">
            Odsetek pierwszych kontaktów z zapytaniem, które doradca miał na pozycjach 1–20 swojej kolejki w chwili
            kontaktu (kolejka obowiązuje od 05:30). Szara linia: odsetek oczekiwany, gdyby doradca wybierał losowo
            spośród otwartych zapytań swojego miasta.
          </p>
          <WykresLinii
            tytul="Adopcja kolejki według tygodnia"
            tygodnie={zKontaktami.map((t) => t.tydzien)}
            serie={[
              { nazwa: "adopcja (top 20)", kolor: "seria-1", wartosci: zKontaktami.map((t) => t.adopcja) },
              { nazwa: "losowy wybór", kolor: "kontekst", wartosci: zKontaktami.map((t) => t.adopcja_losowa) },
            ]}
            jednostka="udzial"
            opisyTygodni={zKontaktami.map(
              (t) =>
                `${liczba(t.pierwsze_kontakty_z_top)} z ${liczba(t.pierwsze_kontakty)} pierwszych kontaktów; ${t.dni_kolejki} dni kolejki`,
            )}
          />

          <h2>Górny decyl kolejki</h2>
          <p className="podtytul">
            Zapytania z pierwszych 10% rankingu swojego miasta w pierwszej kolejce po utworzeniu, według tygodnia tej
            kolejki; tylko zapytania z pełnym oknem 45 dni. Szara linia: pozostałe zapytania.
          </p>
          <WykresLinii
            tytul="Konwersja na umowę w 45 dni według tygodnia"
            tygodnie={zKontaktami.map((t) => t.tydzien)}
            serie={[
              { nazwa: "górny decyl", kolor: "seria-1", wartosci: zKontaktami.map((t) => t.konwersja_decyl) },
              { nazwa: "pozostałe", kolor: "kontekst", wartosci: zKontaktami.map((t) => t.konwersja_poza_decylem) },
            ]}
            jednostka="udzial"
            opisyTygodni={zKontaktami.map(
              (t) => `górny decyl: ${liczba(t.umowy_decyl)} umów z ${liczba(t.zapytania_decyl)}; pozostałe: ${liczba(t.zapytania_poza_decylem)} zapytań`,
            )}
          />
          <h3>Mediana czasu od utworzenia zapytania do pierwszego kontaktu</h3>
          <WykresLinii
            tytul="Mediana czasu do pierwszego kontaktu według tygodnia"
            tygodnie={zKontaktami.map((t) => t.tydzien)}
            serie={[
              { nazwa: "górne 10%", kolor: "seria-1", wartosci: zKontaktami.map((t) => t.mediana_godz_kontaktu_decyl) },
              { nazwa: "pozostałe", kolor: "kontekst", wartosci: zKontaktami.map((t) => t.mediana_godz_kontaktu_poza_decylem) },
            ]}
            jednostka="godz"
            opisyTygodni={zKontaktami.map((t) => `bez kontaktu w 45 dni (górne 10%): ${fmtUdzial(t.bez_kontaktu_decyl)}`)}
          />

          <h2>Adopcja według doradcy</h2>
          <table>
            <thead>
              <tr>
                <th>Doradca</th>
                <th>Miasto</th>
                <th className="liczba">Dni</th>
                <th className="liczba">Pierwsze kontakty</th>
                <th className="liczba">Z top 20</th>
                <th className="liczba">Adopcja</th>
                <th className="liczba">Losowy wybór</th>
              </tr>
            </thead>
            <tbody>
              {doradcy.map((r) => (
                <tr key={r.id_doradcy}>
                  <td className="id">{r.id_doradcy}</td>
                  <td>{r.miasto}</td>
                  <td className="liczba">{liczba(r.dni)}</td>
                  <td className="liczba">{liczba(r.pierwsze_kontakty)}</td>
                  <td className="liczba">{liczba(r.z_top)}</td>
                  <td className="liczba">{fmtUdzial(r.adopcja)}</td>
                  <td className="liczba">{fmtUdzial(r.adopcja_losowa)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}

      <h2>Pominięcia z powodami</h2>
      <p className="podtytul">
        Doradca pomija pozycję kolejki w CRM, wybierając powód pominięcia; CRM przekazuje je do Domilo (tabela{" "}
        <code>kolejka_pominiecia</code>). Wszystkie okresy.
      </p>
      {sumaPominiec > 0 ? <WykresPowodow powody={d.pominiecia.powody} /> : <p>Brak pominięć zgłoszonych z CRM.</p>}
      {d.pominiecia.ostatnie.length > 0 && (
        <table>
          <thead>
            <tr>
              <th>Dzień kolejki</th>
              <th>Doradca</th>
              <th className="liczba">Pozycja</th>
              <th>Zapytanie</th>
              <th>Powód</th>
              <th>Komentarz</th>
              <th className="liczba">EV</th>
              <th>Zgłoszono</th>
            </tr>
          </thead>
          <tbody>
            {d.pominiecia.ostatnie.map((p) => (
              <tr key={`${p.data_kolejki}-${p.id_leada}`}>
                <td>{p.data_kolejki}</td>
                <td className="id">{p.id_doradcy}</td>
                <td className="liczba">{p.pozycja}</td>
                <td className="id">{p.id_leada}</td>
                <td>{d.pominiecia.powody.find((x) => x.powod === p.powod)?.opis ?? p.powod}</td>
                <td className="powod">{p.komentarz ?? "—"}</td>
                <td className="liczba">{fmtZl(p.ev_pln)}</td>
                <td>{fmtCzas(p.zmieniono)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </>
  );
}
