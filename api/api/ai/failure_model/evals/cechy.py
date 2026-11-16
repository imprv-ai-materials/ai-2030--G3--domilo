"""Cechy modelu awarii wind (`cechy_windy`): tabele do docs/b4_cechy.md.

Czyta domilo.duckdb: `cechy_windy`, `dni_wind`, `serwis_windy`, `telemetra_windy`, `awarie_odtworzone`.
Uruchomienie (z katalogu api/): `python -m api.ai.failure_model.evals.cechy [C1 C2 ...]` — tabele Markdown.
C7 (AUC pojedynczych cech) liczy scikit-learn na całej tabeli: to opis, nie ocena modelu.
"""

import sys

import duckdb
from api.ai.failure_model.evals.historia_awarii import _komorka
from api.ai.failure_model.evals.target import zapytanie_md
from api.ai.features.windy.cechy import RODZINY, nazwy_cech, przygotuj, sygnaly

LF5 = "TIMESTAMPTZ '2025-11-17 02:00+01'"  # aktualizacja wszystkich wind Liftar do LF-5.0.0 (telemetra_firmware)

ZAPYTANIA: dict[str, str] = {
    # Kształt tabeli
    "C1": """
SELECT
    count(*) AS wiersze,
    count(DISTINCT id_windy) AS windy,
    min(dzien) AS pierwszy_dzien,
    max(dzien) AS ostatni_dzien,
    (SELECT count(*) FROM dni_wind) AS wiersze_dni_wind,
    (SELECT count(*) - 2 FROM (DESCRIBE cechy_windy)) AS kolumny_cech
FROM cechy_windy
""",
    # Czujnik wibracji
    "C3": """
SELECT
    ma_czujnik_wibracji,
    count(*) AS wiersze,
    count(wibracje_rms_sr_24h) AS z_wibracje_sr_24h,
    count(wibracje_rms_norma) AS z_norma,
    count(wibracje_rms_trend_7d) AS z_trendem,
    min(dzien) AS od,
    max(dzien) AS do
FROM cechy_windy
GROUP BY ma_czujnik_wibracji
ORDER BY ma_czujnik_wibracji
""",
    # Okna 10-min: tryb i aktualizacja LF-5 (różnica w różnicach: Liftar wobec pozostałych, 4 tygodnie przed / po)
    "C4": f"""
SELECT
    w.producent,
    CASE WHEN t.ts_utc >= {LF5} THEN 'po' ELSE 'przed' END AS okres,
    count(*) AS okna,
    round(1000 * avg(t.bledy_drzwi), 2) AS bledy_drzwi_na_1000_okien,
    round(1000 * avg(t.bledy_napedu), 2) AS bledy_napedu_na_1000_okien,
    round(1000 * avg(t.bledy_sterownika), 2) AS bledy_sterownika_na_1000_okien,
    round(avg(t.ponowne_otwarcia), 4) AS ponowne_otwarcia_sr,
    round(avg(t.czas_zamykania_drzwi_sr_s), 3) AS czas_zamykania_sr_s,
    round(avg(t.prad_silnika_sr_a), 3) AS prad_sr_a,
    round(avg(t.kursy), 3) AS kursy_sr
FROM telemetra_windy AS t
JOIN serwis_windy AS w USING (id_windy)
WHERE t.tryb = 'normalny'
  AND t.ts_utc >= {LF5} - INTERVAL 28 DAY AND t.ts_utc < {LF5} + INTERVAL 28 DAY
GROUP BY ALL
ORDER BY w.producent, okres DESC
""",
    # Awarie przed / po LF-5 (czy błędy rosną razem z awariami)
    "C5": f"""
WITH dni AS (
    SELECT w.producent, t.ts_utc >= {LF5} AS po, count(*) / 144.0 AS winda_dni
    FROM telemetra_windy AS t JOIN serwis_windy AS w USING (id_windy)
    GROUP BY ALL
),
aw AS (
    SELECT w.producent, a.start_awarii_tz >= {LF5} AS po, count(*) AS awarie,
        count(*) FILTER (a.podzespol = 'drzwi') AS awarie_drzwi
    FROM awarie_odtworzone AS a JOIN serwis_windy AS w USING (id_windy)
    WHERE a.start_awarii_tz IS NOT NULL
    GROUP BY ALL
)
SELECT
    producent,
    CASE WHEN po THEN 'po' ELSE 'przed' END AS okres,
    awarie,
    round(1000 * awarie / winda_dni, 2) AS awarie_na_1000_winda_dni,
    round(1000 * awarie_drzwi / winda_dni, 2) AS awarie_drzwi_na_1000_winda_dni
FROM dni JOIN aw USING (producent, po)
ORDER BY producent, po
""",
    # Skutek w cechach: stosunek błędów drzwi do normy, Liftar wobec reszty, 44 dni przed i po LF-5
    "C6": """
SELECT
    CASE WHEN w.producent = 'Liftar' THEN 'Liftar' ELSE 'pozostali' END AS producent,
    CASE WHEN c.dzien >= DATE '2025-11-18' THEN 'po (44 dni)' ELSE 'przed (44 dni)' END AS okres,
    count(*) AS wiersze,
    round(avg(c.drzwi_bledy_sr_7d) * 1000, 2) AS drzwi_bledy_sr_7d_na_1000,
    round(avg(c.drzwi_bledy_do_normy_7d), 2) AS drzwi_bledy_do_normy_7d_sr,
    round(100.0 * avg(CAST(c.drzwi_bledy_do_normy_7d > 2 AS INTEGER)), 1) AS proc_do_normy_7d_ponad_2,
    round(avg(c.drzwi_ponowne_otwarcia_do_normy_7d), 3) AS ponowne_otwarcia_do_normy_7d_sr,
    sum(c.firmware_zmiana_glowna_44d) AS z_flaga_zmiany_glownej
FROM cechy_windy AS c
JOIN serwis_windy AS w USING (id_windy)
WHERE c.dzien BETWEEN DATE '2025-11-18' - 44 AND DATE '2025-11-18' + 43
GROUP BY ALL
ORDER BY 1, 2 DESC
""",
}


def braki_md(con: duckdb.DuckDBPyConnection) -> str:
    """C2: odsetek NULL według sygnału i rodzaju cechy."""
    przygotuj(con)
    wiersze = []
    for rodzina in RODZINY:
        for s in sygnaly(con, rodzina):
            k = nazwy_cech(s)
            proc = ", ".join(
                f"round(100.0 * count(*) FILTER ({c} IS NULL) / count(*), 1) AS \"{c.removeprefix(s + '_')}\""
                for c in (k[0], k[4], k[6], k[7], k[10])
            )
            wiersze.append(f"SELECT '{rodzina}' AS rodzina, '{s}' AS sygnal, {proc} FROM cechy_windy")
    return zapytanie_md(con, " UNION ALL ".join(wiersze))


def auc_md(con: duckdb.DuckDBPyConnection, n: int = 15, min_wierszy: int = 1000) -> str:
    """C7: AUC pojedynczej cechy wobec awaria_7d (NULL pominięte; cechy z co najmniej min_wierszy wartościami),
    n cech najdalej od 0,5, a na końcu cecha najlepsza w każdej rodzinie."""
    from sklearn.metrics import roc_auc_score

    df = con.execute("SELECT c.*, d.awaria_7d FROM cechy_windy AS c JOIN dni_wind AS d USING (id_windy, dzien)").df()
    wyniki = []
    for kolumna in df.columns.drop(["id_windy", "dzien", "awaria_7d"]):
        x = df[[kolumna, "awaria_7d"]].dropna()
        if len(x) >= min_wierszy and x["awaria_7d"].nunique() == 2 and x[kolumna].nunique() > 1:
            auc = float(roc_auc_score(x["awaria_7d"], x[kolumna]))
            wyniki.append((kolumna, len(x), int(x["awaria_7d"].sum()), round(auc, 3)))
    wyniki.sort(key=lambda w: -abs(w[3] - 0.5))
    najlepsze_rodzin = []
    for rodzina in (*RODZINY, "ma_czujnik", "firmware"):
        w = next((w for w in wyniki if w[0].startswith(rodzina)), None)
        if w and w not in wyniki[:n]:
            najlepsze_rodzin.append(w)
    linie = ["| cecha | wiersze_bez_null | dodatnie | auc |", "|---|---|---|---|"]
    linie += [
        f"| {c} | {_komorka(w)} | {_komorka(d)} | {a:.3f} |".replace(".", ",")
        for c, w, d, a in wyniki[:n] + najlepsze_rodzin
    ]
    return "\n".join(linie)


def main(wybrane: list[str]) -> None:
    from api.adapters.duckdb_baza import polacz

    con = polacz()
    for nazwa, sql in ZAPYTANIA.items():
        if not wybrane or nazwa in wybrane:
            print(f"### {nazwa}\n\n{zapytanie_md(con, sql)}\n")
    if not wybrane or "C2" in wybrane:
        print(f"### C2\n\n{braki_md(con)}\n")
    if not wybrane or "C7" in wybrane:
        print(f"### C7\n\n{auc_md(con)}\n")


if __name__ == "__main__":
    main(sys.argv[1:])
