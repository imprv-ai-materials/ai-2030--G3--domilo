"""Jak zmienia się wartość oczekiwana (EV) zapytań po zamianie czasu najmu na RMST60 (docs/kolejka_ev.md, sekcja
„Czas najmu z RMST60”).

Uruchomienie: cd api && poetry run python -m api.ai.lead_model.evals.ev_czas_najmu

- Dzień: najnowszy ranking zadania kolejka-doradcow w `kolejka_ranking` (zrodlo_kolejki = 'zadanie'); linia i liczba
  lokali z `crm_leady`. EV = p × czynsz × czas najmu × lokale (leasing_bc/wartosc.py), p z rankingu (to samo p).
- „Przed”: czas_najmu_naiwny (średnia z zakończonych, wartości z zalozenia.yaml do 2026-11-15), „po”: czas_najmu_mies
  z danych (RMST60 dla B2C i B2B; MID bez zmian). Obie wersje liczy zalozenia_z_danych.policz, więc nie zależą od
  stanu pliku YAML; sprawdzamy też, że „przed” odtwarza ev_pln zapisane przez zadanie.
- Ranga: w mieście według EV malejąco, remis według id_leada (jak kolejka_dzienna.ranking_kolejki, wariant EV).
- Kolejka według EV: górne k zapytań miasta, k = liczba nielosowych pozycji w kolejkach doradców tego miasta tego dnia
  (kolejka_historia, losowa = false); 5% pozycji losowych eksperymentu nie zależy od EV.
- 10 przykładów: pozycje z kolejek doradców tego dnia, 4 B2C, 4 B2B, 2 MID; w każdej linii najwyższe pozycje
  (pozycja, id_doradcy, id_leada); kolumna `losowa` z kolejka_historia.
Zapis: lead_model/evals/wyniki/ev_czas_najmu.json.
"""

import json
from pathlib import Path

import numpy as np
import pandas as pd
from api.adapters.duckdb_baza import polacz
from api.contexts_boundaries.leasing_bc.wartosc import wartosc_oczekiwana
from api.contexts_boundaries.leasing_bc.zalozenia import wczytaj_zalozenia
from api.contexts_boundaries.leasing_bc.zalozenia_z_danych import policz

SCIEZKA_WYNIKU = Path(__file__).with_name("wyniki") / "ev_czas_najmu.json"
PRZYKLADY = {"B2C": 4, "B2B": 4, "MID": 2}

SQL_RANKING = """
WITH dzien AS (SELECT max(data_kolejki) AS d FROM kolejka_ranking WHERE zrodlo_kolejki = 'zadanie')
SELECT r.data_kolejki, r.id_leada, r.miasto, r.ranga, r.p, r.ev_pln, r.id_doradcy, r.pozycja,
       l.linia_pref, l.liczba_lokali
FROM kolejka_ranking AS r
JOIN dzien ON r.data_kolejki = dzien.d
JOIN crm_leady AS l USING (id_leada)
WHERE r.zrodlo_kolejki = 'zadanie'
"""


def _rangi(df: pd.DataFrame, kolumna: str) -> pd.Series:
    """Ranga w mieście według EV malejąco (remis: id_leada rosnąco), 1 = pierwsze."""
    posort = df.sort_values(["miasto", kolumna, "id_leada"], ascending=[True, False, True], kind="mergesort")
    return posort.groupby("miasto").cumcount().add(1).reindex(df.index)


def main() -> dict:
    con = polacz()
    df = con.execute(SQL_RANKING).df()
    dane = policz(con)
    k_miasta = (
        con.execute(
            "SELECT miasto, count(*) AS k FROM kolejka_historia WHERE data_kolejki = ? AND NOT losowa GROUP BY miasto",
            [df["data_kolejki"].iloc[0]],
        )
        .df()
        .set_index("miasto")["k"]
    )
    losowe = con.execute(
        "SELECT id_leada, id_doradcy, losowa FROM kolejka_historia WHERE data_kolejki = ?", [df["data_kolejki"].iloc[0]]
    ).df()
    con.close()

    z = wczytaj_zalozenia()
    przed = {**z, "czas_najmu_mies": {"wartosc": dane["czas_najmu_naiwny"]}}
    po = {**z, "czas_najmu_mies": {"wartosc": dane["czas_najmu_mies"]}}
    df = df[df["p"].notna()].reset_index(drop=True)
    df["ev_przed"] = wartosc_oczekiwana(df["p"], df, przed)
    df["ev_po"] = wartosc_oczekiwana(df["p"], df, po)
    zgodnosc = float(np.nanmax(np.abs(df["ev_przed"] - df["ev_pln"])))
    df["ranga_przed"] = _rangi(df, "ev_przed")
    df["ranga_po"] = _rangi(df, "ev_po")
    k = df["miasto"].map(k_miasta).fillna(0)
    df["w_kolejce_przed"] = df["ranga_przed"] <= k
    df["w_kolejce_po"] = df["ranga_po"] <= k

    w_kolejkach = df[df["pozycja"].notna()].copy()
    przyklady = pd.concat(
        [
            w_kolejkach[w_kolejkach["linia_pref"] == linia].sort_values(["pozycja", "id_doradcy", "id_leada"]).head(n)
            for linia, n in PRZYKLADY.items()
        ]
    )
    kolumny = ["id_leada", "miasto", "linia_pref", "liczba_lokali", "p", "ev_przed", "ev_po", "ranga_przed", "ranga_po"]
    przyklady = przyklady.merge(losowe, on=["id_leada", "id_doradcy"], how="left")
    przyklady = przyklady[["id_doradcy", "pozycja", "losowa", *kolumny]].assign(
        zmiana_pln=lambda d: d["ev_po"] - d["ev_przed"], zmiana_proc=lambda d: d["ev_po"] / d["ev_przed"] - 1
    )

    podsumowanie_linii = (
        df.groupby("linia_pref")
        .agg(
            zapytania=("id_leada", "size"),
            ev_przed_suma=("ev_przed", "sum"),
            ev_po_suma=("ev_po", "sum"),
            w_kolejce_przed=("w_kolejce_przed", "sum"),
            w_kolejce_po=("w_kolejce_po", "sum"),
        )
        .reset_index()
    )
    wynik = {
        "data_kolejki": str(df["data_kolejki"].iloc[0]),
        "zapytania_w_rankingu": int(len(df)),
        "miejsca_w_kolejkach_wedlug_ev": int(k_miasta.sum()),
        "czas_najmu_przed": dane["czas_najmu_naiwny"],
        "czas_najmu_po": dane["czas_najmu_mies"],
        "maks_roznica_ev_przed_vs_zapisane_pln": zgodnosc,
        "zmiana_rangi": {
            "zapytania_ze_zmiana": int((df["ranga_przed"] != df["ranga_po"]).sum()),
            "weszly_do_kolejki": int((~df["w_kolejce_przed"] & df["w_kolejce_po"]).sum()),
            "wypadly_z_kolejki": int((df["w_kolejce_przed"] & ~df["w_kolejce_po"]).sum()),
        },
        "linie": podsumowanie_linii.to_dict("records"),
        "przyklady": przyklady.to_dict("records"),
    }
    SCIEZKA_WYNIKU.parent.mkdir(exist_ok=True)
    SCIEZKA_WYNIKU.write_text(json.dumps(wynik, ensure_ascii=False, indent=2, default=float), encoding="utf-8")
    return wynik


if __name__ == "__main__":
    w = main()
    print(json.dumps({k: v for k, v in w.items() if k not in ("przyklady", "linie")}, ensure_ascii=False, indent=2))
    print(pd.DataFrame(w["linie"]).round(0).to_string(index=False))
    pd.set_option("display.width", 250)
    print(pd.DataFrame(w["przyklady"]).round(3).to_string(index=False))
