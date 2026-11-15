"""Liczby do raportu docs/b1_dane.md: jednostka tabel Radaru, rozkład cen RCN, opóźnienie publikacji, podział.

Uruchomienie (wymaga domilo.duckdb: `pypyr baza`), z katalogu api/ repozytorium:
    cd api && poetry run python -m api.ai.features.wycena.opis_danych_b1 [nazwa_zapytania ...]
Wypisuje tabele Markdown w kolejności sekcji raportu.
"""

import sys

from api.adapters.duckdb_baza import polacz
from api.ai.features.wycena.podzial import sql_podzialu

ZAPYTANIA: dict[str, str] = {}

# --- 1. Co oznacza jeden wiersz -------------------------------------------------------------------------------

ZAPYTANIA["1a_rcn_klucz"] = """
SELECT count(*) AS wiersze,
       count(DISTINCT id_transakcji) AS rozne_id,
       min(data_aktu)::DATE AS pierwszy_akt,
       max(data_aktu)::DATE AS ostatni_akt,
       count(*) FILTER (data_aktu <> date_trunc('day', data_aktu)) AS akt_z_godzina,
       count(*) FILTER (abs(cena_m2 - cena_pln / metraz) > 0.5) AS cena_m2_rozna_od_ilorazu_o_ponad_0_5_zl,
       count(*) FILTER (cena_m2 <> round(cena_pln / metraz)) AS cena_m2_inaczej_zaokraglona,
       count(*) FILTER (rynek = 'wtorny') AS rynek_wtorny,
       count(*) FILTER (rynek = 'pierwotny') AS rynek_pierwotny,
       count(*) FILTER (cena_pln IS NULL OR metraz IS NULL) AS braki_ceny_lub_metrazu
FROM rcn_transakcje
"""

ZAPYTANIA["1b_rcn_duplikaty"] = """
-- Czy ten sam lokal (współrzędne, metraż, piętro, pokoje) występuje kilka razy
SELECT count(*) AS grupy, sum(n) AS transakcje, max(n) AS max_w_grupie,
       count(*) FILTER (rozne_daty = 1) AS grupy_z_tym_samym_dniem_aktu
FROM (SELECT count(*) AS n, count(DISTINCT data_aktu) AS rozne_daty
      FROM rcn_transakcje GROUP BY lat, lon, metraz, pietro, pokoje HAVING count(*) > 1)
"""

ZAPYTANIA["1c_oferty_klucz"] = """
WITH grupy AS (  -- ten sam lokal = te same współrzędne, metraż, piętro i rok budowy
    SELECT count(*) AS n, count(DISTINCT portal) AS portale
    FROM radar_oferty GROUP BY lat, lon, metraz, pietro, rok_budowy
)
SELECT (SELECT count(*) FROM radar_oferty) AS wiersze,
       (SELECT count(DISTINCT id_oferty) FROM radar_oferty) AS rozne_id,
       count(*) AS rozne_lokale,
       count(*) FILTER (n > 1) AS lokale_w_wielu_ogloszeniach,
       sum(n) FILTER (n > 1) AS ogloszenia_tych_lokali,
       count(*) FILTER (n > 1 AND portale = n) AS w_tym_kazde_na_innym_portalu
FROM grupy
"""

ZAPYTANIA["1d_oferty_portale"] = """
SELECT coalesce(portal, 'RAZEM') AS portal, count(*) AS ogloszenia, count(id_pakietu) AS w_pakiecie_dewelopera,
       count(*) FILTER (rynek = 'pierwotny') AS rynek_pierwotny,
       count(*) FILTER (miasto = 'Katowice') AS katowice,
       count(*) FILTER (cena_ofertowa <= 0) AS cena_niedodatnia,
       count(*) FILTER (data_publikacji >= TIMESTAMP '2026-10-01') AS po_dniu_eksportu
FROM radar_oferty GROUP BY ROLLUP (portal) ORDER BY ogloszenia DESC
"""

ZAPYTANIA["1e_dopasowania"] = """
SELECT count(*) AS pary,
       count(DISTINCT id_transakcji) AS rozne_transakcje,
       count(DISTINCT id_oferty) AS rozne_oferty,
       min(d.pewnosc) AS min_pewnosc, max(d.pewnosc) AS max_pewnosc,
       round(100.0 * count(*) / (SELECT count(*) FROM rcn_transakcje), 1) AS proc_transakcji_z_oferta,
       count(*) FILTER (o.miasto <> t.miasto OR o.dzielnica <> t.dzielnica OR o.metraz <> t.metraz
                        OR o.pietro <> t.pietro) AS niezgodne_cechy,
       count(*) FILTER (o.data_publikacji > t.data_aktu) AS oferta_po_akcie,
       median(date_diff('day', o.data_publikacji, t.data_aktu)) AS mediana_dni_oferta_do_aktu,
       round(median(t.cena_pln / o.cena_ofertowa), 3) AS mediana_cena_transakcji_do_ofertowej,
       round(quantile_cont(t.cena_pln / o.cena_ofertowa, 0.05), 3) AS p5_relacji,
       round(quantile_cont(t.cena_pln / o.cena_ofertowa, 0.95), 3) AS p95_relacji
FROM radar_dopasowania d
JOIN rcn_transakcje t USING (id_transakcji)
JOIN radar_oferty o USING (id_oferty)
"""

ZAPYTANIA["1f_operaty"] = """
SELECT typ, count(*) AS operaty,
       count(id_lokalu) AS z_id_lokalu, count(DISTINCT id_lokalu) AS rozne_lokale,
       count(id_oferty) AS z_id_oferty,
       strftime(min(data_wyceny), '%Y-%m-%d') AS od, strftime(max(data_wyceny), '%Y-%m-%d') AS do,
       count(DISTINCT wykonawca) AS wykonawcy,
       median(wartosc_pln) AS mediana_wartosci
FROM operaty GROUP BY typ ORDER BY operaty DESC
"""

ZAPYTANIA["1g_operaty_roczne"] = """
SELECT strftime(data_wyceny, '%Y-%m') AS miesiac, count(*) AS operaty_roczne, count(DISTINCT id_lokalu) AS lokale
FROM operaty WHERE typ = 'roczny' GROUP BY ALL ORDER BY miesiac
"""

ZAPYTANIA["1h_operaty_powiazania"] = """
-- Operaty kontrolne -> lokale Domilo; operaty due diligence -> oferty z pakietów deweloperów
SELECT o.typ,
       count(*) FILTER (l.id_lokalu IS NOT NULL) AS lokal_w_pms,
       count(*) FILTER (r.id_oferty IS NOT NULL) AS oferta_w_radarze,
       count(*) FILTER (r.id_pakietu IS NOT NULL) AS oferta_z_pakietu,
       count(*) FILTER (d.id_oferty IS NOT NULL) AS oferta_z_transakcja_rcn,
       count(*) FILTER (o.typ = 'kontrolny' AND EXISTS (
           SELECT 1 FROM operaty x WHERE x.typ = 'roczny' AND x.id_lokalu = o.id_lokalu)) AS lokal_ma_tez_operat_roczny
FROM operaty o
LEFT JOIN pms_lokale l USING (id_lokalu)
LEFT JOIN radar_oferty r USING (id_oferty)
LEFT JOIN radar_dopasowania d USING (id_oferty)
WHERE o.typ <> 'roczny' GROUP BY o.typ ORDER BY o.typ
"""

# --- 2. Rozkład cen -------------------------------------------------------------------------------------------

ZAPYTANIA["2a_ceny_miasta"] = """
SELECT coalesce(miasto, 'RAZEM') AS miasto, count(*) AS transakcje,
       round(median(cena_pln), -3) AS cena_mediana,
       round(quantile_cont(cena_pln, 0.05), -3) AS cena_p5,
       round(quantile_cont(cena_pln, 0.95), -3) AS cena_p95,
       round(median(cena_m2)) AS m2_mediana,
       round(quantile_cont(cena_m2, 0.05)) AS m2_p5,
       round(quantile_cont(cena_m2, 0.95)) AS m2_p95,
       round(median(metraz), 1) AS metraz_mediana
FROM rcn_transakcje GROUP BY ROLLUP (miasto) ORDER BY transakcje DESC
"""

ZAPYTANIA["2b_cena_m2_miasta_zbiory"] = f"""
-- Mediana ceny m² w miastach w zbiorach podziału (zmiana poziomu cen w czasie)
SELECT t.miasto,
       round(median(t.cena_m2) FILTER (p.zbior = 'trening')) AS trening,
       round(median(t.cena_m2) FILTER (p.zbior = 'walidacja')) AS walidacja,
       round(median(t.cena_m2) FILTER (p.zbior = 'test')) AS test,
       round(100.0 * (median(t.cena_m2) FILTER (p.zbior = 'test')
                      / median(t.cena_m2) FILTER (p.zbior = 'trening') - 1), 1) AS zmiana_test_vs_trening_proc
FROM rcn_transakcje t JOIN ({sql_podzialu()}) p USING (id_transakcji)
GROUP BY t.miasto ORDER BY trening DESC
"""

ZAPYTANIA["2c_ceny_nietypowe"] = """
-- Transakcje z ceną m² daleko od mediany swojej dzielnicy (mediana z całego okresu, tylko opisowo)
WITH t AS (
    SELECT *, cena_m2 / median(cena_m2) OVER (PARTITION BY miasto, dzielnica) AS wzgl
    FROM rcn_transakcje
)
SELECT CASE WHEN wzgl < 0.5 THEN '< 0,5 × mediany dzielnicy'
            WHEN wzgl <= 2 THEN '0,5–2 × mediany dzielnicy'
            ELSE '> 2 × mediany dzielnicy' END AS przedzial,
       count(*) AS transakcje,
       count(*) FILTER (cena_pln = 60000) AS cena_dokladnie_60_tys,
       min(cena_m2) AS min_cena_m2, max(cena_m2) AS max_cena_m2
FROM t GROUP BY ALL ORDER BY min_cena_m2
"""

# --- 3. Transakcje na miesiąc ---------------------------------------------------------------------------------

ZAPYTANIA["3_transakcje_miesiac"] = """
SELECT strftime(data_aktu, '%Y-%m') AS miesiac_aktu,
       count(*) AS razem,
       count(*) FILTER (miasto = 'Warszawa') AS warszawa,
       count(*) FILTER (miasto = 'Kraków') AS krakow,
       count(*) FILTER (miasto = 'Wrocław') AS wroclaw,
       count(*) FILTER (miasto = 'Poznań') AS poznan,
       count(*) FILTER (miasto = 'Gdańsk') AS gdansk,
       count(*) FILTER (miasto = 'Łódź') AS lodz,
       count(*) FILTER (data_publikacji_rejestru >= TIMESTAMP '2026-10-01') AS opublikowane_po_eksporcie
FROM rcn_transakcje GROUP BY ALL ORDER BY miesiac_aktu
"""

ZAPYTANIA["3b_transakcje_miesiac_podsumowanie"] = """
SELECT min(n) AS min_mies, median(n) AS mediana_mies, max(n) AS max_mies
FROM (SELECT strftime(data_aktu, '%Y-%m') AS m, count(*) AS n FROM rcn_transakcje GROUP BY ALL)
"""

# --- 4. Opóźnienie publikacji ---------------------------------------------------------------------------------

ZAPYTANIA["4a_opoznienie"] = """
WITH t AS (SELECT *, date_diff('day', data_aktu, data_publikacji_rejestru) AS dni FROM rcn_transakcje)
SELECT coalesce(CAST(year(data_aktu) AS VARCHAR), 'RAZEM') AS rok_aktu, count(*) AS transakcje,
       min(dni) AS min, quantile_disc(dni, 0.05) AS p5, quantile_disc(dni, 0.25) AS p25, median(dni) AS mediana,
       quantile_disc(dni, 0.75) AS p75, quantile_disc(dni, 0.95) AS p95, max(dni) AS max,
       round(corr(dni, cena_m2), 3) AS korelacja_z_cena_m2
FROM t GROUP BY ROLLUP (year(data_aktu)) ORDER BY rok_aktu
"""

ZAPYTANIA["4b_opoznienie_kubelki"] = """
WITH t AS (SELECT date_diff('day', data_aktu, data_publikacji_rejestru) AS dni FROM rcn_transakcje)
SELECT CASE WHEN dni >= 120 THEN '120' ELSE (10 * (dni // 10)) || '–' || (10 * (dni // 10) + 9) END AS dni,
       count(*) AS transakcje, round(100.0 * count(*) / sum(count(*)) OVER (), 1) AS proc
FROM t GROUP BY ALL ORDER BY min(dni)
"""

ZAPYTANIA["4c_opoznienie_miasta"] = """
SELECT miasto, median(date_diff('day', data_aktu, data_publikacji_rejestru)) AS mediana_dni,
       quantile_disc(date_diff('day', data_aktu, data_publikacji_rejestru), 0.05) AS p5,
       quantile_disc(date_diff('day', data_aktu, data_publikacji_rejestru), 0.95) AS p95
FROM rcn_transakcje GROUP BY ALL ORDER BY miasto
"""

ZAPYTANIA["4d_kompletnosc_w_dniu_eksportu"] = """
-- Ile transakcji z ostatnich miesięcy było znanych w dniu eksportu (opublikowane do 2026-09-30)
SELECT strftime(data_aktu, '%Y-%m') AS miesiac_aktu, count(*) AS transakcje,
       count(*) FILTER (data_publikacji_rejestru < TIMESTAMP '2026-10-01') AS znane_2026_09_30,
       round(100.0 * count(*) FILTER (data_publikacji_rejestru < TIMESTAMP '2026-10-01') / count(*), 1) AS proc
FROM rcn_transakcje WHERE data_aktu >= TIMESTAMP '2026-04-01' GROUP BY ALL ORDER BY miesiac_aktu
"""

# --- 5. Podział -----------------------------------------------------------------------------------------------

ZAPYTANIA["5a_podzial"] = f"""
WITH p AS ({sql_podzialu()})
SELECT coalesce(p.zbior, 'RAZEM') AS zbior, count(*) AS transakcje,
       strftime(min(p.data_aktu), '%Y-%m-%d') AS od, strftime(max(p.data_aktu), '%Y-%m-%d') AS do,
       count(DISTINCT strftime(p.data_aktu, '%Y-%m')) AS miesiace,
       count(*) FILTER (t.miasto = 'Warszawa') AS warszawa,
       count(*) FILTER (t.miasto = 'Kraków') AS krakow,
       count(*) FILTER (t.miasto = 'Wrocław') AS wroclaw,
       count(*) FILTER (t.miasto = 'Poznań') AS poznan,
       count(*) FILTER (t.miasto = 'Gdańsk') AS gdansk,
       count(*) FILTER (t.miasto = 'Łódź') AS lodz,
       count(*) FILTER (t.rynek = 'pierwotny') AS rynek_pierwotny,
       count(d.id_oferty) AS z_dopasowana_oferta
FROM p JOIN rcn_transakcje t USING (id_transakcji) LEFT JOIN radar_dopasowania d USING (id_transakcji)
GROUP BY ROLLUP (p.zbior) ORDER BY grouping(p.zbior), min(p.data_aktu)
"""

ZAPYTANIA["5b_poza_podzialem"] = f"""
SELECT count(*) AS wszystkie_transakcje,
       count(p.id_transakcji) AS w_podziale,
       count(*) - count(p.id_transakcji) AS poza_podzialem,
       count(*) FILTER (p.id_transakcji IS NULL AND t.data_publikacji_rejestru >= TIMESTAMP '2026-10-01')
           AS poza_bo_opublikowane_po_eksporcie
FROM rcn_transakcje t LEFT JOIN ({sql_podzialu()}) p USING (id_transakcji)
"""

ZAPYTANIA["5c_rynek_pierwotny_polrocza"] = """
-- Udział rynku pierwotnego w półroczach (data_aktu), wszystkie transakcje
SELECT year(data_aktu) || '-H' || CASE WHEN month(data_aktu) <= 6 THEN 1 ELSE 2 END AS polrocze,
       count(*) AS transakcje,
       count(*) FILTER (rynek = 'pierwotny') AS rynek_pierwotny,
       round(100.0 * count(*) FILTER (rynek = 'pierwotny') / count(*), 1) AS proc_pierwotny
FROM rcn_transakcje GROUP BY ALL ORDER BY polrocze
"""


def _komorka(x) -> str:
    if x is None:
        return ""
    if isinstance(x, float) and x.is_integer():
        x = int(x)
    if isinstance(x, int):
        return f"{x:,}".replace(",", " ")
    if isinstance(x, float):
        return f"{x:,}".replace(",", " ").replace(".", ",")
    return str(x)


def tabela_md(con, sql: str) -> str:
    kursor = con.execute(sql)
    kolumny = [k[0] for k in kursor.description]
    wiersze = kursor.fetchall()
    linie = ["| " + " | ".join(kolumny) + " |", "|" + "---|" * len(kolumny)]
    linie += ["| " + " | ".join(_komorka(x) for x in w) + " |" for w in wiersze]
    return "\n".join(linie)


def main(wybrane: list[str]) -> None:
    con = polacz()
    for nazwa, sql in ZAPYTANIA.items():
        if wybrane and nazwa not in wybrane:
            continue
        print(f"### {nazwa}\n\n{tabela_md(con, sql)}\n")


if __name__ == "__main__":
    main(sys.argv[1:])
