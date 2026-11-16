"""Założenia leasing_bc liczone z danych metodą wskazaną przez użytkownika (polecenie z 2026-11-15).

Wartości są przepisane do zalozenia.yaml (ze źródłem i osobą odpowiedzialną). Ten moduł pokazuje, jak je policzono,
a test (api/tests/test_leasing_wartosc.py) sprawdza, że YAML zgadza się z danymi.

    cd api && poetry run python -m api.contexts_boundaries.leasing_bc.zalozenia_z_danych

- `czas_najmu_mies` (od 2026-11-16, polecenie użytkownika): B2C i B2B = RMST do 60 miesięcy z krzywej Kaplana-Meiera
  na tabeli `czas_najmu` (trwające najmy jako cenzura; churn_model/evals/przezycie_grupy.py, docs/przezycie.md);
  MID = średni czas zakończonych najmów (dni / 30,4375), bo `czas_najmu` nie obejmuje linii MID. Dawna naiwna średnia
  dla wszystkich linii zostaje w wyniku jako `czas_najmu_naiwny` (porównanie).
- `czynsz_mediana_pln`: mediana `pms_lokale.czynsz_katalogowy` dla linii w każdym mieście (miasto z `pms_budynki`).
  To stan na dzień eksportu (2026-09-30), nie czynsz z chwili zapytania.
- `godziny_doradcow`: godziny z `crm_grafik` w ostatnich 12 miesiącach przed eksportem, według miasta doradcy
  (`crm_doradcy.miasto`), na dzień pracy (dzień z jakimkolwiek wpisem w grafiku).
"""

import json

import duckdb

DNI_W_MIESIACU = 365.25 / 12
EKSPORT = "2026-09-30 23:59:59"
GRAFIK_OD, GRAFIK_DO = "2025-10-01", "2026-10-01"  # [od, do): 12 miesięcy kończących się w dniu eksportu

SQL_CZAS_NAJMU = f"""
SELECT linia,
       count(*) AS najmy_zakonczone,
       avg(date_diff('day', data_wprowadzenia, data_wyprowadzenia)) AS sredni_czas_dni,
       median(date_diff('day', data_wprowadzenia, data_wyprowadzenia)) AS mediana_czasu_dni
FROM pms_najmy
WHERE data_wyprowadzenia IS NOT NULL AND data_wyprowadzenia <= TIMESTAMP '{EKSPORT}'
GROUP BY linia
ORDER BY linia
"""

SQL_CZYNSZ = """
SELECT b.miasto, l.linia, count(*) AS lokale, median(l.czynsz_katalogowy) AS mediana_czynszu
FROM pms_lokale AS l JOIN pms_budynki AS b USING (id_budynku)
GROUP BY ALL
ORDER BY ALL
"""

SQL_GODZINY = f"""
WITH g AS (
    SELECT g.data, g.id_doradcy, d.miasto, g.godziny_pracy
    FROM crm_grafik AS g JOIN crm_doradcy AS d USING (id_doradcy)
    WHERE g.data >= DATE '{GRAFIK_OD}' AND g.data < DATE '{GRAFIK_DO}'
)
SELECT miasto,
       count(DISTINCT id_doradcy) AS doradcy,
       sum(godziny_pracy) AS godziny,
       (SELECT count(DISTINCT data) FROM g) AS dni_pracy,
       sum(godziny_pracy) / (SELECT count(DISTINCT data) FROM g) AS godziny_na_dzien_pracy
FROM g
GROUP BY miasto
ORDER BY miasto
"""

LINIE = ("B2B", "B2C", "MID")
LINIE_RMST = ("B2B", "B2C")
HORYZONT_RMST = 60


def rmst_linii(con: duckdb.DuckDBPyConnection, horyzont: float = HORYZONT_RMST) -> dict[str, float]:
    """RMST do `horyzont` mies. z Kaplana-Meiera na czas_najmu (B2C, B2B), zaokrąglone do 0,01 mies."""
    from api.ai.churn_model.evals.przezycie_grupy import metryki_km

    czasy = con.execute("SELECT linia, miesiace, zdarzenie FROM czas_najmu").df()
    return {li: round(metryki_km(czasy[czasy["linia"] == li], horyzont)["rmst_km"], 2) for li in LINIE_RMST}


def policz(con: duckdb.DuckDBPyConnection) -> dict:
    """Wartości trzech założeń w układzie pola `wartosc` z zalozenia.yaml."""
    czas = con.execute(SQL_CZAS_NAJMU).df()
    czynsz = con.execute(SQL_CZYNSZ).df()
    godziny = con.execute(SQL_GODZINY).df()
    miasta = sorted(czynsz["miasto"].unique())
    mediany = {(r.miasto, r.linia): float(r.mediana_czynszu) for r in czynsz.itertuples()}
    return {
        "czas_najmu_mies": {
            **{r.linia: round(r.sredni_czas_dni / DNI_W_MIESIACU, 2) for r in czas.itertuples()},
            **rmst_linii(con),
        },
        "czas_najmu_naiwny": {r.linia: round(r.sredni_czas_dni / DNI_W_MIESIACU, 2) for r in czas.itertuples()},
        "czas_najmu_szczegoly": czas.to_dict("records"),
        "czynsz_mediana_pln": {m: {li: mediany.get((m, li)) for li in LINIE} for m in miasta},
        "czynsz_lokale": {f"{r.miasto}/{r.linia}": int(r.lokale) for r in czynsz.itertuples()},
        "godziny_doradcow": {
            "okres": f"{GRAFIK_OD} – 2026-09-30",
            "dni_pracy": int(godziny["dni_pracy"].iloc[0]),
            "godziny_na_dzien_pracy": {
                "razem": round(float(godziny["godziny"].sum() / godziny["dni_pracy"].iloc[0]), 2),
                **{r.miasto: round(float(r.godziny_na_dzien_pracy), 2) for r in godziny.itertuples()},
            },
            "doradcy": {r.miasto: int(r.doradcy) for r in godziny.itertuples()},
            "godziny_w_okresie": {r.miasto: float(r.godziny) for r in godziny.itertuples()},
        },
    }


if __name__ == "__main__":
    from api.adapters.duckdb_baza import polacz

    print(json.dumps(policz(polacz()), ensure_ascii=False, indent=2, default=str))
