"""Target modelu awarii wind (`dni_wind`, awaria_7d): tabele do docs/b4_target.md.

Czyta domilo.duckdb: `dni_wind` (api/api/ai/features/windy/dni_wind.sql), `awarie_odtworzone`, `telemetra_windy`.
Uruchomienie (z katalogu api/): `python -m api.ai.failure_model.evals.target [T1 T2 ...]` — tabele Markdown.
"""

import sys

import duckdb
from api.ai.failure_model.evals.historia_awarii import _komorka

# Start awarii i koniec przestoju tak jak w dni_wind.sql
AWARIE = """
awarie AS (
    SELECT
        id_awarii, id_windy, podzespol, zrodlo_startu, okna_przestoju,
        coalesce(start_awarii_tz, timezone('Europe/Warsaw', pierwsze_zgloszenie)) AS start_tz,
        start_awarii_tz,
        start_awarii_tz + okna_przestoju * INTERVAL 10 MINUTE AS koniec_przestoju_tz
    FROM awarie_odtworzone
)"""

# Winda × dzień z telemetrią przed pominięciem postojów (te same warunki co dni_z_telemetria w dni_wind.sql)
DNI_Z_TELEMETRIA = """
dni_z_telemetria AS (
    SELECT t.id_windy, CAST(d.dzien AS DATE) AS dzien,
        timezone('Europe/Warsaw', d.dzien + INTERVAL 6 HOUR) AS moment_predykcji
    FROM (SELECT id_windy, min(ts_utc) AS od, max(ts_utc) AS do FROM telemetra_windy GROUP BY id_windy) AS t
    CROSS JOIN generate_series(TIMESTAMP '2023-03-01', TIMESTAMP '2026-09-22', INTERVAL 1 DAY) AS d(dzien)
    WHERE timezone('Europe/Warsaw', d.dzien + INTERVAL 6 HOUR) >= t.od
      AND timezone('Europe/Warsaw', d.dzien + INTERVAL 7 DAY + INTERVAL 6 HOUR) <= t.do
)"""

ZAPYTANIA: dict[str, str] = {
    # Ogółem
    "T1": """
SELECT
    count(*) AS wiersze,
    count(DISTINCT id_windy) AS windy,
    min(dzien) AS pierwszy_dzien,
    max(dzien) AS ostatni_dzien,
    sum(awaria_7d) AS dodatnie,
    round(100.0 * avg(awaria_7d), 2) AS proc_dodatnich,
    count(*) FILTER (liczba_awarii_7d >= 2) AS wiersze_z_2_i_wiecej_awariami
FROM dni_wind
""",
    # Według producenta (ostatni wiersz: RAZEM)
    "T2": """
SELECT
    coalesce(producent, 'RAZEM') AS producent,
    count(DISTINCT id_windy) AS windy,
    count(*) AS wiersze,
    sum(awaria_7d) AS dodatnie,
    round(100.0 * avg(awaria_7d), 2) AS proc_dodatnich
FROM dni_wind
GROUP BY ROLLUP (producent)
ORDER BY producent IS NULL, producent
""",
    # Według roku dnia predykcji (2023: od 1 marca; 2026: do 22 września)
    "T3": """
SELECT
    coalesce(CAST(year(dzien) AS VARCHAR), 'RAZEM') AS rok,
    count(*) AS wiersze,
    sum(awaria_7d) AS dodatnie,
    round(100.0 * avg(awaria_7d), 2) AS proc_dodatnich
FROM dni_wind
GROUP BY ROLLUP (year(dzien))
ORDER BY year(dzien) IS NULL, year(dzien)
""",
    # Pominięte dni (winda stoi o 06:00) i wariant „cały dzień kalendarzowy”
    "T4": f"""
WITH {AWARIE.strip()},
{DNI_Z_TELEMETRIA.strip()},
caly_dzien AS (
    -- wariant odrzucony: pomiń dzień, gdy przestój zachodzi na dowolną część doby [00:00 t; 00:00 t+1)
    SELECT DISTINCT d.id_windy, d.dzien
    FROM dni_wind AS d
    JOIN awarie AS a
        ON a.id_windy = d.id_windy
       AND a.start_awarii_tz < timezone('Europe/Warsaw', d.dzien + INTERVAL 1 DAY)
       AND a.koniec_przestoju_tz > timezone('Europe/Warsaw', CAST(d.dzien AS TIMESTAMP))
)
SELECT
    (SELECT count(*) FROM dni_z_telemetria) AS dni_z_telemetria,
    (SELECT count(*) FROM dni_wind) AS w_dni_wind,
    (SELECT count(*) FROM dni_z_telemetria) - (SELECT count(*) FROM dni_wind) AS pominiete_winda_stoi_o_6,
    (SELECT count(*) FROM caly_dzien) AS dodatkowo_pominiete_w_wariancie_caly_dzien,
    (SELECT count(*) FROM caly_dzien JOIN dni_wind USING (id_windy, dzien) WHERE awaria_7d = 1)
        AS w_tym_dodatnie,
    (SELECT count(*) FROM caly_dzien JOIN dni_wind USING (id_windy, dzien)
      WHERE awaria_7d = 1 AND godziny_do_startu < 18) AS w_tym_dodatnie_ze_startem_tego_dnia
""",
    # Pokrycie awarii: czy każda awaria z zakresu ma choć jeden dzień z awaria_7d = 1
    "T5": f"""
WITH {AWARIE.strip()},
okno AS (
    SELECT id_windy, min(moment_predykcji) AS od, max(koniec_okna) AS do FROM dni_wind GROUP BY id_windy
),
pokrycie AS (
    SELECT
        a.*,
        a.start_tz > o.od AND a.start_tz <= o.do AS w_zakresie,
        EXISTS (
            SELECT 1 FROM dni_wind AS d
            WHERE d.id_windy = a.id_windy AND a.start_tz > d.moment_predykcji AND a.start_tz <= d.koniec_okna
        ) AS ma_dzien_dodatni,
        (
            SELECT count(*) FROM dni_wind AS d
            WHERE d.id_windy = a.id_windy AND a.start_tz > d.moment_predykcji AND a.start_tz <= d.koniec_okna
        ) AS dni_dodatnie
    FROM awarie AS a
    JOIN okno AS o USING (id_windy)
)
SELECT
    count(*) AS awarie_odtworzone,
    count(*) FILTER (w_zakresie) AS start_w_zakresie_dni_wind,
    count(*) FILTER (w_zakresie AND ma_dzien_dodatni) AS z_dniem_dodatnim,
    count(*) FILTER (w_zakresie AND NOT ma_dzien_dodatni) AS bez_dnia_dodatniego,
    count(*) FILTER (w_zakresie AND dni_dodatnie < 7) AS z_mniej_niz_7_dniami_dodatnimi,
    count(*) FILTER (w_zakresie AND zrodlo_startu <> 'telemetria') AS start_z_pierwszego_zgloszenia
FROM pokrycie
""",
    # Dodatnie wiersze według podzespołu pierwszej awarii w oknie
    "T6": """
SELECT
    coalesce(podzespol, 'RAZEM') AS podzespol,
    count(*) AS dodatnie,
    round(100.0 * count(*) / sum(count(*)) FILTER (podzespol IS NOT NULL) OVER (), 1) AS proc
FROM dni_wind
WHERE awaria_7d = 1
GROUP BY ROLLUP (podzespol)
ORDER BY podzespol IS NULL, dodatnie DESC
""",
    # Przypadki brzegowe w danych
    "T7": f"""
WITH {AWARIE.strip()}
SELECT
    (SELECT count(*) FROM awarie
      WHERE strftime(timezone('Europe/Warsaw', start_tz), '%H:%M') = '06:00') AS starty_dokladnie_o_6,
    (SELECT count(*) FROM awarie WHERE koniec_przestoju_tz - start_awarii_tz > INTERVAL 7 DAY) AS przestoje_ponad_7_dni,
    (SELECT max(okna_przestoju) / 6.0 / 24 FROM awarie) AS najdluzszy_przestoj_dni,
    (SELECT count(*) FROM dni_wind
      WHERE (epoch(koniec_okna) - epoch(moment_predykcji)) / 3600 <> 168) AS okna_ze_zmiana_czasu,
    (SELECT max(minuty_start_do_zgloszenia) FROM awarie_odtworzone) AS max_min_start_do_zgloszenia,
    (SELECT max(koniec_okna) FROM dni_wind) AS ostatni_koniec_okna
""",
}


def komorka(x) -> str:
    if isinstance(x, float):
        return f"{x:.2f}".replace(".", ",")
    if hasattr(x, "strftime") and hasattr(x, "hour"):
        return x.strftime("%Y-%m-%d %H:%M %z")
    return _komorka(x)


def zapytanie_md(con: duckdb.DuckDBPyConnection, sql: str) -> str:
    kursor = con.execute(sql)
    kolumny = [k[0] for k in kursor.description]
    linie = ["| " + " | ".join(kolumny) + " |", "|" + "---|" * len(kolumny)]
    linie += ["| " + " | ".join(komorka(x) for x in w) + " |" for w in kursor.fetchall()]
    return "\n".join(linie)


def main(wybrane: list[str]) -> None:
    from api.adapters.duckdb_baza import polacz

    con = polacz()
    for nazwa, sql in ZAPYTANIA.items():
        if not wybrane or nazwa in wybrane:
            print(f"### {nazwa}\n\n{zapytanie_md(con, sql)}\n")


if __name__ == "__main__":
    main(sys.argv[1:])
